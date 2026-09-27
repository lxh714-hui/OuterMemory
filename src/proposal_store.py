from datetime import datetime, timezone
import json
import re
from uuid import uuid4

from memory_loader import MemoryValidationError, validate_memory_id
from memory_schema import MemorySchema
from repository_paths import repository_root


PROPOSAL_ID_PATTERN = re.compile(r"prop_[0-9a-f]{32}\Z")


class ProposalError(Exception):
    pass


def validate_proposal_id(proposal_id):
    if not isinstance(proposal_id, str) or not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
        raise ProposalError("invalid proposal id")
    return proposal_id


class ProposalService:
    """AI-facing capability: create proposals and inspect their status."""

    def __init__(self, root=None):
        self._repository = _ProposalRepository(root)

    def create_proposal(self, operation, target, change, reason, source_request_ids=None):
        if source_request_ids is None:
            source_request_ids = []
        elif not isinstance(source_request_ids, list) or not all(isinstance(request_id, str) for request_id in source_request_ids):
            raise ProposalError("source_request_ids must be None or a list of strings")
        if not isinstance(target, dict) or target.get("category") not in MemorySchema.CATEGORIES:
            raise ProposalError("invalid proposal category")
        try:
            validate_memory_id(target.get("id"))
        except MemoryValidationError as error:
            raise ProposalError("invalid logical memory id") from error
        if len(set(source_request_ids)) != len(source_request_ids):
            raise ProposalError("source governance request ids must be unique")
        if source_request_ids:
            from governance import GovernanceError, GovernanceService
            try:
                governance = GovernanceService(self._repository.root)
                for request_id in source_request_ids:
                    governance.request(request_id)
            except GovernanceError as error:
                raise ProposalError("source governance request not found") from error
        return self._repository.create(operation, target, change, reason, source_request_ids)

    def get_status(self, proposal_id):
        proposal = self._repository.load(proposal_id)
        return {
            "proposal_id": proposal["proposal_id"],
            "status": proposal["status"],
            "applied_event_id": proposal["applied_event_id"],
        }


class HumanProposalDecisions:
    """Human-facing capability, used only by the confirmation CLI."""

    def __init__(self, root=None):
        self._repository = _ProposalRepository(root)

    def approve(self, proposal_id):
        return self._repository.decide(proposal_id, "approved")

    def reject(self, proposal_id):
        return self._repository.decide(proposal_id, "rejected")

    def decide_many(self, proposal_ids, status):
        """Human-only bulk decision; validates the entire group before writing."""
        if status not in {"approved", "rejected"} or not proposal_ids:
            raise ProposalError("invalid bulk decision")
        if len(set(proposal_ids)) != len(proposal_ids):
            raise ProposalError("proposal group contains duplicates")
        proposals = [self._repository.load(proposal_id) for proposal_id in proposal_ids]
        if any(proposal["status"] != "pending" for proposal in proposals):
            raise ProposalError("only pending proposals may be decided")
        try:
            return [self._repository.decide(proposal_id, status) for proposal_id in proposal_ids]
        except (OSError, ProposalError):
            # Keep a failed bulk decision from leaving an accidental partial
            # review state. These are proposal records, never trusted memory.
            for proposal in proposals:
                self._repository._save(proposal)
            raise


class _ProposalRepository:
    VALID_OPERATIONS = {"create", "update", "delete", "merge"}

    def __init__(self, root=None):
        self.root = repository_root(root)
        self.proposals_root = (self.root / "proposals").resolve()
        self.proposals_root.mkdir(parents=True, exist_ok=True)

    def create(self, operation, target, change, reason, source_request_ids=None):
        if operation not in self.VALID_OPERATIONS:
            raise ProposalError("unsupported proposal operation")
        if not isinstance(target, dict) or not target.get("category") or not target.get("id"):
            raise ProposalError("proposal target requires category and id")
        proposal = {
            "proposal_id": f"prop_{uuid4().hex}", "operation": operation,
            "target": target, "change": change or {}, "reason": reason,
            "timestamp": self._timestamp(), "status": "pending",
            "decision_timestamp": None, "applied_event_id": None,
            "source_request_ids": list(source_request_ids or []),
        }
        self._save(proposal)
        return proposal

    def load(self, proposal_id):
        path = self._path(proposal_id)
        if not path.is_file():
            raise ProposalError(f"proposal not found: {proposal_id}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def decide(self, proposal_id, status):
        proposal = self.load(proposal_id)
        if proposal["status"] != "pending":
            raise ProposalError("only pending proposals may be decided")
        proposal["status"] = status
        proposal["decision_timestamp"] = self._timestamp()
        self._save(proposal)
        return proposal

    def mark_applied(self, proposal_id, event_id):
        proposal = self.load(proposal_id)
        if proposal["status"] != "approved" or proposal["applied_event_id"] is not None:
            raise ProposalError("proposal is not eligible to be applied")
        proposal["applied_event_id"] = event_id
        self._save(proposal)
        return proposal

    def find_by_source_request(self, request_id):
        return [proposal for proposal in self._proposals() if request_id in proposal.get("source_request_ids", [])]

    def _proposals(self):
        for path in self.proposals_root.glob("prop_*.json"):
            with path.open("r", encoding="utf-8") as handle:
                yield json.load(handle)

    def _path(self, proposal_id):
        validate_proposal_id(proposal_id)
        path = (self.proposals_root / f"{proposal_id}.json").resolve()
        if not path.is_relative_to(self.proposals_root):
            raise ProposalError("proposal id escapes proposal storage")
        return path

    def _save(self, proposal):
        path = self._path(proposal["proposal_id"])
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(proposal, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(path)

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()
