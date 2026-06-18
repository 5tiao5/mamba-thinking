import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { WorkspaceEvidenceBoard } from "../components/workspace/WorkspaceEvidenceBoard";
import { WorkspaceInsightsPanel } from "../components/workspace/WorkspaceInsightsPanel";
import { WorkspaceRunFlow } from "../components/workspace/WorkspaceRunFlow";
import { WorkspaceSummarySection } from "../components/workspace/WorkspaceSummarySection";
import { WorkspaceTaxonomyRail } from "../components/workspace/WorkspaceTaxonomyRail";
import { api, toErrorMessage } from "../lib/api";
import { DEMO_CONVERSATION_ID, DEMO_WORKSPACE_TASK_ID } from "../lib/demoData";
import { cleanDisplayText } from "../lib/displayText";
import { taskStatusLabel } from "../lib/productText";
import type {
  ResearchTaskDetailItem,
  ResearchTaskEventItem,
  WorkspacePaper,
  WorkspaceSnapshot,
} from "../types/api";

type WorkspaceView = "conversation" | "task";
type WorkspaceSection = "overview" | "evidence" | "map" | "context" | "run";

function taskStatusMessage(task: ResearchTaskDetailItem) {
  if (task.status === "running") {
    return "结果仍在生成中，请稍后再刷新。";
  }
  if (task.status === "created") {
    return "这个研究还没有生成结果，点击“生成结果”后会展示完整分析。";
  }
  if (task.status === "failed") {
    return "结果生成失败了，可以重新生成一次。";
  }
  return `当前状态为${taskStatusLabel(task.status)}，暂时没有可展示结果。`;
}

function resolveWorkspaceView(
  taskId: string,
  conversationId: string,
  requestedView: string | null
): WorkspaceView {
  if (requestedView === "conversation" && conversationId) {
    return "conversation";
  }
  if (requestedView === "task" && taskId) {
    return "task";
  }
  if (conversationId && !taskId) {
    return "conversation";
  }
  return "task";
}

function splitWorkspaceTopic(topic?: string) {
  const text = cleanDisplayText(topic ?? "", 220);
  if (!text) {
    return { root: "", focus: "" };
  }

  const separatorMatch = text.match(/\s[-–—]\s/);
  if (separatorMatch?.index !== undefined) {
    const root = text.slice(0, separatorMatch.index).trim();
    const focus = text.slice(separatorMatch.index + separatorMatch[0].length).trim();
    if (root && focus && /[\u4e00-\u9fa5]|继续|补充|扩展|缩小|关注|对比|梳理|近\d|近[一二三四五六七八九十]/.test(focus)) {
      return { root, focus };
    }
  }

  return { root: text, focus: "" };
}

function isTerminalTaskEvent(event?: ResearchTaskEventItem) {
  if (!event) {
    return false;
  }
  const stage = (event.stage || "").toLowerCase();
  const status = (event.status || "").toLowerCase();
  if (status.includes("failed") || status.includes("error")) {
    return true;
  }
  if (!stage.includes("runtime")) {
    return false;
  }
  return status.includes("completed") || status.includes("degraded") || status.includes("step_limit");
}

export function WorkspacePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const taskIdFromQuery = searchParams.get("task_id") ?? "";
  const conversationIdFromQuery = searchParams.get("conversation_id") ?? "";
  const requestedView = searchParams.get("view");
  const activeView = resolveWorkspaceView(taskIdFromQuery, conversationIdFromQuery, requestedView);
  const [taskId, setTaskId] = useState(taskIdFromQuery);
  const [conversationId, setConversationId] = useState(conversationIdFromQuery);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [status, setStatus] = useState("从对话页或首页进入任务后，可以运行分析或读取工作台。");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [selectedBranchId, setSelectedBranchId] = useState("");
  const [evidenceViewMode, setEvidenceViewMode] = useState<"analysis" | "extended">("analysis");
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("overview");
  const [runEvents, setRunEvents] = useState<ResearchTaskEventItem[]>([]);
  const [runEventsLoading, setRunEventsLoading] = useState(false);
  const [runEventsError, setRunEventsError] = useState("");

  function syncWorkspaceRoute(next: {
    view: WorkspaceView;
    conversationId?: string;
    taskId?: string;
  }) {
    const params = new URLSearchParams();
    if (next.conversationId) {
      params.set("conversation_id", next.conversationId);
    }
    if (next.taskId) {
      params.set("task_id", next.taskId);
    }
    params.set("view", next.view);
    setSearchParams(params);
  }

  useEffect(() => {
    setTaskId(taskIdFromQuery);
    setConversationId(conversationIdFromQuery);

    if (activeView === "conversation" && conversationIdFromQuery) {
      void handleLoadConversationWorkspace(conversationIdFromQuery, {
        syncUrl: false,
        fallbackTaskId: taskIdFromQuery,
      });
      return;
    }

    if (taskIdFromQuery) {
      void handleLoadWorkspace(taskIdFromQuery, {
        syncUrl: false,
        preferredConversationId: conversationIdFromQuery,
      });
      return;
    }

    if (conversationIdFromQuery) {
      void handleLoadConversationWorkspace(conversationIdFromQuery, { syncUrl: false });
      return;
    }

    setWorkspace(null);
    setStatus("从对话页或首页进入后，可以运行分析或读取工作台。");
  }, [activeView, conversationIdFromQuery, taskIdFromQuery]);

  const analysisPaperIds = useMemo(
    () => new Set(workspace?.analysis_paper_ids ?? []),
    [workspace]
  );
  const analysisPapers = useMemo(
    () => (workspace?.papers ?? []).filter((paper) => analysisPaperIds.has(paper.paper_id)),
    [analysisPaperIds, workspace]
  );
  const paperLookupPool = workspace?.papers ?? analysisPapers;
  const visibleEvidencePapers = evidenceViewMode === "analysis" ? analysisPapers : workspace?.papers ?? [];

  const paperCategories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const paper of analysisPapers) {
      const key = paper.taxonomy_category || "未分类";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
  }, [analysisPapers]);

  const taxonomyBranches = useMemo(() => workspace?.taxonomy?.branches ?? [], [workspace]);
  const taxonomyCoverage = useMemo(() => workspace?.taxonomy?.coverage ?? {}, [workspace]);

  useEffect(() => {
    if (!taxonomyBranches.length) {
      setSelectedBranchId("");
      return;
    }
    setSelectedBranchId((previous) => {
      if (previous && taxonomyBranches.some((branch) => branch.branch_id === previous)) {
        return previous;
      }
      return taxonomyBranches[0].branch_id;
    });
  }, [taxonomyBranches]);

  const filteredPapers = useMemo(() => {
    const papers = visibleEvidencePapers;
    if (selectedCategory === "all") {
      return papers;
    }
    return papers.filter((paper) => (paper.taxonomy_category || "未分类") === selectedCategory);
  }, [selectedCategory, visibleEvidencePapers]);

  const taxonomyEvidencePapers = useMemo(() => {
    if (!workspace || !selectedBranchId) {
      return [] as WorkspacePaper[];
    }
    const matchedIds = workspace.taxonomy.coverage[selectedBranchId]?.matched_paper_ids ?? [];
    if (!matchedIds.length) {
      return [] as WorkspacePaper[];
    }
    const idSet = new Set(matchedIds);
    return analysisPapers.filter((paper) => idSet.has(paper.paper_id));
  }, [analysisPapers, selectedBranchId, workspace]);

  const selectedPaper = useMemo(() => {
    if (!filteredPapers.length) {
      return undefined;
    }
    return filteredPapers.find((paper) => paper.paper_id === selectedPaperId) ?? filteredPapers[0];
  }, [filteredPapers, selectedPaperId]);

  const usesFallbackPapers = useMemo(
    () => (workspace?.papers ?? []).some((paper) => (paper.source || "").toLowerCase() === "fallback"),
    [workspace]
  );

  const priorityNote = useMemo(() => workspace?.gaps?.[0]?.summary, [workspace]);
  const recommendation = useMemo(() => {
    const topIdea = workspace?.ideas?.[0]?.title;
    if (!topIdea) {
      return undefined;
    }
    return `建议先围绕“${topIdea}”继续细化，并补充真实论文证据。`;
  }, [workspace]);

  const runEventTaskId = useMemo(() => {
    const workspaceTaskId = workspace?.task_id ?? "";
    if (workspaceTaskId && !workspaceTaskId.startsWith("conversation::")) {
      return workspaceTaskId;
    }
    return taskId || taskIdFromQuery;
  }, [taskId, taskIdFromQuery, workspace?.task_id]);

  useEffect(() => {
    const targetTaskId = runEventTaskId.trim();
    if (activeSection !== "run" || !targetTaskId || targetTaskId.startsWith("conversation::")) {
      setRunEvents([]);
      setRunEventsError("");
      setRunEventsLoading(false);
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof window.setInterval> | undefined;
    setRunEventsError("");

    const fetchEvents = async (showLoading: boolean) => {
      if (showLoading) {
        setRunEventsLoading(true);
      }
      try {
        const response = await api.listTaskEvents(targetTaskId);
        if (cancelled) {
          return false;
        }
        const items = response.data.items ?? [];
        setRunEvents(items);
        const latestEvent = [...items].sort((left, right) => right.sequence - left.sequence)[0];
        return isTerminalTaskEvent(latestEvent);
      } catch (error) {
        if (cancelled) {
          return false;
        }
        setRunEvents([]);
        setRunEventsError(toErrorMessage(error));
        return true;
      } finally {
        if (!cancelled) {
          setRunEventsLoading(false);
        }
      }
    };

    void fetchEvents(true).then((isTerminal) => {
      if (cancelled || (isTerminal && !running)) {
        return;
      }
      intervalId = window.setInterval(() => {
        void fetchEvents(false).then((nextTerminal) => {
          if (nextTerminal && !running && intervalId) {
            window.clearInterval(intervalId);
            intervalId = undefined;
          }
        });
      }, 1600);
    });

    return () => {
      cancelled = true;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [activeSection, runEventTaskId, running]);

  const viewHeadline = activeView === "conversation" ? "本研究总览" : "本次结果";
  const viewDescription =
    activeView === "conversation"
      ? "聚合同一研究主题下所有已完成任务的累计结果，适合看全局脉络。"
      : "聚焦某一次生成或某一次追问的局部结果，适合回看这轮具体增量。";
  const workspaceTopic = splitWorkspaceTopic(workspace?.topic);
  const workspaceTitle = workspaceTopic.root || "研究工作台";
  const workspaceSectionItems: Array<{
    id: WorkspaceSection;
    label: string;
    title: string;
    description: string;
    badge: string;
  }> = [
    {
      id: "overview",
      label: "Overview",
      title: "研究简报",
      description: "先看结论、风险和下一步。",
      badge: workspace?.research_brief?.must_read_papers.length
        ? `${workspace.research_brief.must_read_papers.length} 篇必读`
        : "简报",
    },
    {
      id: "evidence",
      label: "Evidence",
      title: "论文证据",
      description: "核查核心论文和扩展证据池。",
      badge: `${analysisPapers.length}/${workspace?.papers.length ?? 0}`,
    },
    {
      id: "map",
      label: "Map",
      title: "研究结构",
      description: "浏览 taxonomy 与论文关系。",
      badge: `${taxonomyBranches.length} 分支`,
    },
    {
      id: "context",
      label: "Context",
      title: "知识上下文",
      description: "区分 RAG、记忆和论文证据。",
      badge: `${workspace?.source_trace?.knowledge_hit_count ?? 0} 命中`,
    },
    {
      id: "run",
      label: "Run",
      title: "运行轨迹",
      description: "查看 Agent 步骤和降级点。",
      badge: `${workspace?.trace?.action_history.length ?? 0} 动作`,
    },
  ];

  async function handleLoadWorkspace(
    targetId = taskId,
    options?: { syncUrl?: boolean; preferredConversationId?: string }
  ) {
    const trimmedId = targetId.trim();
    if (!trimmedId) {
      setStatus("请先从对话页或首页选择一个研究任务。");
      return;
    }

    setLoading(true);
    setStatus("正在读取工作台...");
    try {
      const response = await api.getWorkspace(trimmedId);
      setWorkspace(response.data);
      setEvidenceViewMode("analysis");
      setSelectedCategory("all");
      setSelectedPaperId(response.data.papers[0]?.paper_id ?? "");
      setSelectedBranchId(response.data.taxonomy.branches[0]?.branch_id ?? "");
      setStatus("工作台已加载。");
      let nextConversationId = options?.preferredConversationId || conversationId || conversationIdFromQuery;
      if (trimmedId === DEMO_WORKSPACE_TASK_ID) {
        nextConversationId = DEMO_CONVERSATION_ID;
      } else {
        try {
          const taskResponse = await api.getTask(trimmedId);
          nextConversationId = taskResponse.data.conversation_id;
        } catch {
          nextConversationId = "";
        }
      }
      setConversationId(nextConversationId);
      if (options?.syncUrl !== false) {
        syncWorkspaceRoute({
          view: "task",
          taskId: trimmedId,
          conversationId: nextConversationId,
        });
      }
    } catch (error) {
      setWorkspace(null);
      setSelectedPaperId("");
      setSelectedBranchId("");
      const errorMessage = toErrorMessage(error);
      if (errorMessage.includes("Workspace does not exist")) {
        try {
          const taskResponse = await api.getTask(trimmedId);
          setStatus(taskStatusMessage(taskResponse.data));
        } catch (taskError) {
          setStatus(`加载失败：${errorMessage}；并且读取任务状态失败：${toErrorMessage(taskError)}`);
        }
      } else {
        setStatus(`加载失败：${errorMessage}`);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTask() {
    const trimmedId = taskId.trim();
    if (!trimmedId) {
      setStatus("请先从对话页或首页选择一个研究任务。");
      return;
    }

    setRunning(true);
    setActiveSection("run");
    setStatus("任务运行中，分析可能需要一点时间...");
    try {
      await api.runTask(trimmedId);
      setStatus("任务运行完成，正在读取工作台...");
      await handleLoadWorkspace(trimmedId);
    } catch (error) {
      setStatus(`运行失败：${toErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  }

  async function handleLoadConversationWorkspace(
    targetConversationId = conversationId || conversationIdFromQuery,
    options?: { syncUrl?: boolean; fallbackTaskId?: string }
  ) {
    if (!targetConversationId) {
      setStatus("当前任务还没有关联到会话，无法读取本研究总览。");
      return;
    }

    setLoading(true);
    setStatus("正在读取本研究总览...");
    try {
      const response = await api.getConversationWorkspace(targetConversationId);
      setWorkspace(response.data);
      setEvidenceViewMode("analysis");
      setSelectedCategory("all");
      setSelectedPaperId(response.data.papers[0]?.paper_id ?? "");
      setSelectedBranchId(response.data.taxonomy.branches[0]?.branch_id ?? "");
      setConversationId(targetConversationId);
      setStatus("本研究总览已加载。");
      if (options?.syncUrl !== false) {
        syncWorkspaceRoute({
          view: "conversation",
          conversationId: targetConversationId,
          taskId: options?.fallbackTaskId || taskId || taskIdFromQuery,
        });
      }
    } catch (error) {
      setStatus(`读取本研究总览失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleCloseWorkspace() {
    const targetConversationId = conversationId || conversationIdFromQuery;
    if (targetConversationId) {
      const params = new URLSearchParams();
      params.set("conversation_id", targetConversationId);
      if (taskId) {
        params.set("task_id", taskId);
      }
      navigate(`/conversation?${params.toString()}`);
      return;
    }
    navigate("/conversation");
  }

  return (
    <div className="dense-layout">
      <section className="surface content-pad workspace-command-surface">
        <div className="workspace-toolbar">
          <div className="workspace-context-summary">
            <div className="section-eyebrow">研究工作台</div>
            <div className="workspace-topic-row">
              <strong>{workspaceTitle}</strong>
              {workspaceTopic.focus ? (
                <span className="workspace-focus-pill">本轮聚焦：{cleanDisplayText(workspaceTopic.focus, 96)}</span>
              ) : null}
            </div>
            <span>{workspace ? `当前查看：${viewHeadline}。${viewDescription}` : "从左侧研究记录进入后，这里会展示证据、方向和建议。"}</span>
          </div>
          <div className="workspace-toolbar-actions">
            <div className="workspace-view-switch" role="tablist" aria-label="工作台视图切换">
              <button
                className={activeView === "conversation" ? "primary-button" : "secondary-button"}
                disabled={loading || !(conversationId || conversationIdFromQuery)}
                onClick={() =>
                  handleLoadConversationWorkspace(conversationId || conversationIdFromQuery, {
                    fallbackTaskId: taskId || taskIdFromQuery,
                  })
                }
                type="button"
              >
                本研究总览
              </button>
              <button
                className={activeView === "task" ? "primary-button" : "secondary-button"}
                disabled={loading || !(taskId || taskIdFromQuery)}
                onClick={() =>
                  handleLoadWorkspace(taskId || taskIdFromQuery, {
                    preferredConversationId: conversationId || conversationIdFromQuery,
                  })
                }
                type="button"
              >
                本次结果
              </button>
            </div>
            <div className="button-row workspace-action-row">
              <button className="secondary-button" onClick={handleCloseWorkspace} type="button">
                返回对话
              </button>
              <button className="primary-button" disabled={running} onClick={handleRunTask} type="button">
                {running ? "生成中" : "生成结果"}
              </button>
              <button
                className="secondary-button"
                disabled={loading}
                onClick={() =>
                  activeView === "conversation"
                    ? handleLoadConversationWorkspace(conversationId || conversationIdFromQuery, {
                        fallbackTaskId: taskId || taskIdFromQuery,
                      })
                    : handleLoadWorkspace(taskId || taskIdFromQuery, {
                        preferredConversationId: conversationId || conversationIdFromQuery,
                      })
                }
                type="button"
              >
                {loading ? "刷新中" : "刷新结果"}
              </button>
            </div>
          </div>
        </div>
        <div className="workspace-utility-row">
          <details className="advanced-task-selector">
            <summary>手动定位本次结果</summary>
            <label>
              <span className="field-label">结果引用</span>
              <input
                className="input"
                onChange={(event) => setTaskId(event.target.value)}
                placeholder="从研究记录进入后会自动填充"
                value={taskId}
              />
            </label>
          </details>
          <div className="status-line workspace-status-line">
            {status}
          </div>
        </div>
      </section>

      <section className="workspace-section-nav surface" aria-label="工作台分区导航">
        {workspaceSectionItems.map((item) => (
          <button
            className={
              activeSection === item.id
                ? "workspace-section-tab workspace-section-tab-active"
                : "workspace-section-tab"
            }
            key={item.id}
            onClick={() => setActiveSection(item.id)}
            type="button"
          >
            <span>{item.label}</span>
            <strong>{item.title}</strong>
            <small>{item.description}</small>
            <em>{item.badge}</em>
          </button>
        ))}
      </section>

      {activeSection === "overview" ? (
        <>
          <WorkspaceSummarySection
            alignmentScore={workspace?.alignment_score ?? 0}
            evidenceSnapshot={workspace?.evidence_snapshot ?? null}
            evidenceStatus={workspace?.evidence_status}
            gapCount={workspace?.gaps.length ?? 0}
            ideaCount={workspace?.ideas.length ?? 0}
            paperCount={workspace?.papers.length ?? 0}
            analysisPaperCount={analysisPapers.length}
            analysisPapers={analysisPapers}
            gaps={workspace?.gaps ?? []}
            ideas={workspace?.ideas ?? []}
            priorityNote={priorityNote}
            recommendation={recommendation}
            researchBrief={workspace?.research_brief ?? null}
            sourceTrace={workspace?.source_trace ?? null}
            summary={workspace?.summary}
            topic={workspace?.topic}
            usesFallbackPapers={usesFallbackPapers}
          />
          <WorkspaceInsightsPanel
            evidenceStatus={workspace?.evidence_status}
            gaps={workspace?.gaps ?? []}
            graphEdges={workspace?.graph_edges ?? []}
            inheritedContext={workspace?.inherited_context ?? null}
            ideas={workspace?.ideas ?? []}
            papers={paperLookupPool}
            sectionMode="insights"
            sourceTrace={workspace?.source_trace ?? null}
            trace={workspace?.trace ?? null}
            workingMemory={workspace?.working_memory ?? null}
            showWorkingMemory={activeView === "conversation"}
          />
        </>
      ) : null}

      {activeSection === "evidence" ? (
        <WorkspaceEvidenceBoard
          analysisPaperCount={analysisPapers.length}
          onSelectPaper={setSelectedPaperId}
          onViewModeChange={(mode) => {
            setEvidenceViewMode(mode);
            setSelectedCategory("all");
            const nextPapers = mode === "analysis" ? analysisPapers : workspace?.papers ?? [];
            setSelectedPaperId(nextPapers[0]?.paper_id ?? "");
          }}
          papers={filteredPapers}
          selectedPaperId={selectedPaper?.paper_id ?? ""}
          showRoundMarkers={activeView === "task"}
          taskId={workspace?.task_id}
          totalPaperCount={workspace?.papers.length ?? 0}
          viewMode={evidenceViewMode}
        />
      ) : null}

      {activeSection === "map" ? (
        <section className="workspace-grid workspace-map-grid">
          <WorkspaceTaxonomyRail
            branches={taxonomyBranches}
            categories={paperCategories}
            coverage={taxonomyCoverage}
            evidenceStatus={workspace?.evidence_status}
            onSelectBranch={setSelectedBranchId}
            onSelectCategory={setSelectedCategory}
            paperCount={analysisPapers.length}
            papers={taxonomyEvidencePapers}
            selectedBranchId={selectedBranchId}
            selectedCategory={selectedCategory}
            topic={workspace?.topic ?? ""}
          />
          <WorkspaceInsightsPanel
            evidenceStatus={workspace?.evidence_status}
            gaps={workspace?.gaps ?? []}
            graphEdges={workspace?.graph_edges ?? []}
            inheritedContext={workspace?.inherited_context ?? null}
            ideas={workspace?.ideas ?? []}
            papers={paperLookupPool}
            sectionMode="map"
            sourceTrace={workspace?.source_trace ?? null}
            trace={workspace?.trace ?? null}
            workingMemory={workspace?.working_memory ?? null}
            showWorkingMemory={activeView === "conversation"}
          />
        </section>
      ) : null}

      {activeSection === "context" ? (
        <WorkspaceInsightsPanel
          evidenceStatus={workspace?.evidence_status}
          gaps={workspace?.gaps ?? []}
          graphEdges={workspace?.graph_edges ?? []}
          inheritedContext={workspace?.inherited_context ?? null}
          ideas={workspace?.ideas ?? []}
          papers={paperLookupPool}
          sectionMode="context"
          sourceTrace={workspace?.source_trace ?? null}
          trace={workspace?.trace ?? null}
          workingMemory={workspace?.working_memory ?? null}
          showWorkingMemory={activeView === "conversation"}
        />
      ) : null}

      {activeSection === "run" ? (
        <>
          <WorkspaceRunFlow
            eventError={runEventsError}
            events={runEvents}
            loadingEvents={runEventsLoading}
            workspace={workspace}
            viewLabel={viewHeadline}
          />
          <WorkspaceInsightsPanel
            evidenceStatus={workspace?.evidence_status}
            gaps={workspace?.gaps ?? []}
            graphEdges={workspace?.graph_edges ?? []}
            inheritedContext={workspace?.inherited_context ?? null}
            ideas={workspace?.ideas ?? []}
            papers={paperLookupPool}
            sectionMode="run"
            sourceTrace={workspace?.source_trace ?? null}
            trace={workspace?.trace ?? null}
            workingMemory={workspace?.working_memory ?? null}
            showWorkingMemory={activeView === "conversation"}
          />
        </>
      ) : null}
    </div>
  );
}
