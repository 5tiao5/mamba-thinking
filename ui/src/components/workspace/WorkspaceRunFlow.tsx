import { cleanDisplayText } from "../../lib/displayText";
import type { ResearchTaskEventItem, WorkspaceSnapshot } from "../../types/api";
import { StatusPill } from "../ui/StatusPill";

type WorkspaceRunFlowProps = {
  workspace: WorkspaceSnapshot | null;
  viewLabel: string;
  events?: ResearchTaskEventItem[];
  loadingEvents?: boolean;
  eventError?: string;
};

type RunStageStatus = "completed" | "degraded" | "pending" | "running" | "failed";

type RunStage = {
  id: string;
  title: string;
  agentName: string;
  detail: string;
  status: RunStageStatus;
  metric: string;
  eventCount: number;
  latestEvent?: ResearchTaskEventItem;
};

function statusTone(status: RunStageStatus): "success" | "warning" | "neutral" | "danger" | "info" {
  if (status === "completed") return "success";
  if (status === "degraded") return "warning";
  if (status === "running") return "info";
  if (status === "failed") return "danger";
  return "neutral";
}

function statusLabel(status: RunStageStatus) {
  if (status === "completed") return "完成";
  if (status === "degraded") return "降级";
  if (status === "running") return "运行中";
  if (status === "failed") return "失败";
  return "待生成";
}

function normalizeEventStage(stage: string) {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("planner") || normalized === "task") return "query";
  if (normalized.includes("search")) return "retrieval";
  if (normalized.includes("audit") || normalized.includes("correct")) return "curation";
  if (normalized.includes("taxonomy")) return "taxonomy";
  if (normalized.includes("evolution") || normalized.includes("graph")) return "graph";
  if (normalized.includes("synth")) return "brief";
  if (normalized.includes("runtime")) return "runtime";
  return normalized || "pipeline";
}

function eventDrivenStatus(
  stageId: string,
  events: ResearchTaskEventItem[],
  fallback: RunStageStatus
): Pick<RunStage, "status" | "eventCount" | "latestEvent"> {
  const relatedEvents = events.filter((event) => normalizeEventStage(event.stage) === stageId);
  const runtimeEvents = stageId === "brief"
    ? events.filter((event) => {
        const status = (event.status || "").toLowerCase();
        return (
          normalizeEventStage(event.stage) === "runtime" &&
          !status.includes("started") &&
          !status.includes("running") &&
          !status.includes("progress")
        );
      })
    : [];
  const candidates = [...relatedEvents, ...runtimeEvents].sort((left, right) => left.sequence - right.sequence);
  const latestEvent = candidates[candidates.length - 1];
  if (!latestEvent) {
    return { status: fallback, eventCount: 0 };
  }

  const statuses = candidates.map((event) => (event.status || "").toLowerCase());
  if (statuses.some((status) => status.includes("failed") || status.includes("error"))) {
    return { status: "failed", eventCount: candidates.length, latestEvent };
  }
  if (statuses.some((status) => status.includes("degraded") || status.includes("step_limit"))) {
    return { status: "degraded", eventCount: candidates.length, latestEvent };
  }
  if (statuses.some((status) => status.includes("started") || status.includes("progress") || status.includes("running"))) {
    const hasCompleted = statuses.some((status) => status.includes("completed"));
    return { status: hasCompleted ? "completed" : "running", eventCount: candidates.length, latestEvent };
  }
  if (statuses.some((status) => status.includes("completed"))) {
    return { status: "completed", eventCount: candidates.length, latestEvent };
  }
  return { status: fallback, eventCount: candidates.length, latestEvent };
}

function withEvents(
  stage: Omit<RunStage, "eventCount" | "latestEvent">,
  events: ResearchTaskEventItem[]
): RunStage {
  const eventState = eventDrivenStatus(stage.id, events, stage.status);
  return {
    ...stage,
    ...eventState,
    detail: eventState.latestEvent?.message
      ? cleanDisplayText(eventState.latestEvent.message, 160)
      : stage.detail,
    metric: eventState.eventCount ? `${eventState.eventCount} 条事件` : stage.metric,
  };
}

function buildRunStages(workspace: WorkspaceSnapshot | null, events: ResearchTaskEventItem[] = []): RunStage[] {
  const sourceTrace = workspace?.source_trace;
  const trace = workspace?.trace;
  const paperCount = workspace?.papers.length ?? 0;
  const analysisPaperCount = workspace?.analysis_paper_ids.length ?? 0;
  const branchCount = workspace?.taxonomy?.branches.length ?? 0;
  const graphEdgeCount = workspace?.graph_edges.length ?? 0;
  const hasBrief = Boolean(workspace?.research_brief?.executive_summary);
  const evidenceInsufficient = workspace?.evidence_status?.insufficient ?? false;
  const fallbackUsed = sourceTrace?.fallback_used ?? false;
  const externalSearchSkipped = sourceTrace?.external_search_skipped ?? false;

  const stages: Array<Omit<RunStage, "eventCount" | "latestEvent">> = [
    {
      id: "query",
      title: "理解研究意图",
      agentName: "Query Strategist",
      detail: workspace
        ? cleanDisplayText(workspace.topic, 120) || "已读取当前研究主题。"
        : "等待任务结果后解析研究主题。",
      status: workspace ? "completed" : "pending",
      metric: `${trace?.context_inputs.length ?? 0} 组上下文`,
    },
    {
      id: "retrieval",
      title: "检索与补搜证据",
      agentName: "Retriever",
      detail: sourceTrace?.retrieval_message
        ? cleanDisplayText(sourceTrace.retrieval_message, 150)
        : externalSearchSkipped
          ? "本轮外部检索跳过，主要依赖导入资料或已有上下文。"
          : "根据主题和追问约束组装论文候选池。",
      status: workspace ? (fallbackUsed || externalSearchSkipped ? "degraded" : "completed") : "pending",
      metric: `${paperCount} 篇候选`,
    },
    {
      id: "curation",
      title: "筛选核心论文",
      agentName: "Evidence Curator",
      detail: evidenceInsufficient
        ? cleanDisplayText(workspace?.evidence_status?.message, 150) || "证据不足，核心结论需要谨慎阅读。"
        : "从候选池中筛出参与 taxonomy、演进图和结论生成的核心论文。",
      status: workspace ? (evidenceInsufficient ? "degraded" : "completed") : "pending",
      metric: `${analysisPaperCount} 篇核心`,
    },
    {
      id: "taxonomy",
      title: "构建研究方向",
      agentName: "Taxonomy Builder",
      detail: branchCount
        ? "已将核心论文组织成可浏览的研究方向分支。"
        : "方向图需要足够论文证据后才适合展示。",
      status: workspace ? (branchCount ? "completed" : "degraded") : "pending",
      metric: `${branchCount} 个分支`,
    },
    {
      id: "graph",
      title: "推断演进关系",
      agentName: "Graph Builder",
      detail: graphEdgeCount
        ? "仅展示达到可信门槛的引用、扩展、改进或强相关关系。"
        : "当前没有足够强的关系证据，避免把弱相关包装成演进结论。",
      status: workspace ? (graphEdgeCount ? "completed" : "degraded") : "pending",
      metric: `${graphEdgeCount} 条关系`,
    },
    {
      id: "brief",
      title: "生成研究简报",
      agentName: "Synthesizer",
      detail: hasBrief
        ? cleanDisplayText(workspace?.research_brief?.executive_summary, 150)
        : "等待结构化研究简报生成。",
      status: workspace ? (hasBrief ? "completed" : "degraded") : "pending",
      metric: workspace?.research_brief?.source || "deterministic",
    },
  ];
  return stages.map((stage) => withEvents(stage, events));
}

function formatEventTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function WorkspaceRunFlow({
  workspace,
  viewLabel,
  events = [],
  loadingEvents = false,
  eventError = "",
}: WorkspaceRunFlowProps) {
  const stages = buildRunStages(workspace, events);
  const completedCount = stages.filter((stage) => stage.status === "completed").length;
  const degradedCount = stages.filter((stage) => stage.status === "degraded").length;
  const failedCount = stages.filter((stage) => stage.status === "failed").length;
  const runningStage = stages.find((stage) => stage.status === "running");
  const failedStage = stages.find((stage) => stage.status === "failed");
  const latestEvent = [...events].sort((left, right) => right.sequence - left.sequence)[0];
  const recentEvents = [...events].sort((left, right) => right.sequence - left.sequence).slice(0, 6);
  const liveTitle = runningStage
    ? `当前执行：${runningStage.title}`
    : failedStage
      ? `停在：${failedStage.title}`
      : workspace
        ? "运行快照已形成"
        : "等待任务运行";
  const liveDetail = runningStage?.latestEvent?.message
    ? cleanDisplayText(runningStage.latestEvent.message, 180)
    : failedStage?.latestEvent?.message
      ? cleanDisplayText(failedStage.latestEvent.message, 180)
      : latestEvent?.message
        ? `最后事件：${cleanDisplayText(latestEvent.message, 180)}`
        : "进入 Run 分区后会读取后端 task events；如果没有事件，则用最终 workspace 快照推断阶段。";

  return (
    <section className="surface workspace-run-flow">
      <div className="workspace-run-flow-head">
        <div>
          <div className="section-eyebrow">Agent Run</div>
          <h2>本轮 Agent 状态图</h2>
          <p>
            {viewLabel}下把后端 task events 折叠成可读的流程节点：先看当前卡在哪一步，
            再展开事件流排查检索、筛选或生成问题。
          </p>
        </div>
        <div className="workspace-run-flow-summary">
          <StatusPill compact tone={failedCount ? "danger" : runningStage ? "info" : degradedCount ? "warning" : "success"}>
            {failedCount ? "存在失败" : runningStage ? "运行中" : degradedCount ? "存在降级" : "流程完整"}
          </StatusPill>
          <strong>{completedCount}/{stages.length}</strong>
          <span>阶段完成</span>
        </div>
      </div>

      <div
        className={`workspace-run-live ${
          failedStage ? "workspace-run-live-failed" : runningStage ? "workspace-run-live-running" : ""
        }`}
      >
        <span className="workspace-run-live-dot" />
        <div>
          <strong>{liveTitle}</strong>
          <p>{liveDetail}</p>
        </div>
      </div>

      <div className="workspace-run-map" aria-label="Agent 运行阶段图">
        {stages.map((stage, index) => (
          <div className={`workspace-run-node workspace-run-node-${stage.status}`} key={stage.id}>
            <div className="workspace-run-node-index">{index + 1}</div>
            <div>
              <div className="workspace-run-node-title">
                <strong>{stage.title}</strong>
                <StatusPill compact tone={statusTone(stage.status)}>
                  {statusLabel(stage.status)}
                </StatusPill>
              </div>
              <span className="workspace-run-node-agent">{stage.agentName}</span>
              <p>{stage.detail}</p>
              <span className="workspace-run-node-metric">{stage.metric}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="workspace-run-event-panel">
        <div className="workspace-run-event-head">
          <div>
            <strong>内部事件流</strong>
            <span>
              {loadingEvents
                ? "正在读取运行事件..."
                : events.length
                  ? `已读取 ${events.length} 条 task events`
                  : "暂无真实事件，当前节点由最终 workspace 快照推断"}
            </span>
          </div>
          {eventError ? <StatusPill compact tone="warning">事件读取失败</StatusPill> : null}
        </div>
        {eventError ? <div className="workspace-run-event-error">{eventError}</div> : null}
        {recentEvents.length ? (
          <div className="workspace-run-event-list">
            {recentEvents.map((event) => (
              <div className="workspace-run-event-item" key={event.event_id}>
                <span>{formatEventTime(event.created_at) || `#${event.sequence}`}</span>
                <strong>{cleanDisplayText(event.stage, 48)}</strong>
                <em>{cleanDisplayText(event.status, 48)}</em>
                <p>{cleanDisplayText(event.message, 150)}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
