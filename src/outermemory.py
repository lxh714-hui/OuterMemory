from memory_loader import MemoryLoader
from memory_retriever import MemoryRetriever
from proposal_store import ProposalService
from repository_paths import repository_root
from governance import GovernanceService


class OuterMemory:
    """AI-facing application interface for a project memory."""

    def __init__(self, root=None):
        self.root = repository_root(root)
        self.proposals = ProposalService(self.root)
        self._governance = GovernanceService(self.root)
        # A failed scan intentionally propagates: its success timestamp must not move.
        self.startup_scan = self._governance.startup_scan()

    def retrieve(self, question, topk=5):
        memory = MemoryLoader(repository_root_path=self.root).load()
        retriever = MemoryRetriever(memory)
        results = retriever.retrieve(question, topk)
        self._governance.record_retrieval(results)
        self._governance.contextual_self_check(results)
        return results

    def propose(self, operation, target, change=None, reason=None, source_request_ids=None):
        return self.proposals.create_proposal(
            operation=operation,
            target=target,
            change=change or {},
            reason=reason,
            source_request_ids=source_request_ids,
        )

    def proposal_status(self, proposal_id):
        return self.proposals.get_status(proposal_id)
