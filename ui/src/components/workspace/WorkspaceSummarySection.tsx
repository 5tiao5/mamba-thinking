import type { WorkspaceEvidenceStatus } from "../../types/api";
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
  return summary
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
        <div className="section-eyebrow">Research Overview</div>
        <h1 className="workspace-hero-title">{topic || "未加载研究主题"}</h1>
        <div className="workspace-hero-summary">
          {summary ? cleanSummaryText(summary) : "运行任务后，这里会汇总本轮分析的核心结论。"}
        </div>

        {priorityNote || recommendation ? (
          <div className="workspace-hero-notes">
            {priorityNote ? (
              <div className="workspace-note-card">
                <div className="workspace-note-label">优先关注</div>
                <div>{priorityNote}</div>
              </div>
            ) : null}
            {recommendation ? (
              <div className="workspace-note-card workspace-note-card-accent">
                <div className="workspace-note-label">建议动作</div>
                <div>{recommendation}</div>
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
            {evidenceStatus?.message}
            {evidenceStatus?.candidate_branches?.length
              ? ` 当前更适合把 ${evidenceStatus.candidate_branches.join(" / ")} 当作候选研究分支，而不是直接展示完整 taxonomy。`
              : ""}
          </span>
        </div>
      ) : usesFallbackPapers ? (
        <div className="workspace-fallback-banner">
          <StatusPill compact tone="warning">
            系统回退
          </StatusPill>
          <span>
            当前结果包含保底论文，说明外部检索证据不足。系统先用种子论文维持
            taxonomy 与 gap 分析链路，后续仍建议继续补充真实论文。
          </span>
        </div>
      ) : null}
    </section>
  );
}
