from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from governance import GovernanceError, GovernanceService
from memory_writer import ControlledMemoryWriter
from proposal_store import HumanProposalDecisions, ProposalError, ProposalService


def record(memory_id):
    return f"# Metadata\n\nid: {memory_id}\nfrequency: 0\nlast_used:\n\n# Description\n\ntrace test\n"


class GovernanceTraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)
        self.governance = GovernanceService(self.root)
        self.proposals = ProposalService(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def request(self, memory_id):
        item = {"id": memory_id, "category": "variables", "path": f"variables/{memory_id}.md", "data": {}}
        for _ in range(5):
            result = self.governance.record_retrieval([{"item": item}])
        return result["requests"][0]

    def test_provenance_traces_request_proposal_and_event(self):
        first, second = self.request("v_ONE"), self.request("v_TWO")
        proposal = self.proposals.create_proposal("create", {"category": "variables", "id": "v_NEW"}, {"content": record("v_NEW")}, "trace", [first["request_id"], second["request_id"]])
        self.assertEqual([first["request_id"], second["request_id"]], proposal["source_request_ids"])
        self.governance.resolve_request(first["request_id"], "reviewed")
        self.assertEqual("pending", proposal["status"])
        HumanProposalDecisions(self.root).approve(proposal["proposal_id"])
        event = ControlledMemoryWriter(self.root).apply_approved_proposal(proposal["proposal_id"])
        self.assertEqual(proposal["source_request_ids"], event["source_request_ids"])
        trace = self.governance.trace(first["request_id"])
        self.assertEqual(proposal["proposal_id"], trace["linked_proposals"][0]["proposal_id"])
        self.assertEqual(event["event_id"], trace["linked_proposals"][0]["history_event_id"])

    def test_direct_and_invalid_provenance(self):
        direct = self.proposals.create_proposal("create", {"category": "variables", "id": "v_DIRECT"}, {"content": record("v_DIRECT")}, "direct")
        self.assertEqual([], direct["source_request_ids"])
        with self.assertRaises(ProposalError):
            self.proposals.create_proposal("create", {"category": "variables", "id": "v_BAD"}, {"content": record("v_BAD")}, "bad", ["gov_" + "0" * 32])
        with self.assertRaises(GovernanceError):
            self.governance.trace("not-an-id")

    def test_source_request_ids_must_be_a_list_of_strings(self):
        target = {"category": "variables", "id": "v_TYPED"}
        change = {"content": record("v_TYPED")}
        with self.assertRaisesRegex(ProposalError, "list of strings"):
            self.proposals.create_proposal("create", target, change, "typed", "gov_anything")
        with self.assertRaisesRegex(ProposalError, "list of strings"):
            self.proposals.create_proposal("create", target, change, "typed", [123])

    def test_dismissed_request_remains_attention_only_provenance(self):
        request = self.request("v_DISMISSED")
        self.governance.resolve_request(request["request_id"], "dismissed")
        proposal = self.proposals.create_proposal(
            "create", {"category": "variables", "id": "v_LINKED"},
            {"content": record("v_LINKED")}, "provenance", [request["request_id"]],
        )
        self.assertEqual("dismissed", self.governance.request(request["request_id"])["resolution"]["status"])
        self.assertEqual("pending", proposal["status"])
        self.assertIsNone(proposal["applied_event_id"])
        self.assertFalse((self.root / "memory" / "variables" / "v_LINKED.md").exists())


if __name__ == "__main__":
    unittest.main()
