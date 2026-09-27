"""Small adapter-only translation for existing expected domain failures."""

import json

from governance import GovernanceError
from history_manager import HistoryError
from memory_loader import MemoryValidationError
from memory_writer import MemoryWriteError
from proposal_store import ProposalError


EXPECTED_ADAPTER_ERRORS = (
    GovernanceError,
    HistoryError,
    MemoryValidationError,
    MemoryWriteError,
    ProposalError,
    json.JSONDecodeError,
    OSError,
)


def error_details(error):
    """Return stable, actionable details without changing core exceptions."""
    message = str(error)
    if isinstance(error, ProposalError):
        if message.startswith("proposal not found:"):
            return "proposal_not_found", "Proposal not found in the selected project."
        return "proposal_error", f"Proposal request cannot be completed: {message}"
    if isinstance(error, MemoryWriteError):
        if message == "proposed content Metadata.id must match target id":
            return "proposal_content_mismatch", (
                "Cannot apply proposal: the proposed memory ID must match the target ID."
            )
        return "mutation_error", f"Governed memory change cannot be completed: {message}"
    if isinstance(error, MemoryValidationError):
        if message.startswith("memory root does not exist:"):
            return "project_memory_error", "Selected project does not contain a memory directory."
        return "project_memory_error", f"Project memory is invalid: {message}"
    if isinstance(error, GovernanceError):
        return "governance_error", f"Governance request cannot be completed: {message}"
    if isinstance(error, HistoryError):
        return "history_error", f"History operation cannot be completed: {message}"
    return "project_state_error", "Project state could not be accessed."
