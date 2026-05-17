import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { api, toErrorMessage } from "../lib/api";
import type { ContinueConversationPayload, MessageItem } from "../types/api";

const modeOptions = [
  { value: "default", label: "Default" },
  { value: "fast", label: "Fast" },
  { value: "balanced", label: "Balanced" },
];

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

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

  const messageStats = useMemo(() => {
    const userMessages = messages.filter((message) => message.role === "user").length;
    return {
      total: messages.length,
      user: userMessages,
      assistant: messages.length - userMessages,
    };
  }, [messages]);

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
    <div className="conversation-grid">
      <aside className="pane">
        <SectionHeader title="Session" eyebrow="Context" />
        <div className="content-pad content-grid">
          <label>
            <span className="field-label">Conversation ID</span>
            <input
              className="input"
              onChange={(event) => setConversationId(event.target.value)}
              placeholder="输入 conversation_id"
              value={conversationId}
            />
          </label>
          <button className="secondary-button" disabled={loadingMessages} onClick={() => loadMessages()} type="button">
            {loadingMessages ? "加载中" : "加载消息"}
          </button>
          <div className="status-line">{status}</div>
        </div>

        <SectionHeader title="Message Stats" eyebrow="Flow" />
        <div className="metrics-strip" style={{ borderLeft: 0, borderRight: 0, borderRadius: 0 }}>
          <div className="metric-cell">
            <div className="metric-label">Total</div>
            <div className="metric-value">{messageStats.total}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">User</div>
            <div className="metric-value">{messageStats.user}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">Agent</div>
            <div className="metric-value">{messageStats.assistant}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">Mode</div>
            <div className="metric-value" style={{ fontSize: "0.8rem" }}>
              {mode}
            </div>
          </div>
        </div>

        <SectionHeader title="Context Preview" eyebrow={`${latestContinue?.context_preview.length ?? 0} lines`} />
        <div className="pane-scroll" style={{ maxHeight: 260 }}>
          {latestContinue?.context_preview.length ? (
            <ul className="compact-list">
              {latestContinue.context_preview.map((item, index) => (
                <li className="compact-item" key={`${item}-${index}`}>
                  <div className="fine-print">{item}</div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="content-pad">
              <div className="empty-state">发送追问后展示最近上下文预览。</div>
            </div>
          )}
        </div>
      </aside>

      <main className="pane">
        <SectionHeader
          actions={
            messages.length ? (
              <StatusPill tone="info" compact>
                {messages.length} messages
              </StatusPill>
            ) : null
          }
          title="Conversation Log"
          eyebrow="Messages"
        />
        <div className="pane-scroll message-feed">
          {messages.length ? (
            messages.map((message) => (
              <article
                className={`message-row ${message.role === "user" ? "message-user" : "message-assistant"}`}
                key={message.message_id}
              >
                <div className="message-meta">
                  <strong>{message.role}</strong>
                  <span>{formatTime(message.created_at)}</span>
                  <code>{message.message_id}</code>
                </div>
                <div className="message-body">{message.content}</div>
              </article>
            ))
          ) : (
            <div className="content-pad">
              <div className="empty-state">当前没有可展示消息。发送追问后会出现在这里。</div>
            </div>
          )}
        </div>
      </main>

      <aside className="pane">
        <SectionHeader title="Continue" eyebrow="Follow-up" />
        <div className="content-pad form-grid">
          <label>
            <span className="field-label">追问内容</span>
            <textarea
              className="input textarea"
              onChange={(event) => setContent(event.target.value)}
              placeholder="输入本轮追问"
              value={content}
            />
          </label>
          <label>
            <span className="field-label">聚焦方向</span>
            <input
              className="input"
              onChange={(event) => setFocus(event.target.value)}
              placeholder="例如 benchmark evaluation"
              value={focus}
            />
          </label>
          <div>
            <span className="field-label">任务模式</span>
            <SegmentedControl label="任务模式" onChange={setMode} options={modeOptions} value={mode} />
          </div>
          <ToggleSwitch checked={createFollowUpTask} label="创建 follow-up task" onChange={setCreateFollowUpTask} />
          <button className="primary-button" disabled={sending} onClick={handleContinueConversation} type="button">
            {sending ? "发送中" : "发送追问"}
          </button>
        </div>

        <SectionHeader title="Task Handoff" eyebrow="Run / Open" />
        <div className="content-pad">
          {latestContinue?.follow_up_task ? (
            <div className="content-grid">
              <div>
                <div className="insight-title">{latestContinue.follow_up_task.topic}</div>
                <div className="fine-print">trigger: {latestContinue.follow_up_task.trigger_message_id ?? "-"}</div>
              </div>
              <div className="button-row">
                <StatusPill tone="warning">{latestContinue.follow_up_task.status}</StatusPill>
                <code>{latestContinue.follow_up_task.task_id}</code>
              </div>
              <div className="button-row">
                <button
                  className="primary-button"
                  disabled={runningTaskId === latestContinue.follow_up_task.task_id}
                  onClick={() => runFollowUpTask(latestContinue.follow_up_task!.task_id)}
                  type="button"
                >
                  {runningTaskId === latestContinue.follow_up_task.task_id ? "运行中" : "运行并打开"}
                </button>
                <Link
                  className="secondary-button"
                  to={`/workspace?task_id=${encodeURIComponent(latestContinue.follow_up_task.task_id)}`}
                >
                  打开 Workspace
                </Link>
              </div>
            </div>
          ) : (
            <div className="empty-state">勾选创建 follow-up task 后，发送追问即可在这里看到任务入口。</div>
          )}
        </div>
      </aside>
    </div>
  );
}
