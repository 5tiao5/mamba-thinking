from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from product_agent.domain import ConversationWorkingMemory, ResearchTask, ResearchWorkspace
from product_agent.repositories import WorkingMemoryRepository
from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text


_KNOWLEDGE_SCOPE_LABELS = {
    "none": "no shared knowledge",
    "conversation_only": "conversation knowledge only",
    "shared": "shared knowledge enabled",
}

_GOAL_LABELS = {
    "compare": "compare evidence",
    "narrow_literature_scope": "narrow literature scope",
    "survey": "survey landscape",
    "gap_analysis": "analyze research gaps",
    "benchmark_evaluation": "focus on benchmark evaluation",
    "extend_context": "expand evidence coverage",
}


class WorkingMemoryService:
    """Maintain a lightweight, explicit conversation working memory."""

    def __init__(self, repository: WorkingMemoryRepository) -> None:
        self.repository = repository

    def get_conversation_memory(self, conversation_id: str) -> ConversationWorkingMemory | None:
        return self.repository.get(conversation_id)

    def delete_conversation_memory(self, conversation_id: str) -> bool:
        return self.repository.delete(conversation_id)

    def refresh_from_workspace(
        self,
        *,
        task: ResearchTask,
        workspace: ResearchWorkspace,
        query_intent: dict[str, Any] | None = None,
        conversation_topic: str = "",
    ) -> ConversationWorkingMemory:
        previous = self.repository.get(task.conversation_id)
        intent = self._normalize_query_intent(query_intent, workspace=workspace)
        current_focus = self._derive_current_focus(
            task=task,
            query_intent=intent,
            conversation_topic=conversation_topic,
            previous=previous,
        )
        active_constraints = self._derive_active_constraints(
            query_intent=intent,
            knowledge_scope=task.knowledge_scope,
            previous=previous,
        )
        stable_findings = self._derive_stable_findings(workspace=workspace, previous=previous)
        open_questions = self._derive_open_questions(workspace=workspace, previous=previous)
        supporting_task_ids = self._merge_items(
            [task.task_id],
            list(previous.supporting_task_ids) if previous else [],
            max_items=8,
            max_length=40,
        )
        summary = self._build_summary(
            current_focus=current_focus,
            stable_findings=stable_findings,
            open_questions=open_questions,
            active_constraints=active_constraints,
        )
        now = datetime.now(timezone.utc)
        memory = ConversationWorkingMemory(
            conversation_id=task.conversation_id,
            current_focus=current_focus,
            summary=summary,
            stable_findings=stable_findings,
            open_questions=open_questions,
            active_constraints=active_constraints,
            supporting_task_ids=supporting_task_ids,
            source_task_id=task.task_id,
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )
        return self.repository.save(memory)

    def _normalize_query_intent(
        self,
        query_intent: dict[str, Any] | None,
        *,
        workspace: ResearchWorkspace,
    ) -> dict[str, Any]:
        if isinstance(query_intent, dict) and query_intent:
            return dict(query_intent)

        trace = getattr(workspace, "trace", {}) or {}
        context_inputs = list(trace.get("context_inputs", []) or []) if isinstance(trace, dict) else []
        for entry in reversed(context_inputs):
            if isinstance(entry, dict) and str(entry.get("kind", "")).strip() == "query_intent":
                return dict(entry)
        return {}

    def _derive_current_focus(
        self,
        *,
        task: ResearchTask,
        query_intent: dict[str, Any],
        conversation_topic: str,
        previous: ConversationWorkingMemory | None,
    ) -> str:
        base_focus = clean_internal_context_text(
            str(query_intent.get("core_topic", "") or conversation_topic or task.topic),
            max_length=180,
        )
        if not base_focus and previous:
            base_focus = previous.current_focus

        qualifiers: list[str] = []
        paper_scope = clean_internal_context_items(list(query_intent.get("paper_scope", []) or []), max_length=60)
        if paper_scope:
            qualifiers.append(", ".join(paper_scope[:2]))

        time_range = query_intent.get("time_range") if isinstance(query_intent.get("time_range"), dict) else None
        time_label = clean_internal_context_text(str((time_range or {}).get("label", "") or ""), max_length=60)
        if time_label:
            qualifiers.append(time_label)

        goal_label = _GOAL_LABELS.get(str(query_intent.get("user_goal", "") or "").strip())
        if goal_label:
            qualifiers.append(goal_label)

        if qualifiers and base_focus:
            return clean_internal_context_text(f"{base_focus} | {'; '.join(qualifiers)}", max_length=220) or base_focus
        return base_focus or (previous.current_focus if previous else task.topic)

    def _derive_active_constraints(
        self,
        *,
        query_intent: dict[str, Any],
        knowledge_scope: str,
        previous: ConversationWorkingMemory | None,
    ) -> list[str]:
        current: list[str] = []
        goal = str(query_intent.get("user_goal", "") or "").strip()
        if goal and goal != "follow_up":
            label = _GOAL_LABELS.get(goal, goal.replace("_", " "))
            current.append(f"goal: {label}")

        paper_scope = clean_internal_context_items(list(query_intent.get("paper_scope", []) or []), max_length=70)
        if paper_scope:
            current.append("paper scope: " + ", ".join(paper_scope[:2]))

        time_range = query_intent.get("time_range") if isinstance(query_intent.get("time_range"), dict) else None
        time_label = clean_internal_context_text(str((time_range or {}).get("label", "") or ""), max_length=80)
        if time_label:
            current.append(f"time window: {time_label}")

        knowledge_label = _KNOWLEDGE_SCOPE_LABELS.get(knowledge_scope, "")
        if knowledge_label:
            current.append(f"knowledge scope: {knowledge_label}")

        if not current and previous:
            return list(previous.active_constraints)
        return self._merge_items(current, list(previous.active_constraints) if previous else [], max_items=6, max_length=120)

    def _derive_stable_findings(
        self,
        *,
        workspace: ResearchWorkspace,
        previous: ConversationWorkingMemory | None,
    ) -> list[str]:
        findings: list[str] = []
        summary_payload = getattr(workspace, "summary_payload", {}) or {}
        headline = clean_internal_context_text(str(summary_payload.get("headline", "") or ""), max_length=140)
        if headline and not self._looks_like_generic_headline(headline, workspace.topic):
            findings.append(headline)

        taxonomy = getattr(workspace, "taxonomy", {}) or {}
        branches = list(taxonomy.get("branches", []) or [])
        ranked_branches = sorted(
            branches,
            key=lambda item: int(item.get("paper_count", 0) or 0),
            reverse=True,
        )
        for branch in ranked_branches:
            name = clean_internal_context_text(str(branch.get("name", "") or ""), max_length=90)
            paper_count = int(branch.get("paper_count", 0) or 0)
            if name and paper_count > 0:
                findings.append(f"Evidence cluster: {name} ({paper_count} papers)")
            if len(findings) >= 3:
                break

        if not findings:
            for paper in list(getattr(workspace, "papers", []) or [])[:2]:
                title = clean_internal_context_text(str(getattr(paper, "title", "") or ""), max_length=120)
                if title:
                    findings.append(f"Representative evidence: {title}")

        return self._merge_items(findings, list(previous.stable_findings) if previous else [], max_items=6, max_length=160)

    def _derive_open_questions(
        self,
        *,
        workspace: ResearchWorkspace,
        previous: ConversationWorkingMemory | None,
    ) -> list[str]:
        current_questions = [
            clean_internal_context_text(str(getattr(gap, "summary", "") or ""), max_length=180)
            for gap in list(getattr(workspace, "gaps", []) or [])[:3]
        ]
        current_questions = [item for item in current_questions if item]
        if not current_questions and previous:
            return list(previous.open_questions)
        return self._merge_items(current_questions, list(previous.open_questions) if previous else [], max_items=6, max_length=180)

    def _build_summary(
        self,
        *,
        current_focus: str,
        stable_findings: list[str],
        open_questions: list[str],
        active_constraints: list[str],
    ) -> str:
        parts: list[str] = []
        if current_focus:
            parts.append(f"Current focus: {current_focus}.")
        if stable_findings:
            parts.append("Stable findings: " + "; ".join(stable_findings[:2]) + ".")
        if open_questions:
            parts.append("Open questions: " + "; ".join(open_questions[:2]) + ".")
        if active_constraints:
            parts.append("Active constraints: " + "; ".join(active_constraints[:2]) + ".")
        return clean_internal_context_text(" ".join(parts), max_length=480)

    @staticmethod
    def _merge_items(
        primary: list[str],
        secondary: list[str],
        *,
        max_items: int,
        max_length: int,
    ) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for value in [*primary, *secondary]:
            clean_value = clean_internal_context_text(str(value or ""), max_length=max_length)
            if not clean_value:
                continue
            key = clean_value.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(clean_value)
            if len(merged) >= max_items:
                break
        return merged

    @staticmethod
    def _looks_like_generic_headline(headline: str, topic: str) -> bool:
        clean_headline = " ".join((headline or "").split()).strip().casefold()
        clean_topic = " ".join((topic or "").split()).strip().casefold()
        if not clean_headline:
            return True
        generic_suffixes = ("research audit overview", "研究审计概览", "研究概览", "overview")
        if clean_topic and clean_headline.startswith(clean_topic) and any(
            clean_headline.endswith(suffix.casefold()) for suffix in generic_suffixes
        ):
            return True
        return False
