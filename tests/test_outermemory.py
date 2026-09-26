from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outermemory import OuterMemory


def record(memory_id, description="Test memory"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class OuterMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)

        (self.root / "memory" / "variables" / "v_DATASET.md").write_text(
            record("v_DATASET", "Dataset path for the demo project"),
            encoding="utf-8",
        )

        self.outermemory = OuterMemory(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_retrieve_project_memory(self):
        results = self.outermemory.retrieve("dataset", topk=5)

        self.assertTrue(results)
        self.assertEqual("v_DATASET", results[0]["item"]["id"])

    def test_create_and_inspect_proposal(self):
        proposal = self.outermemory.propose(
            operation="create",
            target={"category": "variables", "id": "v_NEW"},
            change={"content": record("v_NEW", "New project memory")},
            reason="test proposal",
        )

        self.assertEqual("pending", proposal["status"])

        status = self.outermemory.proposal_status(proposal["proposal_id"])

        self.assertEqual(proposal["proposal_id"], status["proposal_id"])
        self.assertEqual("pending", status["status"])
        self.assertIsNone(status["applied_event_id"])

    def test_ai_facing_interface_cannot_make_human_decisions(self):
        for capability in ("approve", "reject", "apply", "rollback"):
            self.assertFalse(hasattr(self.outermemory, capability))


if __name__ == "__main__":
    unittest.main()
