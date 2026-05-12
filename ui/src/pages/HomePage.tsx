import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";

export function HomePage() {
  const [topic, setTopic] = useState("AI Agent Tool Use");
  const [title, setTitle] = useState("Agent 调研");
  const [result, setResult] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function handleCreateConversation() {
    setLoading(true);
    setResult("");
    try {
      const response = await api.createConversation({ topic, title });
      setResult(`已创建会话：${response.data.conversation_id}`);
    } catch (error) {
      setResult(`创建失败：${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">迭代三产品入口</div>
        <h2 style={{ marginBottom: 10, fontSize: "2.2rem" }}>从研究主题到工作台快照</h2>
        <p className="muted" style={{ maxWidth: 720 }}>
          这个页面对应用户的新建任务入口。前端同学后续需要在这里继续补模式选择、工具开关、共享知识等表单项。
        </p>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">新建研究会话</h3>
          <p className="section-subtitle">当前直接对接 `POST /conversations`，用来验证前后端基础链路。</p>

          <div style={{ display: "grid", gap: 14, marginTop: 18 }}>
            <label>
              <div className="muted" style={{ marginBottom: 6 }}>
                研究主题
              </div>
              <input
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                style={inputStyle}
              />
            </label>
            <label>
              <div className="muted" style={{ marginBottom: 6 }}>
                会话标题
              </div>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                style={inputStyle}
              />
            </label>
            <button onClick={handleCreateConversation} disabled={loading} style={buttonStyle}>
              {loading ? "创建中..." : "创建会话"}
            </button>
            {result ? <div className="list-item">{result}</div> : null}
          </div>
        </div>

        <div className="panel">
          <h3 className="section-title">当前前端待实现重点</h3>
          <ul className="list">
            <li className="list-item">补会话创建后自动跳转到对话区</li>
            <li className="list-item">补模式选择、工具开关、共享知识选项</li>
            <li className="list-item">补最近会话列表和最近任务入口</li>
          </ul>
          <div style={{ marginTop: 18 }}>
            <Link to="/workspace" className="badge">
              查看工作台模板
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  borderRadius: 14,
  border: "1px solid rgba(20, 33, 61, 0.12)",
  padding: "12px 14px",
  background: "#fff",
} as const;

const buttonStyle = {
  border: "none",
  borderRadius: 14,
  padding: "12px 16px",
  background: "#123a6d",
  color: "#fff",
  fontWeight: 700,
  cursor: "pointer",
} as const;
