from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_loader import DuplicateMemoryIdError, MemoryLoader
from memory_retriever import MemoryRetriever
from memory_writer import ControlledMemoryWriter, MemoryWriteError
from proposal_store import HumanProposalDecisions, ProposalService


def record(memory_id, description="", aliases=(), related=(), extra_sections=(), frequency=0):
    """Build a record in the currently supported section-based Markdown schema."""
    parts = [
        "# Metadata\n\n",
        f"id: {memory_id}\nfrequency: {frequency}\nlast_used:\n\n",
        "# Description\n\n",
        f"{description}\n",
    ]
    if aliases:
        parts.extend(["\n# Aliases\n\n", "".join(f"- {alias}\n" for alias in aliases)])
    if related:
        parts.extend(["\n# Related\n\n", "".join(f"- {item}\n" for item in related)])
    for heading, content in extra_sections:
        parts.extend([f"\n# {heading}\n\n", f"{content}\n"])
    return "".join(parts)


def result_ids(results):
    return [result["item"]["id"] for result in results]


def recall_at_k(results, relevant_ids, k):
    """Recall for one query: fraction of expected records present in its first k results."""
    expected = set(relevant_ids)
    if not expected:
        return 1.0
    return len(set(results[:k]) & expected) / len(expected)


def reciprocal_rank(results, relevant_ids):
    """Reciprocal rank for one query; zero when none of its expected IDs is retrieved."""
    expected = set(relevant_ids)
    for position, memory_id in enumerate(results, start=1):
        if memory_id in expected:
            return 1.0 / position
    return 0.0


def mean_reciprocal_rank(cases):
    """Mean reciprocal rank for (result_ids, relevant_ids) fixture cases."""
    if not cases:
        return 0.0
    return sum(reciprocal_rank(results, expected) for results, expected in cases) / len(cases)


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for category in ("variables", "resources", "functions", "standards"):
            (self.root / "memory" / category).mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_record(self, category, memory_id, **kwargs):
        path = self.root / "memory" / category / f"{memory_id}.md"
        path.write_text(record(memory_id, **kwargs), encoding="utf-8")
        return path

    def retrieve(self, question, topk=5):
        memory = MemoryLoader(repository_root_path=self.root).load()
        return MemoryRetriever(memory).retrieve(question, topk)


class RetrievalCharacterizationTests(MemoryTestCase):
    """Characterize the existing lexical retriever; these are not desired-future tests."""

    def setUp(self):
        super().setUp()
        self.write_record(
            "variables", "v_EXACT_ID", description="A description lookup phrase",
            aliases=("exact-alias",), related=("r_RELATED",),
        )
        self.write_record("resources", "r_RELATED", description="Related record only")
        self.write_record("standards", "s_GRANDCHILD", description="Not one hop away")
        # This relationship deliberately proves expansion stops after one hop.
        related_path = self.root / "memory" / "resources" / "r_RELATED.md"
        related_path.write_text(
            record("r_RELATED", "Related record only", related=("s_GRANDCHILD",)),
            encoding="utf-8",
        )
        self.write_record("variables", "v_TOP_A", description="topk common phrase")
        self.write_record("variables", "v_TOP_B", description="topk common phrase")
        self.write_record("variables", "v_TOP_C", description="topk common phrase")
        self.write_record("variables", "v_TIE_A", description="equal-score-token")
        self.write_record("variables", "v_TIE_B", description="equal-score-token")
        self.write_record("variables", "v_DIRECT_WEAK", description="exact-alias")

    def test_exact_id_matching_has_current_id_weight(self):
        results = self.retrieve("v_EXACT_ID")
        self.assertEqual("v_EXACT_ID", result_ids(results)[0])
        self.assertEqual(11, results[0]["score"])

    def test_exact_alias_matching_has_current_alias_weight(self):
        results = self.retrieve("exact-alias")
        self.assertEqual("v_EXACT_ID", result_ids(results)[0])
        self.assertEqual(6, results[0]["score"])

    def test_description_matching_is_case_insensitive_substring_matching(self):
        results = self.retrieve("LOOKUP")
        # v_EXACT_ID is the literal Description match. Its Related entry is then
        # appended by the production retriever's one-hop expansion and sorts after
        # the direct score-1 match with score 0.
        self.assertEqual(["v_EXACT_ID", "r_RELATED"], result_ids(results))
        self.assertEqual(1, results[0]["score"])
        self.assertEqual(0, results[1]["score"])

    def test_punctuation_attached_query_token_is_normalized(self):
        results = self.retrieve("(exact-alias),")
        self.assertEqual("v_EXACT_ID", result_ids(results)[0])
        self.assertEqual(6, results[0]["score"])

    def test_related_expansion_remains_secondary_to_direct_matches(self):
        results = self.retrieve("exact-alias", topk=5)
        self.assertEqual(["v_EXACT_ID", "v_DIRECT_WEAK", "r_RELATED"], result_ids(results))
        self.assertEqual([6, 1, 5], [result["score"] for result in results])

    def test_frequency_does_not_affect_lexical_relevance_or_tie_breaking(self):
        self.write_record(
            "variables", "v_FREQUENCY_A", description="frequency-neutral-token", frequency=999,
        )
        self.write_record("variables", "v_FREQUENCY_B", description="frequency-neutral-token")
        results = self.retrieve("frequency-neutral-token", topk=2)
        self.assertEqual(["v_FREQUENCY_A", "v_FREQUENCY_B"], result_ids(results))
        self.assertEqual([1, 1], [result["score"] for result in results])

    def test_multiple_query_terms_deduplicate_to_the_highest_scored_result(self):
        results = self.retrieve("v_EXACT_ID exact-alias")
        matches = [result for result in results if result["item"]["id"] == "v_EXACT_ID"]
        self.assertEqual(1, len(matches))
        self.assertEqual(11, matches[0]["score"])

    def test_topk_is_applied_after_ranking(self):
        results = self.retrieve("topk", topk=2)
        self.assertEqual(2, len(results))
        self.assertEqual({"v_TOP_A", "v_TOP_B"}, set(result_ids(results)))

    def test_related_expansion_is_one_hop_and_parent_score_minus_one(self):
        results = self.retrieve("exact-alias", topk=5)
        scores = {result["item"]["id"]: result["score"] for result in results}
        self.assertEqual(6, scores["v_EXACT_ID"])
        self.assertEqual(5, scores["r_RELATED"])
        self.assertNotIn("s_GRANDCHILD", scores)

    def test_equal_score_order_is_id_ascending_even_when_fixture_order_is_reversed(self):
        memory = MemoryLoader(repository_root_path=self.root).load()
        reversed_fixture = {
            "variables": {
                "v_TIE_B": memory["variables"]["v_TIE_B"],
                "v_TIE_A": memory["variables"]["v_TIE_A"],
            },
            "resources": {}, "functions": {}, "standards": {},
        }
        first = result_ids(MemoryRetriever(reversed_fixture).retrieve("equal-score-token", topk=5))
        second = result_ids(MemoryRetriever(reversed_fixture).retrieve("equal-score-token", topk=5))
        self.assertEqual(["v_TIE_A", "v_TIE_B"], first)
        self.assertEqual(first, second)

    def test_unrelated_query_returns_no_results(self):
        self.assertEqual([], self.retrieve("unrelated-nonexistent-token"))


class MemoryIdentityCharacterizationTests(MemoryTestCase):
    def test_metadata_id_is_persisted_logical_identity(self):
        path = self.write_record("variables", "v_LOGICAL_ID", description="identity record")
        item = MemoryLoader(repository_root_path=self.root).load()["variables"]["v_LOGICAL_ID"]
        self.assertEqual("v_LOGICAL_ID", item["id"])
        self.assertEqual("v_LOGICAL_ID", item["data"]["Metadata"]["id"])
        self.assertEqual("variables/v_LOGICAL_ID.md", item["path"])
        self.assertEqual("v_LOGICAL_ID.md", path.name)

    def test_target_id_must_match_metadata_id_during_controlled_mutation(self):
        service = ProposalService(self.root)
        proposal = service.create_proposal(
            "create", {"category": "variables", "id": "v_TARGET"},
            {"content": record("v_OTHER", "mismatched identity")}, "characterization",
        )
        HumanProposalDecisions(self.root).approve(proposal["proposal_id"])
        with self.assertRaisesRegex(MemoryWriteError, "Metadata.id must match target id"):
            ControlledMemoryWriter(self.root).apply_approved_proposal(proposal["proposal_id"])
        self.assertFalse((self.root / "memory" / "variables" / "v_TARGET.md").exists())

    def test_create_path_is_derived_from_target_id_not_an_independent_input(self):
        service = ProposalService(self.root)
        proposal = service.create_proposal(
            "create", {"category": "variables", "id": "v_DERIVED_PATH"},
            {"content": record("v_DERIVED_PATH", "derived location")}, "characterization",
        )
        HumanProposalDecisions(self.root).approve(proposal["proposal_id"])
        ControlledMemoryWriter(self.root).apply_approved_proposal(proposal["proposal_id"])
        expected = self.root / "memory" / "variables" / "v_DERIVED_PATH.md"
        self.assertTrue(expected.is_file())
        loaded = MemoryLoader(repository_root_path=self.root).load()["variables"]["v_DERIVED_PATH"]
        self.assertEqual("variables/v_DERIVED_PATH.md", loaded["path"])

    def test_persisted_duplicate_metadata_ids_are_rejected_even_across_categories(self):
        self.write_record("variables", "v_DUPLICATE", description="first")
        path = self.root / "memory" / "resources" / "r_OTHER_FILENAME.md"
        path.write_text(record("v_DUPLICATE", "second"), encoding="utf-8")
        with self.assertRaises(DuplicateMemoryIdError):
            MemoryLoader(repository_root_path=self.root).load()


class RetrievalQualityBaselineTests(MemoryTestCase):
    """A deterministic 71-record corpus for baseline quality, not performance timing."""

    PRIMARY = "v_SESSION_POLICY"

    def setUp(self):
        super().setUp()
        self.write_record(
            "variables", self.PRIMARY,
            description="Session expiration policy for authenticated user login state.",
            aliases=("session-lifecycle", "login session"),
            related=("s_SESSION_SECURITY", "r_REFRESH_CONFIG"),
        )
        self.write_record("standards", "s_SESSION_SECURITY", description="Rotate refresh tokens after expiry.")
        self.write_record("resources", "r_REFRESH_CONFIG", description="Refresh token configuration values.")
        self.write_record(
            "standards", "s_HIDDEN_GUIDANCE", description="General operational guidance.",
            extra_sections=(("Guidelines", "session migration requires a maintenance window."),),
        )
        self.write_record("variables", "v_TIE_A", description="controlled-tie-token")
        self.write_record("variables", "v_TIE_B", description="controlled-tie-token")
        for index in range(35):
            self.write_record(
                "variables", f"v_AUTH_CONFIG_{index:02d}",
                description=f"auth config noisy setting {index}",
            )
        for index in range(30):
            self.write_record(
                "resources", f"r_UNRELATED_{index:02d}",
                description=f"unrelated catalog resource {index}",
            )

    def test_exact_id_baseline_recall_and_rank(self):
        ids = result_ids(self.retrieve(self.PRIMARY, topk=3))
        self.assertEqual(self.PRIMARY, ids[0])
        self.assertEqual(1.0, recall_at_k(ids, {self.PRIMARY}, 1))
        self.assertEqual(1.0, reciprocal_rank(ids, {self.PRIMARY}))

    def test_alias_baseline_recall_and_rank(self):
        ids = result_ids(self.retrieve("session-lifecycle", topk=3))
        self.assertEqual(self.PRIMARY, ids[0])
        self.assertEqual(1.0, recall_at_k(ids, {self.PRIMARY}, 1))
        self.assertEqual(1.0, reciprocal_rank(ids, {self.PRIMARY}))

    def test_common_term_baseline_retrieves_a_broad_low_precision_set(self):
        ids = result_ids(self.retrieve("auth", topk=40))
        # 35 noisy direct matches + the primary + its two one-hop Related records.
        self.assertEqual(38, len(ids))
        self.assertIn(self.PRIMARY, ids)
        self.assertEqual(1.0, recall_at_k(ids, {self.PRIMARY}, 38))
        # ID lexical matches outrank the primary's Description-only match.
        self.assertEqual(36, ids.index(self.PRIMARY) + 1)

    def test_unrelated_query_baseline_has_no_false_positive(self):
        ids = result_ids(self.retrieve("absent-baseline-token", topk=5))
        self.assertEqual([], ids)
        self.assertEqual(0.0, reciprocal_rank(ids, {self.PRIMARY}))

    def test_related_expansion_baseline_returns_one_hop_records(self):
        ids = result_ids(self.retrieve("session-lifecycle", topk=3))
        self.assertEqual(self.PRIMARY, ids[0])
        self.assertEqual({self.PRIMARY, "s_SESSION_SECURITY", "r_REFRESH_CONFIG"}, set(ids))
        self.assertEqual(1.0, recall_at_k(ids, {self.PRIMARY, "s_SESSION_SECURITY", "r_REFRESH_CONFIG"}, 3))

    def test_equal_score_ranking_is_deterministic(self):
        memory = MemoryLoader(repository_root_path=self.root).load()
        first = result_ids(MemoryRetriever(memory).retrieve("controlled-tie-token", topk=2))
        second = result_ids(MemoryRetriever(memory).retrieve("controlled-tie-token", topk=2))
        self.assertEqual(["v_TIE_A", "v_TIE_B"], first)
        self.assertEqual(first, second)

    def test_scale_corpus_contains_seventy_one_records_and_still_retrieves_exact_id(self):
        memory = MemoryLoader(repository_root_path=self.root).load()
        count = sum(len(category) for category in memory.values())
        self.assertEqual(71, count)
        self.assertEqual(self.PRIMARY, result_ids(MemoryRetriever(memory).retrieve(self.PRIMARY, 1))[0])

    def test_paraphrase_is_a_documented_current_miss(self):
        # No query rewriting or semantic matching exists in the current retriever.
        ids = result_ids(self.retrieve("cookie longevity handling", topk=5))
        self.assertNotIn(self.PRIMARY, ids)
        self.assertEqual(0.0, recall_at_k(ids, {self.PRIMARY}, 5))

    def test_bilingual_synonym_query_is_a_documented_current_miss(self):
        # Chinese login-state wording has no literal overlap with the English record.
        ids = result_ids(self.retrieve("登录态怎么管", topk=5))
        self.assertNotIn(self.PRIMARY, ids)
        self.assertEqual(0.0, reciprocal_rank(ids, {self.PRIMARY}))

    def test_non_searchable_section_content_is_a_documented_current_miss(self):
        # MemoryQuery indexes only id, Description, and Aliases, not Guidelines.
        ids = result_ids(self.retrieve("maintenance", topk=5))
        self.assertNotIn("s_HIDDEN_GUIDANCE", ids)
        self.assertEqual(0.0, reciprocal_rank(ids, {"s_HIDDEN_GUIDANCE"}))

    def test_representative_mean_reciprocal_rank_baseline(self):
        cases = [
            (result_ids(self.retrieve(self.PRIMARY, 3)), {self.PRIMARY}),
            (result_ids(self.retrieve("session-lifecycle", 3)), {self.PRIMARY}),
            (result_ids(self.retrieve("登录态怎么管", 3)), {self.PRIMARY}),
        ]
        self.assertEqual(2 / 3, mean_reciprocal_rank(cases))


if __name__ == "__main__":
    unittest.main()
