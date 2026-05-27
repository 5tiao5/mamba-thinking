import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState, type PropsWithChildren } from "react";

import { api, toErrorMessage } from "../../lib/api";
import { DEMO_CONVERSATION_ID, DEMO_WORKSPACE_TASK_ID } from "../../lib/demoData";
import { cleanDisplayText } from "../../lib/displayText";
import { compactText, formatShortTime, taskStatusLabel, taskStatusTone } from "../../lib/productText";
import type {
  ConversationSummaryItem,
  CreateKnowledgeDocumentPayload,
  FollowUpTaskItem,
  KnowledgeDocumentItem,
  MessageItem,
  ResearchTaskSummaryItem,
  SkillItem,
  ToolItem,
  WorkspaceSnapshot,
} from "../../types/api";
import { AssistantMessageContent } from "../chat/AssistantMessageContent";
import { StatusPill } from "../ui/StatusPill";
import { ToggleSwitch } from "../ui/ToggleSwitch";

function knowledgeMetadata(document: KnowledgeDocumentItem, key: string) {
  const value = document.metadata?.[key];
  return typeof value === "string" ? value : "";
}

export function AppShell({ children }: PropsWithChildren) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [conversations, setConversations] = useState<ConversationSummaryItem[]>([]);
  const [tasks, setTasks] = useState<ResearchTaskSummaryItem[]>([]);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [newTopic, setNewTopic] = useState("AI Agent 工具使用评测");
  const [newTitle, setNewTitle] = useState("新的研究");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [toolDialogOpen, setToolDialogOpen] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);
  const [askContent, setAskContent] = useState("");
  const [askStatus, setAskStatus] = useState("选择或创建一个研究后，可以在这里生成结果或继续追问。");
  const [asking, setAsking] = useState(false);
  const [latestFollowUpTask, setLatestFollowUpTask] = useState<FollowUpTaskItem | null>(null);
  const [runningTaskId, setRunningTaskId] = useState("");
  const [deletingConversationId, setDeletingConversationId] = useState("");
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [toolStatus, setToolStatus] = useState("打开后会同步当前工具状态。");
  const [toolDialogTab, setToolDialogTab] = useState<"tools" | "knowledge">("tools");
  const [toolsLoading, setToolsLoading] = useState(false);
  const [updatingToolId, setUpdatingToolId] = useState("");
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeDraft, setKnowledgeDraft] = useState<CreateKnowledgeDocumentPayload>({
    title: "",
    content: "",
    tags: [],
    source_url: "",
    notes: "",
  });
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState("选择左侧研究后，可以生成并查看简略结果。");
  const [resultSummaryOpen, setResultSummaryOpen] = useState(false);

  const isSettingsPage = location.pathname === "/settings";
  const usesUnifiedResearchWindow = location.pathname === "/" || location.pathname === "/conversation";
  const currentTaskId = searchParams.get("task_id") ?? "";
  const currentConversationId = searchParams.get("conversation_id") ?? "";

  async function loadHistory() {
    const [conversationResponse, taskResponse] = await Promise.all([
      api.listConversations({ limit: 30 }),
      api.listTasks({ limit: 80 }),
    ]);
    setConversations(conversationResponse.data.items);
    setTasks(taskResponse.data.items);
  }

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => {
        if (!cancelled) setApiStatus("online");
      })
      .catch(() => {
        if (!cancelled) setApiStatus("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadHistory().catch(() => {
      if (cancelled) return;
      setConversations([]);
      setTasks([]);
    });
    return () => {
      cancelled = true;
    };
  }, [location.key]);

  const statusTone = useMemo(() => {
    if (apiStatus === "online") return "success";
    if (apiStatus === "offline") return "danger";
    return "neutral";
  }, [apiStatus]);

  const latestTaskByConversation = useMemo(() => {
    const mapping = new Map<string, ResearchTaskSummaryItem>();
    const sortedTasks = [...tasks].sort(
      (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
    );
    for (const task of sortedTasks) {
      if (!mapping.has(task.conversation_id)) {
        mapping.set(task.conversation_id, task);
      }
    }
    return mapping;
  }, [tasks]);

  const activeConversationId = currentConversationId || conversations[0]?.conversation_id || "";
  const demoConversation: ConversationSummaryItem = {
    conversation_id: DEMO_CONVERSATION_ID,
    topic: "AI Agent Tool Use 评测体验案例",
    title: "内置体验：工具调用评测研究",
    status: "active",
    latest_task_id: DEMO_WORKSPACE_TASK_ID,
    created_at: "2026-05-17T09:00:00.000Z",
    updated_at: "2026-05-17T09:08:00.000Z",
  };
  const activeConversation =
    activeConversationId === DEMO_CONVERSATION_ID
      ? demoConversation
      : conversations.find((conversation) => conversation.conversation_id === activeConversationId);
  const activeConversationTask = activeConversationId ? latestTaskByConversation.get(activeConversationId) : undefined;
  const activeTaskId =
    activeConversationId === DEMO_CONVERSATION_ID
      ? currentTaskId || DEMO_WORKSPACE_TASK_ID
      : activeConversationTask?.task_id ?? currentTaskId;

  useEffect(() => {
    let cancelled = false;
    if (!activeConversationId) {
      setMessages([]);
      return () => {
        cancelled = true;
      };
    }
    api
      .listMessages(activeConversationId)
      .then((response) => {
        if (!cancelled) setMessages(response.data.items);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeConversationId, location.key]);

  useEffect(() => {
    let cancelled = false;
    if (!activeTaskId) {
      setWorkspace(null);
      setResultSummaryOpen(false);
      setWorkspaceStatus(activeConversationId ? "这个研究还没有生成结果，点击下方按钮开始生成。" : "先从左侧新建或选择一个研究。");
      return () => {
        cancelled = true;
      };
    }

    setWorkspaceStatus("正在读取研究结果...");
    api
      .getWorkspace(activeTaskId)
      .then((response) => {
        if (cancelled) return;
        setWorkspace(response.data);
        setResultSummaryOpen(false);
        setWorkspaceStatus("");
      })
      .catch(() => {
        if (cancelled) return;
        setWorkspace(null);
        setResultSummaryOpen(false);
        setWorkspaceStatus("当前研究还没有可展示的结果，运行后会在这里显示。");
      });

    return () => {
      cancelled = true;
    };
  }, [activeConversationId, activeTaskId]);

  const workspaceDirections = useMemo(() => {
    if (!workspace) return [];
    const branches = workspace.taxonomy.branches.map((branch) => cleanDisplayText(branch.name, 80)).filter(Boolean);
    const ideas = workspace.ideas.map((idea) => cleanDisplayText(idea.title, 100)).filter(Boolean);
    return [...branches, ...ideas].slice(0, 6);
  }, [workspace]);

  async function createConversationFromSidebar() {
    if (!newTopic.trim()) return;
    setCreatingConversation(true);
    try {
      const response = await api.createConversation({
        topic: newTopic.trim(),
        title: newTitle.trim() || undefined,
      });
      setCreateDialogOpen(false);
      setAskStatus("研究已创建。现在可以生成结果，也可以先补充你的要求。");
      await loadHistory();
      navigate(`/conversation?conversation_id=${encodeURIComponent(response.data.conversation_id)}`);
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setCreatingConversation(false);
    }
  }

  async function generateResearchResult() {
    if (!activeConversationId || !activeConversation) {
      setAskStatus("请先在左侧创建或选择一个研究。");
      return;
    }

    setRunningTaskId(activeTaskId || "creating");
    setAskStatus("正在生成研究结果...");
    try {
      let taskId = activeTaskId;
      if (!taskId) {
        const created = await api.createTask({
          conversation_id: activeConversationId,
          topic: activeConversation.topic,
          mode: "balanced",
          use_shared_knowledge: true,
        });
        taskId = created.data.task_id;
      }
      await api.runTask(taskId);
      setAskStatus("结果已生成，可以继续追问来调整方向。");
      await loadHistory();
      navigate(`/conversation?conversation_id=${encodeURIComponent(activeConversationId)}&task_id=${encodeURIComponent(taskId)}`);
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setRunningTaskId("");
    }
  }

  async function submitSideQuestion() {
    if (!activeConversationId) {
      setAskStatus("请先在左侧创建或选择一个研究。");
      return;
    }
    if (!askContent.trim()) {
      setAskStatus("请输入追问内容。");
      return;
    }

    setAsking(true);
    setAskStatus("正在继续追问...");
    try {
      const response = await api.continueConversation({
        conversation_id: activeConversationId,
        content: askContent.trim(),
        create_follow_up_task: true,
        mode: "balanced",
      });
      setAskContent("");
      setLatestFollowUpTask(response.data.follow_up_task ?? null);
      setAskStatus(response.data.follow_up_task ? "已生成后续研究任务，可运行后刷新结果。" : "追问已发送。");
      await loadHistory();
      navigate(`/conversation?conversation_id=${encodeURIComponent(activeConversationId)}`);
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setAsking(false);
    }
  }

  async function runFollowUpTask(taskId: string) {
    setRunningTaskId(taskId);
    setAskStatus("正在运行后续研究任务...");
    try {
      await api.runTask(taskId);
      setAskStatus("新的结果已生成，右侧窗口已刷新。");
      await loadHistory();
      navigate(`/conversation?conversation_id=${encodeURIComponent(activeConversationId)}&task_id=${encodeURIComponent(taskId)}`);
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setRunningTaskId("");
    }
  }

  async function deleteConversation(conversationId: string) {
    const target = conversations.find((conversation) => conversation.conversation_id === conversationId);
    const confirmed = window.confirm(`确定删除「${target?.title || target?.topic || "这个研究"}」吗？相关消息和结果也会一起删除。`);
    if (!confirmed) return;

    setDeletingConversationId(conversationId);
    try {
      await api.deleteConversation(conversationId);
      setAskStatus("研究记录已删除。");
      const remaining = conversations.filter((conversation) => conversation.conversation_id !== conversationId);
      setConversations(remaining);
      await loadHistory();
      if (conversationId === activeConversationId) {
        setMessages([]);
        setWorkspace(null);
        setLatestFollowUpTask(null);
        const nextConversation = remaining[0];
        navigate(nextConversation ? `/conversation?conversation_id=${encodeURIComponent(nextConversation.conversation_id)}` : "/");
      }
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setDeletingConversationId("");
    }
  }

  async function openToolDialog() {
    setToolDialogOpen(true);
    setToolDialogTab("tools");
    setToolsLoading(true);
    setToolStatus("正在加载研究工具和能力...");
    try {
      const [toolResponse, skillResponse] = await Promise.all([api.listTools(), api.listSkills()]);
      setTools(toolResponse.data);
      setSkills(skillResponse.data);
      setToolStatus("研究工具已同步。");
    } catch (error) {
      setTools([]);
      setSkills([]);
      setToolStatus(`加载失败：${toErrorMessage(error)}`);
    } finally {
      setToolsLoading(false);
    }
  }

  async function openKnowledgeDialog() {
    setToolDialogOpen(true);
    setToolDialogTab("knowledge");
    await loadKnowledgeDocuments();
  }

  async function toggleTool(tool: ToolItem) {
    setUpdatingToolId(tool.tool_id);
    setToolStatus(`正在${tool.enabled ? "停用" : "启用"} ${tool.display_name}...`);
    try {
      const response = await api.updateTool(tool.tool_id, {
        enabled: !tool.enabled,
        config: tool.config,
      });
      setTools((current) => current.map((item) => (item.tool_id === tool.tool_id ? response.data : item)));
      setToolStatus(`${response.data.display_name} 已${response.data.enabled ? "启用" : "停用"}。`);
    } catch (error) {
      setToolStatus(`更新失败：${toErrorMessage(error)}`);
    } finally {
      setUpdatingToolId("");
    }
  }

  function getToolDisplayName(toolId: string) {
    return tools.find((tool) => tool.tool_id === toolId)?.display_name ?? toolId;
  }

  async function loadKnowledgeDocuments() {
    setKnowledgeLoading(true);
    setToolStatus("正在同步知识库...");
    try {
      const response = knowledgeQuery.trim()
        ? await api.searchKnowledge({ q: knowledgeQuery.trim(), by: "keyword", limit: 20 })
        : await api.listKnowledgeDocuments();
      setKnowledgeDocuments(response.data.items);
      setToolStatus(knowledgeQuery.trim() ? `搜索到 ${response.data.items.length} 条资料。` : "资料库已同步。");
    } catch (error) {
      setToolStatus(`知识库加载失败：${toErrorMessage(error)}`);
    } finally {
      setKnowledgeLoading(false);
    }
  }

  async function createKnowledgeDocument() {
    if (!knowledgeDraft.title.trim() || !knowledgeDraft.content.trim()) {
      setToolStatus("请先填写知识标题和正文。");
      return;
    }

    setKnowledgeLoading(true);
    setToolStatus("正在导入知识...");
    try {
      const response = await api.createKnowledgeDocument({
        ...knowledgeDraft,
        title: knowledgeDraft.title.trim(),
        content: knowledgeDraft.content.trim(),
        tags: knowledgeDraft.tags?.map((tag) => tag.trim()).filter(Boolean) ?? [],
        source_url: knowledgeDraft.source_url?.trim() || null,
        notes: knowledgeDraft.notes?.trim() || null,
      });
      setKnowledgeDocuments((current) => [response.data, ...current]);
      setKnowledgeDraft({ title: "", content: "", tags: [], source_url: "", notes: "" });
      setToolStatus("资料已导入，后续研究会从资料库检索相关上下文。");
    } catch (error) {
      setToolStatus(`导入失败：${toErrorMessage(error)}`);
    } finally {
      setKnowledgeLoading(false);
    }
  }

  async function deleteKnowledgeDocument(documentId: string) {
    setKnowledgeLoading(true);
    setToolStatus("正在删除知识...");
    try {
      await api.deleteKnowledgeDocument(documentId);
      setKnowledgeDocuments((current) => current.filter((item) => item.document_id !== documentId));
      setToolStatus("知识已删除。");
    } catch (error) {
      setToolStatus(`删除失败：${toErrorMessage(error)}`);
    } finally {
      setKnowledgeLoading(false);
    }
  }

  const shouldShowGenerateButton = Boolean(activeConversationId && !workspace && !latestFollowUpTask);

  return (
    <div className="app-shell app-shell-single">
      <aside className="chat-sidebar">
        <div className="chat-brand-row">
          <Link className="brand-block" to={activeConversationId ? `/conversation?conversation_id=${activeConversationId}` : "/"}>
            <div className="brand-mark">PA</div>
            <div>
              <h1>Product Agent</h1>
              <p>科研调研助手</p>
            </div>
          </Link>
        </div>

        <button className="new-chat-button" onClick={() => setCreateDialogOpen(true)} type="button">
          新建研究
        </button>

        <Link
          className="demo-research-button"
          to={`/conversation?conversation_id=${DEMO_CONVERSATION_ID}&task_id=${DEMO_WORKSPACE_TASK_ID}`}
        >
          体验示例研究
        </Link>

        <div className="sidebar-nav" aria-label="全局导航">
          <Link className={location.pathname === "/history" ? "sidebar-nav-link sidebar-nav-active" : "sidebar-nav-link"} to="/history">
            历史
          </Link>
          <button className="sidebar-nav-link" onClick={() => void openKnowledgeDialog()} type="button">
            资料
          </button>
          <Link className={isSettingsPage ? "sidebar-nav-link sidebar-nav-active" : "sidebar-nav-link"} to="/settings">
            设置
          </Link>
        </div>

        <div className="sidebar-section-title">研究记录</div>
        <div className="chat-history-list">
          {conversations.length ? (
            conversations.map((conversation) => {
              const latestTask = latestTaskByConversation.get(conversation.conversation_id);
              return (
                <div
                  className={
                    conversation.conversation_id === activeConversationId
                      ? "chat-history-item chat-history-active"
                      : "chat-history-item"
                  }
                  key={conversation.conversation_id}
                >
                  <Link
                    className="chat-history-link"
                    to={`/conversation?conversation_id=${encodeURIComponent(conversation.conversation_id)}`}
                  >
                    <span>{conversation.title || conversation.topic}</span>
                    <small>{conversation.topic}</small>
                    <div className="chat-history-meta">
                      <span>{formatShortTime(conversation.updated_at)}</span>
                      {latestTask ? (
                        <StatusPill tone={taskStatusTone(latestTask.status)} compact>
                          {taskStatusLabel(latestTask.status)}
                        </StatusPill>
                      ) : null}
                    </div>
                  </Link>
                  <button
                    aria-label="删除研究"
                    className="history-delete-button"
                    disabled={deletingConversationId === conversation.conversation_id}
                    onClick={() => deleteConversation(conversation.conversation_id)}
                    title="删除研究"
                    type="button"
                  >
                    {deletingConversationId === conversation.conversation_id ? "..." : "×"}
                  </button>
                </div>
              );
            })
          ) : (
            <div className="sidebar-empty">暂无研究。可以新建研究，或点击上方示例先体验流程。</div>
          )}
        </div>

        <div className="sidebar-service">
          <StatusPill tone={statusTone} compact>
            {apiStatus === "online" ? "服务可用" : apiStatus === "offline" ? "服务未连接" : "检查中"}
          </StatusPill>
        </div>
      </aside>

      <main className="single-research-stage">
        {!usesUnifiedResearchWindow ? (
          <div className="single-settings-window">{children}</div>
        ) : (
          <section className="research-window">
            <header className="research-window-head">
              <div>
                <div className="section-eyebrow">当前研究</div>
                <h2>{activeConversation?.title || activeConversation?.topic || "选择一个研究"}</h2>
                <p>{activeConversation?.topic || "左侧新建研究后，这里会成为唯一的结果生成与追问窗口。"}</p>
              </div>
              {activeConversationId ? (
                <div className="research-window-actions">
                  {activeTaskId ? (
                    <Link className="secondary-button" to={`/workspace?task_id=${encodeURIComponent(activeTaskId)}`}>
                      完整工作台
                    </Link>
                  ) : null}
                  <button
                    className="primary-button"
                    disabled={Boolean(runningTaskId)}
                    onClick={generateResearchResult}
                    type="button"
                  >
                    {runningTaskId && runningTaskId !== latestFollowUpTask?.task_id ? "生成中" : workspace ? "重新生成" : "生成结果"}
                  </button>
                </div>
              ) : null}
            </header>

            <div className="research-window-body research-window-body-side">
              <section className="research-chat-area">
                <div className="unified-message-list">
                  {messages.length ? (
                    messages.slice(-8).map((message) => (
                      <div className={`unified-message unified-message-${message.role}`} key={message.message_id}>
                        <div className={`message-avatar message-avatar-${message.role}`} aria-hidden="true">
                          {message.role === "assistant" ? (
                            "AI"
                          ) : (
                            "你"
                          )}
                        </div>
                        <div className="unified-message-bubble">
                          <span className="message-speaker">{message.role === "user" ? "你" : "智能体"}</span>
                          {message.role === "assistant" ? (
                            <AssistantMessageContent content={message.content} />
                          ) : (
                            <p>{cleanDisplayText(message.content)}</p>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="sidebar-empty">这里会显示你和智能体围绕该研究的追加对话。</div>
                  )}
                </div>

                {latestFollowUpTask ? (
                  <div className="ask-task-box">
                    <strong>{cleanDisplayText(latestFollowUpTask.topic, 180)}</strong>
                    <div className="button-row">
                      <button
                        className="primary-button"
                        disabled={runningTaskId === latestFollowUpTask.task_id}
                        onClick={() => runFollowUpTask(latestFollowUpTask.task_id)}
                        type="button"
                      >
                        {runningTaskId === latestFollowUpTask.task_id ? "运行中" : "运行并刷新结果"}
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="unified-composer">
                  <textarea
                    className="input textarea ask-textarea"
                    onChange={(event) => setAskContent(event.target.value)}
                    placeholder="对结果不满意就继续追问，例如：缩小到近两年论文，重新总结三个可做方向"
                    value={askContent}
                  />
                  <div className="unified-composer-footer">
                    <div className="composer-left-tools">
                      <button
                        className="tool-icon-button"
                        onClick={openToolDialog}
                        aria-label="研究设置"
                        title="研究设置"
                        type="button"
                      >
                        <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                          <path d="M4 7h5" />
                          <path d="M15 7h5" />
                          <path d="M4 17h5" />
                          <path d="M15 17h5" />
                          <path d="M4 12h10" />
                          <path d="M18 12h2" />
                          <circle cx="12" cy="7" r="3" />
                          <circle cx="12" cy="17" r="3" />
                          <circle cx="16" cy="12" r="2" />
                        </svg>
                      </button>
                      <div className="composer-status-text" role="status">{askStatus}</div>
                    </div>
                    <button
                      className="primary-button"
                      disabled={asking || !activeConversationId}
                      onClick={submitSideQuestion}
                      type="button"
                    >
                      {asking ? "发送中" : "发送追问"}
                    </button>
                  </div>
                </div>
              </section>

              <aside className="research-result-area" aria-label="研究结果摘要">
                {workspace ? (
                  resultSummaryOpen ? (
                    <>
                      <div className="result-summary-head">
                        <div>
                          <div className="section-eyebrow">本轮结果摘要</div>
                          <div className="result-topic">{cleanDisplayText(workspace.topic, 160)}</div>
                        </div>
                        <button className="secondary-button" onClick={() => setResultSummaryOpen(false)} type="button">
                          收起
                        </button>
                      </div>
                      <p className="result-brief-summary">{compactText(cleanDisplayText(workspace.summary), 360)}</p>
                      <div className="result-directions" aria-label="科研方向">
                        {workspaceDirections.map((direction) => (
                          <span className="direction-chip" key={direction}>
                            {direction}
                          </span>
                        ))}
                      </div>
                      <div className="result-metric-strip" aria-label="结果概览">
                        <div>
                          <span>论文</span>
                          <strong>{workspace.papers.length}</strong>
                        </div>
                        <div>
                          <span>空白</span>
                          <strong>{workspace.gaps.length}</strong>
                        </div>
                        <div>
                          <span>建议</span>
                          <strong>{workspace.ideas.length}</strong>
                        </div>
                        <div>
                          <span>匹配</span>
                          <strong>{workspace.alignment_score.toFixed(2)}</strong>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="result-compact-copy">
                        <span>本轮结果</span>
                        <strong>{cleanDisplayText(workspace.topic, 120)}</strong>
                      </div>
                      <div className="result-compact-metrics" aria-label="结果概览">
                        <span>论文 {workspace.papers.length}</span>
                        <span>空白 {workspace.gaps.length}</span>
                        <span>建议 {workspace.ideas.length}</span>
                        <span>匹配度 {workspace.alignment_score.toFixed(2)}</span>
                      </div>
                      <button className="secondary-button" onClick={() => setResultSummaryOpen(true)} type="button">
                        展开摘要
                      </button>
                      {workspaceDirections.length ? (
                        <div className="result-side-hints">
                          <span>可继续追问</span>
                          <div>
                            {workspaceDirections.slice(0, 5).map((direction) => (
                              <button
                                className="result-hint-chip"
                                key={direction}
                                onClick={() => setAskContent(`继续展开：${direction}`)}
                                type="button"
                              >
                                {direction}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </>
                  )
                ) : (
                  <div className="research-empty-state">
                    <strong>{workspaceStatus}</strong>
                    {shouldShowGenerateButton ? (
                      <button
                        className="primary-button"
                        disabled={Boolean(runningTaskId)}
                        onClick={generateResearchResult}
                        type="button"
                      >
                        {runningTaskId ? "生成中" : "生成研究结果"}
                      </button>
                    ) : null}
                  </div>
                )}
              </aside>
            </div>
          </section>
        )}
      </main>

      {createDialogOpen ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="新建研究">
          <div className="create-dialog">
            <div className="create-dialog-head">
              <div>
                <div className="section-eyebrow">新建研究</div>
                <h2>新建研究</h2>
              </div>
              <button className="ghost-button" onClick={() => setCreateDialogOpen(false)} type="button">
                关闭
              </button>
            </div>
            <label className="field">
              <span>研究主题</span>
              <input
                className="input"
                onChange={(event) => setNewTopic(event.target.value)}
                placeholder="例如：多智能体科研助手的评测方法"
                value={newTopic}
              />
            </label>
            <label className="field">
              <span>会话标题</span>
              <input
                className="input"
                onChange={(event) => setNewTitle(event.target.value)}
                placeholder="用于左侧研究记录展示"
                value={newTitle}
              />
            </label>
            <div className="button-row">
              <button className="secondary-button" onClick={() => setCreateDialogOpen(false)} type="button">
                取消
              </button>
              <button
                className="primary-button"
                disabled={creatingConversation || !newTopic.trim()}
                onClick={createConversationFromSidebar}
                type="button"
              >
                {creatingConversation ? "创建中" : "创建研究"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {toolDialogOpen ? (
        <div className="modal-backdrop modal-backdrop-blur" role="dialog" aria-modal="true" aria-label="研究设置">
          <div className="tool-dialog">
            <div className="create-dialog-head">
              <div>
                <div className="section-eyebrow">研究设置</div>
                <h2>研究设置</h2>
              </div>
              <button className="ghost-button" onClick={() => setToolDialogOpen(false)} type="button">
                关闭
              </button>
            </div>

            <div className="workspace-side-status">{toolStatus}</div>

            <div className="tool-dialog-tabs" role="tablist" aria-label="工具和知识库设置">
              <button
                className={toolDialogTab === "tools" ? "tool-dialog-tab tool-dialog-tab-active" : "tool-dialog-tab"}
                onClick={() => setToolDialogTab("tools")}
                type="button"
              >
                工具能力
              </button>
              <button
                className={toolDialogTab === "knowledge" ? "tool-dialog-tab tool-dialog-tab-active" : "tool-dialog-tab"}
                onClick={() => {
                  setToolDialogTab("knowledge");
                  void loadKnowledgeDocuments();
                }}
                type="button"
              >
                知识库
              </button>
            </div>

            <div className="tool-dialog-body">
              {toolDialogTab === "tools" ? (
              <>
              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>可用工具</strong>
                  <StatusPill tone={toolsLoading ? "neutral" : "success"} compact>
                    {toolsLoading ? "加载中" : `${tools.length} 项`}
                  </StatusPill>
                </div>
                <div className="tool-option-list">
                  {tools.length ? (
                    tools.map((tool) => (
                      <div className="tool-option" key={tool.tool_id}>
                        <div>
                          <strong>{tool.display_name}</strong>
                          <p>{tool.description}</p>
                        </div>
                        <ToggleSwitch
                          checked={tool.enabled}
                          disabled={updatingToolId === tool.tool_id}
                          label={updatingToolId === tool.tool_id ? "更新中" : tool.enabled ? "启用" : "关闭"}
                          onChange={() => toggleTool(tool)}
                        />
                      </div>
                    ))
                  ) : (
                    <div className="sidebar-empty">{toolsLoading ? "正在加载工具..." : "暂无可展示工具。"}</div>
                  )}
                </div>
              </section>

              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>相关能力</strong>
                  <StatusPill tone="info" compact>
                    {skills.length} 项
                  </StatusPill>
                </div>
                <div className="skill-chip-list">
                  {skills.length ? (
                    skills.map((skill) => (
                      <div className="skill-chip-card" key={skill.skill_id}>
                        <div>
                          <strong>{skill.display_name}</strong>
                          <p>{skill.description}</p>
                        </div>
                        <div className="button-row">
                          {skill.required_tools.length ? (
                            skill.required_tools.map((toolId) => (
                              <StatusPill key={toolId} tone="info" compact>
                                {getToolDisplayName(toolId)}
                              </StatusPill>
                            ))
                          ) : (
                            <StatusPill tone="neutral" compact>
                              无依赖
                            </StatusPill>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="sidebar-empty">{toolsLoading ? "正在加载能力..." : "暂无可展示能力。"}</div>
                  )}
                </div>
              </section>
              </>
              ) : (
              <>
              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>导入资料</strong>
                  <StatusPill tone={knowledgeLoading ? "neutral" : "info"} compact>
                    {knowledgeLoading ? "同步中" : "资料库"}
                  </StatusPill>
                </div>
                <div className="knowledge-form">
                  <input
                    className="input"
                    onChange={(event) => setKnowledgeDraft((current) => ({ ...current, title: event.target.value }))}
                    placeholder="知识标题"
                    value={knowledgeDraft.title}
                  />
                  <textarea
                    className="input textarea"
                    onChange={(event) => setKnowledgeDraft((current) => ({ ...current, content: event.target.value }))}
                    placeholder="粘贴论文摘要、调研笔记或已有结论"
                    value={knowledgeDraft.content}
                  />
                  <input
                    className="input"
                    onChange={(event) =>
                      setKnowledgeDraft((current) => ({
                        ...current,
                        tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean),
                      }))
                    }
                    placeholder="标签，用逗号分隔，例如 tool-use,evaluation"
                    value={knowledgeDraft.tags?.join(",") ?? ""}
                  />
                  <div className="knowledge-form-grid">
                    <input
                      className="input"
                      onChange={(event) => setKnowledgeDraft((current) => ({ ...current, source_url: event.target.value }))}
                      placeholder="来源链接，可选"
                      value={knowledgeDraft.source_url ?? ""}
                    />
                    <input
                      className="input"
                      onChange={(event) => setKnowledgeDraft((current) => ({ ...current, notes: event.target.value }))}
                      placeholder="备注，可选"
                      value={knowledgeDraft.notes ?? ""}
                    />
                  </div>
                  <button className="primary-button" disabled={knowledgeLoading} onClick={createKnowledgeDocument} type="button">
                    导入资料
                  </button>
                </div>
              </section>

              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>资料检索</strong>
                  <StatusPill tone="info" compact>
                    {knowledgeDocuments.length} 条
                  </StatusPill>
                </div>
                <div className="knowledge-search-row">
                  <input
                    className="input"
                    onChange={(event) => setKnowledgeQuery(event.target.value)}
                    placeholder="搜索关键词；留空查看全部资料"
                    value={knowledgeQuery}
                  />
                  <button className="secondary-button" disabled={knowledgeLoading} onClick={loadKnowledgeDocuments} type="button">
                    搜索
                  </button>
                </div>
                <div className="knowledge-doc-list">
                  {knowledgeDocuments.length ? (
                    knowledgeDocuments.map((document) => (
                      <article className="knowledge-doc-card" key={document.document_id}>
                        <div>
                          <strong>{cleanDisplayText(document.title, 120)}</strong>
                          <p>{compactText(cleanDisplayText(document.content), 220)}</p>
                          <div className="knowledge-doc-meta">
                            {document.tags.length ? <span>{document.tags.join(" / ")}</span> : null}
                            {knowledgeMetadata(document, "notes") ? (
                              <span>{cleanDisplayText(knowledgeMetadata(document, "notes"), 120)}</span>
                            ) : null}
                            {knowledgeMetadata(document, "source_url") ? (
                              <a href={knowledgeMetadata(document, "source_url")} rel="noreferrer" target="_blank">
                                来源
                              </a>
                            ) : null}
                          </div>
                        </div>
                        <button
                          aria-label="删除资料"
                          className="history-delete-button"
                          disabled={knowledgeLoading}
                          onClick={() => deleteKnowledgeDocument(document.document_id)}
                          title="删除资料"
                          type="button"
                        >
                          x
                        </button>
                      </article>
                    ))
                  ) : (
                    <div className="sidebar-empty">暂无资料。可以先导入一条论文摘要或调研笔记。</div>
                  )}
                </div>
              </section>
              </>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
