import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { api, toErrorMessage } from "../lib/api";
import { formatReadableTime, taskStatusLabel, taskStatusTone } from "../lib/productText";
import type { ConversationSummaryItem, ResearchTaskSummaryItem } from "../types/api";

type HistoryFilter = "all" | "created" | "running" | "completed" | "failed";

const savedFilters: Array<{ value: HistoryFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "running", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

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

  const tasksByConversation = useMemo(() => {
    const mapping = new Map<string, ResearchTaskSummaryItem[]>();
    for (const task of sortedTasks) {
      const current = mapping.get(task.conversation_id) ?? [];
      current.push(task);
      mapping.set(task.conversation_id, current);
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
          latestTask?.topic,
          latestTask?.status ? taskStatusLabel(latestTask.status) : "",
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
            placeholder="按主题、标题、最近进展搜索"
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
          <div className="metric-label">研究</div>
          <div className="metric-value">{conversations.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">生成次数</div>
          <div className="metric-value">{tasks.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">已有结果</div>
          <div className="metric-value">{tasks.filter((task) => task.status === "completed").length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">需要关注</div>
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
          eyebrow="研究时间线"
        />
        <div className="content-pad">
          <div className="status-line" style={{ marginBottom: 12 }}>
            {status}
          </div>
          {filteredConversations.length ? (
            <div className="insight-list">
              {filteredConversations.map((conversation) => {
                const latestTask = latestTaskByConversation.get(conversation.conversation_id);
                const conversationTasks = tasksByConversation.get(conversation.conversation_id) ?? [];
                const completedCount = conversationTasks.filter((task) => task.status === "completed").length;
                return (
                  <article className="insight-item history-record-item" key={conversation.conversation_id}>
                    <div className="item-heading">
                      <div>
                        <div className="section-eyebrow">最近更新 {formatReadableTime(conversation.updated_at)}</div>
                        <div className="insight-title">{conversation.title || conversation.topic}</div>
                      </div>
                      <StatusPill tone={taskStatusTone(latestTask?.status ?? "created")} compact>
                        {taskStatusLabel(latestTask?.status ?? "created")}
                      </StatusPill>
                    </div>
                    <div className="fine-print">主题：{conversation.topic}</div>
                    {latestTask ? (
                      <div className="history-progress-row">
                        <span>最近进展：{latestTask.topic}</span>
                        <span>
                          累计生成 {conversationTasks.length} 次，已完成 {completedCount} 次
                        </span>
                      </div>
                    ) : (
                      <div className="fine-print">还没有生成结果，可以进入研究后先生成一版。</div>
                    )}
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
                          to={`/workspace?conversation_id=${encodeURIComponent(conversation.conversation_id)}&task_id=${encodeURIComponent(latestTask.task_id)}`}
                        >
                          研究总览
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
