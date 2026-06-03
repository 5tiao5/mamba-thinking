import type {
  EvidenceTier,
  WorkspaceEvidenceStatus,
  WorkspacePaper,
  WorkspaceSnapshot,
  WorkspaceTaxonomyBranch,
} from "../../types/api";
import { cleanDisplayText } from "../../lib/displayText";
import {
  coverageExplanation,
  coverageLabel,
  formatCoverageScore,
  formatTaxonomyHeading,
  inferEnglishTaxonomyLabel,
} from "./workspaceFormatters";
import { WorkspaceTaxonomyMap } from "./WorkspaceTaxonomyMap";

type WorkspaceTaxonomyRailProps = {
  topic: string;
  paperCount: number;
  papers: WorkspacePaper[];
  evidenceStatus?: WorkspaceEvidenceStatus;
  categories: Array<{ name: string; count: number }>;
  selectedCategory: string;
  onSelectCategory: (category: string) => void;
  branches: WorkspaceTaxonomyBranch[];
  coverage: WorkspaceSnapshot["taxonomy"]["coverage"];
  selectedBranchId: string;
  onSelectBranch: (branchId: string) => void;
};

function tierLabel(tier: EvidenceTier): string {
  switch (tier) {
    case "strong": return "强证据";
    case "moderate": return "中等证据";
    case "weak": return "弱证据";
    case "candidate": return "候选分支";
    default: return tier;
  }
}

function tierBadgeStyle(tier: EvidenceTier): { bg: string; text: string } {
  switch (tier) {
    case "strong": return { bg: "#2563eb", text: "#fff" };
    case "moderate": return { bg: "#16a34a", text: "#fff" };
    case "weak": return { bg: "#ea580c", text: "#fff" };
    case "candidate": return { bg: "#f5f5f5", text: "#737373" };
    default: return { bg: "#e5e5e5", text: "#525252" };
  }
}

function sourceLabel(source: string) {
  const normalized = (source || "").toLowerCase();
  if (normalized === "fallback") return "系统回退";
  if (normalized === "arxiv") return "ArXiv";
  if (normalized === "semantic_scholar") return "Semantic Scholar";
  return source || "未知来源";
}

export function WorkspaceTaxonomyRail({
  topic,
  paperCount,
  papers,
  evidenceStatus,
  categories,
  selectedCategory,
  onSelectCategory,
  branches,
  coverage,
  selectedBranchId,
  onSelectBranch,
}: WorkspaceTaxonomyRailProps) {
  const insufficientEvidence = evidenceStatus?.insufficient ?? false;
  const selectedBranch =
    branches.find((branch) => branch.branch_id === selectedBranchId) ?? branches[0];
  const selectedCoverage = selectedBranch
    ? coverage[selectedBranch.branch_id]
    : undefined;
  const selectedEnglishLabel = selectedBranch
    ? inferEnglishTaxonomyLabel(selectedBranch)
    : "";
  const selectedHeading = selectedBranch
    ? formatTaxonomyHeading(selectedBranch)
    : "";

  return (
    <aside className="workspace-rail workspace-rail-wide">
      <section className="pane">
        <div className="section-header">
          <div>
            <div className="section-eyebrow">Filter</div>
            <h2>论文筛选</h2>
          </div>
        </div>
        <div className="pane-scroll">
          <div className="workspace-filter-list">
            <button
              className={
                selectedCategory === "all"
                  ? "workspace-filter-card workspace-filter-card-active"
                  : "workspace-filter-card"
              }
              onClick={() => onSelectCategory("all")}
              type="button"
            >
              <span className="workspace-filter-title">全部论文</span>
              <span className="workspace-filter-meta">{paperCount} 篇</span>
            </button>
            {categories.map((entry) => (
              <button
                className={
                  selectedCategory === entry.name
                    ? "workspace-filter-card workspace-filter-card-active"
                    : "workspace-filter-card"
                }
                key={entry.name}
                onClick={() => onSelectCategory(entry.name)}
                type="button"
              >
                <span className="workspace-filter-title">{entry.name}</span>
                <span className="workspace-filter-meta">{entry.count} 篇</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="pane taxonomy-pane-expanded">
        <div className="section-header">
          <div>
            <div className="section-eyebrow">{branches.length} 个分支</div>
            <h2>Taxonomy / 研究分类</h2>
          </div>
        </div>
        <div className="pane-scroll taxonomy-panel">
          {insufficientEvidence ? (
            <div className="taxonomy-layout">
              <div className="taxonomy-detail-card taxonomy-detail-card-warning">
                <div className="section-eyebrow">候选方向</div>
                <div className="taxonomy-detail-title">当前不展示完整方向图</div>
                <div className="taxonomy-detail-copy">
                  {cleanDisplayText(evidenceStatus?.message) ||
                    "当前真实论文证据过薄，这一轮更适合先展示候选研究分支与补证建议。"}
                </div>

                {evidenceStatus?.candidate_branches?.length ? (
                  <>
                    <div className="section-eyebrow">建议方向草稿</div>
                    <div className="taxonomy-chip-wrap">
                      {evidenceStatus.candidate_branches.map((branchName) => (
                        <span className="taxonomy-chip taxonomy-chip-warning" key={branchName}>
                          {cleanDisplayText(branchName, 80)}
                        </span>
                      ))}
                    </div>
                  </>
                ) : null}

                <div className="taxonomy-detail-stats">
                  <div className="taxonomy-stat">
                    <span>真实论文</span>
                    <strong>{evidenceStatus?.real_paper_count ?? 0}</strong>
                  </div>
                  <div className="taxonomy-stat">
                    <span>回退论文</span>
                    <strong>{evidenceStatus?.fallback_paper_count ?? 0}</strong>
                  </div>
                  <div className="taxonomy-stat">
                    <span>覆盖分支</span>
                    <strong>{evidenceStatus?.covered_branch_count ?? 0}</strong>
                  </div>
                </div>

                <div className="taxonomy-helper-copy">
                  这时候继续强行绘制完整方向图，往往会把薄证据包装成很完整的研究地图。更合理的下一步是：
                  缩小问题、补充论文，或者先导入已有资料后再刷新研究总览。
                </div>
              </div>
            </div>
          ) : branches.length ? (
            <div className="taxonomy-layout">
              <WorkspaceTaxonomyMap
                branches={branches}
                coverage={coverage}
                onSelectBranch={onSelectBranch}
                selectedBranchId={selectedBranchId}
                topic={topic}
              />

              {selectedBranch ? (
                <div className="taxonomy-detail-card">
                  <div className="section-eyebrow">当前方向</div>
                  <div className="taxonomy-detail-title">{cleanDisplayText(selectedHeading, 120)}</div>
                  {selectedHeading !== selectedEnglishLabel ? (
                    <div className="taxonomy-detail-english">
                      {cleanDisplayText(selectedEnglishLabel, 120)}
                    </div>
                  ) : null}
                  <div className="taxonomy-detail-copy">
                    {cleanDisplayText(selectedBranch.description) || "当前分支暂时没有补充说明。"}
                  </div>

                  <div className="taxonomy-detail-stats">
                    <div className="taxonomy-stat">
                      <span>论文数</span>
                      <strong>{selectedBranch.paper_count}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>覆盖率</span>
                      <strong>{formatCoverageScore(selectedCoverage?.coverage_score)}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>空白数</span>
                      <strong>{selectedCoverage?.gap_count ?? 0}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>匹配论文</span>
                      <strong>{selectedCoverage?.matched_paper_ids?.length ?? selectedBranch.matched_paper_ids?.length ?? 0}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>匹配空白</span>
                      <strong>{selectedCoverage?.matched_gap_ids?.length ?? selectedBranch.matched_gap_ids?.length ?? 0}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>证据等级</span>
                      <strong
                        style={{
                          color: tierBadgeStyle(selectedBranch.evidence_tier || "candidate").bg,
                        }}
                      >
                        {tierLabel(selectedBranch.evidence_tier || "candidate")}
                      </strong>
                    </div>
                    {selectedBranch.branch_confidence > 0 ? (
                      <div className="taxonomy-stat">
                        <span>置信度</span>
                        <strong>{(selectedBranch.branch_confidence * 100).toFixed(0)}%</strong>
                      </div>
                    ) : null}
                  </div>

                  <div className="workspace-coverage-caption">
                    {coverageLabel(selectedCoverage?.coverage_score)}
                  </div>
                  <div className="taxonomy-helper-copy">
                    {coverageExplanation(
                      selectedCoverage?.coverage_score,
                      selectedBranch.paper_count
                    )}
                  </div>

                  <div className="section-eyebrow">关键概念</div>
                  {selectedBranch.required_concepts.length ? (
                    <div className="taxonomy-chip-wrap">
                      {selectedBranch.required_concepts.map((concept) => (
                        <span className="taxonomy-chip" key={concept}>
                          {cleanDisplayText(concept, 80)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">当前分支还没有列出必要概念。</div>
                  )}

                  <div className="section-eyebrow">匹配论文</div>
                  {papers.length ? (
                    <div className="taxonomy-evidence-list">
                      {papers.map((paper) => (
                        <article className="taxonomy-evidence-item" key={paper.paper_id}>
                          <div className="taxonomy-evidence-title">{cleanDisplayText(paper.title, 160)}</div>
                          <div className="taxonomy-evidence-meta">
                            <span>{paper.paper_id}</span>
                            <span>{sourceLabel(paper.source)}</span>
                            <span>{cleanDisplayText(paper.taxonomy_category, 80) || "未分类"}</span>
                            <span>{paper.publish_date || "-"}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">
                      当前方向还没有稳定归属的论文证据。如果这一轮证据偏弱，更适合先展示候选方向，而不是继续强行生成完整方向图。
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state">当前还没有可视化的研究方向结构。</div>
          )}
        </div>
      </section>
    </aside>
  );
}
