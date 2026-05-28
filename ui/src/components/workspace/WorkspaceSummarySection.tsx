import type { WorkspaceEvidenceStatus } from "../../types/api";
import { cleanDisplayText } from "../../lib/displayText";
import { StatusPill } from "../ui/StatusPill";

type WorkspaceSummarySectionProps = {
  topic?: string;
  paperCount: number;
  gapCount: number;
  ideaCount: number;
  alignmentScore: number;
  summary?: string;
  priorityNote?: string;
  recommendation?: string;
  usesFallbackPapers: boolean;
  evidenceStatus?: WorkspaceEvidenceStatus;
};

function formatScore(score: number) {
  if (Number.isNaN(score)) {
    return "0.00";
  }
  return score.toFixed(3);
}

function cleanSummaryText(summary: string) {
  return cleanDisplayText(summary)
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*/g, "")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .trim();
}

export function WorkspaceSummarySection({
  topic,
  paperCount,
  gapCount,
  ideaCount,
  alignmentScore,
  summary,
  priorityNote,
  recommendation,
  usesFallbackPapers,
  evidenceStatus,
}: WorkspaceSummarySectionProps) {
  const isEvidenceInsufficient = evidenceStatus?.insufficient;

  return (
    <section className="workspace-hero surface">
      <div className="workspace-hero-main">
        <div className="section-eyebrow">研究概览</div>
        <h1 className="workspace-hero-title">{cleanDisplayText(topic, 160) || "研究主题"}</h1>
        <div className="workspace-hero-summary">
          {summary ? cleanSummaryText(summary) : "运行任务后，这里会汇总本轮分析的核心结论。"}
        </div>

        {priorityNote || recommendation ? (
          <div className="workspace-hero-notes">
            {priorityNote ? (
              <div className="workspace-note-card">
                <div className="workspace-note-label">优先关注</div>
                <div>{cleanDisplayText(priorityNote)}</div>
              </div>
            ) : null}
            {recommendation ? (
              <div className="workspace-note-card workspace-note-card-accent">
                <div className="workspace-note-label">建议动作</div>
                <div>{cleanDisplayText(recommendation)}</div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="workspace-hero-side">
        <div className="workspace-kpi-card">
          <span>论文线索</span>
          <strong>{paperCount}</strong>
        </div>
        <div className="workspace-kpi-card">
          <span>研究空白</span>
          <strong>{gapCount}</strong>
        </div>
        <div className="workspace-kpi-card">
          <span>研究建议</span>
          <strong>{ideaCount}</strong>
        </div>
        <div className="workspace-kpi-card">
          <span>匹配度</span>
          <strong>{formatScore(alignmentScore)}</strong>
        </div>
      </div>

      {isEvidenceInsufficient ? (
        <div className="workspace-fallback-banner workspace-fallback-banner-evidence">
          <StatusPill compact tone="warning">
            证据不足模式
          </StatusPill>
          <span>
            {cleanDisplayText(evidenceStatus?.message)}
            {evidenceStatus?.candidate_branches?.length
              ? ` 候选方向：${evidenceStatus.candidate_branches.map((item) => cleanDisplayText(item, 80)).filter(Boolean).join(" / ")}。`
              : ""}
          </span>
        </div>
      ) : usesFallbackPapers ? (
        <div className="workspace-fallback-banner">
          <StatusPill compact tone="warning">
            系统回退
          </StatusPill>
          <span>
            当前结果包含保底论文，说明外部检索证据不足。系统先用种子论文维持方向与空白分析，后续仍建议继续补充真实论文。
          </span>
        </div>
      ) : null}

      {evidenceStatus ? (
        <div className="workspace-evidence-detail">
          <div>
            <span>真实论文</span>
            <strong>{evidenceStatus.real_paper_count}</strong>
          </div>
          <div>
            <span>回退论文</span>
            <strong>{evidenceStatus.fallback_paper_count}</strong>
          </div>
          <div>
            <span>回退比例</span>
            <strong>{Math.round(evidenceStatus.fallback_ratio * 100)}%</strong>
          </div>
          <div>
            <span>覆盖分支</span>
            <strong>{evidenceStatus.covered_branch_count}</strong>
          </div>
        </div>
      ) : null}
    </section>
  );
}
