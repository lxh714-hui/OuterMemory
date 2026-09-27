from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from governance import GovernanceService
from main import main
from proposal_store import ProposalService
from repository_paths import REPOSITORY_ROOT


def record(memory_id, description="root test"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class ProjectRootCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.parent = Path(self.tempdir.name)
        self.root_a = self.parent / "project-a"
        self.root_b = self.parent / "project-b"
        for root, memory_id in ((self.root_a, "v_A"), (self.root_b, "v_B")):
            for category in ("variables", "resources", "functions", "standards"):
                (root / "memory" / category).mkdir(parents=True)
            (root / "memory" / "variables" / f"{memory_id}.md").write_text(
                record(memory_id), encoding="utf-8"
            )

    def tearDown(self):
        self.tempdir.cleanup()

    def invoke(self, *arguments):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["main.py", "--root", str(self.root_a), *arguments])
        return status, output.getvalue()

    def test_human_cli_accepts_root_and_writes_scan_state_to_selected_project(self):
        status, _ = self.invoke("scan")
        self.assertEqual(0, status)
        self.assertTrue((self.root_a / ".outermemory" / "governance.json").is_file())
        self.assertFalse((self.root_b / ".outermemory").exists())

    def test_explicit_root_keeps_proposals_and_history_out_of_other_project_and_source_root(self):
        proposal = ProposalService(self.root_a).create_proposal(
            "create", {"category": "variables", "id": "v_NEW"},
            {"content": record("v_NEW")}, "root isolation",
        )
        with patch("builtins.input", return_value="yes"):
            status, _ = self.invoke("approve", proposal["proposal_id"])
        self.assertEqual(0, status)
        status, _ = self.invoke("apply", proposal["proposal_id"])
        self.assertEqual(0, status)

        self.assertTrue((self.root_a / "memory" / "variables" / "v_NEW.md").is_file())
        self.assertTrue(any((self.root_a / "history" / "events").glob("evt_*.json")))
        self.assertFalse((self.root_b / "memory" / "variables" / "v_NEW.md").exists())
        self.assertFalse((self.root_b / "proposals" / f"{proposal['proposal_id']}.json").exists())
        self.assertFalse((REPOSITORY_ROOT / "proposals" / f"{proposal['proposal_id']}.json").exists())

    def test_trace_uses_selected_projects_governance_state(self):
        governance = GovernanceService(self.root_a)
        item = {"id": "v_A", "category": "variables", "path": "variables/v_A.md", "data": {}}
        for _ in range(5):
            generated = governance.record_retrieval([{"item": item}])["requests"]
        request_id = generated[0]["request_id"]

        status, output = self.invoke("trace", request_id)
        self.assertEqual(0, status)
        self.assertIn(request_id, output)

    def test_omitted_root_preserves_default_service_construction(self):
        with patch("main.GovernanceService") as governance:
            output = StringIO()
            with redirect_stdout(output):
                status = main(["main.py", "requests"])
        self.assertEqual(0, status)
        governance.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
