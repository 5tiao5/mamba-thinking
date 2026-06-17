from __future__ import annotations

from fastapi.testclient import TestClient

from product_agent.app_container import AppContainer
from product_agent.api.handlers import ProductApiHandlers
from product_agent.api.fastapi_app import create_app
from product_agent.api.response import ok


def test_create_task_records_initial_event() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="event test")

    task = container.research_service.create_task(
        conversation_id=conversation.conversation_id,
        topic="event test",
        mode="balanced",
        knowledge_scope="conversation_only",
        research_mode="hybrid",
    )

    events = container.research_service.list_task_events(task.task_id)

    assert len(events) == 1
    assert events[0].stage == "task"
    assert events[0].status == "created"
    assert events[0].payload["mode"] == "balanced"


def test_state_callback_records_pipeline_stage_events() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="event test")
    task = container.research_service.create_task(
        conversation_id=conversation.conversation_id,
        topic="event test",
    )

    recorder = container.research_service._build_state_event_recorder(task.task_id)
    recorder(
        {
            "logs": ["Action started: planner"],
            "next_action": "planner",
            "current_goal": "Plan subgoals and search strategy.",
            "pending_actions": ["searcher"],
            "paper_nodes": {},
            "evidence_pool": {},
        }
    )
    recorder(
        {
            "logs": [
                "Action started: planner",
                "Action planner complete: {'papers': 0, 'evidence_pool': 0}",
            ],
            "next_action": "planner",
            "current_goal": "Plan subgoals and search strategy.",
            "pending_actions": ["searcher"],
            "paper_nodes": {},
            "evidence_pool": {},
        }
    )

    events = container.research_service.list_task_events(task.task_id)
    stage_events = [(event.stage, event.status) for event in events]

    assert ("planner", "started") in stage_events
    assert ("planner", "completed") in stage_events


def test_task_events_api_returns_ordered_events() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="event test")
    task = container.research_service.create_task(
        conversation_id=conversation.conversation_id,
        topic="event test",
    )
    container.research_service._append_task_event(
        task_id=task.task_id,
        stage="runtime",
        status="started",
        message="Research task started.",
    )

    client = TestClient(create_app(container))
    response = client.get(f"/research/tasks/{task.task_id}/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert [item["sequence"] for item in payload["data"]["items"]] == [1, 2]
    assert payload["data"]["items"][1]["stage"] == "runtime"


def test_continue_conversation_schedules_follow_up_run(monkeypatch) -> None:
    scheduled_task_ids: list[str] = []

    def fake_run_research_task(self, task_id: str):
        scheduled_task_ids.append(task_id)
        return ok({"task_id": task_id, "task_status": "completed"})

    monkeypatch.setattr(ProductApiHandlers, "run_research_task", fake_run_research_task)

    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="agent progress test")
    client = TestClient(create_app(container))

    response = client.post(
        "/conversations/continue",
        json={
            "conversation_id": conversation.conversation_id,
            "content": "补充近三年的新论文",
            "create_follow_up_task": True,
            "run_follow_up_task": True,
            "knowledge_scope": "conversation_only",
            "research_mode": "search_only",
        },
    )

    payload = response.json()
    task_id = payload["data"]["follow_up_task"]["task_id"]

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["follow_up_run_scheduled"] is True
    assert scheduled_task_ids == [task_id]
