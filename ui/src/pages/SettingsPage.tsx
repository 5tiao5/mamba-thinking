import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { SkillItem, ToolItem } from "../types/api";

export function SettingsPage() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);

  useEffect(() => {
    Promise.all([api.listTools(), api.listSkills()])
      .then(([toolResponse, skillResponse]) => {
        setTools(toolResponse.data);
        setSkills(skillResponse.data);
      })
      .catch(() => {
        setTools([]);
        setSkills([]);
      });
  }, []);

  return (
    <div className="page">
      <section className="hero-card" style={{ padding: 28 }}>
        <div className="badge">设置页</div>
        <h2 style={{ marginBottom: 10 }}>工具与 Skill 管理</h2>
        <p className="muted">
          这是任务说明里的关键产品能力之一。当前骨架先把列表读出来，后续再补启用/禁用、配置编辑和动态加载。
        </p>
      </section>

      <section className="grid-two">
        <div className="panel">
          <h3 className="section-title">已注册工具</h3>
          <ul className="list">
            {tools.map((tool) => (
              <li className="list-item" key={tool.tool_id}>
                <strong>{tool.display_name}</strong>
                <div className="muted">{tool.description}</div>
                <div className="badge" style={{ marginTop: 10 }}>
                  {tool.enabled ? "已启用" : "已停用"}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <h3 className="section-title">已注册 Skill</h3>
          <ul className="list">
            {skills.map((skill) => (
              <li className="list-item" key={skill.skill_id}>
                <strong>{skill.display_name}</strong>
                <div className="muted">{skill.description}</div>
                <div className="muted" style={{ marginTop: 8 }}>
                  依赖工具：{skill.required_tools.join(", ") || "无"}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
