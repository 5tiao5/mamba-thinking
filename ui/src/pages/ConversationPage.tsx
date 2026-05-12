export function ConversationPage() {
  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">前端 A 负责</div>
        <h2 style={{ marginBottom: 10 }}>多轮对话区</h2>
        <p className="muted">
          这里后续要承接会话历史、当前用户输入、追问焦点和任务触发逻辑。当前只是展示页面骨架。
        </p>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">消息区</h3>
          <div className="empty-state">
            TODO: 渲染消息气泡、会话摘要、运行中状态、继续追问表单。
          </div>
        </div>

        <div className="panel">
          <h3 className="section-title">本页待实现</h3>
          <ul className="list">
            <li className="list-item">对接 `POST /conversations/continue`</li>
            <li className="list-item">做消息列表和输入框</li>
            <li className="list-item">补“运行中 / 已完成 / 出错”状态提示</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
