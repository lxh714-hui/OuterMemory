from pathlib import Path
from uuid import uuid4

from history_manager import _HistoryRepository
from memory_loader import MemoryLoader, MemoryValidationError, validate_memory_id
from memory_parser import MemoryParser
from memory_schema import MemorySchema
from proposal_store import _ProposalRepository
from repository_paths import repository_root


class MemoryWriteError(Exception):
    pass


class ControlledMemoryWriter:
    """Internal writer capability: applies validated, approved proposals only."""

    def __init__(self, root=None):
        self.root = repository_root(root)
        self._memory_root = (self.root / "memory").resolve()
        self._proposals = _ProposalRepository(self.root)
        self._history = _HistoryRepository(self.root)

    def apply_approved_proposal(self, proposal_id):
        self._block_if_recovery_required()
        proposal = self._proposals.load(proposal_id)
        if proposal.get("status") != "approved":
            raise MemoryWriteError("only approved proposals may be applied")
        if proposal.get("applied_event_id") is not None or self._history.find_applied_proposal(proposal_id):
            raise MemoryWriteError("proposal has already been applied")

        memory = MemoryLoader(repository_root_path=self.root).load()
        plan = self._build_plan(proposal, memory)
        event_id = f"evt_{uuid4().hex}"
        targets = [entry["path"] for entry in plan]
        snapshot_ref = self._history.snapshot_targets(event_id, targets)
        event = self._mutation_event(event_id, proposal, snapshot_ref, plan)
        self._history.write_event(event)

        try:
            _apply_plan(self.root, plan)
            MemoryLoader(repository_root_path=self.root).load()
        except Exception as error:
            self._recover_or_require_recovery(event, snapshot_ref, error)
            raise MemoryWriteError("mutation failed and was restored") from error

        try:
            event["state"] = "applied"
            self._history.write_event(event)
            self._proposals.mark_applied(proposal_id, event_id)
        except Exception as error:
            self._recover_or_require_recovery(event, snapshot_ref, error)
            raise MemoryWriteError("mutation finalization failed and was restored") from error
        return event

    def rollback(self, event_id):
        self._block_if_recovery_required()
        original = self._history.load_event(event_id)
        if original.get("kind") != "mutation" or original.get("state") != "applied":
            raise MemoryWriteError("only applied mutation events may be rolled back")
        if original.get("rolled_back_by") or self._history.has_rollback_for(event_id):
            raise MemoryWriteError("event has already been rolled back or rollback is in progress")

        rollback_id = f"evt_{uuid4().hex}"
        current_snapshot = self._history.snapshot_targets(rollback_id, original["result"]["affected_paths"])
        rollback_event = {
            "event_id": rollback_id,
            "kind": "rollback",
            "proposal_id": original["proposal_id"],
            "operation": "rollback",
            "target": original["target"],
            "timestamp": self._history.timestamp(),
            "snapshot_ref": current_snapshot,
            "rollback_of": event_id,
            "state": "prepared",
        }
        self._history.write_event(rollback_event)
        try:
            self._history.restore_for_governed_operation(original["snapshot_ref"])
            MemoryLoader(repository_root_path=self.root).load()
        except Exception as error:
            self._recover_or_require_recovery(rollback_event, current_snapshot, error)
            raise MemoryWriteError("rollback failed and was restored") from error

        try:
            rollback_event["state"] = "applied"
            rollback_event["result"] = {"restored_from": original["snapshot_ref"]}
            self._history.write_event(rollback_event)
            original["state"] = "rolled_back"
            original["rolled_back_by"] = rollback_id
            self._history.write_event(original)
        except Exception as error:
            self._recover_or_require_recovery(rollback_event, current_snapshot, error)
            raise MemoryWriteError("rollback finalization failed and was restored") from error
        return rollback_event

    def _block_if_recovery_required(self):
        if self._history.has_unresolved_recovery():
            raise MemoryWriteError("recovery is required before further governed mutations")

    def _recover_or_require_recovery(self, event, snapshot_ref, error):
        try:
            self._history.restore_for_governed_operation(snapshot_ref)
        except Exception as restore_error:
            event["state"] = "recovery_required"
            event["failure"] = f"{error}; restoration failed: {restore_error}"
            try:
                self._history.write_event(event)
            except Exception:
                pass
            raise MemoryWriteError("restoration failed; recovery is required") from restore_error
        event["state"] = "recovered"
        event["failure"] = str(error)
        self._history.write_event(event)

    def _mutation_event(self, event_id, proposal, snapshot_ref, plan):
        return {
            "event_id": event_id,
            "kind": "mutation",
            "proposal_id": proposal["proposal_id"],
            "source_request_ids": list(proposal.get("source_request_ids", [])),
            "operation": proposal["operation"],
            "target": proposal["target"],
            "timestamp": self._history.timestamp(),
            "snapshot_ref": snapshot_ref,
            "result": {"affected_paths": [entry["path"] for entry in plan], "affected_ids": [entry["id"] for entry in plan]},
            "state": "prepared",
        }

    def _build_plan(self, proposal, memory):
        target = proposal.get("target")
        if not isinstance(target, dict):
            raise MemoryWriteError("invalid proposal target")
        category, memory_id = target.get("category"), target.get("id")
        if category not in MemorySchema.CATEGORIES:
            raise MemoryWriteError("unknown target category")
        try:
            validate_memory_id(memory_id)
        except MemoryValidationError as error:
            raise MemoryWriteError("invalid logical memory id") from error
        existing = memory[category].get(memory_id)
        operation = proposal.get("operation")

        if operation == "create":
            if existing or self._find_item(memory, memory_id):
                raise MemoryWriteError("cannot create an existing memory id")
            return [{"id": memory_id, "path": self._new_path(category, memory_id), "content": self._validated_content(proposal, memory_id)}]
        if operation == "update":
            if not existing:
                raise MemoryWriteError("cannot update a missing target")
            return [{"id": memory_id, "path": self._existing_path(existing), "content": self._validated_content(proposal, memory_id)}]
        if operation == "delete":
            if not existing:
                raise MemoryWriteError("cannot delete a missing target")
            return [{"id": memory_id, "path": self._existing_path(existing), "content": None}]
        if operation == "merge":
            change = proposal.get("change")
            source_id = change.get("source_id") if isinstance(change, dict) else None
            source = self._find_item(memory, source_id)
            if not existing or not source or source["id"] == memory_id:
                raise MemoryWriteError("merge requires distinct existing source and target")
            return [
                {"id": memory_id, "path": self._existing_path(existing), "content": self._validated_content(proposal, memory_id)},
                {"id": source_id, "path": self._existing_path(source), "content": None},
            ]
        raise MemoryWriteError("unsupported proposal operation")

    def _validated_content(self, proposal, expected_id):
        change = proposal.get("change")
        content = change.get("content") if isinstance(change, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise MemoryWriteError("proposal requires non-empty Markdown content")
        metadata = MemoryParser.parse(content).get("Metadata")
        if not isinstance(metadata, dict) or metadata.get("id") != expected_id:
            raise MemoryWriteError("proposed content Metadata.id must match target id")
        return content

    def _new_path(self, category, memory_id):
        return self._checked_relative_path(Path("memory") / category / f"{memory_id}.md", category)

    def _existing_path(self, item):
        return self._checked_relative_path(Path("memory") / item["path"], item["category"])

    def _checked_relative_path(self, relative, category):
        resolved = (self.root / relative).resolve()
        expected = (self._memory_root / category).resolve()
        if not resolved.is_relative_to(expected):
            raise MemoryWriteError("memory path escapes its category")
        return relative.as_posix()

    @staticmethod
    def _find_item(memory, memory_id):
        for category in memory.values():
            if memory_id in category:
                return category[memory_id]
        return None


def _apply_plan(root, plan):
    """Internal plan executor; plans are created only by ControlledMemoryWriter."""
    for entry in plan:
        path = root / entry["path"]
        if entry["content"] is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(entry["content"], encoding="utf-8")
            temporary.replace(path)
