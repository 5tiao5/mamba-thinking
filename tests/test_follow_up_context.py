from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from product_agent.domain import PaperRecord, ResearchTask, ResearchWorkspace
from product_agent.models import PaperNode
from product_agent.research_agent.nodes.searcher import (
    _inherit_previous_round_metadata,
    _previous_round_papers,
)
from product_agent.services.research_service import ResearchService


class _TaskRepository:
    def __init__(self, tasks):
        self.tasks = tasks

    def list_all(self):
        return list(self.tasks)


class _WorkspaceRepository:
    def __init__(self, workspaces):
        self.workspaces = workspaces

    def get_by_task(self, task_id):
        return self.workspaces.get(task_id)


class FollowUpContextTests(unittest.TestCase):
    def test_previous_round_uses_latest_existing_workspace_even_if_task_is_running(self) -> None:
        base_time = datetime(2026, 6, 11, tzinfo=timezone.utc)
        previous_task = ResearchTask(
            task_id="task-previous",
            conversation_id="conversation-1",
            topic="initial topic",
            status="running",
            created_at=base_time,
            updated_at=base_time + timedelta(minutes=3),
        )
        newer_without_workspace = ResearchTask(
            task_id="task-empty",
            conversation_id="conversation-1",
            topic="another queued task",
            status="queued",
            created_at=base_time + timedelta(minutes=1),
            updated_at=base_time + timedelta(minutes=1),
        )
        current_task = ResearchTask(
            task_id="task-current",
            conversation_id="conversation-1",
            topic="follow-up topic",
            status="running",
            created_at=base_time + timedelta(minutes=2),
            updated_at=base_time + timedelta(minutes=2),
        )
        previous_workspace = ResearchWorkspace(
            task_id=previous_task.task_id,
            topic=previous_task.topic,
            papers=[
                PaperRecord(
                    paper_id="paper-a",
                    title="Paper A",
                    abstract="A richer abstract from the previous round.",
                    citation_count=70,
                    citation_count_known=True,
                    citation_source="semantic_scholar",
                )
            ],
            trace={
                "context_inputs": [
                    {
                        "kind": "query_intent",
                        "user_goal": "benchmark_evaluation",
                    }
                ]
            },
        )
        service = ResearchService(
            conversation_repository=None,
            task_repository=_TaskRepository(
                [current_task, previous_task, newer_without_workspace]
            ),
            workspace_repository=_WorkspaceRepository(
                {previous_task.task_id: previous_workspace}
            ),
        )

        context = service._previous_round_context_for_task(current_task)

        self.assertEqual(context["task_id"], previous_task.task_id)
        self.assertEqual(context["paper_ids"], ["paper-a"])
        self.assertEqual(context["papers"][0]["citation_count"], 70)
        self.assertTrue(context["papers"][0]["citation_count_known"])
        self.assertEqual(
            context["query_intent"]["user_goal"],
            "benchmark_evaluation",
        )

    def test_reused_paper_inherits_known_citation_metadata(self) -> None:
        current = PaperNode(
            paper_id="paper-a",
            title="Paper A",
            abstract="Short.",
            citation_count=0,
            citation_count_known=False,
        )
        previous = _previous_round_papers(
            {
                "previous_round_papers": [
                    {
                        "paper_id": "paper-a",
                        "title": "Paper A",
                        "abstract": "A richer abstract from the previous round.",
                        "citation_count": 70,
                        "citation_count_known": True,
                        "citation_source": "semantic_scholar",
                    }
                ]
            }
        )

        inherited = _inherit_previous_round_metadata(
            {"paper-a": current},
            previous,
        )

        self.assertEqual(inherited, 1)
        self.assertEqual(current.citation_count, 70)
        self.assertTrue(current.citation_count_known)
        self.assertEqual(current.citation_source, "semantic_scholar")
        self.assertEqual(
            current.abstract,
            "A richer abstract from the previous round.",
        )


if __name__ == "__main__":
    unittest.main()
