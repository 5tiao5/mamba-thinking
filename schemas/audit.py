from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional


def _make_gap_id(gap_type: str, affected_items: List[str]) -> str:
    """生成稳定的 gap id，基于类型和排序后的受影响项"""
    sorted_items = sorted(set(affected_items))
    key = f"{gap_type}:{':'.join(sorted_items)}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


@dataclass
class AuditReport:
    """结构化审计报告"""
    type: str  # taxonomy, graph, llm
    severity: str  # info, warning, error
    description: str
    affected_items: List[str]  # paper_id, edge, branch 等
    suggestion: Optional[str] = None
    related_gap_ids: List[str] = field(default_factory=list)  # 关联的 gap id

    def to_dict(self) -> dict:
        """显式序列化为 dict，控制 API contract"""
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "affected_items": self.affected_items,
            "suggestion": self.suggestion,
            "related_gap_ids": self.related_gap_ids,
        }


@dataclass
class AuditGap:
    """结构化审计 gap"""
    type: str  # taxonomy, graph, llm
    severity: str  # info, warning, error
    description: str
    affected_items: List[str]
    actionable: bool = False  # 是否可直接修复
    related_papers: List[str] = field(default_factory=list)  # 相关 paper_id
    suggestion: Optional[str] = None
    id: str = None  # 稳定标识符，用于去重和追踪
    confidence: Optional[float] = None  # 置信度（特别用于 LLM gap）

    def __post_init__(self):
        # 如果未设置 id，自动生成
        if self.id is None:
            self.id = _make_gap_id(self.type, self.affected_items)

    def to_dict(self) -> dict:
        """显式序列化为 dict，控制 API contract"""
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "affected_items": self.affected_items,
            "actionable": self.actionable,
            "related_papers": self.related_papers,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class AuditResult:
    """审计结果"""
    score: float
    reports: List[AuditReport]
    gaps: List[AuditGap]


@dataclass
class AuditSummary:
    """审计结果摘要（给前端仪表盘）"""
    score: float
    gap_count: int
    report_count: int
    severity_distribution: dict  # {"error": 2, "warning": 5, "info": 1}
    actionable_gap_count: int
    gap_types: dict  # {"taxonomy": 3, "graph": 2, "llm": 1}

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "gap_count": self.gap_count,
            "report_count": self.report_count,
            "severity_distribution": self.severity_distribution,
            "actionable_gap_count": self.actionable_gap_count,
            "gap_types": self.gap_types,
        }