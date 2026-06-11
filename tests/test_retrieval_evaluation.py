from __future__ import annotations

import unittest

from product_agent.evaluation.retrieval_quality import (
    _paper_evaluation_row,
    load_cases,
)
from product_agent.models import PaperNode


class RetrievalEvaluationTests(unittest.TestCase):
    def test_benchmark_dataset_is_valid_and_covers_product_risks(self) -> None:
        payload = load_cases()
        cases = payload["cases"]
        categories = {case["category"] for case in cases}

        self.assertGreaterEqual(len(cases), 10)
        self.assertIn("core_topic", categories)
        self.assertIn("time_constraint", categories)
        self.assertIn("direction_expansion", categories)
        self.assertIn("mixed_language", categories)

    def test_human_contract_is_independent_from_system_relevance_tier(self) -> None:
        expectations = {
            "min_concept_groups_per_paper": 2,
            "concept_groups": [
                {"name": "agent", "aliases": ["llm agent", "language agent"]},
                {"name": "tool", "aliases": ["tool use", "function calling"]},
                {"name": "evaluation", "aliases": ["benchmark", "evaluation"]},
            ],
            "forbidden_title_terms": [],
        }
        paper = PaperNode(
            paper_id="paper",
            title="Benchmarking Tool Use in Language Agents",
            abstract="Evaluation of function calling behavior.",
            source="arxiv",
            relevance_tier="candidate",
        )

        row = _paper_evaluation_row(paper, expectations)

        self.assertTrue(row["human_contract_match"])
        self.assertEqual(row["relevance_tier"], "candidate")
        self.assertEqual(
            row["matched_concept_groups"],
            ["agent", "tool", "evaluation"],
        )

    def test_year_contract_rejects_out_of_range_paper(self) -> None:
        expectations = {
            "min_concept_groups_per_paper": 2,
            "concept_groups": [
                {"name": "agent", "aliases": ["agent"]},
                {"name": "code", "aliases": ["software engineering"]},
            ],
            "forbidden_title_terms": [],
            "year_range": {"start_year": 2025, "end_year": 2026},
        }
        paper = PaperNode(
            paper_id="old",
            title="Software Engineering Agent Evaluation",
            publish_date="2024-06-01",
            source="arxiv",
        )

        row = _paper_evaluation_row(paper, expectations)

        self.assertFalse(row["constraint_pass"])


if __name__ == "__main__":
    unittest.main()
