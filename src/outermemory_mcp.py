"""MCP transports for project-scoped OuterMemory."""

import argparse
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from outermemory import OuterMemory


def create_server(project_root):
    """Create an MCP server bound to one explicit project root."""
    memory = OuterMemory(Path(project_root).resolve())
    server = MCPServer("OuterMemory")

    @server.tool(name="outermemory_retrieve")
    def retrieve(question: str, topk: int = 5):
        """Retrieve relevant records from this project's memory."""
        return memory.retrieve(question, topk)

    @server.tool(name="outermemory_propose")
    def propose(
        operation: str,
        category: str,
        memory_id: str,
        change: dict | None = None,
        reason: str | None = None,
        source_request_ids: list[str] | None = None,
    ):
        """Create a pending, human-governed proposal for project memory."""
        return memory.propose(
            operation,
            {"category": category, "id": memory_id},
            change,
            reason,
            source_request_ids,
        )

    @server.tool(name="outermemory_proposal_status")
    def proposal_status(proposal_id: str):
        """Get the status of a project-memory proposal."""
        return memory.proposal_status(proposal_id)

    return server


def build_parser():
    parser = argparse.ArgumentParser(description="MCP server for OuterMemory")
    parser.add_argument("--root", required=True, help="project repository root")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp", dest="streamable_http_path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    server = create_server(args.root)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(
            "streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.streamable_http_path,
        )


if __name__ == "__main__":
    main()
