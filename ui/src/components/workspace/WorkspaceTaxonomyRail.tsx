import type {
  WorkspaceSnapshot,
  WorkspaceTaxonomyBranch,
} from "../../types/api";
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
  categories: Array<{ name: string; count: number }>;
  selectedCategory: string;
  onSelectCategory: (category: string) => void;
  branches: WorkspaceTaxonomyBranch[];
  coverage: WorkspaceSnapshot["taxonomy"]["coverage"];
  selectedBranchId: string;
  onSelectBranch: (branchId: string) => void;
};

export function WorkspaceTaxonomyRail({
  topic,
  paperCount,
  categories,
  selectedCategory,
  onSelectCategory,
  branches,
  coverage,
  selectedBranchId,
  onSelectBranch,
}: WorkspaceTaxonomyRailProps) {
  const selectedBranch = branches.find((branch) => branch.branch_id === selectedBranchId) ?? branches[0];
  const selectedCoverage = selectedBranch ? coverage[selectedBranch.branch_id] : undefined;
  const selectedEnglishLabel = selectedBranch ? inferEnglishTaxonomyLabel(selectedBranch) : "";
  const selectedHeading = selectedBranch ? formatTaxonomyHeading(selectedBranch) : "";

  return (
    <aside className="workspace-rail">
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
              className={selectedCategory === "all" ? "workspace-filter-card workspace-filter-card-active" : "workspace-filter-card"}
              onClick={() => onSelectCategory("all")}
              type="button"
            >
              <span className="workspace-filter-title">All Papers / 全部论文</span>
              <span className="workspace-filter-meta">{paperCount} 篇</span>
            </button>
            {categories.map((entry) => (
              <button
                className={
                  selectedCategory === entry.name ? "workspace-filter-card workspace-filter-card-active" : "workspace-filter-card"
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

      <section className="pane">
        <div className="section-header">
          <div>
            <div className="section-eyebrow">{branches.length} branches</div>
            <h2>研究 Taxonomy</h2>
          </div>
        </div>
        <div className="pane-scroll taxonomy-panel">
          {branches.length ? (
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
                  <div className="section-eyebrow">Current branch</div>
                  <div className="taxonomy-detail-title">{selectedHeading}</div>
                  {selectedHeading !== selectedEnglishLabel ? (
                    <div className="taxonomy-detail-english">{selectedEnglishLabel}</div>
                  ) : null}
                  <div className="taxonomy-detail-copy">{selectedBranch.description || "暂无分支描述"}</div>

                  <div className="taxonomy-detail-stats">
                    <div className="taxonomy-stat">
                      <span>论文</span>
                      <strong>{selectedBranch.paper_count}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>Coverage</span>
                      <strong>{formatCoverageScore(selectedCoverage?.coverage_score)}</strong>
                    </div>
                    <div className="taxonomy-stat">
                      <span>Gap</span>
                      <strong>{selectedCoverage?.gap_count ?? 0}</strong>
                    </div>
                  </div>

                  <div className="workspace-coverage-caption">{coverageLabel(selectedCoverage?.coverage_score)}</div>
                  <div className="taxonomy-helper-copy">
                    {coverageExplanation(selectedCoverage?.coverage_score, selectedBranch.paper_count)}
                  </div>

                  <div className="section-eyebrow">Required Concepts</div>
                  {selectedBranch.required_concepts.length ? (
                    <div className="taxonomy-chip-wrap">
                      {selectedBranch.required_concepts.map((concept) => (
                        <span className="taxonomy-chip" key={concept}>
                          {concept}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">暂未列出必要概念。</div>
                  )}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state">暂无研究 taxonomy 摘要。</div>
          )}
        </div>
      </section>
    </aside>
  );
}
