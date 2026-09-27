import asyncio
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import main as human_main
from outermemory_cli import main as json_main
from outermemory_mcp import create_server
from proposal_store import HumanProposalDecisions, ProposalService
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError


def record(memory_id, description="adapter test"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class AdapterErrorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)
        (self.root / "memory" / "variables" / "v_BASE.md").write_text(
            record("v_BASE"), encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def run_json_cli(self, *arguments):
        stderr = StringIO()
        with redirect_stderr(stderr):
            status = json_main(["--root", str(self.root), *arguments])
        return status, stderr.getvalue()

    def test_json_cli_invalid_proposal_uses_a_stable_error_envelope(self):
        status, stderr = self.run_json_cli(
            "propose", "create", "--category", "not-a-category", "--id", "v_NEW"
        )
        error = json.loads(stderr)
        self.assertEqual(1, status)
        self.assertEqual(
            {"ok": False, "error": {"type": "proposal_error", "message": error["error"]["message"]}},
            error,
        )
        self.assertIn("Proposal request cannot be completed", error["error"]["message"])

    def test_json_cli_missing_status_target_uses_nonzero_proposal_not_found_error(self):
        status, stderr = self.run_json_cli("proposal-status", "prop_" + "0" * 32)
        self.assertEqual(1, status)
        self.assertEqual(
            {"ok": False, "error": {
                "type": "proposal_not_found",
                "message": "Proposal not found in the selected project.",
            }},
            json.loads(stderr),
        )

    def test_json_cli_does_not_swallow_unexpected_programming_errors(self):
        with patch("outermemory_cli.OuterMemory", side_effect=RuntimeError("programming defect")):
            with self.assertRaisesRegex(RuntimeError, "programming defect"):
                json_main(["--root", str(self.root), "retrieve", "base"])

    def test_mcp_expected_proposal_error_is_a_tool_error_with_actionable_message(self):
        server = create_server(self.root)
        with self.assertRaises(ToolError) as raised:
            asyncio.run(server.call_tool(
                "outermemory_propose",
                {"operation": "create", "category": "not-a-category", "memory_id": "v_NEW"},
            ))
        self.assertNotIsInstance(raised.exception, UnexpectedToolError)
        self.assertIn("proposal_error:", str(raised.exception))
        self.assertIn("Proposal request cannot be completed", str(raised.exception))

        with patch("outermemory_mcp.OuterMemory") as outer_memory:
            outer_memory.return_value.propose.side_effect = RuntimeError("programming defect")
            server = create_server(self.root)
        with self.assertRaises(UnexpectedToolError):
            asyncio.run(server.call_tool(
                "outermemory_propose",
                {"operation": "create", "category": "variables", "memory_id": "v_NEW"},
            ))

    def test_human_cli_missing_proposal_is_concise_and_has_no_traceback(self):
        output = StringIO()
        with patch("builtins.input", return_value="yes"), redirect_stdout(output):
            status = human_main(["main.py", "--root", str(self.root), "approve", "prop_" + "0" * 32])
        self.assertEqual(1, status)
        self.assertEqual("Proposal not found in the selected project.\n", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_human_cli_translates_proposed_content_identity_mismatch(self):
        proposal = ProposalService(self.root).create_proposal(
            "create", {"category": "variables", "id": "v_TARGET"},
            {"content": record("v_OTHER")}, "adapter error test",
        )
        HumanProposalDecisions(self.root).approve(proposal["proposal_id"])
        output = StringIO()
        with redirect_stdout(output):
            status = human_main(["main.py", "--root", str(self.root), "apply", proposal["proposal_id"]])
        self.assertEqual(1, status)
        self.assertEqual(
            "Cannot apply proposal: the proposed memory ID must match the target ID.\n",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
