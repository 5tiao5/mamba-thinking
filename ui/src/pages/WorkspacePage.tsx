import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { WorkspaceEvidenceBoard } from "../components/workspace/WorkspaceEvidenceBoard";
import { WorkspaceInsightsPanel } from "../components/workspace/WorkspaceInsightsPanel";
import { WorkspaceSummarySection } from "../components/workspace/WorkspaceSummarySection";
import { WorkspaceTaxonomyRail } from "../components/workspace/WorkspaceTaxonomyRail";
import { api, toErrorMessage } from "../lib/api";
import { DEMO_CONVERSATION_ID, DEMO_WORKSPACE_TASK_ID } from "../lib/demoData";
import type { ResearchTaskDetailItem, WorkspacePaper, WorkspaceSnapshot } from "../types/api";

function taskStatusMessage(task: ResearchTaskDetailItem) {
  if (task.status === "running") {
    return "任务仍在运行中，工作台结果还没有生成，请稍后再读取一次。";
  }
  if (task.status === "created") {
    return "任务还没有运行。先点击一次“运行任务”，再读取工作台。";
  }
  if (task.status === "failed") {
    return "任务运行失败了，所以暂时没有 workspace。请重新运行任务，必要时查看后端日志。";
  }
  return `当前任务状态为 ${task.status}，工作台结果暂不可用。`;
}

export function WorkspacePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const taskIdFromQuery = searchParams.get("task_id") ?? "";
  const conversationIdFromQuery = searchParams.get("conversation_id") ?? "";
  const [taskId, setTaskId] = useState(taskIdFromQuery);
  const [conversationId, setConversationId] = useState(conversationIdFromQuery);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [status, setStatus] = useState("从对话页或首页进入任务后，可以运行分析或读取工作台。");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [selectedBranchId, setSelectedBranchId] = useState("");

  useEffect(() => {
    if (taskIdFromQuery) {
      setTaskId(taskIdFromQuery);
      void handleLoadWorkspace(taskIdFromQuery);
    }
  }, [taskIdFromQuery]);

  const paperCategories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const paper of workspace?.papers ?? []) {
      const key = paper.taxonomy_category || "未分类";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
  }, [workspace]);

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
    const papers = workspace?.papers ?? [];
    if (selectedCategory === "all") {
      return papers;
    }
    return papers.filter((paper) => (paper.taxonomy_category || "未分类") === selectedCategory);
  }, [selectedCategory, workspace]);

  const taxonomyEvidencePapers = useMemo(() => {
    if (!workspace || !selectedBranchId) {
      return [] as WorkspacePaper[];
    }
    const matchedIds = workspace.taxonomy.coverage[selectedBranchId]?.matched_paper_ids ?? [];
    if (!matchedIds.length) {
      return [] as WorkspacePaper[];
    }
    const idSet = new Set(matchedIds);
    return workspace.papers.filter((paper) => idSet.has(paper.paper_id));
  }, [selectedBranchId, workspace]);

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

  async function handleLoadWorkspace(targetId = taskId) {
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
      setSelectedCategory("all");
      setSelectedPaperId(response.data.papers[0]?.paper_id ?? "");
      setSelectedBranchId(response.data.taxonomy.branches[0]?.branch_id ?? "");
      setStatus("工作台已加载。");
      setSearchParams({ task_id: trimmedId });
      if (trimmedId === DEMO_WORKSPACE_TASK_ID) {
        setConversationId(DEMO_CONVERSATION_ID);
      } else {
        try {
          const taskResponse = await api.getTask(trimmedId);
          setConversationId(taskResponse.data.conversation_id);
        } catch {
          setConversationId("");
        }
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

  async function handleLoadConversationWorkspace() {
    const targetConversationId = conversationId || conversationIdFromQuery;
    if (!targetConversationId) {
      setStatus("当前任务还没有关联到会话，无法读取本研究总览。");
      return;
    }

    setLoading(true);
    setStatus("正在读取本研究总览...");
    try {
      const response = await api.getConversationWorkspace(targetConversationId);
      setWorkspace(response.data);
      setSelectedCategory("all");
      setSelectedPaperId(response.data.papers[0]?.paper_id ?? "");
      setSelectedBranchId(response.data.taxonomy.branches[0]?.branch_id ?? "");
      setStatus("本研究总览已加载。");
      setSearchParams({ conversation_id: targetConversationId, task_id: taskId });
    } catch (error) {
      setStatus(`读取本研究总览失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleCloseWorkspace() {
    const targetConversationId = conversationId || conversationIdFromQuery;
    if (targetConversationId) {
      navigate(`/conversation?conversation_id=${encodeURIComponent(targetConversationId)}&task_id=${encodeURIComponent(taskId)}`);
      return;
    }
    navigate("/conversation");
  }

  return (
    <div className="dense-layout">
      <section className="surface content-pad">
        <div className="workspace-toolbar">
          <label>
            <span className="field-label">任务引用</span>
            <input
              className="input"
              onChange={(event) => setTaskId(event.target.value)}
              placeholder="从对话页或首页进入后自动填充"
              value={taskId}
            />
          </label>
          <div className="button-row">
            <button className="secondary-button" onClick={handleCloseWorkspace} type="button">
              关闭完整工作台
            </button>
            <button className="secondary-button" disabled={loading || !conversationId} onClick={handleLoadConversationWorkspace} type="button">
              读取本研究总览
            </button>
            <button className="primary-button" disabled={running} onClick={handleRunTask} type="button">
              {running ? "运行中" : "运行任务"}
            </button>
            <button className="secondary-button" disabled={loading} onClick={() => handleLoadWorkspace()} type="button">
              {loading ? "读取中" : "读取工作台"}
            </button>
          </div>
        </div>
        <div className="status-line" style={{ marginTop: 10 }}>
          {status}
        </div>
      </section>

      <WorkspaceSummarySection
        alignmentScore={workspace?.alignment_score ?? 0}
        evidenceStatus={workspace?.evidence_status}
        gapCount={workspace?.gaps.length ?? 0}
        ideaCount={workspace?.ideas.length ?? 0}
        paperCount={workspace?.papers.length ?? 0}
        priorityNote={priorityNote}
        recommendation={recommendation}
        summary={workspace?.summary}
        topic={workspace?.topic}
        usesFallbackPapers={usesFallbackPapers}
      />

      <section className="workspace-grid">
        <WorkspaceTaxonomyRail
          branches={taxonomyBranches}
          categories={paperCategories}
          coverage={taxonomyCoverage}
          evidenceStatus={workspace?.evidence_status}
          onSelectBranch={setSelectedBranchId}
          onSelectCategory={setSelectedCategory}
          paperCount={workspace?.papers.length ?? 0}
          papers={taxonomyEvidencePapers}
          selectedBranchId={selectedBranchId}
          selectedCategory={selectedCategory}
          topic={workspace?.topic ?? ""}
        />
        <WorkspaceEvidenceBoard
          onSelectPaper={setSelectedPaperId}
          papers={filteredPapers}
          selectedPaperId={selectedPaper?.paper_id ?? ""}
        />
      </section>

      <WorkspaceInsightsPanel
        evidenceStatus={workspace?.evidence_status}
        gaps={workspace?.gaps ?? []}
        graphEdges={workspace?.graph_edges ?? []}
        ideas={workspace?.ideas ?? []}
        papers={workspace?.papers ?? []}
        trace={workspace?.trace ?? null}
      />
    </div>
  );
}
