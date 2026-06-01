import { SectionHeader } from "../ui/SectionHeader";
import { cleanDisplayText } from "../../lib/displayText";
import type { WorkspacePaper } from "../../types/api";

type WorkspaceEvidenceBoardProps = {
  papers: WorkspacePaper[];
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
  showRoundMarkers?: boolean;
};

function sourceLabel(source: string) {
  const normalized = (source || "").toLowerCase();
  if (normalized === "fallback") return "系统回退";
  if (normalized === "arxiv") return "ArXiv";
  if (normalized === "semantic_scholar") return "Semantic Scholar";
  return source || "未知";
}

function noveltyLabel(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "本轮新增" : "沿用证据";
}

function noveltyToneClass(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "message-source-trace-chip-info" : "";
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
          {showRoundMarkers ? (
            <span className={`message-source-trace-chip ${noveltyToneClass(paper)}`}>{noveltyLabel(paper)}</span>
          ) : null}
        </div>
      </div>
      <div className="workspace-paper-meta-grid">
        <div className="workspace-paper-meta-item">
          <span>来源</span>
          <strong>{sourceLabel(paper.source)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>年份</span>
          <strong>{paper.publish_date || "-"}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>引用</span>
          <strong>{paper.citation_count}</strong>
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
  selectedPaperId,
  onSelectPaper,
  showRoundMarkers = false,
}: WorkspaceEvidenceBoardProps) {
  const selectedPaper = papers.find((paper) => paper.paper_id === selectedPaperId) ?? papers[0];
  const novelPaperCount = papers.filter((paper) => paper.is_new_this_round).length;
  const eyebrow =
    showRoundMarkers && papers.length
      ? `${papers.length} 篇可见 · 新增 ${novelPaperCount} 篇`
      : `${papers.length} 篇可见`;

  return (
    <section className="workspace-main-column">
      <section className="pane">
        <SectionHeader eyebrow={eyebrow} title="论文线索" />
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
                          {showRoundMarkers ? (
                            <span className={`message-source-trace-chip ${noveltyToneClass(paper)}`}>{noveltyLabel(paper)}</span>
                          ) : null}
                        </div>
                      </td>
                    <td>{sourceLabel(paper.source)}</td>
                    <td>{paper.publish_date || "-"}</td>
                    <td>{cleanDisplayText(paper.taxonomy_category, 80) || "未分类"}</td>
                    <td>{paper.citation_count}</td>
                    <td>
                      {paper.url ? (
                        <a className="inline-link" href={paper.url} rel="noreferrer" target="_blank">
                          打开
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
