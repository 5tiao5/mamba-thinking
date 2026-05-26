import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { StatusPill } from "../components/ui/StatusPill";
import { api, toErrorMessage } from "../lib/api";
import { cleanDisplayText } from "../lib/displayText";
import type { MessageItem } from "../types/api";

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
    return cleanDisplayText(message.content);
  }

  return cleanDisplayText(
    message.content
    .split("\n")
    .filter((line) => !line.includes(taskId))
    .join("\n")
    .trim()
  );
}

export function ConversationPage() {
  const [searchParams] = useSearchParams();
  const conversationIdFromQuery = searchParams.get("conversation_id") ?? "";
  const [conversationId, setConversationId] = useState(conversationIdFromQuery);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [status, setStatus] = useState("从左侧选择历史会话，或在右侧直接追问。");
  const [loadingMessages, setLoadingMessages] = useState(false);

  useEffect(() => {
    if (conversationIdFromQuery) {
      setConversationId(conversationIdFromQuery);
      void loadMessages(conversationIdFromQuery);
    }
  }, [conversationIdFromQuery]);

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

  return (
    <div className="simple-page conversation-simple conversation-results-only">
      <section className="simple-hero simple-hero-compact">
        <div>
          <div className="section-eyebrow">Conversation</div>
          <h1>对话结果</h1>
          <p>这里保留你真正需要阅读的内容。新的追问统一在右侧窗口完成。</p>
        </div>
        <div className="simple-context-input">
          <input
            className="input"
            onChange={(event) => setConversationId(event.target.value)}
            placeholder="conversation_id"
            value={conversationId}
          />
          <button className="secondary-button" disabled={loadingMessages} onClick={() => loadMessages()} type="button">
            {loadingMessages ? "加载中" : "加载消息"}
          </button>
        </div>
      </section>

      <div className="status-line">{status}</div>

      <main className="pane">
        <div className="section-header">
          <div>
            <div className="section-eyebrow">Messages</div>
            <h2>对话记录</h2>
          </div>
          <div className="section-actions">
            {messages.length ? (
              <StatusPill tone="info" compact>
                {messages.length} 条消息
              </StatusPill>
            ) : null}
          </div>
        </div>
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
    </div>
  );
}
