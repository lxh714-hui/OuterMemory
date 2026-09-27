from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from governance import GovernanceError, GovernanceService, SelfCheckEngine
from memory_loader import MemoryValidationError


def record(memory_id, description="Test memory", related="", extra_metadata=""):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n{extra_metadata}\n"
        f"# Description\n\n{description}\n"
        + (f"\n# Related\n\n{related}\n" if related else "")
    )


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.variables = self.root / "memory" / "variables"
        self.variables.mkdir(parents=True)
        for category in ("resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir()
        self.variables.joinpath("v_BASE.md").write_text(record("v_BASE", "same description", "- v_MISSING"), encoding="utf-8")
        self.variables.joinpath("v_COPY.md").write_text(record("v_COPY", "same description"), encoding="utf-8")
        self.governance = GovernanceService(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_milestones_and_announcements_are_independent(self):
        item = {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {}}
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": item}])
        request = result["requests"][0]
        self.assertEqual(5, request["evidence"]["retrieval_count"])
        self.assertEqual("pending", request["resolution"]["status"])
        self.assertEqual("unannounced", request["announcement"]["status"])
        self.governance.resolve_request(request["request_id"])
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": item}])
        self.assertEqual(10, result["requests"][0]["evidence"]["milestone"])

    def test_milestones_double_without_non_threshold_or_duplicates(self):
        item = {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {}}
        emitted = []
        for _ in range(41):
            emitted.extend(request["evidence"]["milestone"] for request in self.governance.record_retrieval([{"item": item}])["requests"])
        self.assertEqual([5, 10, 20, 40], emitted)
        self.assertEqual(41, self.governance._load()["retrievals"]["v_BASE"]["count"])

    def test_immediate_requests_are_not_low_batch_members(self):
        items = [
            {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {"Description": "same"}},
            {"id": "v_COPY", "category": "variables", "path": "variables/v_COPY.md", "data": {"Description": "same"}},
        ]
        requests = self.governance.contextual_self_check([{"item": item} for item in items])
        self.assertEqual(1, len(requests))
        self.assertEqual("immediate", requests[0]["channel"])
        self.assertEqual("announced", requests[0]["announcement"]["status"])
        self.assertIsNone(self.governance.record_retrieval([])["announcement"])

    def test_low_requests_announce_once_in_batches_of_ten(self):
        items = [{"id": f"v_{number}", "category": "variables", "path": f"variables/v_{number}.md", "data": {}} for number in range(10)]
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": item} for item in items])
        self.assertIsNotNone(result["announcement"])
        pending = self.governance.pending_requests()
        self.assertEqual(10, len(pending))
        self.assertTrue(all(request["announcement"]["status"] == "announced" for request in pending))
        self.assertTrue(all(request["resolution"]["status"] == "pending" for request in pending))

    def test_resolved_low_request_is_excluded_from_later_batch(self):
        first = {"id": "v_FIRST", "category": "variables", "path": "variables/v_FIRST.md", "data": {}}
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": first}])
        first_request = result["requests"][0]
        self.governance.resolve_request(first_request["request_id"], "dismissed")

        for number in range(10):
            item = {"id": f"v_PENDING_{number}", "category": "variables", "path": f"variables/v_PENDING_{number}.md", "data": {}}
            for _ in range(5):
                result = self.governance.record_retrieval([{"item": item}])

        batch = result["announcement"]
        self.assertIsNotNone(batch)
        self.assertEqual(10, len(batch["request_ids"]))
        self.assertNotIn(first_request["request_id"], batch["request_ids"])
        self.assertEqual("unannounced", self.governance.request(first_request["request_id"])["announcement"]["status"])

    def test_single_request_resolution_must_be_reviewed_or_dismissed(self):
        item = {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {}}
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": item}])
        request = result["requests"][0]
        with self.assertRaisesRegex(GovernanceError, "invalid request resolution"):
            self.governance.resolve_request(request["request_id"], "approved")
        self.assertEqual("pending", self.governance.request(request["request_id"])["resolution"]["status"])

    def test_full_scan_is_read_only_and_groups_findings(self):
        before = self.variables.joinpath("v_BASE.md").read_bytes()
        scan = self.governance.full_scan()
        self.assertTrue(scan["findings"]["duplicates"])
        self.assertTrue(scan["findings"]["orphaned"])
        self.assertEqual(before, self.variables.joinpath("v_BASE.md").read_bytes())
        finding = scan["findings"]["duplicates"][0]
        self.assertEqual(finding, self.governance.latest_scan(finding_id=finding["finding_id"]))

    def test_failed_scan_does_not_record_success(self):
        self.variables.joinpath("v_BAD.md").write_text("", encoding="utf-8")
        with self.assertRaises(MemoryValidationError):
            self.governance.full_scan()
        self.assertIsNone(self.governance._load()["last_successful_scan"])

    def test_startup_scan_skip_retry_and_success_timestamp(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state = self.governance._load()
        state["last_successful_scan"] = recent
        self.governance._save(state)
        self.assertFalse(self.governance.startup_scan()["ran"])
        state = self.governance._load()
        state["last_successful_scan"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        self.governance._save(state)
        result = self.governance.startup_scan()
        self.assertTrue(result["ran"])
        self.assertNotEqual(recent, self.governance._load()["last_successful_scan"])

    def test_contextual_and_full_scan_share_engine(self):
        original_inspect = SelfCheckEngine.inspect
        with patch.object(SelfCheckEngine, "inspect", autospec=True, side_effect=original_inspect) as inspect:
            items = [
                {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {"Description": "same"}},
                {"id": "v_COPY", "category": "variables", "path": "variables/v_COPY.md", "data": {"Description": "same"}},
            ]
            self.governance.contextual_self_check([{"item": item} for item in items])
            self.governance.full_scan()
        self.assertEqual(2, inspect.call_count)

    def test_request_review_does_not_mutate_memory(self):
        item = {"id": "v_BASE", "category": "variables", "path": "variables/v_BASE.md", "data": {}}
        for _ in range(5):
            request = self.governance.record_retrieval([{"item": item}])["requests"]
        before = self.variables.joinpath("v_BASE.md").read_bytes()
        self.governance.resolve_request(request[0]["request_id"])
        self.assertEqual(before, self.variables.joinpath("v_BASE.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
