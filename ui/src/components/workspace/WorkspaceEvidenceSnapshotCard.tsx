import type { WorkspaceEvidenceSnapshot } from "../../types/api";
import { StatusPill } from "../ui/StatusPill";

type WorkspaceEvidenceSnapshotCardProps = {
  snapshot?: WorkspaceEvidenceSnapshot | null;
};

function numberStat(snapshot: WorkspaceEvidenceSnapshot, key: string) {
  const value = snapshot.stats[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function recordStat(snapshot: WorkspaceEvidenceSnapshot, key: string) {
  const value = snapshot.stats[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function formatSnapshotTime(value: string) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function retrievalOutcomeText(snapshot: WorkspaceEvidenceSnapshot) {
  const outcome = snapshot.retrieval_outcome;
  const status = typeof outcome.status === "string" ? outcome.status : "";
  const message = typeof outcome.message === "string" ? outcome.message : "";
  const novelCount =
    typeof outcome.novel_paper_count === "number" ? outcome.novel_paper_count : undefined;

  if (message) return message;
  if (typeof novelCount === "number") return `本轮补入 ${novelCount} 篇新论文`;
  if (status) return status;
  return "未记录独立检索说明";
}

export function WorkspaceEvidenceSnapshotCard({
  snapshot,
}: WorkspaceEvidenceSnapshotCardProps) {
  if (!snapshot) return null;

  const paperCount = numberStat(snapshot, "paper_count");
  const realPaperCount = numberStat(snapshot, "real_paper_count");
  const newPaperCount = numberStat(snapshot, "new_paper_count");
  const groundedBranchCount = numberStat(snapshot, "grounded_taxonomy_branch_count");
  const evidenceLevels = recordStat(snapshot, "evidence_level_counts");
  const confirmedEdges =
    (typeof evidenceLevels.confirmed === "number" ? evidenceLevels.confirmed : 0) +
    (typeof evidenceLevels.supported === "number" ? evidenceLevels.supported : 0);
  const candidateEdges =
    (typeof evidenceLevels.inferred === "number" ? evidenceLevels.inferred : 0) +
    (typeof evidenceLevels.candidate === "number" ? evidenceLevels.candidate : 0);

  return (
    <details className="workspace-snapshot-card">
      <summary>
        <div className="workspace-snapshot-heading">
          <div>
            <span className="workspace-note-label">本轮证据快照</span>
            <strong>
              基于 {paperCount} 篇论文、{groundedBranchCount} 个有论文支撑的方向生成
            </strong>
          </div>
          <div className="workspace-snapshot-summary-pills">
            <StatusPill compact tone="success">
              已冻结
            </StatusPill>
            {newPaperCount > 0 ? (
              <StatusPill compact tone="info">
                新增 {newPaperCount} 篇
              </StatusPill>
            ) : null}
          </div>
        </div>
        <span className="workspace-snapshot-toggle">查看证据口径</span>
      </summary>

      <div className="workspace-snapshot-body">
        <div className="workspace-snapshot-metrics">
          <div>
            <span>真实论文</span>
            <strong>{realPaperCount}</strong>
          </div>
          <div>
            <span>新增论文</span>
            <strong>{newPaperCount}</strong>
          </div>
          <div>
            <span>确认 / 支持关系</span>
            <strong>{confirmedEdges}</strong>
          </div>
          <div>
            <span>推断 / 候选关系</span>
            <strong>{candidateEdges}</strong>
          </div>
        </div>

        <div className="workspace-snapshot-provenance">
          <div>
            <span>快照 ID</span>
            <code title={snapshot.snapshot_id}>{snapshot.snapshot_id}</code>
          </div>
          <div>
            <span>冻结时间</span>
            <strong>{formatSnapshotTime(snapshot.created_at)}</strong>
          </div>
          <div>
            <span>检索结果</span>
            <strong>{retrievalOutcomeText(snapshot)}</strong>
          </div>
          <div>
            <span>证据对齐分</span>
            <strong>{snapshot.alignment_score.toFixed(3)}</strong>
          </div>
        </div>

        <p className="workspace-snapshot-note">
          本轮研究建议、报告与摘要均从这一份冻结证据生成。后续补搜会形成新的快照，不会静默改写本轮依据。
        </p>
      </div>
    </details>
  );
}
