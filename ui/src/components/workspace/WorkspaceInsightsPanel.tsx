import { SectionHeader } from "../ui/SectionHeader";
import { StatusPill } from "../ui/StatusPill";
import { cleanDisplayText } from "../../lib/displayText";
import type {
  WorkspaceEvidenceStatus,
  WorkspaceGap,
  WorkspaceGraphEdge,
  WorkspaceIdea,
  WorkspacePaper,
  WorkspaceSnapshot,
} from "../../types/api";
import { WorkspaceGraphCanvas } from "./WorkspaceGraphCanvas";

function severityTone(severity: string): "danger" | "warning" | "neutral" {
  const normalized = severity.toLowerCase();
  if (normalized === "high" || normalized === "error") return "danger";
  if (normalized === "medium" || normalized === "warning") return "warning";
  return "neutral";
}

function severityLabel(severity: string) {
  const normalized = severity.toLowerCase();
  if (normalized === "high" || normalized === "error") return "高优先级";
  if (normalized === "medium" || normalized === "warning") return "中优先级";
  if (normalized === "low" || normalized === "info") return "低优先级";
  return severity || "待判断";
}

function GapList({ gaps }: { gaps: WorkspaceGap[] }) {
  if (!gaps.length) {
    return <div className="empty-state">暂时没有整理出稳定的研究空白。</div>;
  }

  return (
    <div className="insight-list">
      {gaps.map((gap, index) => (
        <article className="insight-item" key={`${gap.summary}-${index}`}>
          <div className="item-heading">
            <div className="insight-title">{cleanDisplayText(gap.summary)}</div>
            <StatusPill compact tone={severityTone(gap.severity)}>
              {severityLabel(gap.severity)}
            </StatusPill>
          </div>
          {gap.evidence.length ? (
            <div className="fine-print">{gap.evidence.map((item) => cleanDisplayText(item)).filter(Boolean).join(" / ")}</div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function IdeaList({ ideas }: { ideas: WorkspaceIdea[] }) {
  if (!ideas.length) {
    return <div className="empty-state">暂时没有生成稳定的研究建议。</div>;
  }

  return (
    <div className="insight-list">
      {ideas.map((idea, index) => (
        <article className="insight-item" key={`${idea.title}-${index}`}>
          <div className="insight-title">{cleanDisplayText(idea.title, 160) || "Untitled idea"}</div>
          <div className="fine-print">
            {cleanDisplayText(idea.motivation || idea.raw_text) || "No motivation yet"}
          </div>
          {idea.approach ? <div className="muted">Approach: {cleanDisplayText(idea.approach)}</div> : null}
          {idea.feasibility || idea.contribution ? (
            <div className="fine-print">
              {idea.feasibility ? `Feasibility: ${cleanDisplayText(idea.feasibility)}` : ""}
              {idea.feasibility && idea.contribution ? " / " : ""}
              {idea.contribution ? `Contribution: ${cleanDisplayText(idea.contribution)}` : ""}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function WorkspaceInsightsPanel({
  gaps,
  ideas,
  graphEdges,
  papers,
  evidenceStatus,
  trace,
}: {
  gaps: WorkspaceGap[];
  ideas: WorkspaceIdea[];
  graphEdges: WorkspaceGraphEdge[];
  papers: WorkspacePaper[];
  evidenceStatus?: WorkspaceEvidenceStatus;
  trace: WorkspaceSnapshot["trace"];
}) {
  const insufficientEvidence = evidenceStatus?.insufficient ?? false;

  return (
    <section className="workspace-insights-grid">
      <section className="pane">
        <SectionHeader eyebrow={`${gaps.length} 条`} title="研究空白" />
        <div className="pane-scroll">
          <GapList gaps={gaps} />
        </div>
      </section>

      <section className="pane">
        <SectionHeader eyebrow={`${ideas.length} 条`} title="研究建议" />
        <div className="pane-scroll">
          <IdeaList ideas={ideas} />
        </div>
      </section>

      <section className="pane workspace-graph-pane">
        <SectionHeader eyebrow={`${graphEdges.length} 条关系`} title="整体演进图谱" />
        <div className="content-pad pane-scroll">
          {insufficientEvidence ? (
            <div className="empty-state workspace-evidence-mode-note">
              当前证据不足，这一轮不展示完整演进图谱。等真实论文数量上来，或者用户导入更多资料后，再看关系图谱才更有意义。
            </div>
          ) : (
            <>
              <WorkspaceGraphCanvas graphEdges={graphEdges} papers={papers} />
              <details className="workspace-edge-details">
                <summary>查看关系明细</summary>
                {graphEdges.length ? (
                  <div className="data-table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>起点</th>
                          <th>终点</th>
                          <th>关系</th>
                          <th>依据</th>
                        </tr>
                      </thead>
                      <tbody>
                        {graphEdges.map((edge, index) => (
                          <tr key={`${edge.source}-${edge.target}-${index}`}>
                            <td>{cleanDisplayText(edge.source, 80)}</td>
                            <td>{cleanDisplayText(edge.target, 80)}</td>
                            <td>{cleanDisplayText(edge.relationship, 80)}</td>
                            <td>{cleanDisplayText(edge.reasoning) || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty-state">暂无关系线索。</div>
                )}
              </details>
            </>
          )}
        </div>
      </section>

      <section className="pane">
        <SectionHeader eyebrow="过程记录" title="研究过程" />
        {trace ? (
          <div className="content-grid content-pad">
            <div className="trace-row">
              <div className="trace-label">分析步骤</div>
              <div>{trace.thought_trace.length} 步</div>
            </div>
            <div className="trace-row">
              <div className="trace-label">搜索动作</div>
              <div>{trace.action_history.length} 条</div>
            </div>
            <div className="trace-row">
              <div className="trace-label">上下文</div>
              <div>{trace.context_inputs.length} 组</div>
            </div>
            <div className="empty-state">
              系统已保留本轮分析过程，可用于继续追问、复盘和后续整理。
            </div>
          </div>
        ) : (
          <div className="content-pad">
            <div className="empty-state">暂无研究过程记录。</div>
          </div>
        )}
      </section>
    </section>
  );
}
