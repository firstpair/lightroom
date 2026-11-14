"""Controls for cloud/scripts/index_renewal.py and freeze_build.py.

A real SQLite fixture in WAL mode stands in for `Managed Catalog.wfindex`, and a `sleep` process stands in
for Lightroom, so SIGSTOP/SIGCONT are exercised for real. No Lightroom involved.
"""
import argparse, importlib.util, json, shutil, sqlite3, subprocess, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("index_renewal", REPO / "scripts/index_renewal.py")
ir = importlib.util.module_from_spec(spec); spec.loader.exec_module(ir)
PLAN = json.loads((REPO / "templates/INDEX-PLAN.json").read_text())


def fixture_db(path):
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE asset_sync_status_ui( docId, assetId, prioritizedSyncStatus, syncStatuses, keepLocallyConfiguration, isSearchable, volumeGuidUsedByOriginal, volumeGuidUsedByProxy, spaceId )")
    con.execute("CREATE TABLE purgeCandidates( docId, localId, assetId, hasLocalFile, isPurgeable, binaryType, binarySize, volumeGuidUsedByFile, fileSize, dateLastUpdatedInSeconds, contentIdOrSha256, isMarkedForOfflineUse, ozHasBinary, isVideo )")
    con.execute("BEGIN")
    for i in range(3000):
        con.execute("INSERT INTO purgeCandidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (i, i, f"a{i}", i % 3 != 0, i % 2, ["aux", "original", "proxy", "xmp_develop"][i % 4], 1, "V1", 10 + i, 0, f"h{i % 50}", 0, 1, 0))
        con.execute("INSERT INTO asset_sync_status_ui VALUES(?,?,?,?,?,?,?,?,?)", (i, f"a{i}", [1, 2, 4, 8, 16, 64, 128][i % 7], 0, i % 4, i % 2, "V1", "V2", "s"))
    con.execute("COMMIT"); con.close()


class IndexRenewal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lib = self.tmp / "lib"; self.lib.mkdir()
        self.db = self.lib / "Managed Catalog.wfindex"; fixture_db(self.db)
        self.app = subprocess.Popen(["sleep", "600"])
        self.process = {"pid": self.app.pid, "started": time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(time.time() - 3600))}

    def tearDown(self):
        self.app.kill(); self.app.wait(); shutil.rmtree(self.tmp)

    def args(self, **kw):
        a = dict(library=str(self.lib), state_dir=str(self.tmp / "state"), plan=str(REPO / "templates/INDEX-PLAN.json"),
                 freeze_tool=str(REPO / "scripts/freeze_build.py"), console_log=str(self.tmp / "console.log"), app_comm="sleep",
                 settle=90, idle=1, max_wait=60, min_free_gib=0, dry_run=False)
        a.update(kw); return argparse.Namespace(**a)

    def once(self, **kw):
        with patch.object(ir, "identity", return_value=self.process), patch.object(ir.time, "sleep", side_effect=lambda s: None):
            return ir.once(self.args(**kw))

    def names(self):
        con = sqlite3.connect(self.db); r = {n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}; con.close(); return r

    def test_builds_all_indexes_once_per_launch_and_thaws(self):
        old = self.tmp / "state/run-old/index-rollback"; old.mkdir(parents=True)
        state = self.once()
        self.assertEqual(state["state"], "COMPLETE", state)
        self.assertTrue({i["name"] for i in PLAN["indexes"]} <= self.names())
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(self.app.pid)], capture_output=True, text=True).stdout
        self.assertNotIn("T", stat)
        events = [json.loads(l)["event"] for l in (Path(state["run"]) / "FREEZE.jsonl").read_text().splitlines()]
        self.assertEqual(events.count("INDEX_CREATED"), len(PLAN["indexes"]))
        self.assertEqual(events.count("THAWED"), len(PLAN["indexes"]))
        self.assertGreaterEqual(events.count("SAME_SNAPSHOT_EQUAL"), len(PLAN["queries"]))
        self.assertFalse(old.exists(), "older rollback should be removed")
        self.assertTrue((Path(state["run"]) / "index-rollback/Managed Catalog.wfindex").exists())
        self.assertEqual(self.once()["state"], "ALREADY_ATTEMPTED_THIS_LAUNCH")

    def test_waits_for_settle(self):
        self.process["started"] = time.strftime("%a %b %d %H:%M:%S %Y")
        self.assertEqual(self.once()["state"], "WAIT_STARTUP_SETTLE")

    def test_failed_build_holds_and_keeps_rollbacks(self):
        old = self.tmp / "state/run-old/index-rollback"; old.mkdir(parents=True)
        fail = subprocess.CompletedProcess([], 2, "", "HELD_NOT_IDLE")
        real = subprocess.run
        with patch.object(ir.subprocess, "run", side_effect=lambda cmd, **kw: fail if "freeze_build.py" in " ".join(cmd) else real(cmd, **kw)):
            state = self.once()
        self.assertEqual(state["state"], "HELD"); self.assertIn("freeze build held", state["error"]); self.assertTrue(old.exists())

    def test_lock_errors_hold(self):
        log = self.tmp / "console.log"
        real = subprocess.run
        def run(cmd, **kw):
            if "freeze_build.py" in " ".join(cmd):
                log.write_text(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 1)) + ".000 x\n  continued: database is locked\n")
                return subprocess.CompletedProcess([], 0, "", "")
            return real(cmd, **kw)
        with patch.object(ir.subprocess, "run", side_effect=run):
            state = self.once()
        self.assertEqual(state["state"], "HELD"); self.assertIn("database is locked", state["error"])

    def test_existing_index_is_kept(self):
        con = sqlite3.connect(self.db); con.execute(PLAN["indexes"][0]["sql"]); con.close()
        self.assertEqual(self.once()["state"], "COMPLETE")

    def test_plan_has_no_private_values(self):
        text = (REPO / "templates/INDEX-PLAN.json").read_text() + (REPO / "templates/index-renewal.plist").read_text()
        self.assertNotIn("/Users/", text)
        for idx in PLAN["indexes"] + PLAN["optional"]:
            self.assertTrue(idx["sql"].startswith("CREATE INDEX " + idx["name"] + " ON " + idx["table"]))


if __name__ == "__main__":
    unittest.main()
