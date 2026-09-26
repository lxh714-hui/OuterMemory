import sys

from memory_writer import ControlledMemoryWriter
from proposal_store import HumanProposalDecisions


def confirm(action, identifier):
    response = input(f"Human approval required to {action} {identifier}. Type yes: ")
    return response.strip().lower() == "yes"


def main(argv):
    if len(argv) != 3 or argv[1] not in {"approve", "reject", "apply", "rollback"}:
        print("usage: main.py approve|reject|apply|rollback <id>")
        return 2
    action, identifier = argv[1], argv[2]
    if action in {"approve", "reject"}:
        if not confirm(action, identifier):
            print("No action taken.")
            return 1
        decisions = HumanProposalDecisions()
        proposal = decisions.approve(identifier) if action == "approve" else decisions.reject(identifier)
        print(f"Proposal {proposal['proposal_id']} is {proposal['status']}.")
        return 0
    writer = ControlledMemoryWriter()
    if action == "apply":
        event = writer.apply_approved_proposal(identifier)
        print(f"Applied as history event {event['event_id']}.")
    else:
        if not confirm("rollback", identifier):
            print("No action taken.")
            return 1
        event = writer.rollback(identifier)
        print(f"Rollback recorded as history event {event['event_id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
