import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, toErrorMessage } from "../lib/api";
import type { WorkspaceSnapshot } from "../types/api";

export function WorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const taskIdFromQuery = searchParams.get("task_id") ?? "";
  const [taskId, setTaskId] = useState(taskIdFromQuery);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [status, setStatus] = useState("输入 task_id 后可以运行任务或读取 workspace。");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (taskIdFromQuery) {
      setTaskId(taskIdFromQuery);
      void handleLoadWorkspace(taskIdFromQuery);
    }
  }, [taskIdFromQuery]);

  async function handleLoadWorkspace(targetId = taskId) {
    const trimmedId = targetId.trim();
    if (!trimmedId) {
      setStatus("请先输入 task_id。");
      return;
    }
    setLoading(true);
    setStatus("加载中...");
    try {
      const response = await api.getWorkspace(trimmedId);
      setWorkspace(response.data);
      setStatus("加载成功。");
      setSearchParams({ task_id: trimmedId });
    } catch (error) {
      setWorkspace(null);
      setStatus(`加载失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTask() {
    const trimmedId = taskId.trim();
    if (!trimmedId) {
      setStatus("请先输入 task_id。");
      return;
    }

    setRunning(true);
    setStatus("任务运行中，Agent 分析可能需要一些时间...");
    try {
      await api.runTask(trimmedId);
      setStatus("任务运行完成，正在读取 workspace...");
      await handleLoadWorkspace(trimmedId);
    } catch (error) {
      setStatus(`运行失败：${toErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">研究结果工作台</div>
        <h2 style={{ marginBottom: 10 }}>研究工作台</h2>
        <p className="muted">
          展示任务运行后的 papers、taxonomy、graph、gap、ideas 和 trace，用于验证主链路结果。
        </p>
      </section>

      <section className="panel">
        <h3 className="section-title">任务控制</h3>
        <div className="form-row">
          <input
            className="input"
            value={taskId}
            onChange={(event) => setTaskId(event.target.value)}
            placeholder="输入 task_id"
            style={{ flex: "1 1 280px" }}
          />
          <button className="primary-button" onClick={handleRunTask} disabled={running}>
            {running ? "运行中..." : "运行任务"}
          </button>
          <button className="secondary-button" onClick={() => handleLoadWorkspace()} disabled={loading}>
            {loading ? "加载中..." : "读取 Workspace"}
          </button>
        </div>
        <div className="status-line">{status}</div>
      </section>

      <section className="grid-three">
        <article className="kpi">
          <div className="kpi-label">Papers</div>
          <div className="kpi-value">{workspace?.papers.length ?? 0}</div>
        </article>
        <article className="kpi">
          <div className="kpi-label">Graph Edges</div>
          <div className="kpi-value">{workspace?.graph_edges.length ?? 0}</div>
        </article>
        <article className="kpi">
          <div className="kpi-label">Alignment Score</div>
          <div className="kpi-value">{workspace?.alignment_score ?? 0}</div>
        </article>
      </section>

      <section className="panel">
        <h3 className="section-title">研究摘要</h3>
        {workspace?.summary ? (
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{workspace.summary}</p>
        ) : (
          <div className="empty-state">workspace 加载成功后，这里会展示摘要。</div>
        )}
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">论文列表</h3>
          {workspace?.papers.length ? (
            <ul className="list">
              {workspace.papers.map((paper) => (
                <li className="list-item" key={paper.paper_id}>
                  <strong>{paper.title}</strong>
                  <div className="muted">
                    {paper.publish_date || "未知日期"} · {paper.source || "unknown"} · {paper.taxonomy_category || "未分类"}
                  </div>
                  <div className="muted">引用数：{paper.citation_count}</div>
                  {paper.url ? (
                    <a href={paper.url} target="_blank" rel="noreferrer" className="inline-link">
                      打开来源
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">暂无论文数据。请先运行任务或检查 task_id。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">Taxonomy</h3>
          {workspace && Object.keys(workspace.taxonomy).length ? (
            <pre className="json-block">{JSON.stringify(workspace.taxonomy, null, 2)}</pre>
          ) : (
            <div className="empty-state">暂无 taxonomy 结构。</div>
          )}
        </div>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">Graph Edges</h3>
          {workspace?.graph_edges.length ? (
            <ul className="list">
              {workspace.graph_edges.map((edge, index) => (
                <li className="list-item" key={`${edge.source}-${edge.target}-${index}`}>
                  <strong>
                    {edge.source} {"->"} {edge.target}
                  </strong>
                  <div className="muted">{edge.relationship}</div>
                  {edge.reasoning ? <div>{edge.reasoning}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">暂无 graph edges。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">Research Gaps</h3>
          {workspace?.gaps.length ? (
            <ul className="list">
              {workspace.gaps.map((gap, index) => (
                <li className="list-item" key={`${gap.summary}-${index}`}>
                  <strong>{gap.summary}</strong>
                  <div className="badge" style={{ marginTop: 8 }}>
                    {gap.severity}
                  </div>
                  {gap.evidence.length ? (
                    <div className="muted" style={{ marginTop: 8 }}>
                      证据：{gap.evidence.join("；")}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">暂无 gap 数据。</div>
          )}
        </div>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">Ideas</h3>
          {workspace?.ideas.length ? (
            <ul className="list">
              {workspace.ideas.map((idea, index) => (
                <li className="list-item" key={`${idea.title}-${index}`}>
                  <strong>{idea.title || "未命名选题"}</strong>
                  <div className="muted">{idea.motivation || idea.raw_text}</div>
                  {idea.approach ? <div style={{ marginTop: 8 }}>方法：{idea.approach}</div> : null}
                  {idea.feasibility ? <div className="muted">可行性：{idea.feasibility}</div> : null}
                  {idea.contribution ? <div className="muted">贡献：{idea.contribution}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">暂无 ideas 数据。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">Trace</h3>
          {workspace?.trace ? (
            <div className="list">
              <div className="list-item">Thought Trace：{workspace.trace.thought_trace.length}</div>
              <div className="list-item">Action History：{workspace.trace.action_history.length}</div>
              <div className="list-item">Context Inputs：{workspace.trace.context_inputs.length}</div>
              <pre className="json-block">{JSON.stringify(workspace.trace, null, 2)}</pre>
            </div>
          ) : (
            <div className="empty-state">暂无 trace 数据。</div>
          )}
        </div>
      </section>
    </div>
  );
}
