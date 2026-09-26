from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import history_manager
import memory_writer
from history_manager import HistoryError
from memory_loader import DuplicateMemoryIdError, MemoryLoader, MemoryValidationError
from memory_writer import ControlledMemoryWriter, MemoryWriteError
from proposal_store import HumanProposalDecisions, ProposalError, ProposalService


def record(memory_id, description="Test memory"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class GovernedMutationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.variables = self.root / "memory" / "variables"
        self.variables.mkdir(parents=True)
        (self.variables / "v_BASE.md").write_text(record("v_BASE", "before"), encoding="utf-8")
        for category in ("resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir()
        self.service = ProposalService(self.root)
        self.decisions = HumanProposalDecisions(self.root)
        self.writer = ControlledMemoryWriter(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def create_proposal(self, operation="create", memory_id="v_NEW", content=None, change=None):
        return self.service.create_proposal(
            operation, {"category": "variables", "id": memory_id},
            change if change is not None else {"content": content or record(memory_id, "after")},
            "test proposal",
        )

    def approve(self, proposal):
        return self.decisions.approve(proposal["proposal_id"])

    def test_ai_facing_proposal_service_cannot_decide(self):
        self.assertFalse(hasattr(self.service, "approve"))
        self.assertFalse(hasattr(self.service, "reject"))

    def test_arbitrary_mutation_and_restore_are_not_supported_interfaces(self):
        self.assertFalse(hasattr(self.writer, "apply_plan"))
        self.assertFalse(hasattr(self.writer, "_apply_plan"))
        self.assertFalse(hasattr(history_manager, "HistoryManager"))

    def test_rejected_proposal_leaves_memory_unchanged(self):
        before = (self.variables / "v_BASE.md").read_bytes()
        proposal = self.create_proposal()
        self.decisions.reject(proposal["proposal_id"])
        self.assertEqual(before, (self.variables / "v_BASE.md").read_bytes())
        self.assertFalse((self.variables / "v_NEW.md").exists())

    def test_approved_create_applies_and_records_history(self):
        proposal = self.create_proposal()
        self.approve(proposal)
        event = self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertTrue((self.variables / "v_NEW.md").is_file())
        self.assertEqual("applied", event["state"])
        self.assertTrue((self.root / "history" / "events" / f"{event['event_id']}.json").is_file())
        self.assertTrue((self.root / event["snapshot_ref"] / "manifest.json").is_file())
        self.assertEqual(event["event_id"], self.service.get_status(proposal["proposal_id"])["applied_event_id"])

    def test_create_apply_rollback_restores_absence(self):
        proposal = self.create_proposal()
        self.approve(proposal)
        event = self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.writer.rollback(event["event_id"])
        self.assertFalse((self.variables / "v_NEW.md").exists())

    def test_delete_apply_rollback_restores_file(self):
        before = (self.variables / "v_BASE.md").read_text(encoding="utf-8")
        proposal = self.create_proposal("delete", "v_BASE", change={})
        self.approve(proposal)
        event = self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertFalse((self.variables / "v_BASE.md").exists())
        self.writer.rollback(event["event_id"])
        self.assertEqual(before, (self.variables / "v_BASE.md").read_text(encoding="utf-8"))

    def test_merge_apply_rollback_restores_both_files(self):
        source_path = self.variables / "v_SOURCE.md"
        source_before = record("v_SOURCE", "source")
        source_path.write_text(source_before, encoding="utf-8")
        target_before = (self.variables / "v_BASE.md").read_text(encoding="utf-8")
        proposal = self.create_proposal("merge", "v_BASE", record("v_BASE", "merged"), {"source_id": "v_SOURCE", "content": record("v_BASE", "merged")})
        self.approve(proposal)
        event = self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertFalse(source_path.exists())
        self.writer.rollback(event["event_id"])
        self.assertEqual(target_before, (self.variables / "v_BASE.md").read_text(encoding="utf-8"))
        self.assertEqual(source_before, source_path.read_text(encoding="utf-8"))

    def test_pending_proposal_cannot_apply(self):
        proposal = self.create_proposal()
        with self.assertRaises(MemoryWriteError):
            self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertFalse((self.variables / "v_NEW.md").exists())

    def test_rejected_proposal_cannot_apply(self):
        proposal = self.create_proposal()
        self.decisions.reject(proposal["proposal_id"])
        with self.assertRaises(MemoryWriteError):
            self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertFalse((self.variables / "v_NEW.md").exists())

    def test_applied_proposal_cannot_apply_twice(self):
        proposal = self.create_proposal()
        self.approve(proposal)
        self.writer.apply_approved_proposal(proposal["proposal_id"])
        with self.assertRaises(MemoryWriteError):
            self.writer.apply_approved_proposal(proposal["proposal_id"])

    def test_duplicate_rollback_is_blocked(self):
        proposal = self.create_proposal("update", "v_BASE", record("v_BASE", "after"))
        self.approve(proposal)
        event = self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.writer.rollback(event["event_id"])
        with self.assertRaises(MemoryWriteError):
            self.writer.rollback(event["event_id"])

    def test_memory_id_path_traversal_is_rejected(self):
        with self.assertRaises(ProposalError):
            self.create_proposal("create", "../../outside", record("../../outside"))
        self.assertFalse((self.root / "outside.md").exists())

    def test_proposal_id_path_traversal_is_rejected(self):
        with self.assertRaises(ProposalError):
            self.service.get_status("../../outside")

    def test_event_id_path_traversal_is_rejected(self):
        with self.assertRaises(HistoryError):
            self.writer.rollback("../../outside")

    def test_failure_during_merge_restores_previous_state(self):
        source_path = self.variables / "v_SOURCE.md"
        source_before = record("v_SOURCE", "source")
        source_path.write_text(source_before, encoding="utf-8")
        target_before = (self.variables / "v_BASE.md").read_text(encoding="utf-8")
        proposal = self.create_proposal("merge", "v_BASE", change={"source_id": "v_SOURCE", "content": record("v_BASE", "merged")})
        self.approve(proposal)
        original_apply = memory_writer._apply_plan

        def partial_apply(root, plan):
            original_apply(root, plan[:1])
            raise OSError("simulated second mutation failure")

        with patch("memory_writer._apply_plan", side_effect=partial_apply):
            with self.assertRaises(MemoryWriteError):
                self.writer.apply_approved_proposal(proposal["proposal_id"])
        self.assertEqual(target_before, (self.variables / "v_BASE.md").read_text(encoding="utf-8"))
        self.assertEqual(source_before, source_path.read_text(encoding="utf-8"))

    def test_recovery_required_blocks_further_mutation(self):
        proposal = self.create_proposal()
        self.approve(proposal)
        with patch("memory_writer._apply_plan", side_effect=OSError("simulated failure")), \
             patch.object(self.writer._history, "restore_for_governed_operation", side_effect=OSError("restore failure")):
            with self.assertRaises(MemoryWriteError):
                self.writer.apply_approved_proposal(proposal["proposal_id"])
        event_states = [json.loads(path.read_text(encoding="utf-8"))["state"] for path in (self.root / "history" / "events").glob("*.json")]
        self.assertIn("recovery_required", event_states)
        next_proposal = self.create_proposal("create", "v_NEXT")
        self.approve(next_proposal)
        with self.assertRaises(MemoryWriteError):
            self.writer.apply_approved_proposal(next_proposal["proposal_id"])

    def test_duplicate_metadata_ids_are_rejected(self):
        (self.root / "memory" / "resources" / "r_DUP.md").write_text(record("v_BASE"), encoding="utf-8")
        with self.assertRaises(DuplicateMemoryIdError):
            MemoryLoader(repository_root_path=self.root).load()

    def test_empty_memory_file_is_rejected(self):
        (self.variables / "v_EMPTY.md").write_text("", encoding="utf-8")
        with self.assertRaises(MemoryValidationError):
            MemoryLoader(repository_root_path=self.root).load()


if __name__ == "__main__":
    unittest.main()
