import { cleanDisplayText } from "../../lib/displayText";
import {
  formatRetrievalMessage,
  formatRetrievalPlan,
  retrievalStatusLabel,
  retrievalStatusTone,
  shouldHighlightRetrievalStatus,
} from "../../lib/groundingText";
import type {
  WorkspaceEvidenceSnapshot,
  WorkspaceEvidenceStatus,
  WorkspaceGap,
  WorkspaceIdea,
  WorkspacePaper,
  WorkspaceResearchBrief,
  WorkspaceSourceTrace,
} from "../../types/api";
import { StatusPill } from "../ui/StatusPill";
import { WorkspaceEvidenceSnapshotCard } from "./WorkspaceEvidenceSnapshotCard";
import { cleanWorkspaceText } from "./workspaceFormatters";

type WorkspaceSummarySectionProps = {
  topic?: string;
  paperCount: number;
  analysisPaperCount: number;
  gapCount: number;
  ideaCount: number;
  alignmentScore: number;
  summary?: string;
  priorityNote?: string;
  recommendation?: string;
  usesFallbackPapers: boolean;
  evidenceStatus?: WorkspaceEvidenceStatus;
  evidenceSnapshot?: WorkspaceEvidenceSnapshot | null;
  sourceTrace?: WorkspaceSourceTrace | null;
  researchBrief?: WorkspaceResearchBrief | null;
  analysisPapers?: WorkspacePaper[];
  gaps?: WorkspaceGap[];
  ideas?: WorkspaceIdea[];
};

function formatScore(score: number) {
  if (Number.isNaN(score)) {
    return "0.00";
  }
  return score.toFixed(3);
}

function isExpansionTrace(sourceTrace?: WorkspaceSourceTrace | null) {
  return sourceTrace?.retrieval_plan?.includes("goal=extend_context") ?? false;
}

function expansionFocusFromTopic(topic?: string) {
  const text = cleanDisplayText(topic ?? "", 180);
  for (const marker of ["继续展开：", "继续展开:", "展开：", "展开:"]) {
    if (text.includes(marker)) {
      return text.split(marker, 2)[1]?.trim() ?? "";
    }
  }
  return "";
}

function splitResearchTopic(topic?: string) {
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

function cleanSummaryText(summary: string, options?: { suppressCoverageGap?: boolean }) {
  let text = cleanDisplayText(summary)
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*/g, "")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .trim();

  if (options?.suppressCoverageGap) {
    text = text
      .split(/\n+/)
      .filter((line) => !(line.includes("优先关注") && line.includes("尚未覆盖研究方向")))
      .join("\n")
      .trim();
  }

  return text;
}

function paperYear(paper: WorkspacePaper) {
  const match = paper.publish_date?.match(/\d{4}/);
  return match ? Number(match[0]) : 0;
}

function paperCitationLabel(paper: WorkspacePaper) {
  if (paper.citation_count_known === false) {
    return "引用未获取";
  }
  return `${paper.citation_count ?? 0} 引用`;
}

function paperReason(paper: WorkspacePaper) {
  const explicitReason = paper.relevance_reasons?.find((reason) => reason.trim());
  if (explicitReason) {
    return cleanWorkspaceText(explicitReason, 120);
  }
  if (paper.taxonomy_category?.trim()) {
    return `覆盖方向：${paper.taxonomy_category}`;
  }
  if (paper.is_new_this_round) {
    return "本轮新增证据，适合优先检查是否补上了追问要求。";
  }
  return "进入核心分析池，可作为本轮结论的基础证据。";
}

function paperContributionBrief(paper?: WorkspacePaper, fallbackReason = "") {
  const backendBrief = cleanDisplayText(paper?.paper_brief?.contribution ?? "", 160);
  if (backendBrief) {
    return backendBrief;
  }
  const text = `${paper?.title ?? ""} ${paper?.taxonomy_category ?? ""} ${fallbackReason}`.toLowerCase();
  if (/survey|review|综述|overview|taxonomy/.test(text)) {
    return "梳理已有研究路线、任务设置或开放问题，适合作为快速建立领域地图的入口。";
  }
  if (/benchmark|evaluation|evaluate|dataset|leaderboard|评测|基准|数据集/.test(text)) {
    return "提供评测基准、数据资源或实验协议，适合用来判断后续方案如何验证。";
  }
  if (/fusion|alignment|retrieval|architecture|framework|method|model|system|架构|框架|方法|模型|融合|对齐|检索/.test(text)) {
    return "提出方法或系统框架，适合用来理解当前方向的主要技术路线。";
  }
  if (/robust|failure|missing|uncertainty|noise|鲁棒|失败|缺失|不确定/.test(text)) {
    return "关注鲁棒性、失败模式或边界条件，适合补充风险视角。";
  }
  if (fallbackReason.trim()) {
    return cleanWorkspaceText(fallbackReason, 120);
  }
  return "提供与当前主题相关的论文证据，可作为继续阅读和验证结论的起点。";
}

function rankPaperForBrief(paper: WorkspacePaper) {
  const citationScore = paper.citation_count_known === false ? 0 : Math.min(paper.citation_count ?? 0, 400) / 40;
  const relevanceScore = Math.max(0, Math.min(paper.relevance_score ?? 0, 1)) * 6;
  const newRoundBonus = paper.is_new_this_round ? 3 : 0;
  const coreBonus = paper.paper_pool_status === "core" ? 2 : 0;
  const recentBonus = paperYear(paper) >= 2024 ? 1.5 : 0;
  return citationScore + relevanceScore + newRoundBonus + coreBonus + recentBonus;
}

function evidenceBriefLabel(
  evidenceStatus: WorkspaceEvidenceStatus | undefined,
  analysisPaperCount: number,
  usesFallbackPapers: boolean
) {
  if (evidenceStatus?.insufficient || usesFallbackPapers) {
    return "证据需要补强";
  }
  if (analysisPaperCount >= 8) {
    return "核心证据较稳";
  }
  if (analysisPaperCount >= 4) {
    return "可支持初步判断";
  }
  return "证据偏少";
}

function evidenceBriefText(
  evidenceStatus: WorkspaceEvidenceStatus | undefined,
  analysisPaperCount: number,
  paperCount: number
) {
  if (evidenceStatus?.insufficient && evidenceStatus.message) {
    return cleanDisplayText(evidenceStatus.message, 140);
  }
  const realCount = evidenceStatus?.real_paper_count ?? paperCount;
  const fallbackCount = evidenceStatus?.fallback_paper_count ?? 0;
  return `当前用 ${analysisPaperCount} 篇核心论文支撑结论，证据池共 ${paperCount} 篇；真实论文 ${realCount} 篇，回退论文 ${fallbackCount} 篇。`;
}

function evidenceLevelLabel(level?: string) {
  const normalized = (level || "").toLowerCase();
  if (normalized === "direct" || normalized === "strong") return "直接证据";
  if (normalized === "indirect" || normalized === "moderate" || normalized === "weak") return "间接证据";
  return "探索性";
}

function supportCountLabel(ids?: string[]) {
  const count = ids?.length ?? 0;
  return count ? `${count} 篇论文支撑` : "暂无绑定论文";
}

export function WorkspaceSummarySection({
  topic,
  paperCount,
  analysisPaperCount,
  gapCount,
  ideaCount,
  alignmentScore,
  summary,
  priorityNote,
  recommendation,
  usesFallbackPapers,
  evidenceStatus,
  evidenceSnapshot,
  sourceTrace,
  researchBrief,
  analysisPapers = [],
  gaps = [],
  ideas = [],
}: WorkspaceSummarySectionProps) {
  const isEvidenceInsufficient = evidenceStatus?.insufficient;
  const retrievalStatus = retrievalStatusLabel(sourceTrace?.retrieval_status);
  const retrievalMessage = formatRetrievalMessage(sourceTrace, 180);
  const retrievalPlan = formatRetrievalPlan(sourceTrace?.retrieval_plan, 140);
  const showRetrievalBanner =
    !isEvidenceInsufficient && shouldHighlightRetrievalStatus(sourceTrace?.retrieval_status);
  const showRetrievalNote = Boolean(retrievalStatus || retrievalMessage || retrievalPlan);
  const retrievalNoteToneClass = shouldHighlightRetrievalStatus(sourceTrace?.retrieval_status)
    ? "workspace-note-card-warning"
    : "workspace-note-card-accent";
  const retrievalNoteLabel = retrievalStatus || "检索状态";
  const expansionTrace = isExpansionTrace(sourceTrace);
  const expansionFocus = expansionFocusFromTopic(topic);
  const splitTopic = splitResearchTopic(topic);
  const displayTopic = splitTopic.root || "研究主题";
  const displayFocus = expansionFocus || splitTopic.focus;
  const effectivePriorityNote =
    expansionTrace && expansionFocus
      ? `当前正在展开方向“${expansionFocus}”，本轮结果用于补充这个方向的论文证据和后续研究线索。`
      : priorityNote;
  const displaySummary = summary
    ? cleanSummaryText(summary, { suppressCoverageGap: expansionTrace })
    : "运行任务后，这里会汇总本轮分析的核心结论。";
  const briefExecutiveSummary =
    cleanWorkspaceText(researchBrief?.executive_summary ?? "", 900) || displaySummary;
  const briefHeadline =
    cleanWorkspaceText(researchBrief?.headline ?? "", 120) ||
    (researchBrief?.mode === "conversation" ? "累计研究简报" : "本轮研究简报");
  const briefKeyFinding = cleanWorkspaceText(researchBrief?.key_findings?.[0]?.text, 220);
  const briefNextStep = cleanWorkspaceText(researchBrief?.recommended_next_steps?.[0]?.text, 220);
  const briefOpenGap = cleanWorkspaceText(researchBrief?.open_gaps?.[0]?.text, 220);
  const primaryFindingItem = researchBrief?.key_findings?.[0];
  const primaryGapItem = researchBrief?.open_gaps?.[0];
  const primaryNextStepItem = researchBrief?.recommended_next_steps?.[0];
  const briefWarnings = researchBrief?.evidence_warnings ?? [];
  const showHeroNotes = Boolean((!researchBrief && (effectivePriorityNote || recommendation)) || showRetrievalNote);
  const topBriefPapers = [...analysisPapers]
    .sort((left, right) => rankPaperForBrief(right) - rankPaperForBrief(left))
    .slice(0, 3);
  const paperById = new Map(analysisPapers.map((paper) => [paper.paper_id, paper]));
  const briefPaperCards = researchBrief?.must_read_papers?.length
    ? researchBrief.must_read_papers.slice(0, 4).map((briefPaper) => ({
        briefPaper,
        paper: paperById.get(briefPaper.paper_id),
      }))
    : topBriefPapers.map((paper) => ({
        briefPaper: {
          paper_id: paper.paper_id,
          title: paper.title,
          reason: paperReason(paper),
          source_task_ids: [],
          evidence_level: "direct",
        },
        paper,
      }));
  const primaryGap = gaps[0];
  const primaryIdea = ideas[0];
  const briefNextAction =
    briefNextStep ||
    recommendation ||
    primaryIdea?.title ||
    briefOpenGap ||
    primaryGap?.summary ||
    effectivePriorityNote ||
    "继续围绕核心论文补充证据，优先检查结论是否被论文直接支持。";
  const directPaperCount = sourceTrace?.direct_paper_count ?? 0;
  const adjacentPaperCount = sourceTrace?.adjacent_paper_count ?? 0;
  const novelPaperCount = sourceTrace?.novel_paper_count ?? 0;
  const reusedPaperCount = sourceTrace?.reused_paper_count ?? 0;
  const showEvidenceBanner = Boolean(isEvidenceInsufficient && !briefWarnings.length);

  return (
    <section className="workspace-hero surface">
      <div className="workspace-hero-main">
        <div className="section-eyebrow">研究概览</div>
        <h1 className="workspace-hero-title">{displayTopic}</h1>
        {displayFocus ? (
          <div className="workspace-hero-focus">
            <span>本轮聚焦</span>
            <strong>{cleanDisplayText(displayFocus, 180)}</strong>
          </div>
        ) : null}
        <div className="research-brief-summary">
          <span>{briefHeadline}</span>
          <p>{briefExecutiveSummary}</p>
        </div>

        <div className="research-brief-board">
          <div className="research-brief-card research-brief-card-primary">
            <span>关键发现</span>
            <strong>{briefKeyFinding ? "已有证据支撑" : evidenceBriefLabel(evidenceStatus, analysisPaperCount, usesFallbackPapers)}</strong>
            <p>{cleanWorkspaceText(briefKeyFinding || evidenceBriefText(evidenceStatus, analysisPaperCount, paperCount), 220)}</p>
          </div>
          <div className="research-brief-card">
            <span>建议先读</span>
            <strong>{briefPaperCards.length ? `${briefPaperCards.length} 篇核心论文` : "等待核心论文"}</strong>
            <p>
              {briefPaperCards.length
                ? "已按简报准入规则筛出优先阅读入口，适合先看证据骨架再看图谱细节。"
                : "生成结果后会在这里给出优先阅读顺序。"}
            </p>
          </div>
          <div className="research-brief-card">
            <span>下一步动作</span>
            <strong>{primaryIdea ? "沿建议深化" : primaryGap ? "优先补空白" : "继续验证"}</strong>
            <p>{cleanWorkspaceText(briefNextAction, 180)}</p>
          </div>
          <div className="research-brief-card">
            <span>风险边界</span>
            <strong>{briefWarnings.length ? `${briefWarnings.length} 条提示` : "暂无明显警示"}</strong>
            <p>
              {briefWarnings.length
                ? cleanWorkspaceText(briefWarnings[0], 170)
                : "当前简报会把无论文支撑的内容降级为探索性线索，避免把上下文参考误当证据。"}
            </p>
          </div>
        </div>

        <div className="research-brief-trust-row" aria-label="研究简报可信解释">
          <div className="research-brief-trust-card">
            <span>核心论文怎么选</span>
            <strong>从核心分析池按证据价值排序</strong>
            <p>
              优先考虑直接相关、本轮新增、覆盖分支、高引用和近年论文。当前先读入口展示{" "}
              {briefPaperCards.length || 0} 篇，用来快速搭出证据骨架。
            </p>
          </div>
          <div className="research-brief-trust-card">
            <span>空白和建议怎么来</span>
            <strong>
              {primaryNextStepItem
                ? evidenceLevelLabel(primaryNextStepItem.evidence_level)
                : primaryGapItem
                  ? evidenceLevelLabel(primaryGapItem.evidence_level)
                  : "等待证据绑定"}
            </strong>
            <p>
              研究空白来自 taxonomy 覆盖缺口和审计结果；研究建议必须绑定空白或论文证据。
              {primaryNextStepItem
                ? ` 当前建议：${supportCountLabel(primaryNextStepItem.supporting_paper_ids)}。`
                : primaryGapItem
                  ? ` 当前空白：${supportCountLabel(primaryGapItem.supporting_paper_ids)}。`
                  : " 暂未形成稳定建议时，只作为下一轮追问线索。"}
            </p>
          </div>
          <div className="research-brief-trust-card">
            <span>当前可信边界</span>
            <strong>{directPaperCount >= 3 ? "可作初步判断" : "仍需人工复核"}</strong>
            <p>
              本轮直接证据 {directPaperCount} 篇、邻近证据 {adjacentPaperCount} 篇；
              {sourceTrace?.refresh_triggered
                ? `追问补搜新增 ${novelPaperCount} 篇，沿用 ${reusedPaperCount} 篇。`
                : "当前未触发追问补搜。"}
              {primaryFindingItem ? ` 首条发现为${evidenceLevelLabel(primaryFindingItem.evidence_level)}。` : ""}
            </p>
          </div>
        </div>

        {briefPaperCards.length ? (
          <div className="research-brief-papers" aria-label="优先阅读论文">
            {briefPaperCards.map(({ briefPaper, paper }, index) => (
              <article className="research-brief-paper" key={briefPaper.paper_id || index}>
                <div className="research-brief-paper-rank">{index + 1}</div>
                <div>
                  <strong>{cleanWorkspaceText(paper?.title || briefPaper.title, 150)}</strong>
                  <p>
                    <span className="research-brief-paper-label">做了什么</span>
                    {paperContributionBrief(paper, briefPaper.reason)}
                  </p>
                  <p>
                    <span className="research-brief-paper-label">为什么先读</span>
                    {cleanWorkspaceText(briefPaper.reason || (paper ? paperReason(paper) : ""), 180)}
                  </p>
                  <div className="research-brief-paper-meta">
                    <span>{paper ? paperYear(paper) || "-" : "-"}</span>
                    <span>{paper ? paperCitationLabel(paper) : "引用见论文表"}</span>
                    {paper?.is_new_this_round ? <span>本轮新增</span> : null}
                    {paper?.taxonomy_category ? <span>{paper.taxonomy_category}</span> : null}
                    {briefPaper.evidence_level ? <span>{briefPaper.evidence_level}</span> : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {showHeroNotes ? (
          <div className="workspace-hero-notes">
            {!researchBrief && effectivePriorityNote ? (
              <div className="workspace-note-card">
                <div className="workspace-note-label">优先关注</div>
                <div>{cleanDisplayText(effectivePriorityNote)}</div>
              </div>
            ) : null}
            {!researchBrief && recommendation ? (
              <div className="workspace-note-card workspace-note-card-accent">
                <div className="workspace-note-label">建议动作</div>
                <div>{cleanDisplayText(recommendation)}</div>
              </div>
            ) : null}
            {showRetrievalNote ? (
              <div className={`workspace-note-card ${retrievalNoteToneClass}`}>
                <div className="workspace-note-card-header">
                  <div className="workspace-note-label">本轮检索</div>
                  {retrievalStatus ? (
                    <StatusPill compact tone={retrievalStatusTone(sourceTrace?.retrieval_status)}>
                      {retrievalNoteLabel}
                    </StatusPill>
                  ) : null}
                </div>
                <div>{retrievalMessage || "本轮检索策略已经和当前问题对齐。"}</div>
                {retrievalPlan ? <div className="workspace-note-support">{retrievalPlan}</div> : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="workspace-hero-side">
        <div className="workspace-kpi-card">
          <span>合格论文</span>
          <strong>{paperCount}</strong>
          <small>核心分析 {analysisPaperCount} 篇</small>
        </div>
        <div className="workspace-kpi-card">
          <span>研究空白</span>
          <strong>{gapCount}</strong>
        </div>
        <div className="workspace-kpi-card">
          <span>研究建议</span>
          <strong>{ideaCount}</strong>
        </div>
        <div className="workspace-kpi-card">
          <span>匹配度</span>
          <strong>{formatScore(alignmentScore)}</strong>
        </div>
      </div>

      {showEvidenceBanner ? (
        <div className="workspace-fallback-banner workspace-fallback-banner-evidence">
          <span className="workspace-soft-label">质量提示</span>
          <span>
            {cleanDisplayText(evidenceStatus?.message)}
            {evidenceStatus?.candidate_branches?.length
              ? ` 候选方向：${evidenceStatus.candidate_branches.map((item) => cleanDisplayText(item, 80)).filter(Boolean).join(" / ")}。`
              : ""}
          </span>
        </div>
      ) : showRetrievalBanner ? (
        <div className="workspace-fallback-banner">
          <StatusPill compact tone={retrievalStatusTone(sourceTrace?.retrieval_status)}>
            {retrievalNoteLabel}
          </StatusPill>
          <span>
            {retrievalMessage}
            {retrievalPlan ? ` 当前策略：${retrievalPlan}。` : ""}
          </span>
        </div>
      ) : usesFallbackPapers ? (
        <div className="workspace-fallback-banner">
          <StatusPill compact tone="warning">
            系统回退
          </StatusPill>
          <span>
            当前结果包含保底论文，说明外部检索证据不足。系统先用种子论文维持方向与空白分析，后续仍建议继续补充真实论文。
          </span>
        </div>
      ) : null}

      {evidenceStatus ? (
        <div className="workspace-evidence-detail">
          <div>
            <span>真实论文</span>
            <strong>{evidenceStatus.real_paper_count}</strong>
          </div>
          <div>
            <span>回退论文</span>
            <strong>{evidenceStatus.fallback_paper_count}</strong>
          </div>
          <div>
            <span>回退比例</span>
            <strong>{Math.round(evidenceStatus.fallback_ratio * 100)}%</strong>
          </div>
          <div>
            <span>覆盖分支</span>
            <strong>{evidenceStatus.covered_branch_count}</strong>
          </div>
        </div>
      ) : null}

      <WorkspaceEvidenceSnapshotCard snapshot={evidenceSnapshot} />
    </section>
  );
}
