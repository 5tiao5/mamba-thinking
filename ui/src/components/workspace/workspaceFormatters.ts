import { cleanDisplayText } from "../../lib/displayText";
import type { WorkspaceGap, WorkspaceIdea, WorkspacePaper, WorkspaceTaxonomyBranch } from "../../types/api";

const TAXONOMY_TERM_RULES: Array<{ keywords: string[]; english: string }> = [
  { keywords: ["method", "方法", "模型", "算法", "architecture"], english: "Methods" },
  { keywords: ["evaluation", "benchmark", "评测", "评估", "指标"], english: "Evaluation and Benchmarks" },
  { keywords: ["application", "gap", "应用", "场景", "局限"], english: "Applications and Gaps" },
  { keywords: ["interaction", "human", "人机", "交互", "协作"], english: "Human-Agent Interaction" },
  { keywords: ["software", "engineering", "软件", "工程"], english: "Software Engineering" },
  { keywords: ["peer", "review", "评审", "审稿"], english: "Peer Review Sustainability" },
  { keywords: ["memory", "记忆", "长期上下文"], english: "Memory and Context" },
];

function containsChinese(text: string) {
  return /[\u4e00-\u9fff]/.test(text);
}

function toTitleCase(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function englishConcepts(concepts: string[]) {
  return concepts
    .filter((concept) => /[A-Za-z]/.test(concept))
    .map((concept) => toTitleCase(concept))
    .filter((concept, index, array) => array.indexOf(concept) === index);
}

function trimPunctuation(text: string) {
  return text.replace(/^[,.;:，。；：\s]+/, "").replace(/[,.;:，。；：\s]+$/, "").trim();
}

function removeDecorations(text: string) {
  return text.replace(/[《》「」]/g, "");
}

function stripEllipsis(text: string) {
  return text.replace(/(\.{3,}|…+)\s*$/g, "").trim();
}

export function inferEnglishTaxonomyLabel(branch: WorkspaceTaxonomyBranch) {
  const branchName = branch.name.trim();
  if (branchName && /[A-Za-z]/.test(branchName) && !containsChinese(branchName)) {
    return toTitleCase(branchName);
  }

  const branchId = branch.branch_id.trim();
  if (branchId && branchId !== "branch" && /[A-Za-z]/.test(branchId)) {
    return toTitleCase(branchId);
  }

  const haystack = [branch.name, branch.description, branch.branch_id, ...branch.required_concepts]
    .join(" ")
    .toLowerCase();

  const matchedRule = TAXONOMY_TERM_RULES.find((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)));
  if (matchedRule) {
    return matchedRule.english;
  }

  const inferredConcepts = englishConcepts(branch.required_concepts);
  if (inferredConcepts.length) {
    return inferredConcepts.slice(0, 3).join(" / ");
  }

  return "Emerging Branch";
}

export function formatTaxonomyHeading(branch: WorkspaceTaxonomyBranch) {
  const english = inferEnglishTaxonomyLabel(branch);
  if (!branch.name.trim()) {
    return english;
  }
  if (!containsChinese(branch.name)) {
    return english;
  }
  return `${english} / ${branch.name}`;
}

export function formatCoverageScore(score?: number) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "--";
  }
  return score.toFixed(2);
}

export function coverageLabel(score?: number) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "未评估";
  }
  if (score <= 0.05) {
    return "尚未覆盖";
  }
  if (score < 0.45) {
    return "覆盖偏弱";
  }
  if (score < 0.8) {
    return "覆盖中等";
  }
  return "覆盖较好";
}

export function coverageExplanation(score: number | undefined, paperCount: number) {
  if (!paperCount) {
    return "当前没有论文归入该分支，因此 coverage 为 0.00。";
  }
  return `当前共有 ${paperCount} 篇论文归入该分支，coverage 用于衡量这个分支的证据充足度。`;
}

export function relationshipTone(relationship: string) {
  const value = relationship.toLowerCase();
  if (value.includes("improve")) return "#2f6fed";
  if (value.includes("reference")) return "#0f766e";
  if (value.includes("compare")) return "#b45309";
  return "#64748b";
}

export function relationshipLabel(relationship: string) {
  const value = relationship.toLowerCase();
  if (value.includes("improve")) return "改进关系";
  if (value.includes("reference")) return "参考关系";
  if (value.includes("compare")) return "对比关系";
  return "关联关系";
}

export function relationshipBadgeLabel(relationship: string) {
  const value = relationship.toLowerCase();
  if (value.includes("improve")) return "IMPROVES";
  if (value.includes("reference")) return "REFERENCES";
  if (value.includes("compare")) return "COMPARES";
  return "RELATION";
}

export function categoryTone(category: string) {
  const value = category.toLowerCase();
  if (value.includes("method")) return { fill: "#eef5ff", stroke: "#2f6fed", label: "Methods" };
  if (value.includes("evaluation")) return { fill: "#eefcf8", stroke: "#0f766e", label: "Evaluation" };
  if (value.includes("application")) return { fill: "#fff7ed", stroke: "#c2410c", label: "Applications" };
  if (value.includes("interaction")) return { fill: "#faf5ff", stroke: "#9333ea", label: "Interaction" };
  if (value.includes("software")) return { fill: "#f5f3ff", stroke: "#6d28d9", label: "Software Engineering" };
  return { fill: "#f8fbff", stroke: "#94a3b8", label: category || "Uncategorized" };
}

export function shortPaperLabel(paperId: string, papers: WorkspacePaper[]) {
  const matched = papers.find((paper) => paper.paper_id === paperId);
  if (!matched) {
    return paperId;
  }
  const title = trimPunctuation(removeDecorations(matched.title.trim()));
  if (title.length <= 28) {
    return title;
  }
  return `${title.slice(0, 26)}…`;
}

export function resolvePaperTitle(paperId: string, papers: WorkspacePaper[]) {
  const matched = papers.find((paper) => paper.paper_id === paperId);
  return matched ? trimPunctuation(removeDecorations(cleanDisplayText(matched.title, 200) || paperId)) : paperId;
}

export function formatPaperReference(paperId: string, papers: WorkspacePaper[]) {
  return resolvePaperTitle(paperId, papers);
}

export function formatGraphEdgeHeadline(
  relationship: string,
  sourceId: string,
  targetId: string,
  papers: WorkspacePaper[],
) {
  const source = formatPaperReference(sourceId, papers);
  const target = formatPaperReference(targetId, papers);
  const label = relationshipLabel(relationship);

  if (label === "改进关系") {
    return `${source} 对 ${target} 提供了改进线索`;
  }
  if (label === "参考关系") {
    return `${source} 与 ${target} 存在参考关联`;
  }
  if (label === "对比关系") {
    return `${source} 与 ${target} 形成对比关系`;
  }
  return `${source} 与 ${target} 存在关联`;
}

export function formatGraphEdgeReasoning(reasoning: string | undefined, papers: WorkspacePaper[]) {
  const cleaned = formatTextWithPaperTitles(reasoning || "", papers);
  if (!cleaned) {
    return "当前证据显示这两篇论文存在关联，但还缺少更细的背景说明。";
  }

  const overlapMatch = cleaned.match(/keyword_overlap\s*=\s*([0-9.]+)/i);
  const overlap = overlapMatch ? Number(overlapMatch[1]) : undefined;
  const closeness =
    typeof overlap === "number" && !Number.isNaN(overlap)
      ? overlap >= 0.2
        ? "比较接近"
        : "有一定重合"
      : "存在重合";

  if (/share .*taxonomy.*or keywords/i.test(cleaned) || /keyword_overlap/i.test(cleaned)) {
    return `这两篇论文在研究主题或关键词上${closeness}，适合放在同一条参考脉络里一起看。`;
  }

  return stripEllipsis(trimPunctuation(cleaned));
}

export function formatGraphEdgeReasoningByRelationship(
  relationship: string,
  reasoning: string | undefined,
  papers: WorkspacePaper[],
) {
  const value = relationship.toLowerCase();
  const cleaned = formatTextWithPaperTitles(reasoning || "", papers);
  const overlapMatch = cleaned.match(/keyword_overlap\s*=\s*([0-9.]+)/i);
  const overlap = overlapMatch ? Number(overlapMatch[1]) : undefined;
  const closeness =
    typeof overlap === "number" && !Number.isNaN(overlap)
      ? overlap >= 0.2
        ? "比较接近"
        : "有一定重合"
      : "存在重合";

  if (value.includes("reference")) {
    return `这两篇论文在研究主题或关键词上${closeness}，可以作为同一方向的参考材料。`;
  }
  if (value.includes("improve")) {
    return "从当前证据看，前一篇论文的方法或结论对后一篇论文形成了推进线索。";
  }
  if (value.includes("compare")) {
    return "这两篇论文关注的问题相近，但切入方式不同，适合并排比较。";
  }

  return formatGraphEdgeReasoning(reasoning, papers);
}

function replacePaperIds(text: string, papers: WorkspacePaper[]) {
  return text.replace(/\b\d{4}\.\d{5}v\d+\b/g, (paperId) => formatPaperReference(paperId, papers));
}

export function formatTextWithPaperTitles(text: string, papers: WorkspacePaper[], maxLength?: number) {
  const cleaned = cleanDisplayText(text, maxLength);
  if (!cleaned) return "";
  return removeDecorations(replacePaperIds(cleaned, papers));
}

function normalizeIdeaEnglish(text: string) {
  return text
    .replace(/^The rapid growth of\s+/i, "随着 ")
    .replace(/paper submissions in software engineering/gi, "软件工程论文投稿量")
    .replace(/\s+has outpaced\s+/i, " 的增长已经超过了 ")
    .replace(/the availability of qualified reviewers/gi, "合格审稿人的供给")
    .replace(/creating a sustainability crisis in peer review/gi, "使审稿流程面临可持续性压力")
    .replace(/Existing literature/gi, "现有研究")
    .replace(/\s+highlights the need for\s+/i, " 表明当前需要 ")
    .replace(/\s+but lacks\s+/i, "，但仍缺少 ")
    .replace(/concrete solutions for/gi, "可落地方案来处理")
    .replace(/reviewer training/gi, "审稿人训练")
    .replace(/AI-assisted review/gi, "AI 辅助评审")
    .replace(/This research gap presents an opportunity to\s+/i, "因此可以围绕 ")
    .replace(/^Develop a prototype system that uses\s+/i, "建议先实现一个原型系统，利用 ")
    .replace(/fine-tuned LLM/gi, "微调后的 LLM")
    .replace(/generate initial review comments for submitted papers/gi, "为提交论文生成初步评审意见")
    .replace(/focusing on/gi, "重点关注")
    .replace(/clarity, methodology, and reproducibility/gi, "清晰度、方法设计和可复现性")
    .replace(/The system will include/gi, "系统可包含")
    .replace(/a training module for novice reviewers/gi, "面向新手评审者的训练模块")
    .replace(/where they compare/gi, "其中可以比较")
    .replace(/their own reviews/gi, "人工评审结果")
    .replace(/with AI-generated ones/gi, "与 AI 生成结果")
    .replace(/and receive feedback/gi, "并获得反馈")
    .replace(/^High\.\s*/i, "可行性较高：")
    .replace(/^Medium\.\s*/i, "可行性中等：")
    .replace(/^Low\.\s*/i, "可行性偏低：")
    .replace(/LLMs are readily available and can be fine-tuned on existing review datasets/gi, "现有大模型已经比较成熟，也可以基于已有评审数据继续调优")
    .replace(/existing review datasets/gi, "现有评审数据")
    .replace(/can be implemented/gi, "可以落地实现")
    .replace(/The main challenge is/gi, "主要挑战在于")
    .replace(/which can be mitigated by/gi, "可以通过")
    .replace(/^First empirical study of\s+/i, "预期可形成首个围绕 ")
    .replace(/\s+in software engineering/gi, " 在软件工程场景中的")
    .replace(/\s+to improve\s+/i, "，以提升 ")
    .replace(/\s+to reduce\s+/i, "，并降低 ")
    .replace(/\s+\/ Contribution:\s*/i, "。预期贡献：")
    .replace(/\s+/g, " ")
    .trim();
}

function localizeIdeaText(text: string, papers: WorkspacePaper[], maxLength?: number) {
  const formatted = formatTextWithPaperTitles(text, papers, maxLength);
  if (!formatted) return "";
  return stripEllipsis(trimPunctuation(normalizeIdeaEnglish(formatted)));
}

function compactIdeaText(text: string) {
  return stripEllipsis(
    text
      .replace(/^随着\s+/i, "")
      .replace(/^现有研究表明当前需要/i, "当前更需要")
      .replace(/^现有研究/i, "现有研究")
      .replace(/^因此可以围绕/i, "可围绕")
      .replace(/^建议先实现一个原型系统，利用/i, "建议先做一个原型，利用")
      .replace(/^可行性较高：/i, "")
      .replace(/^可行性中等：/i, "")
      .replace(/^可行性偏低：/i, "")
      .replace(/^预期可形成首个围绕/i, "预期可形成围绕")
      .replace(/审稿流程面临可持续性压力/g, "审稿压力明显增大")
      .replace(/现有评审数据/g, "现有评审数据")
      .replace(/提交论文/g, "论文")
      .replace(/初步评审意见/g, "初步评审建议")
      .replace(/人工评审结果/g, "人工评审结果")
      .replace(/软件工程论文投稿量/g, "软件工程投稿量")
      .replace(/\s+/g, " ")
      .trim(),
  );
}

export type GapCategory = "branch" | "concept" | "evidence" | "general";

function detectGapCategory(raw: string): GapCategory {
  if (/^Missing\s+(?:taxonomy|研究方向图)\s+branch:/i.test(raw)) {
    return "branch";
  }
  if (/^Missing\s+required\s+concepts\s+in\s+/i.test(raw)) {
    return "concept";
  }
  if (/^(?:Unsupported\s+improvement\s+claim|LLM\s+detected\s+unsupported\s+edge):/i.test(raw)) {
    return "evidence";
  }
  return "general";
}

export function formatGapCategory(gap: WorkspaceGap) {
  const raw = cleanDisplayText(gap.summary, 260);
  const category = detectGapCategory(raw);
  if (category === "branch") return "方向缺失";
  if (category === "concept") return "概念缺失";
  if (category === "evidence") return "证据不足";
  return "一般空白";
}

export function gapCategoryTone(gap: WorkspaceGap) {
  const raw = cleanDisplayText(gap.summary, 260);
  const category = detectGapCategory(raw);
  if (category === "branch") return "warning";
  if (category === "concept") return "accent";
  if (category === "evidence") return "neutral";
  return "neutral";
}

export function formatGapHeadline(gap: WorkspaceGap, papers: WorkspacePaper[]) {
  const raw = cleanDisplayText(gap.summary, 260);
  if (!raw) return "待补充的研究空白";

  let match = raw.match(/^Missing\s+(?:taxonomy|研究方向图)\s+branch:\s*(.+?)\.?$/i);
  if (match) {
    return `当前证据尚未覆盖研究方向「${trimPunctuation(removeDecorations(cleanDisplayText(match[1]) || ""))}」`;
  }

  match = raw.match(/^Missing\s+required\s+concepts\s+in\s+'(.+?)':\s*(.+?)\.?$/i);
  if (match) {
    const branch = trimPunctuation(removeDecorations(cleanDisplayText(match[1]) || ""));
    const concepts = trimPunctuation(removeDecorations(cleanDisplayText(match[2]) || "")).replace(/\s*,\s*/g, "、");
    return `方向「${branch}」缺少关键概念：${concepts}`;
  }

  match = raw.match(/^Unsupported\s+improvement\s+claim:\s*(.+?)\s*->\s*(.+?)\.?$/i);
  if (match) {
    return `${formatPaperReference(match[1], papers)} 与 ${formatPaperReference(match[2], papers)} 之间的“改进关系”缺少证据支持`;
  }

  match = raw.match(/^LLM\s+detected\s+unsupported\s+edge:\s*(.+?)\s*->\s*(.+?)\.?$/i);
  if (match) {
    return `${formatPaperReference(match[1], papers)} 与 ${formatPaperReference(match[2], papers)} 之间的关系推断仍不稳定`;
  }

  return stripEllipsis(trimPunctuation(replacePaperIds(raw, papers)));
}

export function formatGapDetail(gap: WorkspaceGap, papers: WorkspacePaper[]) {
  const raw = cleanDisplayText(gap.summary, 360);
  if (!raw) return "";

  let match = raw.match(/^Missing\s+(?:taxonomy|研究方向图)\s+branch:\s*(.+?)\.?$/i);
  if (match) {
    const branch = trimPunctuation(removeDecorations(cleanDisplayText(match[1]) || ""));
    return `这表示当前检索到的真实论文还不足以支撑「${branch}」这个研究分支，建议继续补充这个方向的代表性论文或综述。`;
  }

  match = raw.match(/^Missing\s+required\s+concepts\s+in\s+'(.+?)':\s*(.+?)\.?$/i);
  if (match) {
    const concepts = trimPunctuation(removeDecorations(cleanDisplayText(match[2]) || "")).replace(/\s*,\s*/g, "、");
    return `这意味着现有论文还没有充分覆盖这些关键概念：${concepts}。`;
  }

  match = raw.match(/^Unsupported\s+improvement\s+claim:\s*(.+?)\s*->\s*(.+?)\.?$/i);
  if (match) {
    return "系统当前没有找到足够证据来证明这两篇论文之间存在明确的改进关系。";
  }

  match = raw.match(/^LLM\s+detected\s+unsupported\s+edge:\s*(.+?)\s*->\s*(.+?)\.?$/i);
  if (match) {
    return "当前关系图中的这条连边更像候选推断，还需要更多文献证据来确认。";
  }

  return stripEllipsis(trimPunctuation(replacePaperIds(raw, papers)));
}

export function formatGapEvidenceItems(gap: WorkspaceGap, papers: WorkspacePaper[]) {
  return gap.evidence
    .map((item) => stripEllipsis(trimPunctuation(replacePaperIds(cleanDisplayText(item, 180), papers))))
    .filter(Boolean);
}

export function formatIdeaSummary(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.motivation || idea.raw_text, papers, 78)) || "这条建议目前还没有补充完整的背景说明。";
}

export function formatIdeaApproach(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.approach, papers, 72));
}

export function formatIdeaFeasibility(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.feasibility, papers, 50));
}

export function formatIdeaContribution(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.contribution, papers, 54));
}

export function formatIdeaSummaryFull(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.motivation || idea.raw_text, papers)) || "这条建议目前还没有补充完整的背景说明。";
}

export function formatIdeaApproachFull(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.approach, papers));
}

export function formatIdeaFeasibilityFull(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.feasibility, papers));
}

export function formatIdeaContributionFull(idea: WorkspaceIdea, papers: WorkspacePaper[]) {
  return compactIdeaText(localizeIdeaText(idea.contribution, papers));
}
