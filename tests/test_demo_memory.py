from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_loader import MemoryLoader
from memory_retriever import MemoryRetriever
from outermemory import OuterMemory


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DEMO_ROOT = REPOSITORY_ROOT / "examples" / "demo-memory"
CLI = REPOSITORY_ROOT / "src" / "outermemory_cli.py"


def result_ids(results):
    return [result["item"]["id"] for result in results]


class DemoMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.demo_root = Path(self.tempdir.name) / "demo-memory"
        shutil.copytree(SOURCE_DEMO_ROOT, self.demo_root)

    def tearDown(self):
        self.tempdir.cleanup()

    def retrieve(self, question, topk=3):
        memory = MemoryLoader(repository_root_path=self.demo_root).load()
        return MemoryRetriever(memory).retrieve(question, topk)

    def test_demo_is_a_valid_standalone_root_with_exactly_three_records(self):
        memory = MemoryLoader(repository_root_path=SOURCE_DEMO_ROOT).load()
        records = [item for category in memory.values() for item in category.values()]
        self.assertEqual(
            {"v_DEMO_SESSION_POLICY", "r_DEMO_WORKSPACE", "s_DEMO_CONVENTION"},
            {item["id"] for item in records},
        )
        self.assertEqual(3, len(records))

    def test_direct_lexical_demo_query_returns_primary_record(self):
        results = self.retrieve("v_DEMO_SESSION_POLICY", topk=1)
        self.assertEqual(["v_DEMO_SESSION_POLICY"], result_ids(results))

    def test_alias_demo_query_returns_primary_record(self):
        results = self.retrieve("session-policy", topk=1)
        self.assertEqual(["v_DEMO_SESSION_POLICY"], result_ids(results))

    def test_alias_query_expands_one_hop_related_records(self):
        results = self.retrieve("session-policy", topk=3)
        self.assertEqual("v_DEMO_SESSION_POLICY", result_ids(results)[0])
        self.assertEqual(
            {"v_DEMO_SESSION_POLICY", "r_DEMO_WORKSPACE", "s_DEMO_CONVENTION"},
            set(result_ids(results)),
        )

    def test_retrieval_does_not_modify_demo_trusted_memory(self):
        before = {
            path.relative_to(self.demo_root): path.read_bytes()
            for path in (self.demo_root / "memory").rglob("*.md")
        }
        OuterMemory(self.demo_root).retrieve("session-policy", topk=3)
        after = {
            path.relative_to(self.demo_root): path.read_bytes()
            for path in (self.demo_root / "memory").rglob("*.md")
        }
        self.assertEqual(before, after)

    def test_documented_cli_root_arguments_use_the_demo_project(self):
        result = subprocess.run(
            [
                sys.executable, str(CLI), "--root", str(self.demo_root),
                "retrieve", "session-policy", "--topk", "3",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            ["v_DEMO_SESSION_POLICY", "r_DEMO_WORKSPACE", "s_DEMO_CONVENTION"],
            result_ids(json.loads(result.stdout)),
        )


if __name__ == "__main__":
    unittest.main()
