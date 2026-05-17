import { NavLink, useLocation, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState, type PropsWithChildren } from "react";

import { API_BASE_URL, api } from "../../lib/api";
import { StatusPill } from "../ui/StatusPill";

const navItems = [
  { to: "/", label: "Launch", description: "新建研究" },
  { to: "/conversation", label: "Conversation", description: "多轮追问" },
  { to: "/workspace", label: "Workspace", description: "结果分析" },
  { to: "/history", label: "History", description: "历史入口" },
  { to: "/settings", label: "Settings", description: "工具配置" },
];

const routeTitles: Record<string, string> = {
  "/": "Research Launch",
  "/conversation": "Conversation Workflow",
  "/workspace": "Research Workspace",
  "/history": "History",
  "/settings": "Tools & Skills",
};

export function AppShell({ children }: PropsWithChildren) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const contextId = searchParams.get("task_id") ?? searchParams.get("conversation_id") ?? "";
  const activeTitle = routeTitles[location.pathname] ?? "Product Agent";
  const contextLabel = searchParams.get("task_id") ? "task" : searchParams.get("conversation_id") ? "conversation" : "context";

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => {
        if (!cancelled) setApiStatus("online");
      })
      .catch(() => {
        if (!cancelled) setApiStatus("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusTone = useMemo(() => {
    if (apiStatus === "online") return "success";
    if (apiStatus === "offline") return "danger";
    return "neutral";
  }, [apiStatus]);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <div className="brand-mark">PA</div>
          <div>
            <h1>Product Agent</h1>
            <p>科研调研工作台</p>
          </div>
        </div>

        <nav className="side-nav">
          {navItems.map((item) => (
            <NavLink
              className={({ isActive }) => (isActive ? "side-nav-link side-nav-active" : "side-nav-link")}
              key={item.to}
              to={item.to}
            >
              <span>{item.label}</span>
              <small>{item.description}</small>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>API</span>
          <code>{API_BASE_URL.replace(/^https?:\/\//, "")}</code>
        </div>
      </aside>

      <div className="app-frame">
        <header className="top-context-bar">
          <div className="top-context-title">
            <span>{activeTitle}</span>
            {contextId ? (
              <code>
                {contextLabel}:{contextId}
              </code>
            ) : null}
          </div>
          <div className="top-context-meta">
            <StatusPill tone={statusTone} compact>
              API {apiStatus}
            </StatusPill>
            <span>{new Date().toLocaleDateString()}</span>
          </div>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
