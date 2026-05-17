import { useEffect, useState } from "react";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
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
    <div className="dense-layout">
      <section className="surface content-pad">
        <div className="item-heading">
          <div>
            <div className="section-eyebrow">Registry</div>
            <strong>工具与 Skill 管理</strong>
          </div>
          <StatusPill tone={loading ? "neutral" : "success"}>{loading ? "loading" : "ready"}</StatusPill>
        </div>
        <div className="status-line" style={{ marginTop: 10 }}>
          {status}
        </div>
      </section>

      <section className="settings-grid">
        <div className="pane">
          <SectionHeader title="Tools" eyebrow={`${tools.length} registered`} />
          <div className="data-table-wrap">
            {tools.length ? (
              <table className="data-table settings-tools-table">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Status</th>
                    <th>Description</th>
                    <th>Config</th>
                    <th>Control</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool) => (
                    <tr key={tool.tool_id}>
                      <td>
                        <div className="table-title">{tool.display_name}</div>
                        <div className="table-subline">{tool.tool_id}</div>
                      </td>
                      <td>
                        <StatusPill tone={tool.enabled ? "success" : "neutral"} compact>
                          {tool.enabled ? "enabled" : "disabled"}
                        </StatusPill>
                      </td>
                      <td>{tool.description}</td>
                      <td>
                        <div className="config-cell">{JSON.stringify(tool.config)}</div>
                      </td>
                      <td>
                        <ToggleSwitch
                          checked={tool.enabled}
                          disabled={updatingToolId === tool.tool_id}
                          label={updatingToolId === tool.tool_id ? "更新中" : "启用"}
                          onChange={() => toggleTool(tool)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="content-pad">
                <div className="empty-state">{loading ? "正在加载工具..." : "暂无工具数据，或后端服务不可用。"}</div>
              </div>
            )}
          </div>
        </div>

        <div className="pane">
          <SectionHeader title="Skills" eyebrow={`${skills.length} registered`} />
          <div className="data-table-wrap">
            {skills.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Skill</th>
                    <th>Status</th>
                    <th>Required Tools</th>
                  </tr>
                </thead>
                <tbody>
                  {skills.map((skill) => (
                    <tr key={skill.skill_id}>
                      <td>
                        <div className="table-title">{skill.display_name}</div>
                        <div className="table-subline">{skill.skill_id}</div>
                        <div className="fine-print">{skill.description}</div>
                      </td>
                      <td>
                        <StatusPill tone={skill.enabled ? "success" : "neutral"} compact>
                          {skill.enabled ? "enabled" : "disabled"}
                        </StatusPill>
                      </td>
                      <td>
                        {skill.required_tools.length ? (
                          <div className="button-row">
                            {skill.required_tools.map((toolId) => (
                              <StatusPill key={toolId} tone="info" compact>
                                {toolId}
                              </StatusPill>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">none</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="content-pad">
                <div className="empty-state">{loading ? "正在加载 Skill..." : "暂无 Skill 数据，或后端服务不可用。"}</div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
