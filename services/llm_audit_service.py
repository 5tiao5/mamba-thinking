from __future__ import annotations

import os
from typing import Dict, List

from llm_client import call_openai_json

from product_agent.research_agent.models import EvolutionEdge, PaperNode
from product_agent.schemas.audit import AuditGap, AuditReport, AuditResult


class LLMAuditService:
    """LLM 辅助审计服务"""

    def audit(
        self, papers: Dict[str, PaperNode], edges: List[EvolutionEdge]
    ) -> AuditResult:
        if os.environ.get("SKIP_AUDITOR_LLM") == "1":
            return AuditResult(
                score=1.0,  # 跳过时视为通过
                reports=[
                    AuditReport(
                        type="llm",
                        severity="info",
                        description="已按环境变量配置跳过 LLM 关系审计。",
                        affected_items=[],
                        suggestion="如需更细的语义审计，可重新开启 LLM 审计。",
                    )
                ],
                gaps=[],
            )

        improves_edges = [edge for edge in edges if edge.relationship.lower() in {"improves", "extends", "solves"}]
        if not improves_edges:
            return AuditResult(
                score=1.0,
                reports=[
                    AuditReport(
                        type="llm",
                        severity="info",
                        description="当前没有需要做 LLM 语义审计的“改进类”关系边。",
                        affected_items=[],
                    )
                ],
                gaps=[],
            )

        payload = []
        for edge in improves_edges[:5]:
            source = papers.get(edge.source)
            target = papers.get(edge.target)
            if source and target:
                payload.append(
                    {
                        "source_id": edge.source,
                        "source_title": source.title,
                        "source_abstract": source.abstract[:1200],
                        "target_id": edge.target,
                        "target_title": target.title,
                        "target_abstract": target.abstract[:1200],
                        "relationship": edge.relationship,
                    }
                )

        if not payload:
            return AuditResult(
                score=0.5,
                reports=[
                    AuditReport(
                        type="llm",
                        severity="warning",
                        description="当前没有可用于 LLM 审计的有效关系边。",
                        affected_items=[],
                        suggestion="请先检查关系边数据是否完整。",
                    )
                ],
                gaps=[],
            )

        data = call_openai_json(
            (
                "Audit whether the following paper evolution edges are actually supported by semantic evidence. "
                "Return JSON STRICTLY in this format with NO variations:\n"
                '{"items":[{"source":"A","target":"B","supported":true,"confidence":0.85,"reason":"...","gap_type":"unsupported_edge"}]}\n'
                "gap_type must be one of: unsupported_edge, weak_evidence, semantic_mismatch\n"
                f"{payload}"
            ),
            system=(
                "You are a research-logic auditor. Judge whether the target abstract truly supports the claimed "
                "relationship to the source paper. Return ONLY valid JSON, no markdown or extra text. "
                "Use standardized gap_type values: unsupported_edge, weak_evidence, semantic_mismatch. "
                "Provide confidence as float 0-1."
            ),
            max_output_tokens=1600,
        )
        if not data or not isinstance(data.get("items"), list):
            return AuditResult(
                score=0.5,
                reports=[
                    AuditReport(
                        type="llm",
                        severity="error",
                        description="LLM 关系审计未返回有效结果。",
                        affected_items=[],
                        suggestion="可以重试一次，或退回规则审计结果。",
                    )
                ],
                gaps=[],
            )

        reports: List[AuditReport] = []
        gaps: List[AuditGap] = []
        supported_count = 0
        for item in data["items"]:
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            reason = str(item.get("reason", "")).strip()
            supported = bool(item.get("supported", False))
            confidence = float(item.get("confidence", 0.5))
            gap_type_suffix = str(item.get("gap_type", "unsupported_edge")).lower()
            
            if not source or not target:
                continue
            
            affected_items = [source, target]
            edge_desc = f"{source} -> {target}"
            
            if supported:
                supported_count += 1
            
            if reason:
                reports.append(
                    AuditReport(
                        type="llm",
                        severity="info" if supported else "warning",
                        description=f"LLM 对关系 {edge_desc} 的判断：{reason}",
                        affected_items=affected_items,
                    )
                )
            
            if not supported:
                # 使用结构化的 gap 类型而非自由文本
                gap_type = f"llm:{gap_type_suffix}"  # e.g., "llm:unsupported_edge"
                gaps.append(
                    AuditGap(
                        type=gap_type,
                        severity="warning",
                        description=f"LLM 判断关系 {edge_desc} 存在问题：{gap_type_suffix.replace('_', ' ')}。",
                        affected_items=affected_items,
                        actionable=True,
                        related_papers=affected_items,
                        suggestion="请复核这条关系，必要时删除或调整关系类型。",
                        confidence=confidence,
                    )
                )

        score = supported_count / len(data["items"]) if data["items"] else 0.5
        return AuditResult(
            score=score,
            reports=reports,
            gaps=gaps,
        )
