import { useMemo, useState } from "react";

import { cleanDisplayText } from "../../lib/displayText";
import type { WorkspaceGraphEdge, WorkspacePaper } from "../../types/api";
import {
  categoryTone,
  formatGraphEdgeHeadline,
  formatGraphEdgeReasoningByRelationship,
  relationshipBadgeLabel,
  relationshipLabel,
  relationshipTone,
  shortPaperLabel,
} from "./workspaceFormatters";

type WorkspaceGraphCanvasProps = {
  graphEdges: WorkspaceGraphEdge[];
  papers: WorkspacePaper[];
};

type GraphNode = {
  id: string;
  title: string;
  fullTitle: string;
  subtitle: string;
  category: string;
  x: number;
  y: number;
  degree: number;
};

function uniqueNodeIds(graphEdges: WorkspaceGraphEdge[], papers: WorkspacePaper[]) {
  return Array.from(
    new Set([
      ...papers.map((paper) => paper.paper_id),
      ...graphEdges.flatMap((edge) => [edge.source, edge.target]),
    ].filter(Boolean))
  );
}

function curvedPath(source: GraphNode, target: GraphNode) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.max(Math.hypot(dx, dy), 1);
  const offset = Math.min(70, distance * 0.18);
  const mx = (source.x + target.x) / 2;
  const my = (source.y + target.y) / 2;
  const nx = -dy / distance;
  const ny = dx / distance;
  const cx = mx + nx * offset;
  const cy = my + ny * offset;
  return `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`;
}

function wrapTitle(title: string, maxCharsPerLine = 14, maxLines = 2) {
  const normalized = title.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return ["Untitled"];
  }

  const words = normalized.split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxCharsPerLine || !current) {
      current = next;
      continue;
    }
    lines.push(current);
    current = word;
    if (lines.length === maxLines - 1) {
      break;
    }
  }

  if (lines.length < maxLines && current) {
    lines.push(current);
  }

  const consumedLength = lines.join(" ").length;
  if (consumedLength < normalized.length) {
    const last = lines[lines.length - 1] ?? "";
    lines[lines.length - 1] =
      last.length > maxCharsPerLine - 1 ? `${last.slice(0, maxCharsPerLine - 1)}…` : `${last}…`;
  }

  return lines.slice(0, maxLines);
}

function evidenceLevelLabel(level?: string) {
  const normalized = (level || "").toLowerCase();
  if (normalized === "confirmed") return "已证实";
  if (normalized === "supported") return "文本支持";
  if (normalized === "inferred") return "有依据推断";
  return "候选关系";
}

function confidenceLabel(confidence?: number) {
  const normalized = Math.max(0, Math.min(1, confidence ?? 0));
  return `置信度 ${Math.round(normalized * 100)}%`;
}

export function WorkspaceGraphCanvas({ graphEdges, papers }: WorkspaceGraphCanvasProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const [activeRelationships, setActiveRelationships] = useState<string[]>([]);
  const [graphExpanded, setGraphExpanded] = useState(false);

  const { nodes, edgesByNode, relationshipStats, categoryStats } = useMemo(() => {
    const ids = uniqueNodeIds(graphEdges, papers);
    const width = 820;
    const height = 380;
    const cx = width / 2;
    const cy = height / 2;
    const radiusX = 290;
    const radiusY = 125;

    const degreeMap = new Map<string, number>();
    for (const edge of graphEdges) {
      degreeMap.set(edge.source, (degreeMap.get(edge.source) ?? 0) + 1);
      degreeMap.set(edge.target, (degreeMap.get(edge.target) ?? 0) + 1);
    }

    const graphNodes = ids.map((id, index) => {
      const matchedPaper = papers.find((paper) => paper.paper_id === id);
      const angle = (Math.PI * 2 * index) / Math.max(ids.length, 1) - Math.PI / 2;
      return {
        id,
        title: cleanDisplayText(shortPaperLabel(id, papers), 80),
        fullTitle: cleanDisplayText(matchedPaper?.title?.trim() || id, 180),
        subtitle: matchedPaper?.paper_id ?? id,
        category: cleanDisplayText(matchedPaper?.taxonomy_category, 80) || "Uncategorized",
        x: cx + Math.cos(angle) * radiusX,
        y: cy + Math.sin(angle) * radiusY,
        degree: degreeMap.get(id) ?? 0,
      };
    });

    const nodeEdges = new Map<string, WorkspaceGraphEdge[]>();
    const relationshipCounter = new Map<string, number>();
    const categoryCounter = new Map<string, number>();

    for (const edge of graphEdges) {
      const relationship = cleanDisplayText(edge.relationship, 80);
      relationshipCounter.set(relationship, (relationshipCounter.get(relationship) ?? 0) + 1);
      nodeEdges.set(edge.source, [...(nodeEdges.get(edge.source) ?? []), edge]);
      nodeEdges.set(edge.target, [...(nodeEdges.get(edge.target) ?? []), edge]);
    }

    for (const node of graphNodes) {
      categoryCounter.set(node.category, (categoryCounter.get(node.category) ?? 0) + 1);
    }

    return {
      nodes: graphNodes,
      edgesByNode: nodeEdges,
      relationshipStats: Array.from(relationshipCounter.entries()),
      categoryStats: Array.from(categoryCounter.entries()),
    };
  }, [graphEdges, papers]);

  const visibleRelationships = activeRelationships.length ? new Set(activeRelationships) : null;
  const visibleEdges = useMemo(
    () =>
      graphEdges.filter((edge) => {
        if (!visibleRelationships) {
          return true;
        }
        return visibleRelationships.has(cleanDisplayText(edge.relationship, 80));
      }),
    [graphEdges, visibleRelationships]
  );

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0];
  const selectedEdges = selectedNode
    ? (edgesByNode.get(selectedNode.id) ?? []).filter((edge) =>
        visibleRelationships ? visibleRelationships.has(cleanDisplayText(edge.relationship, 80)) : true
      )
    : [];

  function toggleRelationship(relationship: string) {
    setActiveRelationships((previous) => {
      if (!previous.length) {
        return [relationship];
      }
      if (previous.includes(relationship)) {
        return previous.filter((item) => item !== relationship);
      }
      return [...previous, relationship];
    });
  }

  if (!nodes.length) {
    return (
      <div className="empty-state">
        暂无可展示的核心论文。
      </div>
    );
  }

  return (
    <div className={graphExpanded ? "graph-canvas-card graph-canvas-card-expanded" : "graph-canvas-card"}>
      <div className="graph-legend">
        {graphExpanded ? (
          <button className="graph-reset-button" onClick={() => setGraphExpanded(false)} type="button">
            关闭放大
          </button>
        ) : (
          <button className="graph-reset-button" onClick={() => setGraphExpanded(true)} type="button">
            放大查看
          </button>
        )}
        {relationshipStats.map(([relationship, count]) => (
          <button
            className={
              activeRelationships.length === 0 || activeRelationships.includes(relationship)
                ? "graph-legend-item graph-legend-item-active"
                : "graph-legend-item"
            }
            key={relationship}
            onClick={() => toggleRelationship(relationship)}
            type="button"
          >
            <span className="graph-legend-swatch" style={{ backgroundColor: relationshipTone(relationship) }} />
            {relationshipLabel(relationship)} · {count}
          </button>
        ))}
        {activeRelationships.length ? (
          <button className="graph-reset-button" onClick={() => setActiveRelationships([])} type="button">
            清除筛选
          </button>
        ) : null}
        {!graphEdges.length ? (
          <span className="graph-legend-item">暂无达到展示门槛的关系，当前仅展示核心论文节点</span>
        ) : null}
      </div>

      <div className="graph-category-strip">
        {categoryStats.map(([category, count]) => {
          const tone = categoryTone(category);
          return (
            <span className="graph-category-pill" key={category}>
              <span className="graph-category-dot" style={{ backgroundColor: tone.stroke }} />
              {tone.label} · {count}
            </span>
          );
        })}
      </div>

      <div className={graphExpanded ? "graph-expanded-body" : "graph-inline-body"}>
        <div
          className={graphExpanded ? "graph-canvas-wrap graph-canvas-wrap-expanded" : "graph-canvas-wrap"}
          onClick={() => {
            if (!graphExpanded) {
              setGraphExpanded(true);
            }
          }}
          role="button"
          tabIndex={0}
          title={graphExpanded ? "研究关系图谱放大视图" : "单击放大研究关系图谱"}
          onKeyDown={(event) => {
            if (!graphExpanded && (event.key === "Enter" || event.key === " ")) {
              setGraphExpanded(true);
            }
          }}
        >
          <svg className="graph-canvas" viewBox="0 0 820 380">
            <defs>
              <marker
                id="workspace-graph-arrow"
                markerHeight="8"
                markerWidth="8"
                orient="auto-start-reverse"
                refX="7"
                refY="4"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill="#9fb8e5" />
              </marker>
            </defs>

            {visibleEdges.map((edge, index) => {
              const source = nodes.find((node) => node.id === edge.source);
              const target = nodes.find((node) => node.id === edge.target);
              if (!source || !target) {
                return null;
              }

              const active = selectedNode ? edge.source === selectedNode.id || edge.target === selectedNode.id : false;

              return (
                <path
                  d={curvedPath(source, target)}
                  fill="none"
                  key={`${edge.source}-${edge.target}-${index}`}
                  markerEnd="url(#workspace-graph-arrow)"
                  opacity={active ? 1 : 0.45}
                  stroke={relationshipTone(cleanDisplayText(edge.relationship, 80))}
                  strokeWidth={active ? 2.6 : 1.5}
                />
              );
            })}

            {nodes.map((node) => {
              const active = selectedNode?.id === node.id;
              const radius = 22 + Math.min(node.degree * 2.4, 10);
              const lines = wrapTitle(node.title);
              const tone = categoryTone(node.category);
              return (
                <g
                  className="graph-node-group"
                  key={node.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedNodeId(node.id);
                  }}
                >
                  <title>{`${node.fullTitle}\nPaper ID: ${node.subtitle}`}</title>
                  <circle
                    className={active ? "graph-node-circle graph-node-circle-active" : "graph-node-circle"}
                    cx={node.x}
                    cy={node.y}
                    fill={active ? tone.fill : "#ffffff"}
                    r={radius}
                    stroke={tone.stroke}
                  />
                  <text className="graph-node-title" textAnchor="middle" x={node.x} y={node.y - 8}>
                    {lines.map((line, index) => (
                      <tspan dy={index === 0 ? 0 : 12} key={`${node.id}-line-${index}`} x={node.x}>
                        {line}
                      </tspan>
                    ))}
                  </text>
                  <text className="graph-node-degree" textAnchor="middle" x={node.x} y={node.y + 13}>
                    degree {node.degree}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {selectedNode ? (
          <div className="graph-node-detail">
            <div className="section-eyebrow">选中节点</div>
            <div className="graph-node-detail-title">{selectedNode.fullTitle}</div>
            <div className="graph-node-detail-meta">
              <div className="fine-print">Paper ID: {selectedNode.id}</div>
              <div className="fine-print">Taxonomy Category: {selectedNode.category}</div>
            </div>
            <div className="graph-node-detail-list">
              {selectedEdges.length ? (
                selectedEdges.map((edge, index) => (
                  <div className="graph-node-detail-item" key={`${edge.source}-${edge.target}-${index}`}>
                    <div className="workspace-paper-title-row">
                      <strong>{relationshipBadgeLabel(cleanDisplayText(edge.relationship, 80))}</strong>
                      <span className="message-source-trace-chip">
                        {evidenceLevelLabel(edge.evidence_level)}
                      </span>
                      <span className="message-source-trace-chip">
                        {confidenceLabel(edge.confidence)}
                      </span>
                    </div>
                    <span>{formatGraphEdgeHeadline(edge.relationship, edge.source, edge.target, papers)}</span>
                    <small>{formatGraphEdgeReasoningByRelationship(edge.relationship, edge.reasoning, papers)}</small>
                    {edge.provenance ? (
                      <small className="fine-print">
                        判定来源：{cleanDisplayText(edge.provenance, 100)}
                      </small>
                    ) : null}
                    {edge.evidence_snippets?.slice(0, 2).map((snippet, snippetIndex) => (
                      <small className="fine-print" key={`${edge.source}-${edge.target}-evidence-${snippetIndex}`}>
                        {cleanDisplayText(snippet, 220)}
                      </small>
                    ))}
                  </div>
                ))
              ) : (
                <div className="empty-state">该节点在当前筛选条件下暂无连接关系。</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
