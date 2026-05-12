import { useState } from "react";

import { api } from "../lib/api";
import type { WorkspaceSnapshot } from "../types/api";

export function WorkspacePage() {
  const [taskId, setTaskId] = useState("");
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [status, setStatus] = useState("你可以先输入 task_id，后续前端同学可改成从创建任务结果自动跳转。");

  async function handleLoadWorkspace() {
    if (!taskId.trim()) {
      setStatus("请先输入 task_id。");
      return;
    }
    setStatus("加载中...");
    try {
      const response = await api.getWorkspace(taskId.trim());
      setWorkspace(response.data);
      setStatus("加载成功。");
    } catch (error) {
      setStatus(`加载失败：${String(error)}`);
    }
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">前端 B 负责</div>
        <h2 style={{ marginBottom: 10 }}>研究工作台</h2>
        <p className="muted">
          这里是产品价值最集中的页面。后续要把论文列表、taxonomy、graph、gap、ideas 都放在这一页组织起来。
        </p>
      </section>

      <section className="panel">
        <h3 className="section-title">读取工作台快照</h3>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <input
            value={taskId}
            onChange={(event) => setTaskId(event.target.value)}
            placeholder="输入 task_id"
            style={{
              flex: "1 1 280px",
              borderRadius: 14,
              border: "1px solid rgba(20, 33, 61, 0.12)",
              padding: "12px 14px",
            }}
          />
          <button
            onClick={handleLoadWorkspace}
            style={{
              border: "none",
              borderRadius: 14,
              padding: "12px 16px",
              background: "#123a6d",
              color: "#fff",
              fontWeight: 700,
            }}
          >
            获取 Workspace
          </button>
        </div>
        <p className="muted" style={{ marginTop: 14 }}>
          {status}
        </p>
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
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">TODO: 后续需要支持筛选、排序和关键论文对比入口。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">Gap 与 Ideas</h3>
          {workspace ? (
            <div className="list">
              <div className="list-item">Gap 数量：{workspace.gaps.length}</div>
              <div className="list-item">Ideas 数量：{workspace.ideas.length}</div>
            </div>
          ) : (
            <div className="empty-state">TODO: 这里后续需要分开展示 gap 列表和选题建议卡片。</div>
          )}
        </div>
      </section>
    </div>
  );
}
