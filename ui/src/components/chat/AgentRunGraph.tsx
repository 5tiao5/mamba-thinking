import { cleanDisplayText } from "../../lib/displayText";
import { formatShortTime, taskStatusLabel } from "../../lib/productText";
import type { ResearchTaskEventItem } from "../../types/api";

type AgentNodeId =
  | "planner"
  | "searcher"
  | "taxonomy"
  | "evolution"
  | "auditor"
  | "corrector"
  | "synthesizer"
  | "runtime";

type AgentNodeStatus = "pending" | "running" | "completed" | "degraded" | "failed";

type AgentNodeDefinition = {
  id: AgentNodeId;
  label: string;
  title: string;
  detail: string;
  x: number;
  y: number;
};

type AgentEdgeDefinition = {
  source: AgentNodeId;
  target: AgentNodeId;
  bend?: number;
  label: string;
  explanation: string;
  observedOnly?: boolean;
};

type AgentRunGraphProps = {
  events: ResearchTaskEventItem[];
  onDismiss: () => void;
};

const terminalTaskStatuses = new Set(["completed", "degraded", "failed", "step_limit_reached"]);

const agentNodes: AgentNodeDefinition[] = [
  {
    id: "planner",
    label: "Planner",
    title: "理解与拆解",
    detail: "把用户问题转成可检索、可验证的研究意图。",
    x: 82,
    y: 154,
  },
  {
    id: "searcher",
    label: "Searcher",
    title: "检索证据",
    detail: "并行召回外部论文、导入论文和相关上下文。",
    x: 224,
    y: 64,
  },
  {
    id: "taxonomy",
    label: "Taxonomy",
    title: "方向组织",
    detail: "把论文归纳成研究分支，检查覆盖度。",
    x: 384,
    y: 74,
  },
  {
    id: "evolution",
    label: "Evolution",
    title: "关系推断",
    detail: "推断论文之间的延续、改进、引用和主题关系。",
    x: 390,
    y: 232,
  },
  {
    id: "auditor",
    label: "Auditor",
    title: "证据审计",
    detail: "检查结论是否有足够论文支撑，避免跑题证据污染。",
    x: 224,
    y: 244,
  },
  {
    id: "corrector",
    label: "Corrector",
    title: "补搜修正",
    detail: "发现证据不足时补搜或收紧准入。",
    x: 82,
    y: 224,
  },
  {
    id: "synthesizer",
    label: "Synth",
    title: "生成结论",
    detail: "整合研究简报、方向图、演进图和建议。",
    x: 300,
    y: 154,
  },
  {
    id: "runtime",
    label: "Result",
    title: "结果落盘",
    detail: "保存 workspace、消息和可追溯运行记录。",
    x: 524,
    y: 154,
  },
];

const agentEdges: AgentEdgeDefinition[] = [
  {
    source: "planner",
    target: "searcher",
    bend: -18,
    label: "拆解后检索",
    explanation: "理解用户需求后，把主题、年份、方法约束转成检索策略。",
  },
  {
    source: "searcher",
    target: "taxonomy",
    bend: 8,
    label: "证据入方向图",
    explanation: "检索到论文后，先组织研究方向和分支覆盖。",
  },
  {
    source: "searcher",
    target: "evolution",
    bend: 44,
    label: "证据入关系图",
    explanation: "同一批论文也会进入演进关系候选构建。",
  },
  {
    source: "taxonomy",
    target: "auditor",
    bend: 34,
    label: "方向审计",
    explanation: "检查 taxonomy 分支是否有论文支撑，避免空分支伪装成结论。",
  },
  {
    source: "evolution",
    target: "auditor",
    bend: -28,
    label: "关系审计",
    explanation: "检查演进边是否有引用、方法或文本证据支撑。",
  },
  {
    source: "auditor",
    target: "corrector",
    bend: 18,
    label: "不足则修正",
    explanation: "如果证据不足或跑题，进入补搜、过滤或降级修正。",
  },
  {
    source: "corrector",
    target: "searcher",
    bend: -64,
    label: "补搜回环",
    explanation: "修正节点可能触发再次检索，所以 Searcher 可以运行多次。",
  },
  {
    source: "auditor",
    target: "synthesizer",
    bend: -30,
    label: "通过后综合",
    explanation: "证据审计通过或降级后，才进入研究简报和建议生成。",
  },
  {
    source: "taxonomy",
    target: "synthesizer",
    bend: -10,
    label: "方向供综合",
    explanation: "方向图为最终研究结论提供结构。",
  },
  {
    source: "evolution",
    target: "synthesizer",
    bend: 14,
    label: "关系供综合",
    explanation: "演进关系为最终结论提供论文脉络。",
  },
  {
    source: "synthesizer",
    target: "runtime",
    bend: 0,
    label: "结果落盘",
    explanation: "最终产物写入 workspace 和消息，供用户查看。",
  },
];

const nodeById = agentNodes.reduce(
  (mapping, node) => {
    mapping[node.id] = node;
    return mapping;
  },
  {} as Record<AgentNodeId, AgentNodeDefinition>
);

function normalizeStage(stage?: string): AgentNodeId {
  switch ((stage ?? "").toLowerCase()) {
    case "planner":
    case "query":
    case "strategist":
    case "task":
      return "planner";
    case "searcher":
    case "retriever":
    case "retrieval":
    case "evidence":
      return "searcher";
    case "taxonomy":
    case "taxonomist":
      return "taxonomy";
    case "evolution":
    case "graph":
    case "mapper":
      return "evolution";
    case "auditor":
    case "evidence_auditor":
      return "auditor";
    case "corrector":
    case "repair":
    case "supplement":
      return "corrector";
    case "synthesizer":
    case "synth":
    case "summary":
      return "synthesizer";
    case "runtime":
    case "workspace":
      return "runtime";
    default:
      return "planner";
  }
}

function isTerminalEvent(event?: ResearchTaskEventItem) {
  return Boolean(event && event.stage === "runtime" && terminalTaskStatuses.has(event.status));
}

function eventNodeStatus(event?: ResearchTaskEventItem): AgentNodeStatus {
  if (!event) return "pending";
  if (event.status === "failed") return "failed";
  if (event.status === "degraded" || event.status === "step_limit_reached") return "degraded";
  if (event.status === "completed" || terminalTaskStatuses.has(event.status)) return "completed";
  return "running";
}

function statusText(status: AgentNodeStatus) {
  switch (status) {
    case "running":
      return "运行中";
    case "completed":
      return "已完成";
    case "degraded":
      return "证据受限";
    case "failed":
      return "失败";
    case "pending":
    default:
      return "待接力";
  }
}

function defaultMessageForNode(node: AgentNodeDefinition) {
  return `系统正在进入“${node.title}”阶段。${node.detail}`;
}

function curvedPath(source: AgentNodeDefinition, target: AgentNodeDefinition, bend = 0) {
  const midX = (source.x + target.x) / 2 + bend;
  const midY = (source.y + target.y) / 2;
  return `M ${source.x} ${source.y} C ${midX} ${source.y}, ${midX} ${target.y}, ${target.x} ${target.y}`;
}

function orderedUniqueNodes(events: ResearchTaskEventItem[]) {
  const ordered: AgentNodeId[] = [];
  for (const event of events) {
    const nodeId = normalizeStage(event.stage);
    if (ordered[ordered.length - 1] !== nodeId) {
      ordered.push(nodeId);
    }
  }
  return ordered;
}

function edgeKey(source: AgentNodeId, target: AgentNodeId) {
  return `${source}->${target}`;
}

function edgeKeyOf(edge: Pick<AgentEdgeDefinition, "source" | "target">) {
  return edgeKey(edge.source, edge.target);
}

function incrementCount(mapping: Record<string, number>, key: string) {
  mapping[key] = (mapping[key] ?? 0) + 1;
}

function parseTransitionKey(key: string): [AgentNodeId, AgentNodeId] | null {
  const [source, target] = key.split("->") as [AgentNodeId | undefined, AgentNodeId | undefined];
  if (!source || !target || !(source in nodeById) || !(target in nodeById)) {
    return null;
  }
  return [source, target];
}

function isTransition(value: [AgentNodeId, AgentNodeId] | null): value is [AgentNodeId, AgentNodeId] {
  return value !== null;
}

function eventCountFromPayload(event?: ResearchTaskEventItem, keys: string[] = []) {
  if (!event?.payload) return 0;
  for (const key of keys) {
    const value = event.payload[key];
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return Math.round(value);
    }
  }
  return 0;
}

function nodeNarrative(node: AgentNodeDefinition, event?: ResearchTaskEventItem) {
  const status = eventNodeStatus(event);
  const paperCount = eventCountFromPayload(event, ["paper_count", "analysis_paper_count", "evidence_pool_count"]);
  const filteredCount = eventCountFromPayload(event, ["filtered_out_count", "low_relevance_filtered_count"]);

  if (status === "failed") {
    return {
      headline: `${node.title}阶段遇到问题`,
      body: "系统会保留失败阶段，方便你判断是检索、证据审计还是生成阶段出了问题。",
      userHint: "可以稍后重试，或缩小研究主题、补充论文资料后再运行。",
    };
  }
  if (status === "degraded") {
    return {
      headline: `${node.title}阶段降级完成`,
      body: "系统没有强行包装成完整结论，而是保留证据受限状态，避免把不稳结论说得过满。",
      userHint: "建议优先查看 Evidence 和 Context，确认是否需要补充论文或调整追问。",
    };
  }

  switch (node.id) {
    case "planner":
      return {
        headline: "正在把自然语言问题转成研究任务",
        body: "系统会识别主题、时间范围、方法约束和用户追问意图，后续检索会按这些约束展开。",
        userHint: "如果这里反复停留，通常说明任务刚进入队列或问题正在被拆解。",
      };
    case "searcher":
      return {
        headline: "正在补充和筛选论文证据",
        body: paperCount
          ? `当前阶段已整理到约 ${paperCount} 篇候选或核心论文。`
          : "系统正在从外部论文库、用户论文池和已有上下文中召回候选证据。",
        userHint: filteredCount ? `已有 ${filteredCount} 条低相关或不满足约束的候选被过滤。` : "后续结果应能看到新增/沿用论文的差异。",
      };
    case "taxonomy":
      return {
        headline: "正在组织研究方向",
        body: "系统会把论文聚成若干研究分支，并检查每个分支是否真的有论文支撑。",
        userHint: "如果某个分支没有论文名，后面应在 Map 区暴露为覆盖不足，而不是硬凑结论。",
      };
    case "evolution":
      return {
        headline: "正在判断论文之间的关系",
        body: "系统会尝试识别引用、方法改进、评测对比和主题关联，但弱关系不应伪装成强演进。",
        userHint: "演进图中的强边应能在关系详情里解释依据。",
      };
    case "auditor":
      return {
        headline: "正在审计结论是否站得住",
        body: "系统会检查论文数量、相关性、证据等级和结论绑定，防止跑题论文进入核心结论。",
        userHint: "如果证据不够，后续可能进入补搜修正或生成探索性建议。",
      };
    case "corrector":
      return {
        headline: "正在修正证据缺口",
        body: "系统可能会重新检索、放宽召回、收紧过滤或降级部分结论。",
        userHint: "这个节点可以多次出现，出现多次说明系统正在主动补救，而不是简单复用旧论文。",
      };
    case "synthesizer":
      return {
        headline: "正在生成可读研究结果",
        body: "系统会把论文证据、方向图、演进关系和审计结果汇总成研究简报、空白和建议。",
        userHint: "若没有生成研究建议，页面应解释原因，并给出继续阅读或追问方向。",
      };
    case "runtime":
    default:
      return {
        headline: "正在保存结果与可追溯记录",
        body: "系统会把 workspace、消息和运行事件保存下来，便于你回看本轮结果。",
        userHint: "任务完成后可以进入本次结果或研究总览查看。",
      };
  }
}

export function AgentRunGraph({ events, onDismiss }: AgentRunGraphProps) {
  const latestEvent = events[events.length - 1];
  const currentNodeId = latestEvent ? normalizeStage(latestEvent.stage) : "planner";
  const terminalEvent = isTerminalEvent(latestEvent);
  const eventOrder = orderedUniqueNodes(events);
  const visitedNodeIds = new Set(eventOrder);
  const nodeRunCounts: Partial<Record<AgentNodeId, number>> = {};
  const transitionCounts: Record<string, number> = {};

  const latestEventByNode = events.reduce(
    (mapping, event) => {
      mapping[normalizeStage(event.stage)] = event;
      return mapping;
    },
    {} as Partial<Record<AgentNodeId, ResearchTaskEventItem>>
  );

  for (const nodeId of eventOrder) {
    nodeRunCounts[nodeId] = (nodeRunCounts[nodeId] ?? 0) + 1;
  }

  for (let index = 1; index < eventOrder.length; index += 1) {
    incrementCount(transitionCounts, edgeKey(eventOrder[index - 1], eventOrder[index]));
  }

  const templateEdgeKeys = new Set(agentEdges.map(edgeKeyOf));
  const observedOnlyEdges = Object.keys(transitionCounts)
    .filter((key) => !templateEdgeKeys.has(key))
    .map(parseTransitionKey)
    .filter(isTransition)
    .map(([source, target]) => ({
      source,
      target,
      bend: 0,
      label: "实际跳转",
      explanation: "该边不是预置工作流模板的一部分，而是本轮 task events 实际出现的阶段跳转。",
      observedOnly: true,
    })) as AgentEdgeDefinition[];
  const renderedEdges = [...agentEdges, ...observedOnlyEdges];

  const currentNode = nodeById[currentNodeId];
  const currentStatus = latestEvent ? eventNodeStatus(latestEvent) : "running";
  const recentEvents = events.slice(-3).reverse();
  const currentNarrative = nodeNarrative(currentNode, latestEvent);
  const currentTransitionKey =
    eventOrder.length >= 2 ? edgeKey(eventOrder[eventOrder.length - 2], eventOrder[eventOrder.length - 1]) : "";
  const repeatedNodeCount = Object.values(nodeRunCounts).filter((count) => (count ?? 0) > 1).length;
  const transitionCount = Object.values(transitionCounts).reduce((total, count) => total + count, 0);
  const repeatedTransitions: Array<{ key: string; label: string; count: number }> = [];
  for (const [key, count] of Object.entries(transitionCounts)) {
    if (count <= 1) continue;
    const transition = parseTransitionKey(key);
    if (!transition) continue;
    const [source, target] = transition;
    repeatedTransitions.push({
      key,
      label: `${nodeById[source].label} → ${nodeById[target].label}`,
      count,
    });
  }

  function nodeStatus(nodeId: AgentNodeId): AgentNodeStatus {
    const event = latestEventByNode[nodeId];
    if (nodeId === currentNodeId && !terminalEvent) {
      return eventNodeStatus(event);
    }
    if (event) {
      const status = eventNodeStatus(event);
      return status === "running" ? "completed" : status;
    }
    if (!events.length && nodeId === "planner") {
      return "running";
    }
    return visitedNodeIds.has(nodeId) ? "completed" : "pending";
  }

  function edgeStatus(edge: AgentEdgeDefinition) {
    const key = edgeKeyOf(edge);
    if (!terminalEvent && currentStatus === "running" && key === currentTransitionKey) {
      return "active";
    }
    if (transitionCounts[key]) {
      return "visited";
    }
    return "idle";
  }

  return (
    <div className="agent-run-graph-card" aria-live="polite">
      <div className="agent-run-graph-head">
        <div>
          <span>Agent 运行图谱</span>
          <strong>{currentNode.title}</strong>
          <p>
            预置边表示产品工作流的可达路径，高亮边来自本轮真实 task events；如果补搜发生，节点和边会显示重复次数。
          </p>
        </div>
        <button className="agent-run-graph-close" onClick={onDismiss} type="button">
          收起
        </button>
      </div>

      <div className="agent-run-graph-body">
        <div className="agent-run-graph-canvas" aria-label="Agent 运行节点图">
          <svg role="img" viewBox="0 0 620 310">
            <defs>
              <marker id="agent-graph-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                <path d="M 0 0 L 8 4 L 0 8 z" />
              </marker>
            </defs>

            {renderedEdges.map((edge) => {
              const source = nodeById[edge.source];
              const target = nodeById[edge.target];
              const status = edgeStatus(edge);
              const count = transitionCounts[edgeKeyOf(edge)] ?? 0;
              return (
                <g key={`${edge.source}-${edge.target}-${edge.observedOnly ? "observed" : "template"}`}>
                  <path
                    className={`agent-run-graph-edge agent-run-graph-edge-${status} ${
                      edge.observedOnly ? "agent-run-graph-edge-observed" : ""
                    }`}
                    d={curvedPath(source, target, edge.bend)}
                    markerEnd="url(#agent-graph-arrow)"
                  >
                    <title>
                      {edge.label}：{edge.explanation}
                      {count > 1 ? ` 本轮重复 ${count} 次。` : ""}
                    </title>
                  </path>
                </g>
              );
            })}

            {agentNodes.map((node) => {
              const status = nodeStatus(node.id);
              const runCount = nodeRunCounts[node.id] ?? 0;
              return (
                <g
                  className={`agent-run-graph-node agent-run-graph-node-${status}`}
                  key={node.id}
                  transform={`translate(${node.x} ${node.y})`}
                >
                  <circle className="agent-run-graph-node-halo" r="35" />
                  <circle className="agent-run-graph-node-core" r="26" />
                  <text className="agent-run-graph-node-label" textAnchor="middle" y="-2">
                    {node.label}
                  </text>
                  <text className="agent-run-graph-node-status" textAnchor="middle" y="15">
                    {statusText(status)}
                  </text>
                  {runCount > 1 ? (
                    <g className="agent-run-graph-node-count" transform="translate(0 38)">
                      <rect height="20" rx="10" width={runCount >= 10 ? 34 : 28} x={runCount >= 10 ? -17 : -14} y="-10" />
                      <text textAnchor="middle" y="3.5">
                        ×{runCount}
                      </text>
                    </g>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>

        <aside className={`agent-run-live-panel agent-run-live-panel-${currentStatus}`}>
          <span className="agent-run-live-eyebrow">当前节点</span>
          <strong>{currentNarrative.headline}</strong>
          <p>{cleanDisplayText(currentNarrative.body || defaultMessageForNode(currentNode), 220)}</p>
          <div className="agent-run-live-meta">
            <span>{currentNode.label} · {statusText(currentStatus)}</span>
            <span>{transitionCount} 次阶段跳转</span>
            {repeatedNodeCount ? <span>{repeatedNodeCount} 个节点重复运行</span> : null}
            <span>{latestEvent ? formatShortTime(latestEvent.created_at) : "刚刚"}</span>
          </div>

          {repeatedTransitions.length ? (
            <div className="agent-run-repeat-strip" aria-label="重复运行路径">
              {repeatedTransitions.slice(0, 4).map((transition) => (
                <span key={transition.key}>
                  {transition.label} ×{transition.count}
                </span>
              ))}
            </div>
          ) : null}

          <div className="agent-run-user-hint">
            <b>你可以关注</b>
            <span>{currentNarrative.userHint}</span>
          </div>

          <details className="agent-run-edge-help">
            <summary>这些边怎么来的？</summary>
            <p>
              灰色边是系统预置工作流模板，表示理论上可能发生的阶段转移；蓝色/绿色边来自本轮真实
              task events。若某个节点多次运行，说明发生了补搜、修正或重复审计。
            </p>
          </details>

          <div className="agent-run-event-stack" aria-label="最近运行事件">
            {(recentEvents.length ? recentEvents : [{ event_id: "pending" } as ResearchTaskEventItem]).map((event) => {
              const node = event.event_id === "pending" ? currentNode : nodeById[normalizeStage(event.stage)];
              const narrative = event.event_id === "pending" ? null : nodeNarrative(node, event);
              return (
                <div className="agent-run-event-chip" key={event.event_id}>
                  <b>{node.title}</b>
                  <span>
                    {event.event_id === "pending"
                      ? "等待 Agent 接手"
                      : cleanDisplayText(narrative?.headline || taskStatusLabel(event.status), 92)}
                  </span>
                </div>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}
