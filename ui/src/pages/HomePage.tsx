import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, toErrorMessage } from "../lib/api";
import { DEMO_CONVERSATION_ID, DEMO_WORKSPACE_TASK_ID } from "../lib/demoData";
import type { ConversationResponsePayload } from "../types/api";

const modeOptions = [
  { value: "default", label: "default" },
  { value: "fast", label: "fast" },
  { value: "balanced", label: "balanced" },
];

export function HomePage() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("AI Agent Tool Use");
  const [title, setTitle] = useState("Agent 调研");
  const [mode, setMode] = useState("balanced");
  const [useSharedKnowledge, setUseSharedKnowledge] = useState(false);
  const [conversation, setConversation] = useState<ConversationResponsePayload | null>(null);
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("填写主题后创建会话，随后可以进入对话页或直接创建研究任务。");
  const [loading, setLoading] = useState(false);
  const [taskLoading, setTaskLoading] = useState(false);

  async function handleCreateConversation() {
    if (!topic.trim()) {
      setStatus("请先填写研究主题。");
      return;
    }

    setLoading(true);
    setStatus("正在创建会话...");
    try {
      const response = await api.createConversation({
        topic: topic.trim(),
        title: title.trim() || undefined,
      });
      setConversation(response.data);
      setTaskId("");
      setStatus(`已创建会话：${response.data.conversation_id}`);
    } catch (error) {
      setStatus(`创建失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateTask() {
    if (!conversation) {
      setStatus("请先创建会话，再创建研究任务。");
      return;
    }

    setTaskLoading(true);
    setStatus("正在创建研究任务...");
    try {
      const response = await api.createTask({
        conversation_id: conversation.conversation_id,
        topic: conversation.topic,
        mode,
        use_shared_knowledge: useSharedKnowledge,
        enabled_tools: [],
      });
      setTaskId(response.data.task_id);
      setStatus(`已创建任务：${response.data.task_id}`);
    } catch (error) {
      setStatus(`创建任务失败：${toErrorMessage(error)}`);
    } finally {
      setTaskLoading(false);
    }
  }

  function openConversation() {
    if (!conversation) {
      setStatus("请先创建会话。");
      return;
    }
    navigate(`/conversation?conversation_id=${encodeURIComponent(conversation.conversation_id)}`);
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">迭代三产品入口</div>
        <h2 style={{ marginBottom: 10, fontSize: "2.2rem" }}>从研究主题到工作台快照</h2>
        <p className="muted" style={{ maxWidth: 720 }}>
          先创建研究会话，再进入对话区继续追问；也可以直接创建一条研究任务，后续到工作台运行和查看结果。
        </p>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">新建研究会话</h3>
          <p className="section-subtitle">对接 `POST /conversations` 与 `POST /research/tasks`。</p>

          <div className="form-stack">
            <label>
              <div className="field-label">研究主题</div>
              <input
                className="input"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
            </label>
            <label>
              <div className="field-label">会话标题</div>
              <input
                className="input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <div className="form-row">
              <label style={{ flex: "1 1 180px" }}>
                <div className="field-label">任务模式</div>
                <select className="input" value={mode} onChange={(event) => setMode(event.target.value)}>
                  {modeOptions.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={useSharedKnowledge}
                  onChange={(event) => setUseSharedKnowledge(event.target.checked)}
                />
                使用共享知识
              </label>
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={handleCreateConversation} disabled={loading}>
                {loading ? "创建中..." : "创建会话"}
              </button>
              <button className="secondary-button" onClick={openConversation} disabled={!conversation}>
                进入对话区
              </button>
            </div>
            <button className="secondary-button" onClick={handleCreateTask} disabled={!conversation || taskLoading}>
              {taskLoading ? "创建任务中..." : "基于当前会话创建研究任务"}
            </button>
            <div className="status-line">{status}</div>
          </div>
        </div>

        <div className="panel">
          <h3 className="section-title">当前链路状态</h3>
          {conversation ? (
            <div className="list">
              <div className="list-item">
                <strong>{conversation.title}</strong>
                <div className="muted">{conversation.topic}</div>
                <code>{conversation.conversation_id}</code>
              </div>
              {taskId ? (
                <div className="list-item">
                  <strong>研究任务</strong>
                  <div>
                    <code>{taskId}</code>
                  </div>
                  <div className="button-row" style={{ marginTop: 12 }}>
                    <Link className="secondary-button link-button" to={`/workspace?task_id=${encodeURIComponent(taskId)}`}>
                      打开工作台
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="empty-state">还没有创建研究任务。可以先进入对话区追问，或在左侧直接创建任务。</div>
              )}
            </div>
          ) : (
            <div className="empty-state">创建会话后，这里会显示 conversation_id 和后续任务入口。</div>
          )}
          <div className="button-row" style={{ marginTop: 18 }}>
            <Link
              to={`/conversation?conversation_id=${encodeURIComponent(DEMO_CONVERSATION_ID)}`}
              className="primary-button link-button"
            >
              预览演示对话流程
            </Link>
            <Link
              to={`/workspace?task_id=${encodeURIComponent(DEMO_WORKSPACE_TASK_ID)}`}
              className="secondary-button link-button"
            >
              直接预览演示工作台
            </Link>
            <Link to="/settings" className="badge">
              查看工具与 Skill
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
