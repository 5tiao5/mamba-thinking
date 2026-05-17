import { useEffect, useState } from "react";

import { api, toErrorMessage } from "../lib/api";
import type { SkillItem, ToolItem } from "../types/api";

export function SettingsPage() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [status, setStatus] = useState("正在加载工具和 Skill...");
  const [loading, setLoading] = useState(true);
  const [updatingToolId, setUpdatingToolId] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listTools(), api.listSkills()])
      .then(([toolResponse, skillResponse]) => {
        setTools(toolResponse.data);
        setSkills(skillResponse.data);
        setStatus("工具和 Skill 加载成功。");
      })
      .catch((error) => {
        setTools([]);
        setSkills([]);
        setStatus(`加载失败：${toErrorMessage(error)}`);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  async function toggleTool(tool: ToolItem) {
    setUpdatingToolId(tool.tool_id);
    setStatus(`正在${tool.enabled ? "停用" : "启用"} ${tool.display_name}...`);
    try {
      const response = await api.updateTool(tool.tool_id, {
        enabled: !tool.enabled,
        config: tool.config,
      });
      setTools((current) => current.map((item) => (item.tool_id === tool.tool_id ? response.data : item)));
      setStatus(`${response.data.display_name} 已${response.data.enabled ? "启用" : "停用"}。`);
    } catch (error) {
      setStatus(`更新失败：${toErrorMessage(error)}`);
    } finally {
      setUpdatingToolId("");
    }
  }

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">设置页</div>
        <h2 style={{ marginBottom: 10 }}>工具与 Skill 管理</h2>
        <p className="muted">
          展示后端已注册工具与 Skill，并支持工具启用/停用。
        </p>
      </section>

      <section className="panel">
        <h3 className="section-title">加载状态</h3>
        <div className="status-line">{status}</div>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">已注册工具</h3>
          {tools.length ? (
            <ul className="list">
              {tools.map((tool) => (
                <li className="list-item" key={tool.tool_id}>
                  <div className="item-heading">
                    <strong>{tool.display_name}</strong>
                    <span className="badge">{tool.enabled ? "已启用" : "已停用"}</span>
                  </div>
                  <div className="muted">{tool.description}</div>
                  <code>{tool.tool_id}</code>
                  <pre className="json-block compact">{JSON.stringify(tool.config, null, 2)}</pre>
                  <button
                    className={tool.enabled ? "secondary-button" : "primary-button"}
                    onClick={() => toggleTool(tool)}
                    disabled={updatingToolId === tool.tool_id}
                    style={{ marginTop: 12 }}
                  >
                    {updatingToolId === tool.tool_id ? "更新中..." : tool.enabled ? "停用工具" : "启用工具"}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">{loading ? "正在加载工具..." : "暂无工具数据，或后端服务不可用。"}</div>
          )}
        </div>

        <div className="panel">
          <h3 className="section-title">已注册 Skill</h3>
          {skills.length ? (
            <ul className="list">
              {skills.map((skill) => (
                <li className="list-item" key={skill.skill_id}>
                  <div className="item-heading">
                    <strong>{skill.display_name}</strong>
                    <span className="badge">{skill.enabled ? "已启用" : "未启用"}</span>
                  </div>
                  <div className="muted">{skill.description}</div>
                  <code>{skill.skill_id}</code>
                  <div className="muted" style={{ marginTop: 8 }}>
                    依赖工具：{skill.required_tools.join(", ") || "无"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">{loading ? "正在加载 Skill..." : "暂无 Skill 数据，或后端服务不可用。"}</div>
          )}
        </div>
      </section>
    </div>
  );
}
