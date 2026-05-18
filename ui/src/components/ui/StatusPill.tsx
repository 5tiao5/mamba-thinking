import type { PropsWithChildren } from "react";

type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

type StatusPillProps = PropsWithChildren<{
  tone?: StatusTone;
  compact?: boolean;
}>;

export function StatusPill({ children, tone = "neutral", compact = false }: StatusPillProps) {
  return <span className={`status-pill status-pill-${tone} ${compact ? "status-pill-compact" : ""}`}>{children}</span>;
}
