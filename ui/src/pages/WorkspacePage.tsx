import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { api, toErrorMessage } from "../lib/api";
import type { WorkspaceGap, WorkspaceIdea, WorkspacePaper, WorkspaceSnapshot } from "../types/api";

type TaxonomyEntry = {
  name: string;
  values: string[];
};

function normalizeTaxonomyValue(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }
  if (value && typeof value === "object") {
    return Object.entries(value).map(([key, item]) => `${key}: ${String(item)}`);
  }
  if (value === undefined || value === null || value === "") {
    return [];
  }
  return [String(value)];
}

function buildTaxonomyEntries(taxonomy: Record<string, unknown>): TaxonomyEntry[] {
  return Object.entries(taxonomy).map(([name, value]) => ({
    name,
    values: normalizeTaxonomyValue(value),
  }));
}

function severityTone(severity: string): "danger" | "warning" | "neutral" {
  if (severity.toLowerCase() === "high") return "danger";
  if (severity.toLowerCase() === "medium") return "warning";
  return "neutral";
}

function severityLabel(severity: string) {
  const normalized = severity.toLowerCase();
  if (normalized === "high") return "高优先级";
  if (normalized === "medium") return "中优先级";
  if (normalized === "low") return "低优先级";
  return severity || "待判断";
}

function PaperInspector({ paper }: { paper?: WorkspacePaper }) {
  if (!paper) {
    return <div className="empty-state">选择一篇论文后，这里会显示来源、分类、引用数和外链。</div>;
  }

  return (
    <div className="content-grid">
      <div>
        <div className="section-eyebrow">已选论文</div>
        <div className="insight-title">{paper.title}</div>
      </div>
      <div className="metrics-strip">
        <div className="metric-cell">
          <div className="metric-label">来源</div>
          <div className="metric-value" style={{ fontSize: "0.92rem" }}>
            {paper.source || "未知"}
          </div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">年份</div>
          <div className="metric-value" style={{ fontSize: "0.92rem" }}>
            {paper.publish_date || "-"}
          </div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">引用</div>
          <div className="metric-value" style={{ fontSize: "0.92rem" }}>
            {paper.citation_count}
          </div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">分类</div>
          <div className="metric-value" style={{ fontSize: "0.72rem" }}>
            {paper.taxonomy_category || "未分类"}
          </div>
        </div>
      </div>
      <div className="status-line">{paper.taxonomy_category || "未分类"}</div>
      {paper.url ? (
        <a className="secondary-button" href={paper.url} rel="noreferrer" target="_blank">
          打开论文来源
        </a>
      ) : null}
    </div>
  );
}

function GapList({ gaps }: { gaps: WorkspaceGap[] }) {
  if (!gaps.length) {
    return <div className="empty-state">暂无研究空白。运行分析后会在这里汇总可继续深入的问题。</div>;
  }

  return (
    <div className="insight-list">
      {gaps.map((gap, index) => (
        <article className="insight-item" key={`${gap.summary}-${index}`}>
          <div className="item-heading">
            <div className="insight-title">{gap.summary}</div>
            <StatusPill tone={severityTone(gap.severity)} compact>
              {severityLabel(gap.severity)}
            </StatusPill>
          </div>
          {gap.evidence.length ? <div className="fine-print">{gap.evidence.join(" / ")}</div> : null}
        </article>
      ))}
    </div>
  );
}

function IdeaList({ ideas }: { ideas: WorkspaceIdea[] }) {
  if (!ideas.length) {
    return <div className="empty-state">暂无选题建议。完成分析后这里会集中展示可继续推进的研究选题。</div>;
  }

  return (
    <div className="insight-list">
      {ideas.map((idea, index) => (
        <article className="insight-item" key={`${idea.title}-${index}`}>
          <div className="insight-title">{idea.title || "未命名选题"}</div>
          <div className="fine-print">{idea.motivation || idea.raw_text || "暂无动机描述"}</div>
          {idea.approach ? <div className="muted">方法：{idea.approach}</div> : null}
          {idea.feasibility || idea.contribution ? (
            <div className="fine-print">
              {idea.feasibility ? `可行性：${idea.feasibility}` : ""}
              {idea.feasibility && idea.contribution ? " / " : ""}
              {idea.contribution ? `贡献：${idea.contribution}` : ""}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function WorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const taskIdFromQuery = searchParams.get("task_id") ?? "";
  const [taskId, setTaskId] = useState(taskIdFromQuery);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [status, setStatus] = useState("从对话或首页进入任务后，可以运行分析或读取工作台。");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedPaperId, setSelectedPaperId] = useState("");

  useEffect(() => {
    if (taskIdFromQuery) {
      setTaskId(taskIdFromQuery);
      void handleLoadWorkspace(taskIdFromQuery);
    }
  }, [taskIdFromQuery]);

  const taxonomyEntries = useMemo(
    () => (workspace ? buildTaxonomyEntries(workspace.taxonomy) : []),
    [workspace]
  );

  const filteredPapers = useMemo(() => {
    const papers = workspace?.papers ?? [];
    if (selectedCategory === "all") {
      return papers;
    }
    return papers.filter((paper) => paper.taxonomy_category === selectedCategory);
  }, [selectedCategory, workspace]);

  const selectedPaper = useMemo(() => {
    if (!filteredPapers.length) {
      return undefined;
    }
    return filteredPapers.find((paper) => paper.paper_id === selectedPaperId) ?? filteredPapers[0];
  }, [filteredPapers, selectedPaperId]);

  async function handleLoadWorkspace(targetId = taskId) {
    const trimmedId = targetId.trim();
    if (!trimmedId) {
      setStatus("请先从对话或首页选择一个研究任务。");
      return;
    }
    setLoading(true);
    setStatus("正在读取工作台...");
    try {
      const response = await api.getWorkspace(trimmedId);
      setWorkspace(response.data);
      setSelectedCategory("all");
      setSelectedPaperId(response.data.papers[0]?.paper_id ?? "");
      setStatus("工作台已加载。");
      setSearchParams({ task_id: trimmedId });
    } catch (error) {
      setWorkspace(null);
      setSelectedPaperId("");
      setStatus(`加载失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTask() {
    const trimmedId = taskId.trim();
    if (!trimmedId) {
      setStatus("请先从对话或首页选择一个研究任务。");
      return;
    }

    setRunning(true);
    setStatus("任务运行中，分析可能需要一些时间...");
    try {
      await api.runTask(trimmedId);
      setStatus("任务运行完成，正在读取工作台...");
      await handleLoadWorkspace(trimmedId);
    } catch (error) {
      setStatus(`运行失败：${toErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="dense-layout">
      <section className="surface content-pad">
        <div className="workspace-toolbar">
          <label>
            <span className="field-label">任务引用</span>
            <input
              className="input"
              onChange={(event) => setTaskId(event.target.value)}
              placeholder="从对话或首页进入后自动填充"
              value={taskId}
            />
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={running} onClick={handleRunTask} type="button">
              {running ? "运行中" : "运行任务"}
            </button>
            <button className="secondary-button" disabled={loading} onClick={() => handleLoadWorkspace()} type="button">
              {loading ? "读取中" : "读取工作台"}
            </button>
          </div>
        </div>
        <div className="status-line" style={{ marginTop: 10 }}>
          {status}
        </div>
      </section>

      <section className="metrics-strip">
        <div className="metric-cell">
          <div className="metric-label">研究主题</div>
          <div className="metric-value" style={{ fontSize: "0.96rem" }}>
            {workspace?.topic ?? "未加载研究"}
          </div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">论文</div>
          <div className="metric-value">{workspace?.papers.length ?? 0}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">关系线索</div>
          <div className="metric-value">{workspace?.graph_edges.length ?? 0}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">匹配度</div>
          <div className="metric-value">{workspace?.alignment_score ?? 0}</div>
        </div>
      </section>

      {workspace?.summary ? (
        <section className="surface content-pad">
          <div className="section-eyebrow">研究摘要</div>
          <div style={{ whiteSpace: "pre-wrap" }}>{workspace.summary}</div>
        </section>
      ) : null}

      <section className="workspace-grid">
        <aside className="pane">
          <SectionHeader title="主题分类" eyebrow="筛选" />
          <div className="pane-scroll">
            <ul className="taxonomy-tree">
              <li className="taxonomy-node">
                <button
                  className={selectedCategory === "all" ? "taxonomy-button taxonomy-active" : "taxonomy-button"}
                  onClick={() => setSelectedCategory("all")}
                  type="button"
                >
                  <span className="taxonomy-name">全部论文</span>
                  <span className="taxonomy-values">{workspace?.papers.length ?? 0} 篇</span>
                </button>
              </li>
              {taxonomyEntries.length ? (
                taxonomyEntries.map((entry) => (
                  <li className="taxonomy-node" key={entry.name}>
                    <button
                      className={selectedCategory === entry.name ? "taxonomy-button taxonomy-active" : "taxonomy-button"}
                      onClick={() => setSelectedCategory(entry.name)}
                      type="button"
                    >
                      <span className="taxonomy-name">{entry.name}</span>
                      <span className="taxonomy-values">
                        {entry.values.length ? entry.values.join(" / ") : "暂无子项"}
                      </span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="content-pad">
                  <div className="empty-state">暂无分类结构。</div>
                </li>
              )}
            </ul>
          </div>
        </aside>

        <main className="pane">
          <SectionHeader
            actions={
              selectedCategory !== "all" ? (
                <StatusPill tone="info" compact>
                  {selectedCategory}
                </StatusPill>
              ) : null
            }
            title="论文线索"
            eyebrow={`${filteredPapers.length} 篇可见`}
          />
          <div className="data-table-wrap pane-scroll">
            {filteredPapers.length ? (
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
                  {filteredPapers.map((paper) => (
                    <tr
                      className={selectedPaper?.paper_id === paper.paper_id ? "selected-row" : ""}
                      key={paper.paper_id}
                      onClick={() => setSelectedPaperId(paper.paper_id)}
                    >
                      <td>
                        <div className="table-title">{paper.title}</div>
                      </td>
                      <td>{paper.source || "未知"}</td>
                      <td>{paper.publish_date || "-"}</td>
                      <td>{paper.taxonomy_category || "未分类"}</td>
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
        </main>

        <aside className="pane">
          <SectionHeader title="论文详情" eyebrow="当前选择" />
          <div className="content-pad">
            <PaperInspector paper={selectedPaper} />
          </div>
          <SectionHeader title="研究空白" eyebrow={`${workspace?.gaps.length ?? 0} 条`} />
          <div className="pane-scroll" style={{ maxHeight: 220 }}>
            <GapList gaps={workspace?.gaps ?? []} />
          </div>
          <SectionHeader title="选题建议" eyebrow={`${workspace?.ideas.length ?? 0} 条`} />
          <div className="pane-scroll" style={{ maxHeight: 260 }}>
            <IdeaList ideas={workspace?.ideas ?? []} />
          </div>
        </aside>
      </section>

      <section className="settings-grid">
        <div className="pane">
          <SectionHeader title="关系线索" eyebrow={`${workspace?.graph_edges.length ?? 0} 条关系`} />
          <div className="data-table-wrap">
            {workspace?.graph_edges.length ? (
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
                  {workspace.graph_edges.map((edge, index) => (
                    <tr key={`${edge.source}-${edge.target}-${index}`}>
                      <td>{edge.source}</td>
                      <td>{edge.target}</td>
                      <td>{edge.relationship}</td>
                      <td>{edge.reasoning || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="content-pad">
                <div className="empty-state">暂无关系线索。</div>
              </div>
            )}
          </div>
        </div>

        <div className="pane">
          <SectionHeader title="研究过程" eyebrow="可追溯记录" />
          {workspace?.trace ? (
            <div className="content-grid content-pad">
              <div className="trace-row">
                <div className="trace-label">分析步骤</div>
                <div>{workspace.trace.thought_trace.length} 步</div>
              </div>
              <div className="trace-row">
                <div className="trace-label">检索动作</div>
                <div>{workspace.trace.action_history.length} 条</div>
              </div>
              <div className="trace-row">
                <div className="trace-label">上下文</div>
                <div>{workspace.trace.context_inputs.length} 组</div>
              </div>
              <div className="empty-state">系统已保留本次分析过程，可用于继续追问、复盘和后续整理。</div>
            </div>
          ) : (
            <div className="content-pad">
              <div className="empty-state">暂无研究过程记录。</div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
