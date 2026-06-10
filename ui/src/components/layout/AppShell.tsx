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
  KnowledgeScope,
  KnowledgeDocumentItem,
  MessageItem,
  PaperImportCandidateItem,
  ResearchTaskSummaryItem,
  SkillItem,
  ToolItem,
  WorkspaceSnapshot,
} from "../../types/api";
import { AssistantMessageContent } from "../chat/AssistantMessageContent";
import { MessageSourceTrace } from "../chat/MessageSourceTrace";
import { SegmentedControl } from "../ui/SegmentedControl";
import { StatusPill } from "../ui/StatusPill";
import { ToggleSwitch } from "../ui/ToggleSwitch";

const modeOptions = [
  { value: "default", label: "标准" },
  { value: "fast", label: "快速" },
  { value: "balanced", label: "均衡" },
];

const knowledgeScopeOptions: Array<{ value: KnowledgeScope; label: string }> = [
  { value: "conversation_only", label: "仅会话" },
  { value: "shared", label: "共享知识" },
  { value: "none", label: "关闭增强" },
];

function knowledgeScopeLabel(scope: KnowledgeScope) {
  switch (scope) {
    case "conversation_only":
      return "仅当前会话知识";
    case "none":
      return "不启用知识增强";
    case "shared":
    default:
      return "当前会话 + 共享知识";
  }
}

function knowledgeMetadata(document: KnowledgeDocumentItem, key: string) {
  const value = document.metadata?.[key];
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return "";
}

function paperSourceLabel(candidate: PaperImportCandidateItem) {
  if (candidate.venue?.trim()) {
    return candidate.venue.trim();
  }
  if (candidate.source === "openalex") {
    return "OpenAlex";
  }
  if (candidate.source === "arxiv") {
    return "arXiv";
  }
  return candidate.source;
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
  const [runMode, setRunMode] = useState("balanced");
  const [knowledgeScope, setKnowledgeScope] = useState<KnowledgeScope>("shared");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [toolDialogOpen, setToolDialogOpen] = useState(false);
  const [skillDialogOpen, setSkillDialogOpen] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);
  const [askContent, setAskContent] = useState("");
  const [askStatus, setAskStatus] = useState("选择或创建一个研究后，可以在这里生成结果或继续追问。");
  const [asking, setAsking] = useState(false);
  const [latestFollowUpTask, setLatestFollowUpTask] = useState<FollowUpTaskItem | null>(null);
  const [latestFollowUpTaskScope, setLatestFollowUpTaskScope] = useState<KnowledgeScope>("shared");
  const [runningTaskId, setRunningTaskId] = useState("");
  const [deletingConversationId, setDeletingConversationId] = useState("");
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [toolStatus, setToolStatus] = useState("打开后会同步当前工具状态。");
  const [toolDialogTab, setToolDialogTab] = useState<"tools" | "skills" | "knowledge">("tools");
  const [toolsLoading, setToolsLoading] = useState(false);
  const [updatingToolId, setUpdatingToolId] = useState("");
  const [savingSkillId, setSavingSkillId] = useState("");
  const [deletingSkillId, setDeletingSkillId] = useState("");
  const [editingSkillId, setEditingSkillId] = useState("");
  const [skillDraft, setSkillDraft] = useState({
    skill_id: "",
    display_name: "",
    description: "",
    required_tools: [] as string[],
    enabled: true,
  });
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeDraft, setKnowledgeDraft] = useState<CreateKnowledgeDocumentPayload>({
    title: "",
    content: "",
    tags: [],
    source_url: "",
    notes: "",
  });
  const [paperImportQuery, setPaperImportQuery] = useState("");
  const [paperImportCandidates, setPaperImportCandidates] = useState<PaperImportCandidateItem[]>([]);
  const [paperImportLoading, setPaperImportLoading] = useState(false);
  const [importingPaperCandidateId, setImportingPaperCandidateId] = useState("");
  const [showManualKnowledgeForm, setShowManualKnowledgeForm] = useState(false);
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
  const activeTaskKnowledgeScope =
    activeConversationTask?.knowledge_scope ?? workspace?.source_trace?.knowledge_scope ?? "shared";
  const selectedSkillSummary = useMemo(() => {
    if (!selectedSkillIds.length) return "未选择";
    return selectedSkillIds
      .map((skillId) => skills.find((skill) => skill.skill_id === skillId)?.display_name ?? skillId)
      .join(" / ");
  }, [selectedSkillIds, skills]);
  const selectedSkillItems = useMemo(
    () =>
      selectedSkillIds.map((skillId) => skills.find((skill) => skill.skill_id === skillId)).filter(Boolean) as SkillItem[],
    [selectedSkillIds, skills]
  );

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
    setLatestFollowUpTask(null);
    setLatestFollowUpTaskScope("shared");
  }, [activeConversationId]);

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

  useEffect(() => {
    if (!activeConversationId) {
      setKnowledgeScope("shared");
      setLatestFollowUpTaskScope("shared");
      return;
    }

    setKnowledgeScope(activeTaskKnowledgeScope);
  }, [activeConversationId, activeTaskKnowledgeScope]);

  const workspaceDirections = useMemo(() => {
    if (!workspace) return [];
    const branches = workspace.taxonomy.branches.map((branch) => cleanDisplayText(branch.name, 80)).filter(Boolean);
    const ideas = workspace.ideas.map((idea) => cleanDisplayText(idea.title, 100)).filter(Boolean);
    return [...branches, ...ideas].slice(0, 6);
  }, [workspace]);

  async function createConversationFromSidebar() {
    if (!newTopic.trim()) return;
    const scopeLabel = knowledgeScopeLabel(knowledgeScope);
    setCreatingConversation(true);
    try {
      const response = await api.createConversation({
        topic: newTopic.trim(),
        title: newTitle.trim() || undefined,
      });
      setCreateDialogOpen(false);
      setAskStatus("研究已创建。现在可以生成结果，也可以先补充你的要求。");
      await loadHistory();
      setAskStatus(`结果已生成，本轮使用「${scopeLabel}」。可以继续追问来调整方向。`);
      setAskStatus("研究已创建。现在可以生成结果，也可以先补充你的要求。");
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
    const scopeLabel = knowledgeScopeLabel(knowledgeScope);
    const shouldCreateFreshTask =
      activeConversationId !== DEMO_CONVERSATION_ID &&
      (!activeTaskId || activeTaskKnowledgeScope !== knowledgeScope);
    setAskStatus("正在生成研究结果...");
    try {
      setAskStatus(
        shouldCreateFreshTask
          ? `知识范围已切换为「${scopeLabel}」，正在创建新一轮研究结果...`
          : `正在按「${scopeLabel}」生成研究结果...`
      );
      let taskId = activeTaskId;
      if (shouldCreateFreshTask || !taskId) {
        const created = await api.createTask({
          conversation_id: activeConversationId,
          topic: activeConversation.topic,
          mode: runMode,
          use_shared_knowledge: knowledgeScope === "shared",
          knowledge_scope: knowledgeScope,
          selected_skill_ids: selectedSkillIds,
        });
        taskId = created.data.task_id;
      }
      await api.runTask(taskId);
      setAskStatus(`结果已生成，本轮使用「${scopeLabel}」。可以继续追问来调整方向。`);
      setAskStatus("结果已生成，可以继续追问来调整方向。");
      await loadHistory();
      setAskStatus(`结果已生成，本轮使用「${scopeLabel}」。可以继续追问来调整方向。`);
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
    const scopeLabel = knowledgeScopeLabel(knowledgeScope);
    setAskStatus("正在继续追问...");
    try {
      setAskStatus(`正在按「${scopeLabel}」继续追问...`);
      const response = await api.continueConversation({
        conversation_id: activeConversationId,
        content: askContent.trim(),
        create_follow_up_task: true,
        mode: runMode,
        knowledge_scope: knowledgeScope,
        selected_skill_ids: selectedSkillIds,
      });
      const appliedScope = response.data.knowledge_scope_applied ?? knowledgeScope;
      setAskContent("");
      setLatestFollowUpTask(response.data.follow_up_task ?? null);
      setLatestFollowUpTaskScope(appliedScope);
      setAskStatus(response.data.follow_up_task ? "已生成后续研究任务，可运行后刷新结果。" : "追问已发送。");
      await loadHistory();
      setAskStatus(
        response.data.follow_up_task
          ? `已按「${knowledgeScopeLabel(appliedScope)}」生成后续研究任务，可运行后刷新结果。`
          : `追问已按「${knowledgeScopeLabel(appliedScope)}」发送。`
      );
      navigate(`/conversation?conversation_id=${encodeURIComponent(activeConversationId)}`);
    } catch (error) {
      setAskStatus(toErrorMessage(error));
    } finally {
      setAsking(false);
    }
  }

  async function runFollowUpTask(taskId: string) {
    setRunningTaskId(taskId);
    const scopeLabel = knowledgeScopeLabel(latestFollowUpTaskScope);
    setAskStatus("正在运行后续研究任务...");
    try {
      setAskStatus(`正在按「${scopeLabel}」运行后续研究任务...`);
      await api.runTask(taskId);
      setAskStatus("新的结果已生成，右侧窗口已刷新。");
      await loadHistory();
      setAskStatus(`新的结果已生成，本轮沿用「${scopeLabel}」，右侧窗口已刷新。`);
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
    setShowManualKnowledgeForm(false);
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

  function resetSkillDraft() {
    setEditingSkillId("");
    setSkillDraft({
      skill_id: "",
      display_name: "",
      description: "",
      required_tools: [],
      enabled: true,
    });
  }

  function toggleDraftRequiredTool(toolId: string) {
    setSkillDraft((current) => ({
      ...current,
      required_tools: current.required_tools.includes(toolId)
        ? current.required_tools.filter((item) => item !== toolId)
        : [...current.required_tools, toolId],
    }));
  }

  function editSkill(skill: SkillItem) {
    setEditingSkillId(skill.skill_id);
    setSkillDraft({
      skill_id: skill.skill_id,
      display_name: skill.display_name,
      description: skill.description,
      required_tools: [...skill.required_tools],
      enabled: skill.enabled,
    });
    setToolDialogOpen(false);
    setSkillDialogOpen(true);
  }

  async function saveSkill() {
    const skillId = editingSkillId || skillDraft.skill_id.trim();
    if (!skillId || !skillDraft.display_name.trim()) {
      setToolStatus("请填写能力 ID 和显示名称。");
      return;
    }

    setSavingSkillId(skillId);
    setToolStatus(editingSkillId ? "正在保存研究能力..." : "正在创建研究能力...");
    try {
      const payload = {
        display_name: skillDraft.display_name.trim(),
        description: skillDraft.description.trim(),
        required_tools: skillDraft.required_tools,
        enabled: skillDraft.enabled,
      };
      const response = editingSkillId
        ? await api.updateSkill(editingSkillId, payload)
        : await api.createSkill({ skill_id: skillId, ...payload });
      setSkills((current) => {
        const exists = current.some((skill) => skill.skill_id === response.data.skill_id);
        return exists
          ? current.map((skill) => (skill.skill_id === response.data.skill_id ? response.data : skill))
          : [response.data, ...current];
      });
      setSkillDialogOpen(false);
      resetSkillDraft();
      setToolDialogOpen(true);
      setToolDialogTab("skills");
      setToolStatus(editingSkillId ? "研究能力已更新。" : "研究能力已创建。");
    } catch (error) {
      setToolStatus(`研究能力保存失败：${toErrorMessage(error)}`);
    } finally {
      setSavingSkillId("");
    }
  }

  async function toggleSkillEnabled(skill: SkillItem) {
    setSavingSkillId(skill.skill_id);
    try {
      const response = await api.updateSkill(skill.skill_id, { enabled: !skill.enabled });
      setSkills((current) => current.map((item) => (item.skill_id === skill.skill_id ? response.data : item)));
      if (!response.data.enabled) {
        setSelectedSkillIds((current) => current.filter((skillId) => skillId !== skill.skill_id));
      }
      setToolStatus(`${response.data.display_name} 已${response.data.enabled ? "启用" : "停用"}。`);
    } catch (error) {
      setToolStatus(`研究能力更新失败：${toErrorMessage(error)}`);
    } finally {
      setSavingSkillId("");
    }
  }

  async function deleteSkill(skill: SkillItem) {
    const confirmed = window.confirm(`确定删除研究能力「${skill.display_name}」吗？`);
    if (!confirmed) return;

    setDeletingSkillId(skill.skill_id);
    try {
      await api.deleteSkill(skill.skill_id);
      setSkills((current) => current.filter((item) => item.skill_id !== skill.skill_id));
      setSelectedSkillIds((current) => current.filter((skillId) => skillId !== skill.skill_id));
      setToolStatus("研究能力已删除。");
    } catch (error) {
      setToolStatus(`研究能力删除失败：${toErrorMessage(error)}`);
    } finally {
      setDeletingSkillId("");
    }
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

  async function searchPaperCandidates() {
    if (!paperImportQuery.trim()) {
      setToolStatus("请先输入论文标题、DOI、arXiv ID 或 arXiv 链接。");
      return;
    }

    setPaperImportLoading(true);
    setToolStatus("正在识别论文候选...");
    try {
      const response = await api.searchPaperCandidates({
        query: paperImportQuery.trim(),
        limit: 3,
      });
      setPaperImportCandidates(response.data.items);
      setToolStatus(
        response.data.items.length
          ? `已识别 ${response.data.items.length} 条候选论文，请确认后导入。`
          : "没有找到可导入的候选论文，试试更完整的标题、DOI 或 arXiv 链接。"
      );
    } catch (error) {
      setPaperImportCandidates([]);
      setToolStatus(`识别失败：${toErrorMessage(error)}`);
    } finally {
      setPaperImportLoading(false);
    }
  }

  async function importPaperCandidate(candidateId: string, target: "conversation" | "shared") {
    if (target === "conversation" && !activeConversationId) {
      setToolStatus("当前没有激活的研究会话，暂时只能导入到共享知识。");
      return;
    }

    setImportingPaperCandidateId(candidateId);
    setToolStatus(target === "conversation" ? "正在导入到当前研究..." : "正在导入到共享知识...");
    try {
      const response = await api.importPaperCandidate({
        candidate_id: candidateId,
        conversation_id: target === "conversation" ? activeConversationId : undefined,
      });
      setKnowledgeDocuments((current) => [response.data, ...current]);
      setToolStatus(
        target === "conversation"
          ? "论文已导入到当前研究，后续追问会优先利用这份资料。"
          : "论文已导入到共享知识，后续研究都可以复用它。"
      );
    } catch (error) {
      setToolStatus(`导入失败：${toErrorMessage(error)}`);
    } finally {
      setImportingPaperCandidateId("");
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
                  <Link
                    className="secondary-button"
                    to={`/workspace?conversation_id=${encodeURIComponent(activeConversationId)}${activeTaskId ? `&task_id=${encodeURIComponent(activeTaskId)}` : ""}&view=conversation`}
                  >
                    打开本研究总览
                  </Link>
                  {activeTaskId ? (
                    <Link
                      className="secondary-button"
                      to={`/workspace?conversation_id=${encodeURIComponent(activeConversationId)}&task_id=${encodeURIComponent(activeTaskId)}&view=task`}
                    >
                      查看本次结果
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
                            <>
                              <AssistantMessageContent content={getDisplayMessageContent(message)} />
                              <MessageSourceTrace
                                inheritedContext={message.metadata?.inherited_context}
                                sourceTrace={message.metadata?.source_trace}
                              />
                            </>
                          ) : (
                            <p>{getDisplayMessageContent(message)}</p>
                          )}
                          {message.role === "assistant" && getMessageTaskId(message) ? (
                            <div className="unified-message-actions">
                              {getMessageTaskStatus(message) ? (
                                <StatusPill compact tone={taskStatusTone(getMessageTaskStatus(message))}>
                                  {taskStatusLabel(getMessageTaskStatus(message))}
                                </StatusPill>
                              ) : null}
                              <Link
                                className="secondary-button message-action-button"
                                to={`/workspace?conversation_id=${encodeURIComponent(activeConversationId)}&task_id=${encodeURIComponent(getMessageTaskId(message))}&view=task`}
                              >
                                ↗ 查看本次结果
                              </Link>
                            </div>
                          ) : null}
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
                      <div className="composer-mode-picker">
                        <span className="composer-mode-label">运行模式</span>
                        <SegmentedControl
                          label="运行模式"
                          onChange={setRunMode}
                          options={modeOptions}
                          value={runMode}
                        />
                      </div>
                      <div className="composer-mode-picker">
                        <span className="composer-mode-label">知识范围</span>
                        <SegmentedControl
                          label="知识范围"
                          onChange={(value) => setKnowledgeScope(value as KnowledgeScope)}
                          options={knowledgeScopeOptions}
                          value={knowledgeScope}
                        />
                      </div>
                      <button
                        className="selected-skills-summary"
                        onClick={() => {
                          void openToolDialog();
                          setToolDialogTab("skills");
                        }}
                        type="button"
                      >
                        <span>已选能力</span>
                        <strong>{selectedSkillSummary}</strong>
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
                className={toolDialogTab === "skills" ? "tool-dialog-tab tool-dialog-tab-active" : "tool-dialog-tab"}
                onClick={() => setToolDialogTab("skills")}
                type="button"
              >
                研究能力
              </button>
              <button
                className={toolDialogTab === "knowledge" ? "tool-dialog-tab tool-dialog-tab-active" : "tool-dialog-tab"}
                onClick={() => {
                  setToolDialogTab("knowledge");
                  setShowManualKnowledgeForm(false);
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
) : toolDialogTab === "skills" ? (
              <>
              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>本轮启用能力</strong>
                  <StatusPill tone="info" compact>
                    已选 {selectedSkillIds.length} 项
                  </StatusPill>
                </div>
                <div className="selected-skills-panel">
                  <span>当前已选</span>
                  {selectedSkillItems.length ? (
                    <div className="selected-skills-chip-row">
                      {selectedSkillItems.map((skill) => (
                        <button
                          className="selected-skill-chip"
                          key={skill.skill_id}
                          onClick={() =>
                            setSelectedSkillIds((current) => current.filter((skillId) => skillId !== skill.skill_id))
                          }
                          title="移除这个能力"
                          type="button"
                        >
                          {skill.display_name}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <strong>未选择研究能力</strong>
                  )}
                </div>
                <div className="skill-select-list">
                  {skills.length ? (
                    skills.map((skill) => {
                      const selected = selectedSkillIds.includes(skill.skill_id);
                      return (
                        <button
                          className={selected ? "skill-select-card skill-select-card-active" : "skill-select-card"}
                          disabled={!skill.enabled}
                          key={skill.skill_id}
                          onClick={() =>
                            setSelectedSkillIds((current) =>
                              current.includes(skill.skill_id)
                                ? current.filter((skillId) => skillId !== skill.skill_id)
                                : [...current, skill.skill_id]
                            )
                          }
                          type="button"
                        >
                          <span>
                            <strong>{skill.display_name}</strong>
                            <small>{skill.description || skill.skill_id}</small>
                          </span>
                          <StatusPill tone={skill.enabled ? (selected ? "success" : "neutral") : "danger"} compact>
                            {skill.enabled ? (selected ? "已选择" : "可选择") : "已停用"}
                          </StatusPill>
                        </button>
                      );
                    })
                  ) : (
                    <div className="sidebar-empty">暂无可选研究能力。可以先创建一个。</div>
                  )}
                </div>
              </section>

              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>研究能力库</strong>
                  <button
                    className="primary-button"
                    onClick={() => {
                      resetSkillDraft();
                      setToolDialogOpen(false);
                      setSkillDialogOpen(true);
                    }}
                    type="button"
                  >
                    创建能力
                  </button>
                </div>
                <div className="skill-chip-list">
                  {skills.length ? (
                    skills.map((skill) => (
                      <div className="skill-chip-card skill-manage-card" key={skill.skill_id}>
                        <div>
                          <strong>{skill.display_name}</strong>
                          <p>{skill.description || "暂无描述。"}</p>
                          <div className="button-row">
                            <StatusPill tone={skill.enabled ? "success" : "danger"} compact>
                              {skill.enabled ? "已启用" : "已停用"}
                            </StatusPill>
                            {skill.required_tools.length ? (
                              skill.required_tools.map((toolId) => (
                                <StatusPill key={toolId} tone="info" compact>
                                  {getToolDisplayName(toolId)}
                                </StatusPill>
                              ))
                            ) : (
                              <StatusPill tone="neutral" compact>
                                无工具依赖
                              </StatusPill>
                            )}
                          </div>
                        </div>
                        <div className="skill-card-actions">
                          <button className="secondary-button" onClick={() => editSkill(skill)} type="button">
                            编辑
                          </button>
                          <button
                            className="secondary-button"
                            disabled={savingSkillId === skill.skill_id}
                            onClick={() => toggleSkillEnabled(skill)}
                            type="button"
                          >
                            {skill.enabled ? "停用" : "启用"}
                          </button>
                          <button
                            className="history-delete-button"
                            disabled={deletingSkillId === skill.skill_id}
                            onClick={() => deleteSkill(skill)}
                            title="删除研究能力"
                            type="button"
                          >
                            {deletingSkillId === skill.skill_id ? "..." : "x"}
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="sidebar-empty">暂无研究能力。点击“创建能力”添加一个。</div>
                  )}
                </div>
              </section>
              </>
) : (
              <>
              <section className="tool-dialog-section knowledge-import-primary">
                <div className="tool-dialog-section-head">
                  <div className="knowledge-import-headline">
                    <strong>自动导入论文</strong>
                    <span className="knowledge-import-recommend">推荐入口</span>
                  </div>
                  <StatusPill tone={paperImportLoading ? "neutral" : "info"} compact>
                    {paperImportLoading ? "识别中" : "论文候选"}
                  </StatusPill>
                </div>
                <div className="knowledge-form">
                  <input
                    className="input"
                    onChange={(event) => setPaperImportQuery(event.target.value)}
                    placeholder="输入论文标题、DOI、arXiv ID 或 arXiv 链接"
                    value={paperImportQuery}
                  />
                  <div className="knowledge-import-tip">
                    先识别候选，再一键导入到当前研究或共享知识。这样比手填摘要顺手很多，也更不容易导错论文。
                  </div>
                  <div className="knowledge-import-tip knowledge-import-tip-strong">
                    默认建议先走自动导入；只有在你想录入自己的调研笔记、课堂资料或手工总结时，再切到手动模式。
                  </div>
                  <button
                    className="primary-button"
                    disabled={paperImportLoading}
                    onClick={searchPaperCandidates}
                    type="button"
                  >
                    {paperImportLoading ? "识别中" : "识别候选"}
                  </button>
                  {paperImportCandidates.length ? (
                    <div className="knowledge-doc-list">
                      {paperImportCandidates.map((candidate) => (
                        <article className="knowledge-doc-card knowledge-candidate-card" key={candidate.candidate_id}>
                          <div>
                            <strong>{cleanDisplayText(candidate.title, 140)}</strong>
                            <p>{compactText(cleanDisplayText(candidate.abstract || "上游元数据里暂时没有摘要，可先导入标题和基础信息。"), 220)}</p>
                            <div className="knowledge-doc-meta">
                              {candidate.year ? <span>{candidate.year}</span> : null}
                              <span>{paperSourceLabel(candidate)}</span>
                              {candidate.arxiv_id ? <span>arXiv {candidate.arxiv_id}</span> : null}
                              {candidate.doi ? <span>{cleanDisplayText(candidate.doi, 48)}</span> : null}
                              {candidate.is_exact_match ? <span>高匹配</span> : null}
                            </div>
                            {candidate.authors.length ? (
                              <small>{cleanDisplayText(candidate.authors.slice(0, 4).join(", "), 120)}</small>
                            ) : null}
                          </div>
                          <div className="knowledge-candidate-actions">
                            <button
                              className="primary-button"
                              disabled={importingPaperCandidateId === candidate.candidate_id || !activeConversationId}
                              onClick={() => importPaperCandidate(candidate.candidate_id, "conversation")}
                              type="button"
                            >
                              {importingPaperCandidateId === candidate.candidate_id ? "导入中" : "导入到当前研究"}
                            </button>
                            <button
                              className="secondary-button"
                              disabled={importingPaperCandidateId === candidate.candidate_id}
                              onClick={() => importPaperCandidate(candidate.candidate_id, "shared")}
                              type="button"
                            >
                              导入到共享知识
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : null}
                  <div className="button-row">
                    <button
                      className="secondary-button"
                      onClick={() => setShowManualKnowledgeForm((current) => !current)}
                      type="button"
                    >
                      {showManualKnowledgeForm ? "收起手动录入" : "改用手动录入"}
                    </button>
                  </div>
                </div>
              </section>

              <section className="tool-dialog-section">
                <div className="tool-dialog-section-head">
                  <strong>手动录入（高级）</strong>
                  <StatusPill tone={knowledgeLoading ? "neutral" : "info"} compact>
                    {knowledgeLoading ? "同步中" : "资料库"}
                  </StatusPill>
                </div>
                {showManualKnowledgeForm ? (
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
                ) : (
                <div className="knowledge-import-collapsed-note">
                  这里保留给更复杂的录入场景：例如你自己的调研笔记、课堂资料、中文摘要整理，或者你想手动控制标题、标签和备注。
                </div>
                )}
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
                            {document.conversation_id ? <span>当前研究</span> : <span>共享知识</span>}
                            {document.tags.length ? <span>{document.tags.join(" / ")}</span> : null}
                            {knowledgeMetadata(document, "paper_source") ? (
                              <span>{cleanDisplayText(knowledgeMetadata(document, "paper_source"), 40)}</span>
                            ) : null}
                            {knowledgeMetadata(document, "year") ? (
                              <span>{cleanDisplayText(knowledgeMetadata(document, "year"), 12)}</span>
                            ) : null}
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

      {skillDialogOpen ? (
        <div className="modal-backdrop modal-backdrop-blur" role="dialog" aria-modal="true" aria-label="研究能力设置">
          <div className="create-dialog skill-edit-dialog">
            <div className="create-dialog-head">
              <div>
                <div className="section-eyebrow">研究能力</div>
                <h2>{editingSkillId ? "编辑研究能力" : "创建研究能力"}</h2>
              </div>
              <button
                className="ghost-button"
                onClick={() => {
                  setSkillDialogOpen(false);
                  resetSkillDraft();
                  setToolDialogOpen(true);
                  setToolDialogTab("skills");
                }}
                type="button"
              >
                关闭
              </button>
            </div>
            <div className="workspace-side-status">{toolStatus}</div>
            <div className="skill-form-grid">
              <label className="field">
                <span>能力 ID</span>
                <input
                  className="input"
                  disabled={Boolean(editingSkillId)}
                  onChange={(event) => setSkillDraft((current) => ({ ...current, skill_id: event.target.value }))}
                  placeholder="paper_compare"
                  value={skillDraft.skill_id}
                />
              </label>
              <label className="field">
                <span>显示名称</span>
                <input
                  className="input"
                  onChange={(event) => setSkillDraft((current) => ({ ...current, display_name: event.target.value }))}
                  placeholder="论文对比分析"
                  value={skillDraft.display_name}
                />
              </label>
            </div>
            <label className="field">
              <span>能力说明</span>
              <textarea
                className="input textarea skill-description-input"
                onChange={(event) => setSkillDraft((current) => ({ ...current, description: event.target.value }))}
                placeholder="说明这个能力适合什么时候使用，以及会如何影响研究规划。"
                value={skillDraft.description}
              />
            </label>
            <div className="field">
              <span>依赖工具</span>
              {tools.length ? (
                <div className="skill-tool-picker" aria-label="选择依赖工具">
                  {tools.map((tool) => {
                    const checked = skillDraft.required_tools.includes(tool.tool_id);
                    return (
                      <button
                        className={checked ? "skill-tool-option skill-tool-option-active" : "skill-tool-option"}
                        key={tool.tool_id}
                        onClick={() => toggleDraftRequiredTool(tool.tool_id)}
                        type="button"
                      >
                        <span>
                          <strong>{tool.display_name}</strong>
                          <small>{tool.tool_id}</small>
                        </span>
                        <StatusPill tone={tool.enabled ? (checked ? "success" : "neutral") : "danger"} compact>
                          {tool.enabled ? (checked ? "已选择" : "可选择") : "已停用"}
                        </StatusPill>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="sidebar-empty">暂无可选择工具。请先确认后端 /tools 已返回工具列表。</div>
              )}
            </div>
            <div className="skill-editor-actions">
              <ToggleSwitch
                checked={skillDraft.enabled}
                label={skillDraft.enabled ? "启用" : "停用"}
                onChange={() => setSkillDraft((current) => ({ ...current, enabled: !current.enabled }))}
              />
              <div className="button-row">
                <button
                  className="secondary-button"
                  onClick={() => {
                    setSkillDialogOpen(false);
                    resetSkillDraft();
                    setToolDialogOpen(true);
                    setToolDialogTab("skills");
                  }}
                  type="button"
                >
                  取消
                </button>
                <button className="primary-button" disabled={Boolean(savingSkillId)} onClick={saveSkill} type="button">
                  {savingSkillId ? "保存中" : editingSkillId ? "保存能力" : "创建能力"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
