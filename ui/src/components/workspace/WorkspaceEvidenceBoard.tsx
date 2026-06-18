import { useState } from "react";

import { SectionHeader } from "../ui/SectionHeader";
import { cleanDisplayText } from "../../lib/displayText";
import { api, toErrorMessage } from "../../lib/api";
import type { WorkspacePaper } from "../../types/api";
import { cleanWorkspaceText } from "./workspaceFormatters";

type WorkspaceEvidenceBoardProps = {
  papers: WorkspacePaper[];
  totalPaperCount: number;
  analysisPaperCount: number;
  viewMode: "analysis" | "extended";
  onViewModeChange: (mode: "analysis" | "extended") => void;
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
  showRoundMarkers?: boolean;
  taskId?: string;
};

function sourceLabel(source: string) {
  const normalized = (source || "").toLowerCase();
  if (normalized === "fallback") return "系统回退";
  if (normalized === "user_upload" || normalized === "local_pdf") return "用户上传";
  if (normalized === "user_import") return "用户导入";
  if (normalized === "arxiv") return "ArXiv";
  if (normalized === "semantic_scholar") return "Semantic Scholar";
  return source || "未知";
}

function isUserProvidedPaper(paper: WorkspacePaper) {
  const origin = (paper.origin || "").toLowerCase();
  const source = (paper.source || "").toLowerCase();
  return ["user_upload", "user_import", "local_pdf"].includes(origin)
    || ["user_upload", "user_import", "local_pdf"].includes(source)
    || Boolean(paper.document_id);
}

function evidenceOriginLabel(paper: WorkspacePaper) {
  const origin = (paper.origin || paper.source || "").toLowerCase();
  if (origin === "user_upload" || origin === "local_pdf") return "用户上传";
  if (origin === "user_import") return "用户导入";
  if (origin === "system_search" || origin === "arxiv" || origin === "semantic_scholar") {
    return "系统检索";
  }
  if (paper.source === "fallback") return "系统回退";
  return "系统检索";
}

function sourceDetailLabel(paper: WorkspacePaper) {
  const origin = (paper.origin || paper.source || "").toLowerCase();
  const source = (paper.source || "").toLowerCase();
  if (origin === "user_upload" || source === "user_upload" || origin === "local_pdf" || source === "local_pdf") {
    return "本地 PDF";
  }
  if (origin === "user_import" || source === "user_import") return "手动录入";
  if (source === "arxiv") return "外部论文库";
  if (source === "semantic_scholar") return "元数据增强";
  if (source === "fallback") return "保底结果";
  return evidenceOriginLabel(paper);
}

function poolStatusLabel(paper: WorkspacePaper) {
  if (paper.paper_pool_status === "core") return "用户指定核心";
  if (paper.paper_pool_status === "candidate") return "导入候选";
  return "";
}

function PaperBadges({ paper, showRoundMarkers }: { paper: WorkspacePaper; showRoundMarkers?: boolean }) {
  const poolLabel = poolStatusLabel(paper);
  const briefTags = paper.paper_brief?.tags ?? [];
  return (
    <span className="workspace-paper-badges">
      <span className="message-source-trace-chip">{evidenceOriginLabel(paper)}</span>
      {poolLabel ? (
        <span className="message-source-trace-chip message-source-trace-chip-info">{poolLabel}</span>
      ) : null}
      {briefTags.slice(0, 2).map((tag) => (
        <span className="message-source-trace-chip" key={tag}>{formatPaperBriefTag(tag)}</span>
      ))}
      {showRoundMarkers ? (
        <span className={`message-source-trace-chip ${noveltyToneClass(paper)}`}>{noveltyLabel(paper)}</span>
      ) : null}
    </span>
  );
}

function noveltyLabel(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "本轮新增" : "沿用证据";
}

function noveltyToneClass(paper: WorkspacePaper) {
  return paper.is_new_this_round ? "message-source-trace-chip-info" : "";
}

function citationLabel(paper: WorkspacePaper) {
  if (paper.citation_count_known) return String(paper.citation_count);
  return isUserProvidedPaper(paper) ? "待外部匹配" : "未获取";
}

function categoryLabel(paper: WorkspacePaper) {
  const category = cleanDisplayText(paper.taxonomy_category, 80);
  if (category) return category;
  return isUserProvidedPaper(paper) ? "本地资料待分类" : "未分类";
}

function formatPaperBriefTag(tag: string) {
  const labels: Record<string, string> = {
    benchmark: "基准",
    dataset: "数据",
    "high-citation": "高引用",
    llm: "LLM",
    method: "方法",
    multimodal: "多模态",
    orchestration: "编排",
    recent: "近期",
    retrieval: "检索",
    robustness: "鲁棒",
    survey: "综述",
    "user-provided": "用户上传",
  };
  return labels[tag] ?? tag;
}

function formatBriefSource(source: string) {
  if (source === "full_text_verified") return "按需全文片段核验";
  if (source === "full_text") return "正文片段";
  if (source === "abstract+metadata") return "摘要 + 元数据";
  if (source === "metadata") return "仅元数据";
  return source || "来源未知";
}

function paperReadingRole(paper: WorkspacePaper) {
  const tags = paper.paper_brief?.tags ?? [];
  if (isUserProvidedPaper(paper)) {
    return "用户上传论文：适合作为你已掌握材料和系统检索结果之间的对照锚点。";
  }
  if (tags.includes("survey")) {
    return "综述/路线型论文：适合先读，用来快速建立方向地图。";
  }
  if (tags.includes("benchmark") || tags.includes("dataset")) {
    return "评测/数据型论文：适合判断后续方案如何被验证。";
  }
  if (paper.citation_count_known && paper.citation_count >= 50) {
    return `高影响力论文：当前引用约 ${paper.citation_count} 次，可优先作为背景或基线。`;
  }
  if (paper.is_new_this_round) {
    return "本轮检索补入：建议检查它是否回应了本次追问的新约束。";
  }
  return "核心候选证据：可用于理解当前 taxonomy、研究空白或后续建议。";
}

function paperReadFocus(paper: WorkspacePaper) {
  const tags = paper.paper_brief?.tags ?? [];
  if (tags.includes("survey")) return "建议先看分类框架、开放问题和代表论文表。";
  if (tags.includes("benchmark")) return "建议先看任务定义、指标、数据集和实验协议。";
  if (tags.includes("orchestration")) return "建议重点看任务模型、资源约束、调度目标和系统假设。";
  if (tags.includes("robustness")) return "建议重点看失败模式、缺失信息处理和鲁棒性实验。";
  if (tags.includes("retrieval")) return "建议重点看表征学习、相似度匹配和检索评测设置。";
  if (tags.includes("multimodal")) return "建议重点看融合位置、跨模态对齐方式和消融实验。";
  return "建议先读摘要、方法图和实验设置，再判断是否进入精读。";
}

function paperEvidenceCaveat(paper: WorkspacePaper) {
  const boundary = cleanWorkspaceText(paper.paper_brief?.verification_boundary ?? "", 220);
  if (boundary) {
    return boundary;
  }
  if (!paper.citation_count_known) {
    return "引用数据未获取，影响力判断暂时不能按 0 引用理解。";
  }
  if (!paper.paper_brief || paper.paper_brief.source === "metadata") {
    return "当前解释主要来自标题/元数据，仍需要打开原文核查。";
  }
  return "当前解释来自摘要/元数据级分析，还不是全文 claim verification。";
}

function paperDecisionLevel(paper: WorkspacePaper) {
  const tags = paper.paper_brief?.tags ?? [];
  const hasFullTextSignal = ["full_text", "full_text_verified"].includes(paper.paper_brief?.source ?? "");
  const isDirect = paper.relevance_tier === "direct" || paper.paper_pool_status === "core";
  if (hasFullTextSignal || (isDirect && (tags.includes("survey") || tags.includes("benchmark")))) {
    return {
      label: "优先精读",
      tone: "strong",
      reason: "它能直接支撑本轮结论，且已有较明确的摘要/正文信号，适合先读细节。",
    };
  }
  if (isDirect || paper.is_new_this_round || (paper.citation_count_known && paper.citation_count >= 50)) {
    return {
      label: "先读摘要",
      tone: "medium",
      reason: "它和当前问题相关度较高，建议先看摘要、方法与实验设置，再决定是否精读。",
    };
  }
  return {
    label: "候选补充",
    tone: "light",
    reason: "更适合作为背景或旁证，暂时不应单独支撑核心结论。",
  };
}

function paperUseCases(paper: WorkspacePaper) {
  const tags = paper.paper_brief?.tags ?? [];
  const cases: string[] = [];
  if (tags.includes("survey")) cases.push("领域路线梳理");
  if (tags.includes("benchmark") || tags.includes("dataset")) cases.push("评测设计参考");
  if (tags.includes("orchestration")) cases.push("系统架构/调度假设");
  if (tags.includes("retrieval")) cases.push("检索链路与指标");
  if (tags.includes("multimodal")) cases.push("融合与跨模态对齐");
  if (tags.includes("robustness")) cases.push("失败模式与鲁棒性");
  if (isUserProvidedPaper(paper)) cases.push("本地材料锚点");
  if (paper.is_new_this_round) cases.push("本轮追问补充");
  if (!cases.length) cases.push("背景阅读", "候选证据");
  return cases.slice(0, 4);
}

function paperCaution(paper: WorkspacePaper) {
  const source = paper.paper_brief?.source ?? "";
  if (source === "full_text_verified") {
    return "已完成按需正文片段核验，但仍建议人工复核关键实验数值和结论外推。";
  }
  if (!paper.citation_count_known) {
    return "引用数未获取不等于 0 引用；不要用它直接判断影响力。";
  }
  if (source === "metadata") {
    return "当前主要是元数据级判断，不能直接引用为实验结论。";
  }
  if (source === "abstract+metadata") {
    return "摘要级信息可以判断方向，但实验数值、局限和对比结论仍需回原文核查。";
  }
  return "已具备正文片段信号，但仍不是完整自动审稿；关键 claim 仍建议人工复核。";
}

function paperDeepDiveQuestions(paper: WorkspacePaper) {
  const tags = paper.paper_brief?.tags ?? [];
  const questions = ["它到底解决了哪个具体问题？"];
  if (tags.includes("orchestration")) questions.push("资源、延迟、吞吐或协同约束是怎么建模的？");
  if (tags.includes("multimodal")) questions.push("融合发生在哪一层，是否做了跨模态对齐/缺失模态实验？");
  if (tags.includes("retrieval")) questions.push("检索任务、负样本和评价指标是否贴近你的研究问题？");
  if (tags.includes("benchmark") || tags.includes("dataset")) questions.push("评测协议是否能复用到你的方案？");
  if (!questions.some((question) => question.includes("实验"))) {
    questions.push("它的实验设定和局限是否足以支撑当前研究建议？");
  }
  return questions.slice(0, 3);
}

function PaperDecisionPanel({ paper }: { paper: WorkspacePaper }) {
  const decision = paperDecisionLevel(paper);
  const useCases = paperUseCases(paper);
  const questions = paperDeepDiveQuestions(paper);
  return (
    <section className="workspace-paper-decision-panel" aria-label="论文阅读决策">
      <div className={`workspace-paper-decision-card workspace-paper-decision-${decision.tone}`}>
        <span>阅读决策</span>
        <strong>{decision.label}</strong>
        <p>{decision.reason}</p>
      </div>
      <div className="workspace-paper-decision-card">
        <span>适合支撑</span>
        <div className="workspace-paper-use-tags">
          {useCases.map((item) => (
            <b key={item}>{item}</b>
          ))}
        </div>
      </div>
      <div className="workspace-paper-decision-card">
        <span>读的时候问</span>
        <ul>
          {questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      </div>
      <div className="workspace-paper-decision-card workspace-paper-decision-caution">
        <span>不要误用</span>
        <p>{paperCaution(paper)}</p>
      </div>
    </section>
  );
}

function PaperReadingCard({ paper }: { paper: WorkspacePaper }) {
  const whySelected = cleanWorkspaceText(paper.paper_brief?.why_selected ?? "", 240) || paperReadingRole(paper);
  const readFocus = cleanWorkspaceText(paper.paper_brief?.read_focus ?? "", 220) || paperReadFocus(paper);
  const evidenceBasis = cleanWorkspaceText(paper.paper_brief?.evidence_basis ?? "", 240) || paperEvidenceCaveat(paper);
  return (
    <div className="workspace-paper-reading-card">
      <div>
        <span>为什么进入视野</span>
        <strong>{whySelected}</strong>
      </div>
      <div>
        <span>读法建议</span>
        <strong>{readFocus}</strong>
      </div>
      <div>
        <span>证据来自哪里</span>
        <strong>{evidenceBasis}</strong>
      </div>
    </div>
  );
}

function paperVerificationLevel(paper: WorkspacePaper) {
  const source = paper.paper_brief?.source ?? "";
  const hasLocalPdf = isUserProvidedPaper(paper);
  if (source === "full_text_verified" && hasLocalPdf) return "本地 PDF 按需全文片段核验";
  if (source === "full_text_verified") return "按需全文片段核验";
  if (source === "full_text" && hasLocalPdf) return "本地 PDF 正文片段可用";
  if (source === "full_text") return "正文片段可用";
  if (hasLocalPdf && source === "abstract+metadata") return "本地 PDF + 摘要级核查";
  if (source === "abstract+metadata") return "摘要 + 元数据级核查";
  if (source === "metadata") return "元数据级核查";
  return "初步相关性核查";
}

function paperVerificationBoundary(paper: WorkspacePaper) {
  const source = paper.paper_brief?.source ?? "";
  if (source === "full_text_verified") {
    return "已对当前论文抽取局部正文 claim 并定位支持片段；适合帮助精读，但仍不是自动审稿结论。";
  }
  if (source === "full_text") {
    return "已使用导入/上传材料中的正文片段，但还不是全篇逐 claim 自动审稿。";
  }
  if (isUserProvidedPaper(paper)) {
    return "已知道它来自用户资料，但仍需要抽取正文片段来验证具体 claim。";
  }
  if (source === "abstract+metadata") {
    return "已能判断研究问题、方法和贡献，但尚未逐条核对实验结果与局限。";
  }
  return "目前主要依靠标题、来源和检索相关性，适合先判断是否值得进入精读。";
}

function paperVerificationUpgradeHint(paper: WorkspacePaper) {
  const source = paper.paper_brief?.source ?? "";
  if (source === "full_text_verified") {
    return "下一步可以人工复核高置信 claim、实验表和局限段落，把可信结论沉淀进研究建议。";
  }
  if (source === "full_text") {
    return "下一步需要按章节抽取方法、实验、局限和结论 claim，并检查这些 claim 是否互相冲突。";
  }
  if (isUserProvidedPaper(paper)) {
    return "下一步应重新解析 PDF 正文或补充摘要，避免只凭文件标题判断论文价值。";
  }
  if (source === "abstract+metadata") {
    return "下一步需要获取全文或 PDF，定位方法图、实验表和局限段落。";
  }
  return "下一步需要补充摘要、DOI/arXiv 元数据或 PDF 正文后再做 claim verification。";
}

function claimStatusLabel(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "verified") return "已验证";
  if (normalized === "partial") return "部分支持";
  if (normalized === "conflict") return "存在冲突";
  return "待核查";
}

function claimStatusClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "verified") return "workspace-paper-claim-status-verified";
  if (normalized === "partial") return "workspace-paper-claim-status-partial";
  if (normalized === "conflict") return "workspace-paper-claim-status-conflict";
  return "workspace-paper-claim-status-unknown";
}

function claimSourceLabel(sourceLevel: string, section: string) {
  if (sourceLevel === "full_text") return section ? `正文片段：${section}` : "正文片段证据";
  if (sourceLevel === "abstract") return "摘要证据";
  return "元数据证据";
}

function claimTypeLabel(claimType: string) {
  const normalized = claimType.toLowerCase();
  const labels: Record<string, string> = {
    contribution: "贡献主张",
    contribution_claim: "贡献主张",
    evaluation_claim: "评测主张",
    impact: "影响力主张",
    limitation_claim: "局限主张",
    method: "方法主张",
    method_claim: "方法主张",
    problem: "问题主张",
    topic_relation: "主题关系",
  };
  return labels[normalized] ?? "待核验主张";
}

function claimStatusSummary(claimChecks: NonNullable<WorkspacePaper["paper_brief"]>["claim_checks"]) {
  const checks = claimChecks ?? [];
  const counts = checks.reduce(
    (acc, check) => {
      const normalized = check.status.toLowerCase();
      if (normalized === "verified") acc.verified += 1;
      else if (normalized === "partial") acc.partial += 1;
      else if (normalized === "conflict") acc.conflict += 1;
      else acc.unknown += 1;
      return acc;
    },
    { conflict: 0, partial: 0, unknown: 0, verified: 0 },
  );
  return [
    counts.verified ? `${counts.verified} 已验证` : "",
    counts.partial ? `${counts.partial} 部分支持` : "",
    counts.conflict ? `${counts.conflict} 有冲突` : "",
    counts.unknown ? `${counts.unknown} 待核查` : "",
  ].filter(Boolean).join(" · ");
}

function PaperVerificationPanel({
  isVerifying,
  onVerifyPaper,
  paper,
  verifyStatus,
}: {
  isVerifying?: boolean;
  onVerifyPaper?: (paper: WorkspacePaper) => void;
  paper: WorkspacePaper;
  verifyStatus?: string;
}) {
  const claimChecks = paper.paper_brief?.claim_checks ?? [];
  const statusSummary = claimStatusSummary(claimChecks);
  const visibleClaimChecks = claimChecks.slice(0, 4);
  const verificationBoundary =
    cleanDisplayText(paper.paper_brief?.verification_boundary ?? "", 180) || paperVerificationBoundary(paper);
  const isVerified = paper.paper_brief?.source === "full_text_verified";
  return (
    <div className="workspace-paper-verification-panel">
      <div>
        <span>当前验证级别</span>
        <strong>{paperVerificationLevel(paper)}</strong>
        <p>{verificationBoundary}</p>
      </div>
      <div>
        <span>{isVerified ? "核验后还要注意" : "为什么还不是全文验证"}</span>
        <strong>{isVerified ? "仍需人工复核关键数值" : "未逐条抽取正文 claim"}</strong>
        <p>{paperVerificationUpgradeHint(paper)}</p>
      </div>
      <div>
        <span>可并行升级路径</span>
        <strong>Paper Analyst 逐篇并行</strong>
        <p>后端后续可对核心论文并发抽取正文证据，再把 verified / disputed / unknown 状态回写到论文详情和研究建议。</p>
      </div>
      <div className="workspace-paper-verification-action">
        <span>按需升级</span>
        <strong>{isVerified ? "已升级当前论文" : "只核验当前论文"}</strong>
        <p>点击后会对这篇论文做更深的正文片段 claim 核验，不会重跑整轮研究。</p>
        <button
          className="secondary-button"
          disabled={!onVerifyPaper || isVerifying || isVerified}
          onClick={() => onVerifyPaper?.(paper)}
          type="button"
        >
          {isVerifying ? "核验中..." : isVerified ? "已完成核验" : "升级核验当前论文"}
        </button>
        {verifyStatus ? <small>{verifyStatus}</small> : null}
      </div>
      {claimChecks.length ? (
        <details className="workspace-paper-claim-checks" aria-label="Claim verification checks">
          <summary className="workspace-paper-claim-checks-head">
            <span>主张核验</span>
            <strong>{statusSummary || `${claimChecks.length} 条待核验主张`}</strong>
          </summary>
          <div className="workspace-paper-claim-check-list">
            {visibleClaimChecks.map((check, index) => (
              <article className="workspace-paper-claim-check" key={`${check.claim_type}-${index}`}>
                <span className="workspace-paper-claim-type">{claimTypeLabel(check.claim_type)}</span>
                <div className="workspace-paper-claim-check-title">
                  <span className={claimStatusClass(check.status)}>{claimStatusLabel(check.status)}</span>
                  <strong>{cleanWorkspaceText(check.claim, 140)}</strong>
                </div>
                <p>{cleanWorkspaceText(check.evidence, 140)}</p>
                <small>
                  {claimSourceLabel(check.source_level, check.section)}
                  {check.caveat ? ` · ${cleanWorkspaceText(check.caveat, 80)}` : ""}
                </small>
              </article>
            ))}
            {claimChecks.length > visibleClaimChecks.length ? (
              <div className="workspace-paper-claim-more">
                另有 {claimChecks.length - visibleClaimChecks.length} 条核验记录，已折叠以减少阅读噪音。
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function PaperBriefPanel({ paper }: { paper: WorkspacePaper }) {
  const brief = paper.paper_brief;
  if (!brief) {
    return (
      <div className="workspace-paper-brief-empty">
        当前论文还没有结构化 Paper Brief。后续运行任务后，系统会尽量根据摘要、标题和相关性理由补齐。
      </div>
    );
  }

  const items = [
    { label: "研究问题", text: brief.problem },
    { label: "方法/模型", text: brief.method },
    { label: "主要贡献", text: brief.contribution },
    { label: "局限/注意", text: brief.limitation },
    { label: "与当前主题关系", text: brief.relation_to_topic },
  ].filter((item) => cleanWorkspaceText(item.text, 220).trim());

  return (
    <details className="workspace-paper-brief">
      <summary className="workspace-paper-brief-head">
        <div>
          <span className="section-eyebrow">Structured Brief</span>
          <strong>结构化摘要：问题、方法与边界</strong>
        </div>
        <span className="workspace-paper-brief-source">{formatBriefSource(brief.source)}</span>
      </summary>
      {brief.tags.length ? (
        <div className="workspace-paper-brief-tags">
          {brief.tags.map((tag) => (
            <span key={tag}>{formatPaperBriefTag(tag)}</span>
          ))}
        </div>
      ) : null}
      <div className="workspace-paper-brief-grid">
        {items.map((item) => (
          <div className="workspace-paper-brief-item" key={item.label}>
            <span>{item.label}</span>
            <p>{cleanWorkspaceText(item.text, 220)}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function PaperInspector({
  isVerifying,
  onVerifyPaper,
  paper,
  showRoundMarkers,
  verifyStatus,
}: {
  isVerifying?: boolean;
  onVerifyPaper?: (paper: WorkspacePaper) => void;
  paper?: WorkspacePaper;
  showRoundMarkers?: boolean;
  verifyStatus?: string;
}) {
  if (!paper) {
    return <div className="empty-state">选择一篇论文后，这里会显示来源、年份、分类和外链。</div>;
  }

  return (
    <div className="content-grid">
      <div>
        <div className="section-eyebrow">当前选中</div>
        <div className="workspace-paper-title-row">
          <div className="insight-title">{cleanDisplayText(paper.title, 180)}</div>
          <PaperBadges paper={paper} showRoundMarkers={showRoundMarkers} />
        </div>
      </div>
      <PaperDecisionPanel paper={paper} />
      <PaperReadingCard paper={paper} />
      <PaperVerificationPanel
        isVerifying={isVerifying}
        onVerifyPaper={onVerifyPaper}
        paper={paper}
        verifyStatus={verifyStatus}
      />
      <div className="workspace-paper-meta-grid">
        <div className="workspace-paper-meta-item">
          <span>来源</span>
          <strong>{sourceLabel(paper.source)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>证据身份</span>
          <strong>{poolStatusLabel(paper) || evidenceOriginLabel(paper)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>年份</span>
          <strong>{paper.publish_date || "-"}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>引用</span>
          <strong>{citationLabel(paper)}</strong>
        </div>
        <div className="workspace-paper-meta-item">
          <span>分类</span>
          <strong>{categoryLabel(paper)}</strong>
        </div>
        {showRoundMarkers ? (
          <div className="workspace-paper-meta-item">
            <span>轮次</span>
            <strong>{noveltyLabel(paper)}</strong>
          </div>
        ) : null}
      </div>
      <PaperBriefPanel paper={paper} />
      {paper.url ? (
        <a className="secondary-button" href={paper.url} rel="noreferrer" target="_blank">
          打开论文来源
        </a>
      ) : null}
    </div>
  );
}

export function WorkspaceEvidenceBoard({
  papers,
  totalPaperCount,
  analysisPaperCount,
  viewMode,
  onViewModeChange,
  selectedPaperId,
  onSelectPaper,
  showRoundMarkers = false,
  taskId,
}: WorkspaceEvidenceBoardProps) {
  const [verifiedPapers, setVerifiedPapers] = useState<Record<string, WorkspacePaper>>({});
  const [verifyingPaperId, setVerifyingPaperId] = useState("");
  const [verifyStatus, setVerifyStatus] = useState("");
  const [verifyStatusPaperId, setVerifyStatusPaperId] = useState("");
  const visiblePapers = papers.map((paper) => verifiedPapers[paper.paper_id] ?? paper);
  const selectedPaper = visiblePapers.find((paper) => paper.paper_id === selectedPaperId) ?? visiblePapers[0];
  const novelPaperCount = visiblePapers.filter((paper) => paper.is_new_this_round).length;
  const visibleLabel = viewMode === "analysis" ? "核心分析论文" : "扩展证据库";
  const eyebrow =
    showRoundMarkers && visiblePapers.length
      ? `${visibleLabel} ${visiblePapers.length} 篇 · 新增 ${novelPaperCount} 篇`
      : `${visibleLabel} ${visiblePapers.length} 篇`;

  async function handleVerifyPaper(paper: WorkspacePaper) {
    if (!taskId || !paper.paper_id || verifyingPaperId) {
      return;
    }
    setVerifyingPaperId(paper.paper_id);
    setVerifyStatusPaperId(paper.paper_id);
    setVerifyStatus("正在抽取正文片段并核验关键 claim...");
    try {
      const response = await api.verifyWorkspacePaper(taskId, paper.paper_id);
      setVerifiedPapers((current) => ({
        ...current,
        [response.data.paper_id]: response.data,
      }));
      setVerifyStatus("已完成当前论文的按需正文片段核验。");
    } catch (error) {
      setVerifyStatus(toErrorMessage(error));
    } finally {
      setVerifyingPaperId("");
    }
  }

  return (
    <section className="workspace-main-column">
      <section className="pane">
        <SectionHeader
          actions={
            <div className="workspace-evidence-switch" role="tablist" aria-label="论文证据范围">
              <button
                className={viewMode === "analysis" ? "workspace-evidence-switch-active" : ""}
                onClick={() => onViewModeChange("analysis")}
                type="button"
              >
                核心分析 {analysisPaperCount}
              </button>
              <button
                className={viewMode === "extended" ? "workspace-evidence-switch-active" : ""}
                onClick={() => onViewModeChange("extended")}
                type="button"
              >
                扩展证据 {totalPaperCount}
              </button>
            </div>
          }
          eyebrow={eyebrow}
          title="论文证据"
        />
        <div className="workspace-evidence-scope-note">
          {viewMode === "analysis"
            ? "这些论文参与了本轮 taxonomy、研究关系图谱、研究空白与结论生成。"
            : "这里展示本轮检索到的全部合格论文；未进入核心集的论文用于补充阅读，不直接支撑主要结论。"}
        </div>
        <div className="data-table-wrap pane-scroll">
          {visiblePapers.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>论文</th>
                  <th>来源</th>
                  <th>年份</th>
                  <th>分类</th>
                  <th>引用</th>
                  <th>外链</th>
                </tr>
              </thead>
              <tbody>
                {visiblePapers.map((paper) => (
                  <tr
                    className={selectedPaper?.paper_id === paper.paper_id ? "selected-row" : ""}
                    key={paper.paper_id}
                    onClick={() => onSelectPaper(paper.paper_id)}
                    >
                      <td>
                        <div className="workspace-paper-title-row">
                          <div className="table-title">{cleanDisplayText(paper.title, 180)}</div>
                          <PaperBadges paper={paper} showRoundMarkers={showRoundMarkers} />
                        </div>
                      </td>
                    <td>
                      <div className="workspace-paper-source-cell">
                        <strong>{sourceLabel(paper.source)}</strong>
                        <span>{sourceDetailLabel(paper)}</span>
                      </div>
                    </td>
                    <td>{paper.publish_date || "-"}</td>
                    <td>{categoryLabel(paper)}</td>
                    <td>{citationLabel(paper)}</td>
                    <td>
                      {paper.url ? (
                        <a className="inline-link" href={paper.url} rel="noreferrer" target="_blank">
                          来源
                        </a>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="content-pad">
              <div className="empty-state">暂无论文数据。请先运行任务或检查当前任务是否已有工作台结果。</div>
            </div>
          )}
        </div>
      </section>

      <section className="pane">
        <SectionHeader eyebrow="证据摘要" title="论文详情" />
        <div className="content-pad">
          <PaperInspector
            isVerifying={selectedPaper?.paper_id === verifyingPaperId}
            onVerifyPaper={taskId ? handleVerifyPaper : undefined}
            paper={selectedPaper}
            showRoundMarkers={showRoundMarkers}
            verifyStatus={selectedPaper?.paper_id === verifyStatusPaperId ? verifyStatus : ""}
          />
        </div>
      </section>
    </section>
  );
}
