"""Re-add the indexes that Lightroom (Cloud) drops at every launch, once per app launch.

Lightroom (Cloud) deletes any index its schema doesn't declare when it starts. This watcher notices a new
Lightroom process, waits for it to settle, takes an APFS-clone rollback of `Managed Catalog.wfindex`, then
builds each index in the plan with freeze_build.py (which freezes the app only for the build itself).
Afterwards it scans Lightroom's console log for "database is locked" and keeps only the newest rollback.

Run it from a LaunchAgent every 30-60 s (see cloud/templates/index-renewal.plist), or by hand:

    uv run --no-project python cloud/scripts/index_renewal.py once \
        --library "$HOME/Pictures/Lightroom Library.lrlibrary/<catalog-id>" \
        --state-dir "$HOME/Library/Application Support/FirstPair Lightroom Cloud Indexes"

Each launch is attempted once. A held run (non-zero build, lock error, no quiet window) is recorded and
not retried until the next launch.
"""
from pathlib import Path
import argparse, json, os, secrets, shutil, subprocess, sys, time

HERE = Path(__file__).resolve().parent
DEFAULT_PLAN = HERE.parent / "templates" / "INDEX-PLAN.json"
DEFAULT_LOG = Path.home() / "Library/Application Support/Adobe/Lightroom CC/lrcc_console.log"
APP_COMM = "Adobe Lightroom"


def identity(comm):
    out = subprocess.run(["pgrep", "-x", comm], capture_output=True, text=True).stdout.split()
    if not out:
        return None
    if len(out) != 1:
        raise RuntimeError("multiple app processes")
    pid = int(out[0])
    line = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, check=True).stdout.strip()
    return {"pid": pid, "started": line}


def started_epoch(process):
    return time.mktime(time.strptime(" ".join(process["started"].split()[:5]), "%a %b %d %H:%M:%S %Y"))


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=1) + "\n")
    os.replace(tmp, path)


def family(db):
    result = {}
    for p in (db, Path(str(db) + "-wal")):
        if p.exists():
            s = p.stat()
            result[str(p)] = [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]
    return result


def rollback_snapshot(db, dest, still_same, attempts=10, quiet=10):
    """APFS-clone the index database and WAL after a quiet window; the clone shares blocks until either side changes."""
    for _ in range(attempts):
        before = family(db)
        time.sleep(quiet)
        if not still_same():
            raise RuntimeError("process changed")
        if family(db) == before:
            break
    else:
        raise RuntimeError("index not quiescent")
    dest.mkdir(parents=True)
    for name in before:
        subprocess.run(["/bin/cp", "-c", "-p", name, str(dest / Path(name).name)], check=True)
    if family(db) != before:
        raise RuntimeError("source changed during snapshot")
    return dest


def lock_errors_since(log, epoch):
    if not log.exists():
        return 0
    count, stamp = 0, None
    for line in log.read_text(errors="replace").splitlines():
        try:  # continuation lines inherit the preceding stamp
            stamp = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass
        if "database is locked" in line and stamp is not None and stamp >= epoch:
            count += 1
    return count


def once(args):
    state_dir = Path(args.state_dir); state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "STATE.json"
    process = identity(args.app_comm)
    if process is None:
        return {"state": "NO_APP_PROCESS"}
    previous = json.loads(state_file.read_text()) if state_file.exists() else None
    if previous and previous.get("identity") == process:
        return {"state": "ALREADY_ATTEMPTED_THIS_LAUNCH", "identity": process}
    if time.time() - started_epoch(process) < args.settle:
        return {"state": "WAIT_STARTUP_SETTLE", "identity": process}
    free = shutil.disk_usage(state_dir).free / 2**30
    if free < args.min_free_gib:
        return {"state": "HELD_DISK_RESERVE", "identity": process, "freeGiB": round(free, 1)}
    db = Path(args.library) / "Managed Catalog.wfindex"
    if not db.is_file():
        return {"state": "HELD_NO_INDEX_DATABASE", "identity": process}
    plan = json.loads(Path(args.plan).read_text())
    run = state_dir / ("run-" + secrets.token_hex(8)); run.mkdir()
    state = {"state": "STARTED", "identity": process, "run": str(run), "epoch": time.time()}
    save(state_file, state)  # claim the launch before touching anything
    if args.dry_run:
        state["state"] = "DRY_RUN"; save(state_file, state); return state
    still_same = lambda: identity(args.app_comm) == process
    try:
        rollback_snapshot(db, run / "index-rollback", still_same)
        for idx in plan["indexes"]:
            if not still_same():
                raise RuntimeError("process changed")
            queries = run / ("queries-" + idx["name"] + ".json")
            queries.write_text(json.dumps([q for q in plan.get("queries", []) if "FROM " + idx["table"] in q["sql"]]))
            done = subprocess.run(
                [sys.executable, str(Path(args.freeze_tool)), "--db", str(db), "--pid", str(process["pid"]),
                 "--comm", args.app_comm, "--name", idx["name"], "--sql", idx["sql"], "--table", idx["table"],
                 "--queries", str(queries), "--journal", str(run / "FREEZE.jsonl"),
                 "--idle", str(args.idle), "--max-wait", str(args.max_wait)],
                capture_output=True, text=True, timeout=args.max_wait + 300)
            save(run / ("FREEZE-" + idx["name"] + ".json"), {"returncode": done.returncode, "stderr": done.stderr[-2000:]})
            if done.returncode != 0:
                raise RuntimeError("freeze build held: " + idx["name"])
        locked = lock_errors_since(Path(args.console_log), int(state["epoch"]))
        save(run / "LOCK-SCAN.json", {"lockErrors": locked})
        if locked:
            raise RuntimeError("Lightroom logged database is locked during the run")
        state["state"] = "COMPLETE"
        for other in state_dir.glob("run-*/index-rollback"):
            if other.parent != run:
                shutil.rmtree(other)  # keep only the newest verified rollback
    except Exception as error:
        state.update(state="HELD", error=repr(error))
    finally:
        save(state_file, state)
    return state


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    o = sub.add_parser("once", help="check for a new launch and renew indexes once")
    o.add_argument("--library", required=True, help="the <catalog-id> folder inside 'Lightroom Library.lrlibrary'")
    o.add_argument("--state-dir", required=True)
    o.add_argument("--plan", default=str(DEFAULT_PLAN))
    o.add_argument("--freeze-tool", default=str(HERE / "freeze_build.py"))
    o.add_argument("--console-log", default=str(DEFAULT_LOG))
    o.add_argument("--app-comm", default=APP_COMM)
    o.add_argument("--settle", type=float, default=90)
    o.add_argument("--idle", type=float, default=30)
    o.add_argument("--max-wait", type=float, default=600)
    o.add_argument("--min-free-gib", type=float, default=20)
    o.add_argument("--dry-run", action="store_true", help="claim and report, but build nothing")
    args = ap.parse_args()
    print(json.dumps(once(args)))


if __name__ == "__main__":
    main()
