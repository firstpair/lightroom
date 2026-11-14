"""Build one index in Lightroom (Cloud)'s live `Managed Catalog.wfindex` while the app is frozen with SIGSTOP.

Cloud's own index writers give up after ~5 s on a lock, so a long CREATE INDEX must not overlap Cloud activity.
Sequence: wait for PRAGMA data_version to be stable for --idle seconds; arm an independent resume timer; SIGSTOP Cloud;
BEGIN IMMEDIATE with busy_timeout=0 (if Cloud held the write lock, resume and retry later); verify the index is absent;
CREATE INDEX; COMMIT; SIGCONT. Afterwards prove same-snapshot typed equality (indexed vs NOT INDEXED) for given queries.
Our connection never checkpoints (wal_autocheckpoint=0); Cloud does that itself.
"""
import argparse, json, os, signal, sqlite3, subprocess, sys, time
from pathlib import Path


def journal(path, **event):
    event["t"] = time.time()
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n"); f.flush(); os.fsync(f.fileno())


def alive(pid, comm):
    out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout.strip()
    return out.endswith(comm)


def canon(rows):
    return sorted(json.dumps([[type(v).__name__, v] for v in r]) for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--comm", default="Adobe Lightroom"); ap.add_argument("--name", required=True); ap.add_argument("--sql", required=True)
    ap.add_argument("--table", required=True); ap.add_argument("--queries", default=None, help="JSON file: [{name,sql,params}]")
    ap.add_argument("--idle", type=float, default=30); ap.add_argument("--max-wait", type=float, default=900)
    ap.add_argument("--resume-after", type=float, default=60, help="independent SIGCONT timer")
    ap.add_argument("--attempts", type=int, default=10); ap.add_argument("--journal", required=True)
    a = ap.parse_args()
    J = a.journal
    assert a.sql.strip().upper().startswith("CREATE INDEX " + a.name.upper() + " ON " + a.table.upper()), "only one owned CREATE INDEX"
    assert alive(a.pid, a.comm), "Cloud process not found"
    con = sqlite3.connect(a.db, isolation_level=None, timeout=0)
    for p in ("PRAGMA busy_timeout=0", "PRAGMA wal_autocheckpoint=0", "PRAGMA cache_size=-2000000", "PRAGMA temp_store=MEMORY"):
        con.execute(p)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    schema = lambda: con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    before = schema()
    if any(r[1] == a.name for r in before):
        journal(J, event="ALREADY_PRESENT", name=a.name); return 0
    journal(J, event="START", pid=a.pid, name=a.name, sqlite=sqlite3.sqlite_version)
    start = time.time(); built = False
    for attempt in range(1, a.attempts + 1):
        last = con.execute("PRAGMA data_version").fetchone()[0]; stable_since = time.time()
        while time.time() - stable_since < a.idle:
            if time.time() - start > a.max_wait:
                journal(J, event="HELD_NOT_IDLE"); return 2
            time.sleep(1)
            v = con.execute("PRAGMA data_version").fetchone()[0]
            if v != last: last, stable_since = v, time.time()
        assert alive(a.pid, a.comm), "Cloud process changed"
        guard = subprocess.Popen(["/bin/sh", "-c", f"sleep {a.resume_after}; kill -CONT {a.pid}"], start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.kill(a.pid, signal.SIGSTOP); frozen = time.time()
        try:
            try:
                con.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as e:
                journal(J, event="CLOUD_HELD_WRITE_LOCK_RETRY", attempt=attempt, error=str(e)); continue
            try:
                assert all(r[1] != a.name for r in schema()), "index appeared concurrently"
                t = time.time(); con.execute(a.sql); build = time.time() - t
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK"); raise
            built = True
        finally:
            os.kill(a.pid, signal.SIGCONT); thawed = time.time()
            try:
                os.killpg(guard.pid, signal.SIGKILL)  # the whole guard group, including its sleep
            except ProcessLookupError:
                pass
            guard.wait()
            journal(J, event="THAWED", attempt=attempt, frozenSeconds=round(thawed - frozen, 3))
        if built:
            journal(J, event="INDEX_CREATED", name=a.name, buildSeconds=round(build, 3), frozenSeconds=round(thawed - frozen, 3)); break
    if not built:
        journal(J, event="HELD_ATTEMPTS_EXHAUSTED"); return 3
    after = schema(); added = [r for r in after if r not in before]
    assert len(added) == 1 and added[0][1] == a.name and len(after) == len(before) + 1, "unexpected schema delta"
    if a.queries:
        con.execute("BEGIN")
        for q in json.loads(Path(a.queries).read_text()):
            plain = q["sql"].replace("FROM " + a.table, "FROM " + a.table + " NOT INDEXED")
            plan = [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + q["sql"], q["params"])]
            t = time.time(); x = con.execute(q["sql"], q["params"]).fetchall(); ti = time.time() - t
            t = time.time(); y = con.execute(plain, q["params"]).fetchall(); tn = time.time() - t
            assert canon(x) == canon(y), "indexed and NOT INDEXED results differ: " + q["name"]
            journal(J, event="SAME_SNAPSHOT_EQUAL", query=q["name"], indexed=round(ti, 6), notIndexed=round(tn, 6), rows=len(x), plan=plan)
        con.execute("COMMIT")
    con.close(); journal(J, event="COMPLETE"); return 0


if __name__ == "__main__":
    sys.exit(main())
