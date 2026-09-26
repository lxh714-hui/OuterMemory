"""Command-line adapter for the AI-facing OuterMemory interface."""

import argparse
import json
import sys

from outermemory import OuterMemory


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"error": message}), file=sys.stderr)
        raise SystemExit(2)


def _json_object(value):
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("must be valid JSON") from error
    if not isinstance(decoded, dict):
        raise argparse.ArgumentTypeError("must be a JSON object")
    return decoded


def build_parser():
    parser = JsonArgumentParser(description="JSON CLI for project OuterMemory")
    parser.add_argument("--root", help="project repository root")
    commands = parser.add_subparsers(dest="command", required=True)

    retrieve = commands.add_parser("retrieve")
    retrieve.add_argument("question")
    retrieve.add_argument("--topk", type=int, default=5)

    propose = commands.add_parser("propose")
    propose.add_argument("operation")
    propose.add_argument("--category", required=True)
    propose.add_argument("--id", required=True, dest="memory_id")
    propose.add_argument("--change", type=_json_object, default={})
    propose.add_argument("--reason")

    status = commands.add_parser("proposal-status")
    status.add_argument("proposal_id")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    memory = OuterMemory(args.root)

    try:
        if args.command == "retrieve":
            result = memory.retrieve(args.question, args.topk)
        elif args.command == "propose":
            result = memory.propose(
                args.operation,
                {"category": args.category, "id": args.memory_id},
                args.change,
                args.reason,
            )
        else:
            result = memory.proposal_status(args.proposal_id)
    except Exception as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
