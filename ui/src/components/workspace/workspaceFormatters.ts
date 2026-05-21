import type { WorkspacePaper, WorkspaceTaxonomyBranch } from "../../types/api";

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
  return `当前共有 ${paperCount} 篇论文归入该分支，coverage 用于衡量该分支的证据充足度。`;
}

export function relationshipTone(relationship: string) {
  const value = relationship.toLowerCase();
  if (value.includes("improve")) return "#2f6fed";
  if (value.includes("reference")) return "#0f766e";
  if (value.includes("compare")) return "#b45309";
  return "#64748b";
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
  const title = matched.title.trim();
  if (title.length <= 28) {
    return title;
  }
  return `${title.slice(0, 26)}…`;
}
