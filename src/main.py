import sys

from governance import GovernanceError, GovernanceService
from memory_writer import ControlledMemoryWriter
from proposal_store import HumanProposalDecisions, ProposalError


def confirm(action, identifier):
    response = input(f"Human approval required to {action} {identifier}. Type yes: ")
    return response.strip().lower() == "yes"


def confirm_bulk(action, identifiers):
    response = input(
        f"Human secondary confirmation required to {action} {len(identifiers)} items. "
        f"Type '{action}': "
    )
    return response.strip().lower() == action


def main(argv):
    if len(argv) < 2 or argv[1] not in {"approve", "reject", "apply", "rollback", "scan", "requests", "request", "resolve-request", "approve-all", "reject-all", "review-all", "dismiss-all"}:
        print("usage: main.py approve|reject|apply|rollback <id> | approve-all|reject-all <proposal-id...> | review-all|dismiss-all <request-id...> | scan [issue-type|finding-id] | requests [issue-type] | request <id> | resolve-request <id>")
        return 2
    action = argv[1]
    if action in {"approve-all", "reject-all", "review-all", "dismiss-all"}:
        identifiers = argv[2:]
        verb = {"approve-all": "approve all", "reject-all": "reject all", "review-all": "review all", "dismiss-all": "dismiss all"}[action]
        if not identifiers:
            print(f"usage: main.py {action} <id...>")
            return 2
        if not confirm_bulk(verb, identifiers):
            print("No action taken.")
            return 1
        is_proposal_action = action in {"approve-all", "reject-all"}
        prefix = "prop_" if is_proposal_action else "gov_"
        if any(not identifier.startswith(prefix) for identifier in identifiers):
            print("proposal decisions and governance-request review use separate bulk commands")
            return 2
        try:
            if is_proposal_action:
                count = len(HumanProposalDecisions().decide_many(
                    identifiers, "approved" if action == "approve-all" else "rejected"
                ))
            else:
                count = len(GovernanceService().resolve_many(
                    identifiers, "reviewed" if action == "review-all" else "dismissed"
                ))
        except (GovernanceError, ProposalError, OSError) as error:
            print(str(error))
            return 1
        print(f"{count} items {verb}.")
        return 0
    if action in {"scan", "requests"}:
        if len(argv) > 3:
            print("too many arguments")
            return 2
        governance = GovernanceService()
        try:
            result = governance.full_scan() if action == "scan" and len(argv) == 2 else (
                governance.latest_scan(finding_id=argv[2]) if action == "scan" and argv[2].startswith("finding_") else
                governance.latest_scan(issue_type=argv[2]) if action == "scan" else
                governance.pending_requests(argv[2] if len(argv) == 3 else None)
            )
        except GovernanceError as error:
            print(str(error))
            return 1
        print(result)
        return 0
    if len(argv) != 3:
        print(f"usage: main.py {action} <id>")
        return 2
    identifier = argv[2]
    if action == "request":
        try:
            print(GovernanceService().request(identifier))
            return 0
        except GovernanceError as error:
            print(str(error))
            return 1
    if action == "resolve-request":
        if not confirm("resolve governance request", identifier):
            print("No action taken.")
            return 1
        try:
            request = GovernanceService().resolve_request(identifier)
            print(f"Governance request {request['request_id']} is {request['resolution']['status']}.")
            return 0
        except GovernanceError as error:
            print(str(error))
            return 1
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
