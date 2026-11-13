import copy
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "recognition_selection",
    Path(__file__).resolve().parents[1]
    / "scripts/preview_pipeline/recognition_selection.py",
)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


def publication():
    return dict(
        state="EIGHT_ORIGINAL_STANDARD_INITIAL_INSERTS_INDEPENDENTLY_VERIFIED",
        records=[dict(
            key=[f"synthetic-{i}", "synthetic-digest"],
            selectedSQLRowsExact=True, rootPixelsPreservedExact=True,
            unrelatedRowWitnessesUnchanged=True, originalSourceStat8Unchanged=True,
            payloads=[dict(highestNativeLevel=(level == 3)) for level in range(4)],
            permanentlyRetainedOldTenPreviews=[],
        ) for i in range(8)],
        oldTenPreviewsPermanentlyRetained=0, stagedEncodedOutputs=32,
        QuasarHighestTiers=8, sourceOriginalPayloadReads=0, nativeInvocations=0,
        unknownMarkers=[], wholeDatabaseHashOrCopy=False, fullCatalogComplete=False,
        actualWorkerWait=dict(pid=123, returncode=0, reaped=True,
                             other_group_members_absent_before_reap=True,
                             timed_out=False),
        priorRootToolTerminal=dict(session=456, exitCode=0, noRunningSession=True),
    )


class RecognitionSelectionTests(unittest.TestCase):
    pin = dict(path="/synthetic/publication-audit.json", bytes=1234, sha256="a" * 64)

    def test_all_pairs_preserve_whole_publication_provenance_and_isolation(self):
        parent = publication()
        before = copy.deepcopy(parent)
        for pair in selection.PAIRS:
            result = selection.project_pair(parent, self.pin, list(pair))
            self.assertEqual(result["sourceKeyIndices"], list(pair))
            self.assertEqual(result["sourcePublicationKeyCount"], 8)
            self.assertEqual(result["parentPublicationAudit"], self.pin)
            self.assertEqual(len(result["records"]), 2)
            self.assertEqual(result["priorRootToolTerminal"], parent["priorRootToolTerminal"])
            result["records"][0]["payloads"].clear()
            result["parentPublicationAudit"]["bytes"] = 1
            self.assertEqual(parent, before)
            self.assertEqual(self.pin["bytes"], 1234)

    def test_worker_closure_does_not_substitute_for_missing_parent_terminal(self):
        for terminal in (None, {}, dict(session=456, exitCode=0, noRunningSession=False)):
            with self.subTest(terminal=terminal):
                parent = publication()
                parent["priorRootToolTerminal"] = terminal
                with self.assertRaisesRegex(ValueError, "ACTUAL_TOOL_CLOSED"):
                    selection.project_pair(parent, self.pin, [1, 2])

    def test_nonselected_key_failure_still_refuses_the_pair(self):
        parent = publication()
        parent["records"][7]["rootPixelsPreservedExact"] = False
        with self.assertRaisesRegex(ValueError, "EVERY_PARENT_KEY_QUALIFIED"):
            selection.project_pair(parent, self.pin, [1, 2])

    def test_duplicate_key_and_pending_ownership_refused(self):
        for fault in ("duplicate", "pending"):
            with self.subTest(fault=fault):
                parent = publication()
                if fault == "duplicate":
                    parent["records"][7]["key"] = parent["records"][0]["key"][:]
                else:
                    parent["unknownMarkers"] = ["synthetic-unresolved"]
                with self.assertRaises(ValueError):
                    selection.project_pair(parent, self.pin, [1, 2])


if __name__ == "__main__":
    unittest.main()
