from memory_loader import MemoryLoader
from memory_retriever import MemoryRetriever
from proposal_store import ProposalService
from repository_paths import repository_root


class OuterMemory:
    """AI-facing application interface for a project memory."""

    def __init__(self, root=None):
        self.root = repository_root(root)
        self.proposals = ProposalService(self.root)

    def retrieve(self, question, topk=5):
        memory = MemoryLoader(repository_root_path=self.root).load()
        retriever = MemoryRetriever(memory)
        return retriever.retrieve(question, topk)

    def propose(self, operation, target, change=None, reason=None):
        return self.proposals.create_proposal(
            operation=operation,
            target=target,
            change=change or {},
            reason=reason,
        )

    def proposal_status(self, proposal_id):
        return self.proposals.get_status(proposal_id)
