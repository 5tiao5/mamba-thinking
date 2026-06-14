import { useState, type ReactNode } from "react";

import { cleanDisplayText } from "../../lib/displayText";
import {
  formatRetrievalMessage,
  formatRetrievalPlan,
  knowledgeScopeLabel,
  knowledgeScopeTone,
  retrievalStatusLabel,
  retrievalStatusTone,
  shouldHighlightRetrievalStatus,
} from "../../lib/groundingText";
import type {
  WorkspaceEvidenceStatus,
  WorkspaceGap,
  WorkspaceGraphEdge,
  WorkspaceIdea,
  WorkspaceInheritedContext,
  WorkspaceKnowledgeHit,
  WorkspacePaper,
  WorkspaceSnapshot,
  WorkspaceSourceTrace,
  WorkspaceWorkingMemory,
} from "../../types/api";
import { SectionHeader } from "../ui/SectionHeader";
import { StatusPill } from "../ui/StatusPill";
import { WorkspaceGraphCanvas } from "./WorkspaceGraphCanvas";
import {
  formatGapCategory,
  formatGapDetail,
  formatGapEvidenceItems,
  formatGapHeadline,
  formatIdeaApproach,
  formatIdeaApproachFull,
  formatIdeaContribution,
  formatIdeaContributionFull,
  formatIdeaFeasibility,
  formatIdeaFeasibilityFull,
  formatIdeaSummary,
  formatIdeaSummaryFull,
  gapCategoryTone,
  relationshipLabel,
} from "./workspaceFormatters";

function severityTone(severity: string): "danger" | "warning" | "neutral" {
  const normalized = severity.toLowerCase();
  if (normalized === "high" || normalized === "error") return "danger";
  if (normalized === "medium" || normalized === "warning") return "warning";
  return "neutral";
}

function severityLabel(severity: string) {
  const normalized = severity.toLowerCase();
  if (normalized === "high" || normalized === "error") return "高优先级";
  if (normalized === "medium" || normalized === "warning") return "中优先级";
  if (normalized === "low" || normalized === "info") return "低优先级";
  return severity || "待判断";
}

function uniqueTexts(items: string[], maxItems: number, maxLength = 72) {
  const seen = new Set<string>();
  const values: string[] = [];

  for (const item of items) {
    const cleaned = cleanDisplayText(item, maxLength);
    if (!cleaned || seen.has(cleaned)) {
      continue;
    }
    seen.add(cleaned);
    values.push(cleaned);
    if (values.length >= maxItems) {
      break;
    }
  }

  return values;
}

function uniqueFullTexts(items: string[], maxItems: number) {
  const seen = new Set<string>();
  const values: string[] = [];

  for (const item of items) {
    const cleaned = cleanDisplayText(item);
    if (!cleaned || seen.has(cleaned)) {
      continue;
    }
    seen.add(cleaned);
    values.push(cleaned);
    if (values.length >= maxItems) {
      break;
    }
  }

  return values;
}

function evidenceLevelLabel(level: string) {
  const normalized = (level || "").toLowerCase();
  if (normalized === "strong") return "强证据";
  if (normalized === "moderate") return "中等证据";
  if (normalized === "weak") return "弱证据";
  return "候选证据";
}

function evidenceLevelTone(level: string): "success" | "info" | "warning" | "neutral" {
  const normalized = (level || "").toLowerCase();
  if (normalized === "strong") return "success";
  if (normalized === "moderate") return "info";
  if (normalized === "weak" || normalized === "candidate") return "warning";
  return "neutral";
}

function formatWorkingMemoryDate(value?: string) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatKnowledgeHit(hit: WorkspaceKnowledgeHit) {
  const titleFull = cleanDisplayText(hit.title) || "未命名资料";
  const snippetFull = cleanDisplayText(hit.snippet);
  const parts = [hit.source_type, hit.scope].map((item) => cleanDisplayText(item, 20)).filter(Boolean);
  return {
    title: cleanDisplayText(hit.title, 72) || titleFull,
    titleFull,
    snippet: cleanDisplayText(hit.snippet, 180),
    snippetFull,
    meta: parts.join(" / "),
    score: Number.isFinite(hit.score) ? hit.score.toFixed(2) : "",
    evidenceLevel: hit.evidence_level || "candidate",
    matchedChunkCount: hit.matched_chunk_count ?? 0,
    supportingSnippets: uniqueTexts(hit.supporting_snippets ?? [], 6, 180),
    supportingSnippetsFull: uniqueFullTexts(hit.supporting_snippets ?? [], 6),
  };
}

function GapList({ gaps, papers }: { gaps: WorkspaceGap[]; papers: WorkspacePaper[] }) {
  if (!gaps.length) {
    return <div className="empty-state">暂时没有整理出稳定的研究空白。</div>;
  }

  return (
    <div className="insight-list">
      {gaps.map((gap, index) => (
        <article className="insight-item" key={`${gap.summary}-${index}`}>
          <div className="insight-meta-row">
            <span className={`insight-kind insight-kind-${gapCategoryTone(gap)}`}>{formatGapCategory(gap)}</span>
          </div>
          <div className="item-heading">
            <div className="insight-title">{formatGapHeadline(gap, papers)}</div>
            <StatusPill compact tone={severityTone(gap.severity)}>
              {severityLabel(gap.severity)}
            </StatusPill>
          </div>
          <div className="fine-print insight-copy">{formatGapDetail(gap, papers)}</div>
          {formatGapEvidenceItems(gap, papers).length ? (
            <div className="insight-chip-wrap">
              {formatGapEvidenceItems(gap, papers).slice(0, 3).map((item) => (
                <span className="insight-chip" key={item}>
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function IdeaCard({ idea, papers }: { idea: WorkspaceIdea; papers: WorkspacePaper[] }) {
  const [expanded, setExpanded] = useState(false);

  const title = cleanDisplayText(idea.title, 160) || "未命名建议";
  const summary = formatIdeaSummary(idea, papers);
  const approach = formatIdeaApproach(idea, papers);
  const feasibility = formatIdeaFeasibility(idea, papers);
  const contribution = formatIdeaContribution(idea, papers);

  const fullSummary = formatIdeaSummaryFull(idea, papers);
  const fullApproach = formatIdeaApproachFull(idea, papers);
  const fullFeasibility = formatIdeaFeasibilityFull(idea, papers);
  const fullContribution = formatIdeaContributionFull(idea, papers);

  return (
    <article className={`insight-item ${expanded ? "insight-item-expanded" : ""}`}>
      <div className="insight-meta-row">
        <span className="insight-kind insight-kind-accent">研究机会</span>
      </div>
      <div className="insight-title">{title}</div>

      {!expanded ? (
        <>
          <div className="insight-summary-block">
            <strong>机会摘要</strong>
            <div className="fine-print insight-copy">{summary}</div>
          </div>

          {approach ? (
            <div className="insight-emphasis">
              <strong>建议做法</strong>
              <span>{approach}</span>
            </div>
          ) : null}

          {feasibility || contribution ? (
            <div className="insight-support-grid">
              {feasibility ? (
                <div className="insight-support-card insight-support-card-accent">
                  <strong>可行性</strong>
                  <span>{feasibility}</span>
                </div>
              ) : null}
              {contribution ? (
                <div className="insight-support-card">
                  <strong>预期贡献</strong>
                  <span>{contribution}</span>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : (
        <div className="insight-details-body">
          <div className="insight-summary-block">
            <strong>机会摘要</strong>
            <div className="fine-print insight-copy insight-copy-full">{fullSummary}</div>
          </div>

          {fullApproach ? (
            <div className="insight-emphasis">
              <strong>建议做法</strong>
              <span className="insight-copy-full">{fullApproach}</span>
            </div>
          ) : null}

          {fullFeasibility || fullContribution ? (
            <div className="insight-support-grid">
              {fullFeasibility ? (
                <div className="insight-support-card insight-support-card-accent">
                  <strong>可行性</strong>
                  <span className="insight-copy-full">{fullFeasibility}</span>
                </div>
              ) : null}
              {fullContribution ? (
                <div className="insight-support-card">
                  <strong>预期贡献</strong>
                  <span className="insight-copy-full">{fullContribution}</span>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      <button className="insight-toggle-button" onClick={() => setExpanded((value) => !value)} type="button">
        {expanded ? "收起详情" : "展开详情"}
      </button>
    </article>
  );
}

function IdeaList({ ideas, papers }: { ideas: WorkspaceIdea[]; papers: WorkspacePaper[] }) {
  if (!ideas.length) {
    return <div className="empty-state">暂时没有生成稳定的研究建议。</div>;
  }

  return (
    <div className="insight-list">
      {ideas.map((idea, index) => (
        <IdeaCard idea={idea} key={`${idea.title}-${index}`} papers={papers} />
      ))}
    </div>
  );
}

function KnowledgeHitCard({ hit }: { hit: ReturnType<typeof formatKnowledgeHit> }) {
  const [expanded, setExpanded] = useState(false);
  const hasSupportingSnippets = hit.supportingSnippetsFull.length > 0;
  const title = expanded ? hit.titleFull : hit.title;
  const snippet = expanded ? hit.snippetFull : hit.snippet;
  const supportingSnippets = expanded ? hit.supportingSnippetsFull : hit.supportingSnippets;

  return (
    <div className="workspace-context-list-item">
      <div className="workspace-hit-header">
        <span className={`workspace-hit-title ${expanded ? "workspace-hit-title-expanded" : ""}`} title={hit.titleFull}>
          {title}
        </span>
        <div className="workspace-hit-meta-pills">
          <StatusPill compact tone={evidenceLevelTone(hit.evidenceLevel)}>
            {evidenceLevelLabel(hit.evidenceLevel)}
          </StatusPill>
          {hit.matchedChunkCount > 0 ? (
            <StatusPill compact tone="neutral">
              {hit.matchedChunkCount} 个片段
            </StatusPill>
          ) : null}
        </div>
      </div>

      {snippet ? <p className={expanded ? "workspace-hit-snippet-expanded" : undefined}>{snippet}</p> : null}

      <small>
        {hit.meta || "资料命中"}
        {hit.score ? ` · score ${hit.score}` : ""}
      </small>

      {hasSupportingSnippets ? (
        <>
          <button
            className="workspace-inline-toggle"
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            {expanded ? "收起完整片段" : `展开完整片段 (${hit.supportingSnippetsFull.length})`}
          </button>

          {expanded ? (
            <div className="workspace-supporting-snippets">
              {supportingSnippets.map((snippet, index) => (
                <div className="workspace-supporting-snippet" key={`${snippet}-${index}`}>
                  {snippet}
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function WorkingMemoryPanel({ workingMemory }: { workingMemory?: WorkspaceWorkingMemory | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!workingMemory) {
    return <div className="empty-state">当前还没有形成稳定的会话级工作记忆。</div>;
  }

  const stableFindings = uniqueTexts(workingMemory.stable_findings, 8, 120);
  const openQuestions = uniqueTexts(workingMemory.open_questions, 8, 140);
  const activeConstraints = uniqueTexts(workingMemory.active_constraints, 8, 120);
  const focus = cleanDisplayText(workingMemory.current_focus, 180);
  const summary = cleanDisplayText(workingMemory.summary, 320);
  const updatedAt = formatWorkingMemoryDate(workingMemory.updated_at);

  return (
    <div className="content-pad pane-scroll workspace-context-panel">
      <div className="workspace-memory-overview">
        <div className="workspace-memory-card workspace-memory-card-accent">
          <strong>当前研究焦点</strong>
          <div className="workspace-context-summary-copy">
            {focus || "当前还没有收敛出明确焦点。"}
          </div>
        </div>
        <div className="workspace-memory-card">
          <strong>工作记忆摘要</strong>
          <div className="workspace-context-summary-copy">
            {summary || "系统还在整理本研究的稳定结论和待解问题。"}
          </div>
        </div>
      </div>

      <div className="workspace-context-metrics workspace-memory-metrics">
        <div>
          <span>稳定结论</span>
          <strong>{stableFindings.length}</strong>
        </div>
        <div>
          <span>待解问题</span>
          <strong>{openQuestions.length}</strong>
        </div>
        <div>
          <span>活跃约束</span>
          <strong>{activeConstraints.length}</strong>
        </div>
        <div>
          <span>最近更新</span>
          <strong>{updatedAt || "-"}</strong>
        </div>
      </div>

      <button className="insight-toggle-button" onClick={() => setExpanded((value) => !value)} type="button">
        {expanded ? "收起工作记忆详情" : "展开工作记忆详情"}
      </button>

      {expanded ? (
        <div className="workspace-context-stack">
          <div className="workspace-context-card">
            <strong>稳定结论</strong>
            {stableFindings.length ? (
              <div className="workspace-memory-list">
                {stableFindings.map((item) => (
                  <div className="workspace-memory-list-item" key={item}>
                    {item}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state workspace-inline-empty">当前还没有沉淀出稳定结论。</div>
            )}
          </div>

          <div className="workspace-context-card">
            <strong>待解问题</strong>
            {openQuestions.length ? (
              <div className="workspace-memory-list">
                {openQuestions.map((item) => (
                  <div className="workspace-memory-list-item" key={item}>
                    {item}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state workspace-inline-empty">当前没有挂起的关键问题。</div>
            )}
          </div>

          <div className="workspace-context-card">
            <strong>当前约束</strong>
            {activeConstraints.length ? (
              <div className="workspace-context-chip-wrap">
                {activeConstraints.map((item) => (
                  <span className="insight-chip insight-chip-accent" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            ) : (
              <div className="empty-state workspace-inline-empty">当前没有显式记录的研究约束。</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SourceTracePanel({ sourceTrace }: { sourceTrace?: WorkspaceSourceTrace | null }) {
  if (!sourceTrace) {
    return <div className="empty-state">这轮结果还没有记录可展示的依据摘要。</div>;
  }

  const hits = sourceTrace.knowledge_hits.map(formatKnowledgeHit);
  const workspaceHints = uniqueTexts(sourceTrace.workspace_hints, 6, 72);
  const recentTurns = uniqueTexts(sourceTrace.recent_user_turns, 4, 84);
  const retrievalStatus = retrievalStatusLabel(sourceTrace.retrieval_status);
  const retrievalPlan = formatRetrievalPlan(sourceTrace.retrieval_plan, 220);
  const retrievalMessage = formatRetrievalMessage(sourceTrace, 260);
  const filteredOutCount = sourceTrace.filtered_out_count ?? 0;
  const fallbackUsed = sourceTrace.fallback_used ?? false;
  const hasRetrievalSummary = Boolean(
    retrievalStatus || retrievalPlan || retrievalMessage || filteredOutCount || fallbackUsed
  );

  return (
    <div className="content-pad pane-scroll workspace-context-panel">
      <div className="workspace-context-header">
        <StatusPill compact tone={knowledgeScopeTone(sourceTrace.knowledge_scope)}>
          {knowledgeScopeLabel(sourceTrace.knowledge_scope)}
        </StatusPill>
        {retrievalStatus ? (
          <StatusPill compact tone={retrievalStatusTone(sourceTrace.retrieval_status)}>
            {retrievalStatus}
          </StatusPill>
        ) : null}
        {fallbackUsed ? (
          <StatusPill compact tone="warning">
            fallback 仅作背景参考
          </StatusPill>
        ) : null}
      </div>

      <div className="workspace-context-metrics">
        <div>
          <span>知识命中</span>
          <strong>{sourceTrace.knowledge_hit_count}</strong>
        </div>
        <div>
          <span>历史结论</span>
          <strong>{sourceTrace.workspace_hint_count}</strong>
        </div>
        <div>
          <span>过滤越界</span>
          <strong>{filteredOutCount}</strong>
        </div>
        <div>
          <span>近期追问</span>
          <strong>{sourceTrace.recent_turn_count}</strong>
        </div>
      </div>

      <div className="workspace-context-stack">
        {hasRetrievalSummary ? (
          <div
            className={`workspace-context-card ${
              shouldHighlightRetrievalStatus(sourceTrace.retrieval_status)
                ? "workspace-context-card-warning"
                : "workspace-context-card-accent"
            }`}
          >
            <strong>检索结果说明</strong>
            <div className="workspace-context-summary-copy">
              {retrievalMessage || "这轮检索没有额外的约束说明，但检索策略已按当前意图执行。"}
            </div>
            {retrievalPlan ? (
              <div className="workspace-context-plan-row">
                <span>检索策略</span>
                <small>{retrievalPlan}</small>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="workspace-context-card">
          <strong>命中的知识来源</strong>
          {hits.length ? (
            <div className="workspace-context-list">
              {hits.slice(0, 4).map((hit) => (
                <KnowledgeHitCard hit={hit} key={`${hit.title}-${hit.meta}-${hit.score}-${hit.evidenceLevel}`} />
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">本轮没有命中可展示的知识条目。</div>
          )}
        </div>

        <div className="workspace-context-card">
          <strong>沿用的历史线索</strong>
          {workspaceHints.length ? (
            <div className="workspace-context-chip-wrap">
              {workspaceHints.map((hint) => (
                <span className="insight-chip insight-chip-accent" key={hint}>
                  {hint}
                </span>
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">本轮暂未显式继承历史 workspace 结论。</div>
          )}
        </div>

        <div className="workspace-context-card">
          <strong>承接的近期追问</strong>
          {recentTurns.length ? (
            <div className="workspace-context-list">
              {recentTurns.map((turn) => (
                <div className="workspace-context-list-item" key={turn}>
                  <span>{turn}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">这轮没有记录到可展示的近期追问片段。</div>
          )}
        </div>
      </div>
    </div>
  );
}

function InheritedContextPanel({ inheritedContext }: { inheritedContext?: WorkspaceInheritedContext | null }) {
  if (!inheritedContext) {
    return <div className="empty-state">这轮结果还没有沉淀出可继承的上下文。</div>;
  }

  const workspaceHints = uniqueTexts(inheritedContext.workspace_hints, 6, 72);
  const recentTurns = uniqueTexts(inheritedContext.recent_turns, 4, 84);
  const topic = cleanDisplayText(inheritedContext.conversation_topic, 96);
  const summary = cleanDisplayText(inheritedContext.workspace_summary, 220);

  return (
    <div className="content-pad pane-scroll workspace-context-panel">
      <div className="workspace-context-stack">
        <div className="workspace-context-card workspace-context-card-accent">
          <strong>当前研究主题</strong>
          <div className="workspace-context-summary-copy">
            {topic || "当前主题尚未同步到这里。"}
          </div>
        </div>

        <div className="workspace-context-card">
          <strong>继承的工作区摘要</strong>
          <div className="workspace-context-summary-copy">
            {summary || "当前还没有沉淀出稳定摘要，可在更多轮次后继续观察。"}
          </div>
        </div>

        <div className="workspace-context-card">
          <strong>沿用的关键结论</strong>
          {workspaceHints.length ? (
            <div className="workspace-context-chip-wrap">
              {workspaceHints.map((hint) => (
                <span className="insight-chip" key={hint}>
                  {hint}
                </span>
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">目前还没有抽取出稳定的继承结论。</div>
          )}
        </div>

        <div className="workspace-context-card">
          <strong>最近对话片段</strong>
          {recentTurns.length ? (
            <div className="workspace-context-list">
              {recentTurns.map((turn) => (
                <div className="workspace-context-list-item" key={turn}>
                  <span>{turn}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">最近追问还没有被压缩成可展示片段。</div>
          )}
        </div>
      </div>
    </div>
  );
}

function CollapsibleInsightSection({
  title,
  eyebrow,
  children,
  defaultOpen = false,
  className = "",
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <details className={`pane workspace-collapsible-pane ${className}`} open={defaultOpen}>
      <summary className="workspace-collapsible-summary">
        <span>
          <span className="section-eyebrow">{eyebrow}</span>
          <strong>{title}</strong>
        </span>
        <span className="workspace-collapsible-indicator">展开</span>
      </summary>
      {children}
    </details>
  );
}

export function WorkspaceInsightsPanel({
  gaps,
  ideas,
  graphEdges,
  papers,
  evidenceStatus,
  trace,
  sourceTrace,
  inheritedContext,
  workingMemory,
  showWorkingMemory = false,
}: {
  gaps: WorkspaceGap[];
  ideas: WorkspaceIdea[];
  graphEdges: WorkspaceGraphEdge[];
  papers: WorkspacePaper[];
  evidenceStatus?: WorkspaceEvidenceStatus;
  trace: WorkspaceSnapshot["trace"];
  sourceTrace?: WorkspaceSourceTrace | null;
  inheritedContext?: WorkspaceInheritedContext | null;
  workingMemory?: WorkspaceWorkingMemory | null;
  showWorkingMemory?: boolean;
}) {
  const insufficientEvidence = evidenceStatus?.insufficient ?? false;

  return (
    <section className="workspace-insights-grid">
      <section className="pane">
        <SectionHeader eyebrow={`${gaps.length} 条`} title="研究空白" />
        <div className="pane-scroll">
          <GapList gaps={gaps} papers={papers} />
        </div>
      </section>

      <section className="pane">
        <SectionHeader eyebrow={`${ideas.length} 条`} title="研究建议" />
        <div className="pane-scroll">
          <IdeaList ideas={ideas} papers={papers} />
        </div>
      </section>

      <section className="workspace-secondary-stack">
        <CollapsibleInsightSection
          eyebrow={`${graphEdges.length} 条关系`}
          title="研究关系图谱"
          className="workspace-graph-pane"
        >
          <div className="content-pad pane-scroll">
            <div className="workspace-evidence-scope-note">
              仅展示达到可信门槛的引用、文本支持或高置信推断关系；“主题关联”不代表方法改进或引用继承。
            </div>
            {insufficientEvidence ? (
              <div className="empty-state workspace-evidence-mode-note">
                当前证据不足，这一轮不展示研究关系图谱。补充真实论文或全文证据后再判断论文之间的关系。
              </div>
            ) : (
              <>
                <WorkspaceGraphCanvas graphEdges={graphEdges} papers={papers} />
                <details className="workspace-edge-details">
                  <summary>查看关系明细</summary>
                  {graphEdges.length ? (
                    <div className="data-table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>起点</th>
                            <th>终点</th>
                            <th>关系</th>
                            <th>证据等级</th>
                            <th>置信度</th>
                            <th>判定依据</th>
                          </tr>
                        </thead>
                        <tbody>
                          {graphEdges.map((edge, index) => (
                            <tr key={`${edge.source}-${edge.target}-${index}`}>
                              <td>{cleanDisplayText(edge.source, 80)}</td>
                              <td>{cleanDisplayText(edge.target, 80)}</td>
                              <td>{relationshipLabel(cleanDisplayText(edge.relationship, 80))}</td>
                              <td>{cleanDisplayText(edge.evidence_level || "candidate", 80)}</td>
                              <td>{Math.round((edge.confidence ?? 0) * 100)}%</td>
                              <td>{cleanDisplayText(edge.reasoning) || "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty-state">暂无线索关系可展示。</div>
                  )}
                </details>
              </>
            )}
          </div>
        </CollapsibleInsightSection>

        {showWorkingMemory ? (
          <CollapsibleInsightSection eyebrow="会话级记忆" title="工作记忆">
            <WorkingMemoryPanel workingMemory={workingMemory} />
          </CollapsibleInsightSection>
        ) : null}

        <CollapsibleInsightSection
          eyebrow={sourceTrace ? `${sourceTrace.knowledge_hit_count} 条知识命中` : "结果依据"}
          title="本轮依据"
        >
          <SourceTracePanel sourceTrace={sourceTrace} />
        </CollapsibleInsightSection>

        <CollapsibleInsightSection
          eyebrow={inheritedContext?.conversation_topic ? "连续研究" : "历史上下文"}
          title="继承上下文"
        >
          <InheritedContextPanel inheritedContext={inheritedContext} />
        </CollapsibleInsightSection>

        <CollapsibleInsightSection eyebrow="过程记录" title="研究过程">
          {trace ? (
            <div className="content-grid content-pad">
              <div className="trace-row">
                <div className="trace-label">分析步骤</div>
                <div>{trace.thought_trace.length} 步</div>
              </div>
              <div className="trace-row">
                <div className="trace-label">搜索动作</div>
                <div>{trace.action_history.length} 条</div>
              </div>
              <div className="trace-row">
                <div className="trace-label">上下文输入</div>
                <div>{trace.context_inputs.length} 组</div>
              </div>
            </div>
          ) : (
            <div className="empty-state">暂时没有研究过程记录。</div>
          )}
        </CollapsibleInsightSection>
      </section>
    </section>
  );
}
