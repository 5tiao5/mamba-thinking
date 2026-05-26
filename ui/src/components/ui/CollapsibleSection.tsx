import { useState, type ReactNode } from "react";

type CollapsibleSectionProps = {
  title: string;
  eyebrow?: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

export function CollapsibleSection({
  title,
  eyebrow,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="collapsible-section">
      <button className="collapsible-trigger" onClick={() => setOpen((value) => !value)} type="button">
        <span>
          {eyebrow ? <small>{eyebrow}</small> : null}
          <strong>{title}</strong>
        </span>
        <span className="collapsible-indicator">{open ? "收起" : "展开"}</span>
      </button>
      {open ? <div className="collapsible-body">{children}</div> : null}
    </section>
  );
}
