export function HistoryPage() {
  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">会话历史</div>
        <h2 style={{ marginBottom: 10 }}>历史任务与会话列表</h2>
        <p className="muted">后续这里要展示 conversation 列表、最近 task 以及“继续会话”入口。</p>
      </section>

      <section className="panel">
        <h3 className="section-title">接口状态</h3>
        <div className="empty-state">
          当前后端文档明确尚未提供 `GET /conversations` 和 `GET /research/tasks`，因此本页暂不做假数据列表。
          待后端补齐历史查询接口后，可在这里接入会话列表、最近任务和继续会话入口。
        </div>
      </section>
    </div>
  );
}
