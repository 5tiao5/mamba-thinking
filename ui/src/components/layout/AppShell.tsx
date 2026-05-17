import { NavLink } from "react-router-dom";
import type { PropsWithChildren } from "react";

const navItems = [
  { to: "/", label: "新建任务" },
  { to: "/conversation", label: "对话区" },
  { to: "/workspace", label: "研究工作台" },
  { to: "/history", label: "历史会话" },
  { to: "/settings", label: "工具与 Skill" },
];

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div style={{ marginBottom: 28 }}>
          <div className="badge">Iter 3 Product Agent</div>
          <h1 style={{ margin: "18px 0 8px", fontSize: "1.55rem" }}>科研调研工作台</h1>
          <p className="muted" style={{ margin: 0 }}>
            面向 AI Agent / Code Agent 研究方向的多轮交互式产品骨架。
          </p>
        </div>

        <nav style={{ display: "grid", gap: 10 }}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                padding: "14px 16px",
                borderRadius: 16,
                background: isActive ? "#e8f1fb" : "transparent",
                color: isActive ? "#123a6d" : "#304b66",
                fontWeight: 700,
                border: isActive ? "1px solid rgba(18,58,109,0.08)" : "1px solid transparent",
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main style={{ padding: 28 }}>{children}</main>
    </div>
  );
}
