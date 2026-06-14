import { SectionHeader } from "../ui/SectionHeader";
import { cleanDisplayText } from "../../lib/displayText";
import type { WorkspacePaper } from "../../types/api";

type WorkspaceEvidenceBoardProps = {
  papers: WorkspacePaper[];
  totalPaperCount: number;
  analysisPaperCount: number;
  viewMode: "analysis" | "extended";
  onViewModeChange: (mode: "analysis" | "extended") => void;
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
  showRoundMarkers?: boolean;
};

function sourceLabel(source: string) {
  const normalized = (source || "").toLowerCase();
  if (normalized === "fallback") return "系统回退";
  if (normalized === "user_upload") return "用户上传 PDF";
  if (normalized === "user_import") return "用户导入";
  if (normalized === "arxiv") return "ArXiv";
  if (normalized === "semantic_scholar") return "Semantic Scholar";
  return source || "未知";
}

function evidenceOriginLabel(paper: WorkspacePaper) {
  const origin = (paper.origin || paper.source || "").toLowerCase();
  if (origin === "user_upload") return "用户上传";
  if (origin === "user_import") return "用户导入";
  if (origin === "system_search" || origin === "arxiv" || origin === "semantic_scholar") {
    return "系统检索";
  }
  if (paper.source === "fallback") return "系统回退";
  return "系统检索";
}

function poolStatusLabel(paper: WorkspacePaper) {
  if (paper.paper_pool_status === "core") return "用户指定核心";
  if (paper.paper_pool_status === "candidate") return "导入候选";
  return "";
}

function PaperBadges({ paper, showRoundMarkers }: { paper: WorkspacePaper; showRoundMarkers?: boolean }) {
  const poolLabel = poolStatusLabel(paper);
  return (
    <span className="workspace-paper-badges">
      <span className="message-source-trace-chip">{evidenceOriginLabel(paper)}</span>
      {poolLabel ? (
        <span className="message-source-trace-chip message-source-trace-chip-info">{poolLabel}</span>
      ) : null}
      {showRoundMarkers ? (
        <span className={`message-source-trace-chip ${noveltyToneClass(paper)}`}>{noveltyLabel(paper)}</span>
      ) : null}
    </span>
  );
}

function noveltyLabel(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "本轮新增" : "沿用证据";
}

function noveltyToneClass(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "message-source-trace-chip-info" : "";
}

function citationLabel(paper: WorkspacePaper) {
  return paper.citation_count_known ? String(paper.citation_count) : "未获取";
}

function PaperInspector({ paper, showRoundMarkers }: { paper?: WorkspacePaper; showRoundMarkers?: boolean }) {
  if (!paper) {
    return <div className="empty-state">选择一篇论文后，这里会显示来源、年份、分类和外链。</div>;
  }

  return (
    <div className="content-grid">
      <div>
        <div className="section-eyebrow">当前选中</div>
        <div className="workspace-paper-title-row">
          <div className="insight-title">{cleanDisplayText(paper.title, 180)}</div>
          <PaperBadges paper={paper} showRoundMarkers={showRoundMarkers} />
        </div>
      </div>
      <div className="workspace-paper-meta-grid">
        <div className="workspace-paper-meta-item">
          <span>来源</span>
          <strong>{sourceLabel(paper.source)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>证据身份</span>
          <strong>{poolStatusLabel(paper) || evidenceOriginLabel(paper)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>年份</span>
          <strong>{paper.publish_date || "-"}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>引用</span>
          <strong>{citationLabel(paper)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>分类</span>
          <strong>{cleanDisplayText(paper.taxonomy_category, 80) || "未分类"}</strong>
        </div>
        {showRoundMarkers ? (
          <div className="workspace-paper-meta-item">
            <span>轮次</span>
            <strong>{noveltyLabel(paper)}</strong>
          </div>
        ) : null}
      </div>
      {paper.url ? (
        <a className="secondary-button" href={paper.url} rel="noreferrer" target="_blank">
          打开论文来源
        </a>
      ) : null}
    </div>
  );
}

export function WorkspaceEvidenceBoard({
  papers,
  totalPaperCount,
  analysisPaperCount,
  viewMode,
  onViewModeChange,
  selectedPaperId,
  onSelectPaper,
  showRoundMarkers = false,
}: WorkspaceEvidenceBoardProps) {
  const selectedPaper = papers.find((paper) => paper.paper_id === selectedPaperId) ?? papers[0];
  const novelPaperCount = papers.filter((paper) => paper.is_new_this_round).length;
  const visibleLabel = viewMode === "analysis" ? "核心分析论文" : "扩展证据库";
  const eyebrow =
    showRoundMarkers && papers.length
      ? `${visibleLabel} ${papers.length} 篇 · 新增 ${novelPaperCount} 篇`
      : `${visibleLabel} ${papers.length} 篇`;

  return (
    <section className="workspace-main-column">
      <section className="pane">
        <SectionHeader
          actions={
            <div className="workspace-evidence-switch" role="tablist" aria-label="论文证据范围">
              <button
                className={viewMode === "analysis" ? "workspace-evidence-switch-active" : ""}
                onClick={() => onViewModeChange("analysis")}
                type="button"
              >
                核心分析 {analysisPaperCount}
              </button>
              <button
                className={viewMode === "extended" ? "workspace-evidence-switch-active" : ""}
                onClick={() => onViewModeChange("extended")}
                type="button"
              >
                扩展证据 {totalPaperCount}
              </button>
            </div>
          }
          eyebrow={eyebrow}
          title="论文证据"
        />
        <div className="workspace-evidence-scope-note">
          {viewMode === "analysis"
            ? "这些论文参与了本轮 taxonomy、研究关系图谱、研究空白与结论生成。"
            : "这里展示本轮检索到的全部合格论文；未进入核心集的论文用于补充阅读，不直接支撑主要结论。"}
        </div>
        <div className="data-table-wrap pane-scroll">
          {papers.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>论文</th>
                  <th>来源</th>
                  <th>年份</th>
                  <th>分类</th>
                  <th>引用</th>
                  <th>外链</th>
                </tr>
              </thead>
              <tbody>
                {papers.map((paper) => (
                  <tr
                    className={selectedPaper?.paper_id === paper.paper_id ? "selected-row" : ""}
                    key={paper.paper_id}
                    onClick={() => onSelectPaper(paper.paper_id)}
                    >
                      <td>
                        <div className="workspace-paper-title-row">
                          <div className="table-title">{cleanDisplayText(paper.title, 180)}</div>
                          <PaperBadges paper={paper} showRoundMarkers={showRoundMarkers} />
                        </div>
                      </td>
                    <td>
                      <div className="workspace-paper-source-cell">
                        <strong>{sourceLabel(paper.source)}</strong>
                        <span>{evidenceOriginLabel(paper)}</span>
                      </div>
                    </td>
                    <td>{paper.publish_date || "-"}</td>
                    <td>{cleanDisplayText(paper.taxonomy_category, 80) || "未分类"}</td>
                    <td>{citationLabel(paper)}</td>
                    <td>
                      {paper.url ? (
                        <a className="inline-link" href={paper.url} rel="noreferrer" target="_blank">
                          来源
                        </a>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="content-pad">
              <div className="empty-state">暂无论文数据。请先运行任务或检查当前任务是否已有工作台结果。</div>
            </div>
          )}
        </div>
      </section>

      <section className="pane">
        <SectionHeader eyebrow="证据摘要" title="论文详情" />
        <div className="content-pad">
          <PaperInspector paper={selectedPaper} showRoundMarkers={showRoundMarkers} />
        </div>
      </section>
    </section>
  );
}
