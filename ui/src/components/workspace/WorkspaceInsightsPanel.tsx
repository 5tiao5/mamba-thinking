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
  cleanWorkspaceText,
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
  resolvePaperTitle,
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
  if (normalized === "strong") return "高相关命中";
  if (normalized === "moderate") return "中等相关";
  if (normalized === "weak") return "弱相关参考";
  return "候选参考";
}

function evidenceLevelTone(level: string): "success" | "info" | "warning" | "neutral" {
  const normalized = (level || "").toLowerCase();
  if (normalized === "strong") return "success";
  if (normalized === "moderate") return "info";
  if (normalized === "weak" || normalized === "candidate") return "warning";
  return "neutral";
}

type ConclusionEvidenceLevel = NonNullable<WorkspaceGap["evidence_level"]>;

function conclusionEvidenceLabel(level: ConclusionEvidenceLevel) {
  if (level === "direct") return "直接证据";
  if (level === "indirect") return "间接支撑";
  return "待验证假设";
}

function conclusionEvidenceTone(
  level: ConclusionEvidenceLevel,
): "success" | "info" | "warning" {
  if (level === "direct") return "success";
  if (level === "indirect") return "info";
  return "warning";
}

function conclusionEvidenceReason(
  level: ConclusionEvidenceLevel,
  paperCount: number,
  rawReason?: string,
) {
  const cleaned = cleanDisplayText(rawReason, 260);
  const isGenericBackendReason =
    /^The (conclusion|research gap|research recommendation)\b/i.test(cleaned) ||
    /^No eligible supporting paper\b/i.test(cleaned);

  if (cleaned && !isGenericBackendReason) {
    return cleaned;
  }
  if (level === "direct") {
    return "该结论已与当前分析池中的论文建立直接证据绑定。";
  }
  if (level === "indirect") {
    return `该结论与 ${paperCount} 篇核心论文相关，但尚未完成全文级结论核验。`;
  }
  return paperCount
    ? `该结论由 ${paperCount} 篇核心论文启发，但尚未完成全文核验或实验验证。`
    : "暂无合格论文可直接支撑该结论，当前内容应视为待验证的研究假设。";
}

function ConclusionEvidenceBlock({
  supportingPaperIds,
  evidenceLevel,
  evidenceReason,
  papers,
}: {
  supportingPaperIds?: string[];
  evidenceLevel?: WorkspaceGap["evidence_level"];
  evidenceReason?: string;
  papers: WorkspacePaper[];
}) {
  if (!evidenceLevel) {
    return null;
  }

  const paperIds = Array.from(new Set(supportingPaperIds ?? []));
  const reason = conclusionEvidenceReason(evidenceLevel, paperIds.length, evidenceReason);

  if (!paperIds.length) {
    return (
      <div className="conclusion-evidence conclusion-evidence-exploratory">
        <div className="conclusion-evidence-heading">
          <StatusPill compact tone={conclusionEvidenceTone(evidenceLevel)}>
            {conclusionEvidenceLabel(evidenceLevel)}
          </StatusPill>
          <span>暂无论文证据绑定</span>
        </div>
        <p>{reason}</p>
      </div>
    );
  }

  return (
    <details className="conclusion-evidence">
      <summary>
        <span className="conclusion-evidence-heading">
          <StatusPill compact tone={conclusionEvidenceTone(evidenceLevel)}>
            {conclusionEvidenceLabel(evidenceLevel)}
          </StatusPill>
          <span>依据 {paperIds.length} 篇核心论文</span>
        </span>
        <span className="conclusion-evidence-toggle">查看论文依据</span>
      </summary>
      <div className="conclusion-evidence-body">
        <p>{reason}</p>
        <div className="conclusion-evidence-paper-list">
          {paperIds.map((paperId) => (
            <div className="conclusion-evidence-paper" key={paperId}>
              <span aria-hidden="true" />
              {resolvePaperTitle(paperId, papers)}
            </div>
          ))}
        </div>
      </div>
    </details>
  );
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

function knowledgeSourceLabel(sourceType: string) {
  const normalized = (sourceType || "").toLowerCase();
  if (normalized.includes("pdf")) return "论文 PDF";
  if (normalized.includes("workspace")) return "历史研究结果";
  if (normalized.includes("conversation")) return "当前研究资料";
  if (normalized.includes("manual")) return "手动录入";
  if (normalized.includes("auto")) return "自动沉淀";
  return cleanDisplayText(sourceType, 24) || "知识库资料";
}

function knowledgeScopeDisplay(scope: string) {
  return (scope || "").toLowerCase() === "shared" ? "全局共享" : "当前研究";
}

function knowledgeHitUse(hit: WorkspaceKnowledgeHit) {
  const sourceType = (hit.source_type || "").toLowerCase();
  const scope = (hit.scope || "").toLowerCase();

  if (scope !== "shared") {
    if (sourceType.includes("pdf")) {
      return {
        label: "承接用户论文",
        description: "用于理解你导入论文里的概念、方法和约束，但仍需进入论文证据池后才算核心证据。",
      };
    }
    return {
      label: "承接当前研究",
      description: "用于延续本研究已有资料和本轮追问上下文，帮助系统不从零开始。",
    };
  }

  if (sourceType.includes("workspace") || sourceType.includes("auto")) {
    return {
      label: "复用历史沉淀",
      description: "来自历史研究或自动沉淀内容，只作为背景线索，避免污染本轮论文结论。",
    };
  }

  if (sourceType.includes("manual")) {
    return {
      label: "参考人工资料",
      description: "来自手动录入知识，帮助解释术语和任务边界，不直接替代论文证据。",
    };
  }

  return {
    label: "补充背景理解",
    description: "用于帮助系统理解语境和查询意图，结论仍以论文池和证据审计为准。",
  };
}

function formatKnowledgeHit(hit: WorkspaceKnowledgeHit) {
  const titleFull = cleanWorkspaceText(hit.title) || "未命名资料";
  const use = knowledgeHitUse(hit);
  const matchedChunkCount = hit.matched_chunk_count ?? 0;
  const matchPercent = Number.isFinite(hit.score) ? Math.round(Math.max(0, Math.min(1, hit.score)) * 100) : 0;
  return {
    title: cleanWorkspaceText(hit.title, 72) || titleFull,
    titleFull,
    contextSummary:
      matchedChunkCount > 0
        ? `系统命中了 ${matchedChunkCount} 个资料片段，语义匹配度约 ${matchPercent}%。这些片段用于承接上下文和辅助检索，不直接等同于论文证据。`
        : "系统将这条资料作为上下文线索使用，用于辅助理解当前研究主题和追问约束。",
    useLabel: use.label,
    useDescription: use.description,
    sourceLabel: knowledgeSourceLabel(hit.source_type),
    scope: hit.scope || "shared",
    scopeLabel: knowledgeScopeDisplay(hit.scope),
    matchPercent,
    evidenceLevel: hit.evidence_level || "candidate",
    matchedChunkCount,
    supportingSnippetCount: uniqueFullTexts(hit.supporting_snippets ?? [], 6).length,
  };
}

function contextVerdict({
  researchHitCount,
  sharedHitCount,
  workspaceHintCount,
  recentTurnCount,
  fallbackUsed,
}: {
  researchHitCount: number;
  sharedHitCount: number;
  workspaceHintCount: number;
  recentTurnCount: number;
  fallbackUsed: boolean;
}) {
  if (fallbackUsed) {
    return {
      title: "本轮存在保底背景，需优先看论文证据",
      description: "系统为了不中断流程保留了 fallback 背景，但这些内容只辅助理解，不应被当作最终结论来源。",
    };
  }
  if (researchHitCount > 0) {
    return {
      title: "本轮优先承接当前研究资料",
      description: "系统已经把当前研究内导入资料、历史结果或追问上下文送入分析，适合观察追问是否真正继承了前文。",
    };
  }
  if (sharedHitCount > 0) {
    return {
      title: "本轮使用全局知识补充背景",
      description: "共享知识参与了问题理解和查询辅助，但最终 taxonomy、演进图和研究建议仍应回到论文证据池验证。",
    };
  }
  if (workspaceHintCount > 0 || recentTurnCount > 0) {
    return {
      title: "本轮主要沿用对话上下文",
      description: "系统没有额外采用知识库资料，但继承了历史工作区摘要或近期追问，适合做多轮深化。",
    };
  }
  return {
    title: "本轮主要依赖论文证据",
    description: "这轮没有明显 RAG 命中，结果质量主要取决于检索到的论文和证据审计。",
  };
}

function ContextAuditHero({
  researchHitCount,
  sharedHitCount,
  workspaceHintCount,
  recentTurnCount,
  fallbackUsed,
}: {
  researchHitCount: number;
  sharedHitCount: number;
  workspaceHintCount: number;
  recentTurnCount: number;
  fallbackUsed: boolean;
}) {
  const verdict = contextVerdict({
    researchHitCount,
    sharedHitCount,
    workspaceHintCount,
    recentTurnCount,
    fallbackUsed,
  });

  return (
    <div className="workspace-context-story">
      <div className="workspace-context-story-main">
        <span>上下文使用判断</span>
        <strong>{verdict.title}</strong>
        <p>{verdict.description}</p>
      </div>
      <div className="workspace-context-role-grid">
        <div className={researchHitCount ? "workspace-context-role-card workspace-context-role-card-hot" : "workspace-context-role-card"}>
          <span>当前研究资料</span>
          <strong>{researchHitCount}</strong>
          <small>优先承接导入论文、当前研究笔记和本轮追问。</small>
        </div>
        <div className={sharedHitCount ? "workspace-context-role-card" : "workspace-context-role-card workspace-context-role-card-muted"}>
          <span>全局共享知识</span>
          <strong>{sharedHitCount}</strong>
          <small>作为背景线索，避免把旧知识误当作新论文证据。</small>
        </div>
        <div className="workspace-context-role-card">
          <span>对话继承</span>
          <strong>{workspaceHintCount + recentTurnCount}</strong>
          <small>由历史工作区摘要和近期用户追问共同构成。</small>
        </div>
      </div>
    </div>
  );
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
          <ConclusionEvidenceBlock
            evidenceLevel={gap.evidence_level}
            evidenceReason={gap.evidence_reason}
            papers={papers}
            supportingPaperIds={gap.supporting_paper_ids}
          />
        </article>
      ))}
    </div>
  );
}

function IdeaCard({ idea, papers }: { idea: WorkspaceIdea; papers: WorkspacePaper[] }) {
  const [expanded, setExpanded] = useState(false);

  const title = cleanWorkspaceText(idea.title, 160) || "未命名建议";
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
      <ConclusionEvidenceBlock
        evidenceLevel={idea.evidence_level}
        evidenceReason={idea.evidence_reason}
        papers={papers}
        supportingPaperIds={idea.supporting_paper_ids}
      />

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

function rankPaperForEmptyRecommendation(paper: WorkspacePaper) {
  const newRoundBoost = paper.is_new_this_round ? 1.4 : 0;
  const tierBoost =
    paper.relevance_tier === "direct"
      ? 1
      : paper.relevance_tier === "adjacent"
        ? 0.55
        : paper.relevance_tier === "candidate"
          ? 0.18
          : 0;
  const score = paper.relevance_score ?? 0;
  const citationBoost = paper.citation_count_known ? Math.min(paper.citation_count, 120) / 300 : 0;
  return newRoundBoost + tierBoost + score + citationBoost;
}

function recommendationEmptyCopy({
  sourceTrace,
  evidenceStatus,
  papers,
}: {
  sourceTrace?: WorkspaceSourceTrace | null;
  evidenceStatus?: WorkspaceEvidenceStatus;
  papers: WorkspacePaper[];
}) {
  const novelCount = sourceTrace?.novel_paper_count ?? papers.filter((paper) => paper.is_new_this_round).length;
  const reusedCount = sourceTrace?.reused_paper_count ?? Math.max(0, papers.length - novelCount);
  const directCount = sourceTrace?.direct_paper_count ?? papers.filter((paper) => paper.relevance_tier === "direct").length;
  const analysisCount = sourceTrace?.analysis_paper_count ?? papers.length;
  const evidencePoolCount = sourceTrace?.evidence_pool_count ?? sourceTrace?.total_paper_count ?? papers.length;
  const insufficient = evidenceStatus?.insufficient ?? false;

  if (insufficient) {
    return {
      tone: "warning" as const,
      title: "证据还不足，暂不包装成研究建议",
      reason: "系统没有把缺少论文支撑的想法包装成稳定建议，这是结论准入在起作用。",
      stats: [
        ["核心论文", `${analysisCount}`],
        ["证据池", `${evidencePoolCount}`],
        ["直接相关", `${directCount}`],
      ],
      actions: [
        "先到 Evidence 查看哪些论文真正进入核心分析。",
        "如果主题很新，可以上传 2-3 篇你确认相关的 PDF 再追问。",
        "下一轮追问可以明确方法、任务或数据集，帮助系统收窄证据。",
      ],
    };
  }

  if (novelCount > 0) {
    return {
      tone: "info" as const,
      title: "本轮更像证据补强，暂未形成新的研究机会",
      reason: `系统补入了 ${novelCount} 篇本轮新增论文，并沿用了 ${reusedCount} 篇旧证据；这些论文更像是在加强已有方向，而不是产生独立新建议。`,
      stats: [
        ["本轮新增", `${novelCount}`],
        ["沿用证据", `${reusedCount}`],
        ["直接相关", `${directCount}`],
      ],
      actions: [
        "先阅读本轮新增论文，判断是否只是补强已有方向。",
        "如果希望产出建议，可以追问：基于新增论文，提炼三个可做课题。",
        "也可以追问：哪些新增论文改变了原有 taxonomy 或研究空白？",
      ],
    };
  }

  if (sourceTrace?.external_search_skipped) {
    return {
      tone: "neutral" as const,
      title: "本轮没有外部补搜，建议不会强行新增",
      reason: "当前研究方式或证据策略没有触发外部检索，因此系统主要复用已有论文和上下文。",
      stats: [
        ["核心论文", `${analysisCount}`],
        ["沿用证据", `${reusedCount}`],
        ["上下文命中", `${sourceTrace.knowledge_hit_count}`],
      ],
      actions: [
        "如果想要新建议，可以切换到导入 + 补搜或完全检索。",
        "追问时加入明确范围，例如近三年、某类方法、某个应用场景。",
        "先查看 Context，确认系统是否正确承接了你的研究意图。",
      ],
    };
  }

  return {
    tone: "neutral" as const,
    title: "当前没有形成足够稳定的新研究建议",
    reason: "这不一定代表本轮失败，可能只是本轮结果更偏论文整理、证据补齐或方向复核。",
    stats: [
      ["核心论文", `${analysisCount}`],
      ["证据池", `${evidencePoolCount}`],
      ["低相关过滤", `${sourceTrace?.low_relevance_filtered_count ?? sourceTrace?.filtered_out_count ?? 0}`],
    ],
    actions: [
      "先看 Evidence 中的核心论文和本轮新增标签。",
      "如果需要选题建议，可以追问：基于当前证据生成三个可落地研究方向。",
      "如果结果太保守，可以补充约束：方法、数据集、应用场景或评价指标。",
    ],
  };
}

function RecommendationEmptyState({
  sourceTrace,
  evidenceStatus,
  papers,
}: {
  sourceTrace?: WorkspaceSourceTrace | null;
  evidenceStatus?: WorkspaceEvidenceStatus;
  papers: WorkspacePaper[];
}) {
  const copy = recommendationEmptyCopy({ sourceTrace, evidenceStatus, papers });
  const focusPapers = [...papers].sort((left, right) => rankPaperForEmptyRecommendation(right) - rankPaperForEmptyRecommendation(left)).slice(0, 3);

  return (
    <article className={`recommendation-empty-state recommendation-empty-state-${copy.tone}`}>
      <div className="recommendation-empty-header">
        <div>
          <span>建议生成说明</span>
          <strong>{copy.title}</strong>
        </div>
        <StatusPill compact tone={copy.tone === "warning" ? "warning" : copy.tone === "info" ? "info" : "neutral"}>
          非静默失败
        </StatusPill>
      </div>

      <p>{copy.reason}</p>

      <div className="recommendation-empty-stats">
        {copy.stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      {focusPapers.length ? (
        <div className="recommendation-empty-card">
          <strong>建议先看的证据</strong>
          <div className="recommendation-empty-paper-list">
            {focusPapers.map((paper) => (
              <div className="recommendation-empty-paper" key={paper.paper_id}>
                <span>{paper.is_new_this_round ? "本轮新增" : paper.relevance_tier === "direct" ? "直接相关" : "核心证据"}</span>
                <b>{cleanDisplayText(paper.title, 110)}</b>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="recommendation-empty-card">
        <strong>下一步可做</strong>
        <div className="recommendation-empty-actions">
          {copy.actions.map((action) => (
            <span key={action}>{action}</span>
          ))}
        </div>
      </div>
    </article>
  );
}

function IdeaList({
  ideas,
  papers,
  sourceTrace,
  evidenceStatus,
}: {
  ideas: WorkspaceIdea[];
  papers: WorkspacePaper[];
  sourceTrace?: WorkspaceSourceTrace | null;
  evidenceStatus?: WorkspaceEvidenceStatus;
}) {
  if (!ideas.length) {
    return <RecommendationEmptyState evidenceStatus={evidenceStatus} papers={papers} sourceTrace={sourceTrace} />;
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
  const hasSupportingSnippets = hit.supportingSnippetCount > 0;
  const title = expanded ? hit.titleFull : hit.title;

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

      <div className="workspace-hit-purpose">
        <span>{hit.useLabel}</span>
        <small>{hit.useDescription}</small>
      </div>

      <p>{hit.contextSummary}</p>

      <small>
        {hit.sourceLabel} · {hit.scopeLabel} · 已送入本轮分析上下文
      </small>

      {hasSupportingSnippets ? (
        <>
          <button
            className="workspace-inline-toggle"
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            {expanded ? "收起命中说明" : `查看命中说明 (${hit.supportingSnippetCount})`}
          </button>

          {expanded ? (
            <div className="workspace-hit-expanded-detail">
              <div className="workspace-hit-match-row">
                <span>语义匹配度</span>
                <strong>{hit.matchPercent}%</strong>
                <small>仅表示检索相关性，不代表该资料已经证明最终结论。</small>
              </div>
              <div className="workspace-hit-redacted-snippets">
                原始片段已在主界面折叠。它们只用于 RAG 上下文召回和检索辅助，最终结论仍以论文证据池、Paper Brief 和 claim checks 为准。
              </div>
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
  const sharedHits = hits.filter((hit) => hit.scope.toLowerCase() === "shared");
  const researchHits = hits.filter((hit) => hit.scope.toLowerCase() !== "shared");
  const workspaceHints = uniqueTexts(sourceTrace.workspace_hints, 6, 72);
  const recentTurns = uniqueTexts(sourceTrace.recent_user_turns, 4, 84);
  const retrievalStatus = retrievalStatusLabel(sourceTrace.retrieval_status);
  const retrievalPlan = formatRetrievalPlan(sourceTrace.retrieval_plan, 220);
  const retrievalMessage = formatRetrievalMessage(sourceTrace, 260);
  const filteredOutCount = sourceTrace.filtered_out_count ?? 0;
  const lowRelevanceFilteredCount = sourceTrace.low_relevance_filtered_count ?? 0;
  const displayedFilteredCount = lowRelevanceFilteredCount || filteredOutCount;
  const rescueLabels = [
    sourceTrace.broad_search_triggered ? "扩展检索" : "",
    sourceTrace.recall_rescue_triggered ? "召回补救" : "",
    sourceTrace.facet_rescue_triggered ? "分面补搜" : "",
  ].filter(Boolean);
  const fallbackUsed = sourceTrace.fallback_used ?? false;
  const hasRetrievalSummary = Boolean(
    retrievalStatus || retrievalPlan || retrievalMessage || displayedFilteredCount || fallbackUsed
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

      <ContextAuditHero
        fallbackUsed={fallbackUsed}
        recentTurnCount={sourceTrace.recent_turn_count}
        researchHitCount={researchHits.length}
        sharedHitCount={sharedHits.length}
        workspaceHintCount={sourceTrace.workspace_hint_count}
      />

      <div className="workspace-context-metrics">
        <div>
          <span>采用上下文</span>
          <strong>{hits.length}</strong>
        </div>
        <div>
          <span>研究历史</span>
          <strong>{sourceTrace.workspace_hint_count}</strong>
        </div>
        <div>
          <span>低相关过滤</span>
          <strong>{displayedFilteredCount}</strong>
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
            {rescueLabels.length ? (
              <div className="workspace-context-plan-row">
                <span>补救动作</span>
                <small>{rescueLabels.join(" / ")}</small>
              </div>
            ) : null}
            {lowRelevanceFilteredCount > 0 && filteredOutCount > 0 ? (
              <div className="workspace-context-plan-row">
                <span>过滤明细</span>
                <small>
                  低相关 {lowRelevanceFilteredCount} 条，硬约束越界 {filteredOutCount} 条
                </small>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="workspace-context-card workspace-context-card-accent">
          <div className="workspace-context-card-heading">
            <strong>当前研究资料命中</strong>
            <span>{researchHits.length} 条采用</span>
          </div>
          {researchHits.length ? (
            <div className="workspace-context-list">
              {researchHits.slice(0, 4).map((hit) => (
                <KnowledgeHitCard
                  hit={hit}
                  key={`${hit.title}-${hit.sourceLabel}-${hit.matchPercent}-${hit.evidenceLevel}`}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">本轮没有额外命中当前研究资料。</div>
          )}
        </div>

        <div className="workspace-context-card">
          <div className="workspace-context-card-heading">
            <strong>共享知识命中</strong>
            <span>{sharedHits.length} 条采用</span>
          </div>
          {sharedHits.length ? (
            <div className="workspace-context-list">
              {sharedHits.slice(0, 4).map((hit) => (
                <KnowledgeHitCard
                  hit={hit}
                  key={`${hit.title}-${hit.sourceLabel}-${hit.matchPercent}-${hit.evidenceLevel}`}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">本轮没有采用全局共享知识。</div>
          )}
        </div>

        <div className="workspace-context-card">
          <strong>沿用的研究结论</strong>
          {workspaceHints.length ? (
            <div className="workspace-context-chip-wrap">
              {workspaceHints.map((hint) => (
                <span className="insight-chip insight-chip-accent" key={hint}>
                  {hint}
                </span>
              ))}
            </div>
          ) : (
            <div className="empty-state workspace-inline-empty">本轮暂未显式继承历史研究结论。</div>
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
        <span className="workspace-collapsible-indicator" aria-hidden="true" />
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
  sectionMode = "all",
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
  sectionMode?: "all" | "insights" | "map" | "context" | "run";
}) {
  const insufficientEvidence = evidenceStatus?.insufficient ?? false;
  const graphEyebrow = insufficientEvidence ? `${graphEdges.length} 条关系候选` : `${graphEdges.length} 条关系`;
  const graphTitle = insufficientEvidence ? "研究关系候选" : "研究关系图谱";
  const gapsSection = (
    <section className="pane">
      <SectionHeader eyebrow={`${gaps.length} 条`} title="研究空白" />
      <div className="pane-scroll">
        <GapList gaps={gaps} papers={papers} />
      </div>
    </section>
  );
  const ideasSection = (
    <section className="pane">
      <SectionHeader eyebrow={`${ideas.length} 条`} title="研究建议" />
      <div className="pane-scroll">
        <IdeaList evidenceStatus={evidenceStatus} ideas={ideas} papers={papers} sourceTrace={sourceTrace} />
      </div>
    </section>
  );
  const graphSection = (
    <CollapsibleInsightSection
      eyebrow={graphEyebrow}
      title={graphTitle}
      className="workspace-graph-pane"
      defaultOpen={sectionMode === "map"}
    >
      <div className="content-pad pane-scroll">
        <div className="workspace-evidence-scope-note">
          仅把达到可信门槛的引用、文本支持或高置信推断画成图；普通“主题关联”只作为候选线索，不包装成演进结论。
        </div>
        {insufficientEvidence ? (
          <div className="empty-state workspace-evidence-mode-note">
            当前关系证据还没有达到绘图门槛，本轮只保留候选线索。补充真实论文或全文证据后，再判断论文之间是否存在引用继承、方法改进或评测对比关系。
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
                          <td>{cleanWorkspaceText(resolvePaperTitle(edge.source, papers), 100)}</td>
                          <td>{cleanWorkspaceText(resolvePaperTitle(edge.target, papers), 100)}</td>
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
  );
  const workingMemorySection = showWorkingMemory ? (
    <CollapsibleInsightSection eyebrow="会话级记忆" title="工作记忆" defaultOpen={sectionMode === "context"}>
      <WorkingMemoryPanel workingMemory={workingMemory} />
    </CollapsibleInsightSection>
  ) : null;
  const sourceTraceSection = (
    <CollapsibleInsightSection
      eyebrow={sourceTrace ? `${sourceTrace.knowledge_hit_count} 条上下文采用` : "上下文来源"}
      title="证据与上下文审计"
      defaultOpen={sectionMode === "context"}
    >
      <SourceTracePanel sourceTrace={sourceTrace} />
    </CollapsibleInsightSection>
  );
  const inheritedContextSection = (
    <CollapsibleInsightSection
      eyebrow={inheritedContext?.conversation_topic ? "连续研究" : "历史上下文"}
      title="继承上下文"
      defaultOpen={sectionMode === "context"}
    >
      <InheritedContextPanel inheritedContext={inheritedContext} />
    </CollapsibleInsightSection>
  );
  const processSection = (
    <CollapsibleInsightSection eyebrow="过程记录" title="研究过程" defaultOpen={sectionMode === "run"}>
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
  );

  if (sectionMode === "insights") {
    return (
      <section className="workspace-insights-grid">
        {gapsSection}
        {ideasSection}
      </section>
    );
  }

  if (sectionMode === "map") {
    return (
      <section className="workspace-insights-grid workspace-insights-single">
        <section className="workspace-secondary-stack">
          {graphSection}
        </section>
      </section>
    );
  }

  if (sectionMode === "context") {
    return (
      <section className="workspace-insights-grid workspace-insights-single">
        <section className="workspace-secondary-stack">
          {workingMemorySection}
          {sourceTraceSection}
          {inheritedContextSection}
        </section>
      </section>
    );
  }

  if (sectionMode === "run") {
    return (
      <section className="workspace-insights-grid workspace-insights-single">
        <section className="workspace-secondary-stack">
          {processSection}
        </section>
      </section>
    );
  }

  return (
    <section className="workspace-insights-grid">
      {gapsSection}
      {ideasSection}

      <section className="workspace-secondary-stack">
        {graphSection}
        {workingMemorySection}
        {sourceTraceSection}
        {inheritedContextSection}
        {processSection}
      </section>
    </section>
  );
}
