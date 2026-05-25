import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { api, toErrorMessage } from "../lib/api";
import type { ContinueConversationPayload, MessageItem } from "../types/api";

const modeOptions = [
  { value: "default", label: "标准" },
  { value: "fast", label: "快速" },
  { value: "balanced", label: "均衡" },
];

const modeLabelMap: Record<string, string> = {
  default: "标准",
  fast: "快速",
  balanced: "均衡",
};

const roleLabelMap: Record<MessageItem["role"], string> = {
  user: "用户",
  assistant: "助手",
};

const taskStatusLabelMap: Record<string, string> = {
  pending: "待运行",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function getMessageTaskId(message: MessageItem) {
  const taskId = message.metadata?.task_id;
  return typeof taskId === "string" && taskId.trim() ? taskId : "";
}

function getMessageTaskStatus(message: MessageItem) {
  const taskStatus = message.metadata?.task_status;
  return typeof taskStatus === "string" && taskStatus.trim() ? taskStatus : "";
}

function getDisplayMessageContent(message: MessageItem) {
  const taskId = getMessageTaskId(message);
  if (!taskId) {
    return message.content;
  }

  return message.content
    .split("\n")
    .filter((line) => !line.includes(taskId))
    .join("\n")
    .trim();
}

export function ConversationPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const conversationIdFromQuery = searchParams.get("conversation_id") ?? "";
  const [conversationId, setConversationId] = useState(conversationIdFromQuery);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [content, setContent] = useState("只关注近两年的 benchmark 与 evaluation papers");
  const [focus, setFocus] = useState("评测指标与成本控制");
  const [mode, setMode] = useState("balanced");
  const [createFollowUpTask, setCreateFollowUpTask] = useState(true);
  const [latestContinue, setLatestContinue] = useState<ContinueConversationPayload | null>(null);
  const [status, setStatus] = useState("从首页进入会话后会自动加载消息，也可以使用演示入口查看流程。");
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
      setStatus("请先从首页创建或选择一个会话。");
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
      setStatus("请先从首页创建或选择一个会话。");
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
      setStatus(response.data.follow_up_task ? "追问已发送，并已生成后续研究任务。" : "追问已发送。");
      await loadMessages(trimmedId);
    } catch (error) {
      setStatus(`发送失败：${toErrorMessage(error)}`);
    } finally {
      setSending(false);
    }
  }

  async function runFollowUpTask(taskId: string) {
    setRunningTaskId(taskId);
    setStatus("正在运行后续研究任务，完成后将打开工作台...");
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
        <SectionHeader title="当前会话" eyebrow="研究上下文" />
        <div className="content-pad content-grid">
          <label>
            <span className="field-label">当前会话</span>
            <input
              className="input"
              onChange={(event) => setConversationId(event.target.value)}
              placeholder="从首页进入后自动填充"
              value={conversationId}
            />
          </label>
          <button className="secondary-button" disabled={loadingMessages} onClick={() => loadMessages()} type="button">
            {loadingMessages ? "加载中" : "加载消息"}
          </button>
          <div className="status-line">{status}</div>
        </div>

        <SectionHeader title="对话统计" eyebrow="消息概览" />
        <div className="metrics-strip" style={{ borderLeft: 0, borderRight: 0, borderRadius: 0 }}>
          <div className="metric-cell">
            <div className="metric-label">全部</div>
            <div className="metric-value">{messageStats.total}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">用户</div>
            <div className="metric-value">{messageStats.user}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">助手</div>
            <div className="metric-value">{messageStats.assistant}</div>
          </div>
          <div className="metric-cell">
            <div className="metric-label">模式</div>
            <div className="metric-value" style={{ fontSize: "0.8rem" }}>
              {modeLabelMap[mode] ?? mode}
            </div>
          </div>
        </div>

        <SectionHeader title="上下文预览" eyebrow={`${latestContinue?.context_preview.length ?? 0} 条`} />
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
                {messages.length} 条消息
              </StatusPill>
            ) : null
          }
          title="对话记录"
          eyebrow="消息"
        />
        <div className="pane-scroll message-feed">
          {messages.length ? (
            messages.map((message) => (
              <article
                className={`message-row ${message.role === "user" ? "message-user" : "message-assistant"}`}
                key={message.message_id}
              >
                <div className="message-meta">
                  <strong>{roleLabelMap[message.role] ?? message.role}</strong>
                  <span>{formatTime(message.created_at)}</span>
                </div>
                <div className="message-body">
                  <div>{getDisplayMessageContent(message)}</div>
                  {message.role === "assistant" && getMessageTaskId(message) ? (
                    <div className="message-task-actions">
                      {getMessageTaskStatus(message) ? (
                        <StatusPill compact tone={getMessageTaskStatus(message) === "completed" ? "success" : "warning"}>
                          {taskStatusLabelMap[getMessageTaskStatus(message)] ?? getMessageTaskStatus(message)}
                        </StatusPill>
                      ) : null}
                      <Link
                        className="secondary-button"
                        to={`/workspace?task_id=${encodeURIComponent(getMessageTaskId(message))}`}
                      >
                        在工作台中打开
                      </Link>
                    </div>
                  ) : null}
                </div>
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
        <SectionHeader title="继续追问" eyebrow="生成后续任务" />
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
              placeholder="例如：评测指标、成本控制"
              value={focus}
            />
          </label>
          <div>
            <span className="field-label">任务模式</span>
            <SegmentedControl label="任务模式" onChange={setMode} options={modeOptions} value={mode} />
          </div>
          <ToggleSwitch checked={createFollowUpTask} label="生成后续研究任务" onChange={setCreateFollowUpTask} />
          <button className="primary-button" disabled={sending} onClick={handleContinueConversation} type="button">
            {sending ? "发送中" : "发送追问"}
          </button>
        </div>

        <SectionHeader title="后续研究" eyebrow="任务入口" />
        <div className="content-pad">
          {latestContinue?.follow_up_task ? (
            <div className="content-grid">
              <div>
                <div className="insight-title">{latestContinue.follow_up_task.topic}</div>
                <div className="fine-print">由本轮追问触发，已准备进入工作台分析。</div>
              </div>
              <div className="button-row">
                <StatusPill tone="warning">
                  {taskStatusLabelMap[latestContinue.follow_up_task.status] ?? latestContinue.follow_up_task.status}
                </StatusPill>
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
                  打开工作台
                </Link>
              </div>
            </div>
          ) : (
            <div className="empty-state">勾选生成后续研究任务后，发送追问即可在这里看到任务入口。</div>
          )}
        </div>
      </aside>
    </div>
  );
}
