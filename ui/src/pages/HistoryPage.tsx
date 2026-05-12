export function HistoryPage() {
  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">会话历史</div>
        <h2 style={{ marginBottom: 10 }}>历史任务与会话列表</h2>
        <p className="muted">后续这里要展示 conversation 列表、最近 task 以及“继续会话”入口。</p>
      </section>

      <section className="panel">
        <div className="empty-state">TODO: 对接 conversation 列表接口；后续还要支持搜索和筛选。</div>
      </section>
    </div>
  );
}
