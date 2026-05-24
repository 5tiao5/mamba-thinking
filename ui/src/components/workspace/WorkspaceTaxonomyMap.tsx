import type { EvidenceTier, WorkspaceSnapshot, WorkspaceTaxonomyBranch } from "../../types/api";
import {
  coverageLabel,
  formatCoverageScore,
  formatTaxonomyHeading,
} from "./workspaceFormatters";

type WorkspaceTaxonomyMapProps = {
  topic: string;
  branches: WorkspaceTaxonomyBranch[];
  coverage: WorkspaceSnapshot["taxonomy"]["coverage"];
  selectedBranchId: string;
  onSelectBranch: (branchId: string) => void;
};

function branchNodeStyle(
  score: number,
  paperCount: number,
  evidenceTier: EvidenceTier,
  active: boolean,
) {
  if (active) {
    return { fill: "#eef5ff", stroke: "#2f6fed", badge: "#2f6fed", dash: false };
  }
  if (evidenceTier === "candidate") {
    return { fill: "#fefce8", stroke: "#a3a3a3", badge: "#a3a3a3", dash: true };
  }
  if (evidenceTier === "weak") {
    return { fill: "#fff7ed", stroke: "#ea580c", badge: "#ea580c", dash: false };
  }
  if (evidenceTier === "moderate") {
    return { fill: "#f0fdf4", stroke: "#16a34a", badge: "#16a34a", dash: false };
  }
  // strong
  return { fill: "#eff6ff", stroke: "#2563eb", badge: "#2563eb", dash: false };
}

function truncateLabel(label: string, maxLength = 26) {
  if (label.length <= maxLength) {
    return label;
  }
  return `${label.slice(0, maxLength - 1)}…`;
}

export function WorkspaceTaxonomyMap({
  topic,
  branches,
  coverage,
  selectedBranchId,
  onSelectBranch,
}: WorkspaceTaxonomyMapProps) {
  if (!branches.length) {
    return <div className="empty-state">当前没有可视化 taxonomy 结构。</div>;
  }

  const width = 980;
  const height = 480;
  const centerX = width / 2;
  const centerY = height / 2;
  const radiusX = 340;
  const radiusY = 170;

  return (
    <div className="taxonomy-map-card">
      <svg className="taxonomy-map" viewBox={`0 0 ${width} ${height}`}>
        <g>
          <circle className="taxonomy-map-root" cx={centerX} cy={centerY} r="66" />
          <text
            className="taxonomy-map-root-title"
            textAnchor="middle"
            x={centerX}
            y={centerY - 6}
          >
            Taxonomy
          </text>
          <text
            className="taxonomy-map-root-subtitle"
            textAnchor="middle"
            x={centerX}
            y={centerY + 22}
          >
            {truncateLabel(topic, 24)}
          </text>
        </g>

        {branches.map((branch, index) => {
          const angle = (Math.PI * 2 * index) / branches.length - Math.PI / 2;
          const x = centerX + Math.cos(angle) * radiusX;
          const y = centerY + Math.sin(angle) * radiusY;
          const branchCoverage = coverage[branch.branch_id];
          const paperCount = branch.paper_count;
          const score = branchCoverage?.coverage_score ?? 0;
          const tier: EvidenceTier = branch.evidence_tier || "candidate";
          const active = branch.branch_id === selectedBranchId;
          const style = branchNodeStyle(score, paperCount, tier, active);
          const title = formatTaxonomyHeading(branch);
          const isCandidate = tier === "candidate";

          return (
            <g
              className="taxonomy-map-branch"
              key={branch.branch_id}
              onClick={() => onSelectBranch(branch.branch_id)}
            >
              <line
                className="taxonomy-map-link"
                stroke={style.stroke}
                strokeDasharray={style.dash ? "6,3" : undefined}
                x1={centerX}
                x2={x}
                y1={centerY}
                y2={y}
              />
              <circle
                className={
                  active
                    ? "taxonomy-map-node taxonomy-map-node-active"
                    : "taxonomy-map-node"
                }
                cx={x}
                cy={y}
                fill={style.fill}
                r={isCandidate ? 36 : 42}
                stroke={style.stroke}
                strokeDasharray={style.dash ? "5,3" : undefined}
              />
              <circle
                className="taxonomy-map-badge"
                cx={x + 29}
                cy={y - 28}
                fill={style.badge}
                r="15"
              />
              <text
                className="taxonomy-map-badge-text"
                textAnchor="middle"
                x={x + 29}
                y={y - 22}
              >
                {isCandidate ? "?" : paperCount}
              </text>
              <text className="taxonomy-map-node-title" textAnchor="middle" x={x} y={y - 4}>
                {truncateLabel(title, 24)}
              </text>
              <text className="taxonomy-map-node-meta" textAnchor="middle" x={x} y={y + 19}>
                {isCandidate ? "(candidate)" : coverageLabel(score)}
              </text>
              <title>
                {`${title}\nPapers: ${paperCount}\nCoverage: ${formatCoverageScore(
                  score
                )}\nTier: ${tier}\nGap: ${branchCoverage?.gap_count ?? 0}`}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
