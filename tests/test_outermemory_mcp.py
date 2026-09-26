from pathlib import Path
import asyncio
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outermemory_mcp import build_parser, create_server, main


def record(memory_id, description="Test memory"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class OuterMemoryMcpTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)
        (self.root / "memory" / "variables" / "v_DATASET.md").write_text(
            record("v_DATASET", "Dataset path for the demo project"), encoding="utf-8"
        )
        self.server = create_server(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_exposes_only_ai_facing_tools(self):
        tools = asyncio.run(self.server.list_tools())
        self.assertEqual(
            {"outermemory_retrieve", "outermemory_propose", "outermemory_proposal_status"},
            {tool.name for tool in tools},
        )

    def test_retrieve_delegates_to_project_outermemory(self):
        result = asyncio.run(self.server.call_tool(
            "outermemory_retrieve", {"question": "dataset"}
        ))
        self.assertIn("v_DATASET", str(result))

    def test_propose_and_status_delegate_to_project_outermemory(self):
        proposal = asyncio.run(self.server.call_tool(
            "outermemory_propose",
            {
                "operation": "create",
                "category": "variables",
                "memory_id": "v_NEW",
                "change": {"content": record("v_NEW")},
                "reason": "test proposal",
            },
        ))
        self.assertIn("pending", str(proposal))
        proposal_data = json.loads(next(
            part.text for part in proposal.content if "prop_" in getattr(part, "text", "")
        ))
        status = asyncio.run(self.server.call_tool(
            "outermemory_proposal_status", {"proposal_id": proposal_data["proposal_id"]}
        ))
        self.assertIn("pending", str(status))

    def test_transport_defaults_to_stdio(self):
        args = build_parser().parse_args(["--root", str(self.root)])
        self.assertEqual("stdio", args.transport)

    def test_stdio_transport_runs_server_over_stdio(self):
        server = Mock()
        with patch("outermemory_mcp.create_server", return_value=server):
            main(["--root", str(self.root)])
        server.run.assert_called_once_with("stdio")

    def test_streamable_http_transport_preserves_network_options(self):
        server = Mock()
        with patch("outermemory_mcp.create_server", return_value=server):
            main([
                "--root", str(self.root), "--transport", "streamable-http",
                "--host", "0.0.0.0", "--port", "9000", "--path", "/outermemory",
            ])
        server.run.assert_called_once_with(
            "streamable-http",
            host="0.0.0.0",
            port=9000,
            streamable_http_path="/outermemory",
        )


if __name__ == "__main__":
    unittest.main()
