import { useEffect, useState } from "react";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { api, toErrorMessage } from "../lib/api";
import type { SkillItem, ToolItem } from "../types/api";

export function SettingsPage() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [status, setStatus] = useState("正在加载工具与能力...");
  const [loading, setLoading] = useState(true);
  const [updatingToolId, setUpdatingToolId] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listTools(), api.listSkills()])
      .then(([toolResponse, skillResponse]) => {
        setTools(toolResponse.data);
        setSkills(skillResponse.data);
        setStatus("工具与能力加载成功。");
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

  function getToolDisplayName(toolId: string) {
    return tools.find((tool) => tool.tool_id === toolId)?.display_name ?? "关联工具";
  }

  return (
    <div className="dense-layout">
      <section className="surface content-pad">
        <div className="item-heading">
          <div>
            <div className="section-eyebrow">能力设置</div>
            <strong>工具与能力管理</strong>
          </div>
          <StatusPill tone={loading ? "neutral" : "success"}>{loading ? "加载中" : "已同步"}</StatusPill>
        </div>
        <div className="status-line" style={{ marginTop: 10 }}>
          {status}
        </div>
      </section>

      <section className="settings-grid">
        <div className="pane">
          <SectionHeader title="工具" eyebrow={`${tools.length} 项工具`} />
          <div className="data-table-wrap">
            {tools.length ? (
              <table className="data-table settings-tools-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>说明</th>
                    <th>控制</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool) => (
                    <tr key={tool.tool_id}>
                      <td>
                        <div className="table-title">{tool.display_name}</div>
                      </td>
                      <td>
                        <StatusPill tone={tool.enabled ? "success" : "neutral"} compact>
                          {tool.enabled ? "可用" : "关闭"}
                        </StatusPill>
                      </td>
                      <td>{tool.description}</td>
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
                <div className="empty-state">{loading ? "正在加载工具..." : "暂无可展示的工具。"}</div>
              </div>
            )}
          </div>
        </div>

        <div className="pane">
          <SectionHeader title="能力" eyebrow={`${skills.length} 项能力`} />
          <div className="data-table-wrap">
            {skills.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>依赖工具</th>
                  </tr>
                </thead>
                <tbody>
                  {skills.map((skill) => (
                    <tr key={skill.skill_id}>
                      <td>
                        <div className="table-title">{skill.display_name}</div>
                        <div className="fine-print">{skill.description}</div>
                      </td>
                      <td>
                        <StatusPill tone={skill.enabled ? "success" : "neutral"} compact>
                          {skill.enabled ? "可用" : "关闭"}
                        </StatusPill>
                      </td>
                      <td>
                        {skill.required_tools.length ? (
                          <div className="button-row">
                            {skill.required_tools.map((toolId) => (
                              <StatusPill key={toolId} tone="info" compact>
                                {getToolDisplayName(toolId)}
                              </StatusPill>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">无</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="content-pad">
                <div className="empty-state">{loading ? "正在加载能力..." : "暂无可展示的能力。"}</div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
