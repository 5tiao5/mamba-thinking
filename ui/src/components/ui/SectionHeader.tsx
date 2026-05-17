import type { ReactNode } from "react";

type SectionHeaderProps = {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
};

export function SectionHeader({ title, eyebrow, actions }: SectionHeaderProps) {
  return (
    <div className="section-header">
      <div>
        {eyebrow ? <div className="section-eyebrow">{eyebrow}</div> : null}
        <h2>{title}</h2>
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  );
}
