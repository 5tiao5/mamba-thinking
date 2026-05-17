import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, toErrorMessage } from "../lib/api";
import type { ContinueConversationPayload, MessageItem } from "../types/api";

export function ConversationPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const conversationIdFromQuery = searchParams.get("conversation_id") ?? "";
  const [conversationId, setConversationId] = useState(conversationIdFromQuery);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [content, setContent] = useState("Only focus on benchmark and evaluation papers");
  const [focus, setFocus] = useState("benchmark evaluation");
  const [mode, setMode] = useState("balanced");
  const [createFollowUpTask, setCreateFollowUpTask] = useState(true);
  const [latestContinue, setLatestContinue] = useState<ContinueConversationPayload | null>(null);
  const [status, setStatus] = useState("输入 conversation_id 后加载消息，或从首页创建会话后进入本页。");
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [runningTaskId, setRunningTaskId] = useState("");

  useEffect(() => {
    if (conversationIdFromQuery) {
      setConversationId(conversationIdFromQuery);
      void loadMessages(conversationIdFromQuery);
    }
  }, [conversationIdFromQuery]);

  async function loadMessages(targetId = conversationId) {
    const trimmedId = targetId.trim();
    if (!trimmedId) {
      setStatus("请先输入 conversation_id。");
      return;
    }

    setLoadingMessages(true);
    setStatus("正在加载消息...");
    try {
      const response = await api.listMessages(trimmedId);
      setMessages(response.data.items);
      setStatus(response.data.items.length ? "消息加载成功。" : "当前会话还没有消息，可以发送第一条追问。");
    } catch (error) {
      setMessages([]);
      setStatus(`消息加载失败：${toErrorMessage(error)}`);
    } finally {
      setLoadingMessages(false);
    }
  }

  async function handleContinueConversation() {
    const trimmedId = conversationId.trim();
    const trimmedContent = content.trim();
    if (!trimmedId) {
      setStatus("请先输入 conversation_id。");
      return;
    }
    if (!trimmedContent) {
      setStatus("请输入要继续追问的内容。");
      return;
    }

    setSending(true);
    setStatus("正在发送追问...");
    try {
      const response = await api.continueConversation({
        conversation_id: trimmedId,
        content: trimmedContent,
        focus: focus.trim() || undefined,
        create_follow_up_task: createFollowUpTask,
        mode,
      });
      setLatestContinue(response.data);
      setContent("");
      setStatus(response.data.follow_up_task ? "追问已发送，并已创建 follow-up task。" : "追问已发送。");
      await loadMessages(trimmedId);
    } catch (error) {
      setStatus(`发送失败：${toErrorMessage(error)}`);
    } finally {
      setSending(false);
    }
  }

  async function runFollowUpTask(taskId: string) {
    setRunningTaskId(taskId);
    setStatus("正在运行 follow-up task，完成后将打开工作台...");
    try {
      await api.runTask(taskId);
      navigate(`/workspace?task_id=${encodeURIComponent(taskId)}`);
    } catch (error) {
      setStatus(`运行任务失败：${toErrorMessage(error)}`);
    } finally {
      setRunningTaskId("");
    }
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">多轮主链路</div>
        <h2 style={{ marginBottom: 10 }}>多轮对话区</h2>
        <p className="muted">
          这里承接消息列表、继续追问、上下文预览和 follow-up task 触发逻辑。
        </p>
      </section>

      <section className="panel">
        <h3 className="section-title">当前会话</h3>
        <div className="form-row">
          <input
            className="input"
            value={conversationId}
            onChange={(event) => setConversationId(event.target.value)}
            placeholder="输入 conversation_id"
            style={{ flex: "1 1 320px" }}
          />
          <button className="secondary-button" onClick={() => loadMessages()} disabled={loadingMessages}>
            {loadingMessages ? "加载中..." : "加载消息"}
          </button>
        </div>
        <div className="status-line">{status}</div>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">消息区</h3>
          {messages.length ? (
            <div className="message-list">
              {messages.map((message) => (
                <article className={`message-bubble ${message.role === "user" ? "message-user" : ""}`} key={message.message_id}>
                  <div className="message-meta">
                    <strong>{message.role}</strong>
                    <span>{new Date(message.created_at).toLocaleString()}</span>
                  </div>
                  <p>{message.content}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">当前没有可展示消息。发送追问后会出现在这里。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">继续追问</h3>
          <div className="form-stack">
            <label>
              <div className="field-label">追问内容</div>
              <textarea
                className="input textarea"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="输入本轮追问"
              />
            </label>
            <label>
              <div className="field-label">聚焦方向</div>
              <input
                className="input"
                value={focus}
                onChange={(event) => setFocus(event.target.value)}
                placeholder="例如 benchmark evaluation"
              />
            </label>
            <div className="form-row">
              <label style={{ flex: "1 1 160px" }}>
                <div className="field-label">任务模式</div>
                <select className="input" value={mode} onChange={(event) => setMode(event.target.value)}>
                  <option value="default">default</option>
                  <option value="fast">fast</option>
                  <option value="balanced">balanced</option>
                </select>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={createFollowUpTask}
                  onChange={(event) => setCreateFollowUpTask(event.target.checked)}
                />
                创建 follow-up task
              </label>
            </div>
            <button className="primary-button" onClick={handleContinueConversation} disabled={sending}>
              {sending ? "发送中..." : "发送追问"}
            </button>
          </div>
        </div>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">Context Preview</h3>
          {latestContinue?.context_preview.length ? (
            <ul className="list">
              {latestContinue.context_preview.map((item, index) => (
                <li className="list-item" key={`${item}-${index}`}>
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">发送追问后，这里会展示后端返回的最近上下文预览。</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">Follow-up Task</h3>
          {latestContinue?.follow_up_task ? (
            <div className="list">
              <div className="list-item">
                <strong>{latestContinue.follow_up_task.topic}</strong>
                <div className="muted">状态：{latestContinue.follow_up_task.status}</div>
                <code>{latestContinue.follow_up_task.task_id}</code>
                <div className="button-row" style={{ marginTop: 12 }}>
                  <button
                    className="primary-button"
                    onClick={() => runFollowUpTask(latestContinue.follow_up_task!.task_id)}
                    disabled={runningTaskId === latestContinue.follow_up_task.task_id}
                  >
                    {runningTaskId === latestContinue.follow_up_task.task_id ? "运行中..." : "运行并打开工作台"}
                  </button>
                  <Link
                    className="secondary-button link-button"
                    to={`/workspace?task_id=${encodeURIComponent(latestContinue.follow_up_task.task_id)}`}
                  >
                    只打开工作台
                  </Link>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">勾选创建 follow-up task 后，发送追问即可在这里看到任务入口。</div>
          )}
        </div>
      </section>
    </div>
  );
}
