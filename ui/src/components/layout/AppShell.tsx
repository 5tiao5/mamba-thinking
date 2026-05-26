import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type PropsWithChildren } from "react";

import { api, toErrorMessage } from "../../lib/api";
import { DEMO_CONVERSATION_ID, DEMO_WORKSPACE_TASK_ID } from "../../lib/demoData";
import { cleanDisplayText } from "../../lib/displayText";
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
import { StatusPill } from "../ui/StatusPill";
import { ToggleSwitch } from "../ui/ToggleSwitch";

function formatShortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function taskStatusTone(status?: string): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "failed") return "danger";
  if (status === "created") return "warning";
  return "neutral";
}

function compactText(value: string, maxLength = 260) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
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
  });
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState("选择左侧研究后，可以生成并查看简略结果。");
  const [resultPanePercent, setResultPanePercent] = useState(44);

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
        setWorkspaceStatus("");
      })
      .catch(() => {
        if (cancelled) return;
        setWorkspace(null);
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
    setToolStatus("正在加载工具调用设置...");
    try {
      const [toolResponse, skillResponse] = await Promise.all([api.listTools(), api.listSkills()]);
      setTools(toolResponse.data);
      setSkills(skillResponse.data);
      setToolStatus("工具设置已同步。");
    } catch (error) {
      setTools([]);
      setSkills([]);
      setToolStatus(`加载失败：${toErrorMessage(error)}`);
    } finally {
      setToolsLoading(false);
    }
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
      setToolStatus(knowledgeQuery.trim() ? `搜索到 ${response.data.items.length} 条知识。` : "知识库已同步。");
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
      });
      setKnowledgeDocuments((current) => [response.data, ...current]);
      setKnowledgeDraft({ title: "", content: "", tags: [] });
      setToolStatus("知识已导入，后续可用于检索和追问上下文。");
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

  function startPaneResize(event: ReactPointerEvent<HTMLDivElement>) {
    const container = event.currentTarget.parentElement;
    if (!container) return;
    const bounds = container.getBoundingClientRect();
    event.currentTarget.setPointerCapture(event.pointerId);

    function handlePointerMove(moveEvent: PointerEvent) {
      const nextPercent = ((moveEvent.clientY - bounds.top) / bounds.height) * 100;
      setResultPanePercent(Math.min(72, Math.max(24, nextPercent)));
    }

    function handlePointerUp() {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
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
                          {latestTask.status}
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
                <div className="section-eyebrow">Research</div>
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

            <div
              className="research-window-body"
              style={{ "--result-pane-size": `${resultPanePercent}%` } as CSSProperties}
            >
              <section className="research-result-area">
                {workspace ? (
                  <>
                    <div className="result-topic">{cleanDisplayText(workspace.topic, 160)}</div>
                    <p className="result-brief-summary">{compactText(cleanDisplayText(workspace.summary), 360)}</p>
                    <div className="result-directions" aria-label="科研方向">
                      {workspaceDirections.map((direction) => (
                        <span className="direction-chip" key={direction}>
                          {direction}
                        </span>
                      ))}
                    </div>
                  </>
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
              </section>

              <div
                className="pane-resizer"
                onPointerDown={startPaneResize}
                role="separator"
                aria-label="调整结果和对话比例"
                aria-orientation="horizontal"
                title="拖动调整结果和对话比例"
              >
                <span />
              </div>

              <section className="research-chat-area">
                <div className="unified-message-list">
                  {messages.length ? (
                    messages.slice(-8).map((message) => (
                      <div className={`unified-message unified-message-${message.role}`} key={message.message_id}>
                        <span>{message.role === "user" ? "你" : "智能体"}</span>
                        <p>{cleanDisplayText(message.content)}</p>
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
                        aria-label="工具调用设置"
                        title="工具调用设置"
                        type="button"
                      >
                        ⚙
                      </button>
                      <div className="workspace-side-status">{askStatus}</div>
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
            </div>
          </section>
        )}
      </main>

      {createDialogOpen ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="新建研究">
          <div className="create-dialog">
            <div className="create-dialog-head">
              <div>
                <div className="section-eyebrow">New Research</div>
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
        <div className="modal-backdrop modal-backdrop-blur" role="dialog" aria-modal="true" aria-label="工具调用设置">
          <div className="tool-dialog">
            <div className="create-dialog-head">
              <div>
                <div className="section-eyebrow">Tools</div>
                <h2>工具调用设置</h2>
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
                工具
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
                  <strong>导入知识</strong>
                  <StatusPill tone={knowledgeLoading ? "neutral" : "info"} compact>
                    {knowledgeLoading ? "同步中" : "Knowledge"}
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
                  <button className="primary-button" disabled={knowledgeLoading} onClick={createKnowledgeDocument} type="button">
                    导入知识
                  </button>
                </div>
              </section>

              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>知识检索</strong>
                  <StatusPill tone="info" compact>
                    {knowledgeDocuments.length} 条
                  </StatusPill>
                </div>
                <div className="knowledge-search-row">
                  <input
                    className="input"
                    onChange={(event) => setKnowledgeQuery(event.target.value)}
                    placeholder="搜索关键词；留空则查看全部"
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
                          <strong>{document.title}</strong>
                          <p>{document.content}</p>
                          {document.tags.length ? <small>{document.tags.join(" / ")}</small> : null}
                        </div>
                        <button
                          className="history-delete-button"
                          disabled={knowledgeLoading}
                          onClick={() => deleteKnowledgeDocument(document.document_id)}
                          title="删除知识"
                          type="button"
                        >
                          ×
                        </button>
                      </article>
                    ))
                  ) : (
                    <div className="sidebar-empty">暂无知识文档。可以先导入一条论文摘要或调研笔记。</div>
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
