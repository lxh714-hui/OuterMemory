from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "src" / "outermemory_cli.py"


def record(memory_id, description="Test memory"):
    return (
        "# Metadata\n\n"
        f"id: {memory_id}\nfrequency: 0\nlast_used:\n\n"
        f"# Description\n\n{description}\n"
    )


class OuterMemoryCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)
        (self.root / "memory" / "variables" / "v_DATASET.md").write_text(
            record("v_DATASET", "Dataset path for the demo project"), encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, check=True,
        )

    def test_retrieve_outputs_json(self):
        result = json.loads(self.run_cli("retrieve", "dataset").stdout)
        self.assertEqual("v_DATASET", result[0]["item"]["id"])

    def test_propose_and_inspect_status_output_json(self):
        proposal = json.loads(self.run_cli(
            "propose", "create", "--category", "variables", "--id", "v_NEW",
            "--change", json.dumps({"content": record("v_NEW")}), "--reason", "test",
        ).stdout)
        status = json.loads(self.run_cli("proposal-status", proposal["proposal_id"]).stdout)
        self.assertEqual("pending", status["status"])
        self.assertEqual(proposal["proposal_id"], status["proposal_id"])

    def test_governance_commands_are_not_exposed(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), "approve", "anything"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid choice", json.loads(result.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
