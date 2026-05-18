import { NavLink, useLocation, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState, type PropsWithChildren } from "react";

import { api } from "../../lib/api";
import { StatusPill } from "../ui/StatusPill";

const navItems = [
  { to: "/", label: "新建研究", description: "创建主题" },
  { to: "/conversation", label: "多轮追问", description: "收窄问题" },
  { to: "/workspace", label: "研究工作台", description: "结果分析" },
  { to: "/history", label: "历史记录", description: "回看研究" },
  { to: "/settings", label: "工具设置", description: "能力配置" },
];

const routeTitles: Record<string, string> = {
  "/": "新建研究",
  "/conversation": "多轮追问",
  "/workspace": "研究工作台",
  "/history": "历史记录",
  "/settings": "工具与能力",
};

export function AppShell({ children }: PropsWithChildren) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const activeTitle = routeTitles[location.pathname] ?? "科研调研工作台";
  const hasActiveContext = Boolean(searchParams.get("task_id") ?? searchParams.get("conversation_id"));

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
          <span>主链路</span>
          <strong>会话 / 任务 / 工作台</strong>
        </div>
      </aside>

      <div className="app-frame">
        <header className="top-context-bar">
          <div className="top-context-title">
            <span>{activeTitle}</span>
            {hasActiveContext ? <small>当前研究上下文已载入</small> : null}
          </div>
          <div className="top-context-meta">
            <StatusPill tone={statusTone} compact>
              {apiStatus === "online" ? "服务可用" : apiStatus === "offline" ? "服务未连接" : "服务检查中"}
            </StatusPill>
            <span>{new Date().toLocaleDateString()}</span>
          </div>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
