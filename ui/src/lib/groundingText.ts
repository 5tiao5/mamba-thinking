import { cleanDisplayText } from "./displayText";
import type { StatusTone } from "./productText";
import type { KnowledgeScope, WorkspaceSourceTrace } from "../types/api";

const goalLabelMap: Record<string, string> = {
  compare: "对比不同方案",
  narrow_literature_scope: "收缩文献范围",
  survey: "做领域综述",
  gap_analysis: "识别研究空白",
  benchmark_evaluation: "聚焦评测与基准",
  extend_context: "扩展现有研究脉络",
  follow_up: "延续当前追问",
};

export function knowledgeScopeLabel(scope?: KnowledgeScope) {
  switch (scope) {
    case "none":
      return "未启用知识增强";
    case "conversation_only":
      return "仅当前会话知识";
    case "shared":
      return "共享知识已启用";
    default:
      return "知识范围未标注";
  }
}

export function knowledgeScopeTone(scope?: KnowledgeScope): StatusTone {
  if (scope === "none") {
    return "warning";
  }
  if (scope === "conversation_only") {
    return "neutral";
  }
  return "info";
}

export function retrievalStatusLabel(status?: string) {
  switch (status) {
    case "constrained_fallback_background":
      return "严格约束未命中";
    case "partial_constrained_results":
      return "约束内结果偏少";
    case "constraint_preserved":
      return "已过滤越界结果";
    case "fresh_evidence_added":
      return "已补入新增论文";
    case "refresh_reused_only":
      return "已尝试刷新证据";
    case "fallback_only":
      return "仅背景参考";
    case "normal":
      return "检索策略已对齐";
    default:
      return "";
  }
}

export function retrievalStatusTone(status?: string): StatusTone {
  switch (status) {
    case "constrained_fallback_background":
      return "danger";
    case "partial_constrained_results":
    case "fallback_only":
      return "warning";
    case "constraint_preserved":
    case "fresh_evidence_added":
      return "info";
    case "refresh_reused_only":
      return "neutral";
    default:
      return "neutral";
  }
}

function goalLabel(goal: string) {
  const normalized = goal.trim().toLowerCase();
  return goalLabelMap[normalized] ?? normalized.replace(/_/g, " ");
}

function formatYears(value: string) {
  const [start = "*", end = "*"] = value.split("-", 2);
  const left = start === "*" ? "不限起点" : start;
  const right = end === "*" ? "不限终点" : end;
  return `${left} - ${right}`;
}

function localizePlanPart(part: string) {
  const [rawKey, ...rest] = part.split("=");
  const key = rawKey.trim();
  const value = rest.join("=").trim();
  if (!key) {
    return "";
  }
  if (!value) {
    return cleanDisplayText(part, 120);
  }

  switch (key) {
    case "goal":
      return `目标：${goalLabel(value)}`;
    case "years":
      return `年份：${formatYears(value)}`;
    case "signals":
      return `排序信号：${value.split(",").map((item) => item.trim()).filter(Boolean).join(" / ")}`;
    default:
      return cleanDisplayText(part, 120);
  }
}

export function formatRetrievalPlan(plan?: string, maxLength = 180) {
  const text = cleanDisplayText(plan ?? "", maxLength * 2);
  if (!text) {
    return "";
  }

  const localized = text
    .split(";")
    .map((item) => localizePlanPart(item.trim()))
    .filter(Boolean);

  if (!localized.length) {
    return cleanDisplayText(text, maxLength);
  }

  return cleanDisplayText(localized.join(" · "), maxLength);
}

export function formatRetrievalMessage(
  sourceTrace?: WorkspaceSourceTrace | null,
  maxLength = 220
) {
  const filteredOutCount = sourceTrace?.filtered_out_count ?? 0;
  const novelPaperCount = sourceTrace?.novel_paper_count ?? 0;
  const reusedPaperCount = sourceTrace?.reused_paper_count ?? 0;

  switch (sourceTrace?.retrieval_status) {
    case "constrained_fallback_background":
      return "这轮保留了强约束，但没有命中符合条件的真实论文；当前 fallback 仅作为背景参考。";
    case "partial_constrained_results":
      return "这轮只保留了少量符合约束的真实论文，系统没有再用越界论文把结果凑满。";
    case "constraint_preserved":
      return filteredOutCount > 0
        ? `系统过滤了 ${filteredOutCount} 条越界结果，保留下来的论文更贴近当前问题。`
        : "系统已过滤越界结果，并优先保留更贴近当前问题的论文。";
    case "fresh_evidence_added":
      return novelPaperCount > 0
        ? `系统已按当前追问重新检索，并补入 ${novelPaperCount} 篇本轮新增论文${reusedPaperCount > 0 ? `，同时保留 ${reusedPaperCount} 篇仍然高相关的旧证据` : ""}。`
        : "系统已按当前追问重新检索，并补入了新的高相关论文。";
    case "refresh_reused_only":
      return "系统已经按新的范围重新检索过了，但高相关结果仍与上一轮重合，暂时没有更合适的新论文。";
    case "fallback_only":
      return "检索工具暂时没有拿到可用证据，当前只展示背景参考材料。";
    case "normal":
      return "当前检索结果足以支撑后续分析。";
    default:
      return cleanDisplayText(sourceTrace?.retrieval_message ?? "", maxLength);
  }
}

export function shouldHighlightRetrievalStatus(status?: string) {
  return (
    status === "constrained_fallback_background" ||
    status === "partial_constrained_results" ||
    status === "fallback_only"
  );
}
