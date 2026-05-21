import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { api, toErrorMessage } from "../lib/api";
import type { ConversationSummaryItem, ResearchTaskSummaryItem } from "../types/api";

type HistoryFilter = "all" | "created" | "running" | "completed" | "failed";

const savedFilters: Array<{ value: HistoryFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "running", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function statusTone(status: string): "info" | "success" | "danger" | "warning" | "neutral" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "info";
  if (status === "created") return "warning";
  return "neutral";
}

function statusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "running") return "运行中";
  if (status === "created") return "待运行";
  return status || "未知";
}

export function HistoryPage() {
  const [conversations, setConversations] = useState<ConversationSummaryItem[]>([]);
  const [tasks, setTasks] = useState<ResearchTaskSummaryItem[]>([]);
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState<HistoryFilter>("all");
  const [status, setStatus] = useState("正在加载历史会话和研究任务...");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void loadHistory();
  }, []);

  const sortedTasks = useMemo(
    () =>
      [...tasks].sort(
        (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
      ),
    [tasks]
  );

  const latestTaskByConversation = useMemo(() => {
    const mapping = new Map<string, ResearchTaskSummaryItem>();
    for (const task of sortedTasks) {
      if (!mapping.has(task.conversation_id)) {
        mapping.set(task.conversation_id, task);
      }
    }
    return mapping;
  }, [sortedTasks]);

  const filteredConversations = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return [...conversations]
      .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
      .filter((conversation) => {
        const latestTask = latestTaskByConversation.get(conversation.conversation_id);
        if (activeFilter !== "all") {
          const taskStatus = latestTask?.status ?? "created";
          if (taskStatus !== activeFilter) {
            return false;
          }
        }

        if (!keyword) {
          return true;
        }

        const haystack = [
          conversation.topic,
          conversation.title,
          conversation.conversation_id,
          latestTask?.topic,
          latestTask?.task_id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(keyword);
      });
  }, [activeFilter, conversations, latestTaskByConversation, search]);

  async function loadHistory() {
    setLoading(true);
    setStatus("正在同步历史记录...");
    try {
      const [conversationResponse, taskResponse] = await Promise.all([
        api.listConversations({ limit: 50 }),
        api.listTasks({ limit: 100 }),
      ]);
      setConversations(conversationResponse.data.items);
      setTasks(taskResponse.data.items);
      setStatus("历史记录加载完成。");
    } catch (error) {
      setStatus(`历史记录加载失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="dense-layout">
      <section className="surface content-pad history-toolbar">
        <label>
          <span className="field-label">搜索研究记录</span>
          <input
            className="input"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="按主题、任务 ID、会话标题搜索"
            value={search}
          />
        </label>
        <div>
          <span className="field-label">状态筛选</span>
          <div className="button-row">
            {savedFilters.map((filter) => (
              <button
                className={filter.value === activeFilter ? "primary-button" : "secondary-button"}
                key={filter.value}
                onClick={() => setActiveFilter(filter.value)}
                type="button"
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="metrics-strip">
        <div className="metric-cell">
          <div className="metric-label">会话</div>
          <div className="metric-value">{conversations.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">任务</div>
          <div className="metric-value">{tasks.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">完成</div>
          <div className="metric-value">{tasks.filter((task) => task.status === "completed").length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">失败</div>
          <div className="metric-value">{tasks.filter((task) => task.status === "failed").length}</div>
        </div>
      </section>

      <section className="pane">
        <SectionHeader
          actions={
            <StatusPill tone={loading ? "warning" : filteredConversations.length ? "info" : "neutral"}>
              {loading ? "加载中" : `${filteredConversations.length} 条记录`}
            </StatusPill>
          }
          title="历史研究"
          eyebrow="Saved work"
        />
        <div className="content-pad">
          <div className="status-line" style={{ marginBottom: 12 }}>
            {status}
          </div>
          {filteredConversations.length ? (
            <div className="insight-list">
              {filteredConversations.map((conversation) => {
                const latestTask = latestTaskByConversation.get(conversation.conversation_id);
                return (
                  <article className="insight-item" key={conversation.conversation_id}>
                    <div className="item-heading">
                      <div>
                        <div className="section-eyebrow">{conversation.conversation_id}</div>
                        <div className="insight-title">{conversation.title || conversation.topic}</div>
                      </div>
                      <StatusPill tone={statusTone(latestTask?.status ?? "created")} compact>
                        {statusLabel(latestTask?.status ?? "created")}
                      </StatusPill>
                    </div>
                    <div className="fine-print">主题：{conversation.topic}</div>
                    {latestTask ? (
                      <div className="fine-print">
                        最近任务：{latestTask.task_id} / {latestTask.topic}
                      </div>
                    ) : (
                      <div className="fine-print">还没有研究任务，可以先回到首页创建。</div>
                    )}
                    <div className="fine-print">更新时间：{formatTime(conversation.updated_at)}</div>
                    <div className="button-row" style={{ marginTop: 12 }}>
                      <Link
                        className="secondary-button"
                        to={`/conversation?conversation_id=${encodeURIComponent(conversation.conversation_id)}`}
                      >
                        继续对话
                      </Link>
                      {latestTask ? (
                        <Link
                          className="ghost-button"
                          to={`/workspace?task_id=${encodeURIComponent(latestTask.task_id)}`}
                        >
                          打开工作台
                        </Link>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">
              当前没有匹配的历史记录。你可以先回首页创建会话和研究任务，后续就会在这里累积起来。
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
