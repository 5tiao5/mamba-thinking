import { useEffect, useState } from "react";

import { KnowledgeLibraryPanel } from "../components/knowledge/KnowledgeLibraryPanel";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { api, toErrorMessage } from "../lib/api";
import type { RuntimeApiKeyProvider, RuntimeConfigStatus, SkillItem, ToolItem } from "../types/api";

const providerLabels: Record<RuntimeApiKeyProvider, string> = {
  openai: "OpenAI",
  deepseek: "DeepSeek",
  s2: "Semantic Scholar",
};

function configTone(enabled: boolean) {
  return enabled ? "success" : "neutral";
}

function sourceLabel(source: string) {
  if (source === ".env") return ".env";
  if (source === "process") return "进程环境";
  if (source === "process_override") return "进程覆盖";
  return "未配置";
}

export function SettingsPage() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [status, setStatus] = useState("正在加载工具与研究策略模板...");
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigStatus | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState("正在读取运行配置...");
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({});
  const [savingProvider, setSavingProvider] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatingToolId, setUpdatingToolId] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listTools(), api.listSkills(), api.getRuntimeConfig()])
      .then(([toolResponse, skillResponse, configResponse]) => {
        setTools(toolResponse.data);
        setSkills(skillResponse.data);
        setRuntimeConfig(configResponse.data);
        setStatus("工具与研究策略模板加载成功。");
        setRuntimeStatus("运行配置已同步。");
      })
      .catch((error) => {
        setTools([]);
        setSkills([]);
        setStatus(`加载失败：${toErrorMessage(error)}`);
        setRuntimeStatus(`运行配置读取失败：${toErrorMessage(error)}`);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  async function refreshRuntimeConfig(nextStatus = "运行配置已刷新。") {
    try {
      const response = await api.getRuntimeConfig();
      setRuntimeConfig(response.data);
      setRuntimeStatus(nextStatus);
    } catch (error) {
      setRuntimeStatus(`运行配置刷新失败：${toErrorMessage(error)}`);
    }
  }

  async function saveApiKey(provider: RuntimeApiKeyProvider) {
    const value = (apiKeyDrafts[provider] ?? "").trim();
    if (!value) {
      setRuntimeStatus("请先粘贴 API key，再保存。");
      return;
    }
    setSavingProvider(provider);
    setRuntimeStatus(`正在保存 ${providerLabels[provider]} key...`);
    try {
      const response = await api.updateRuntimeApiKey({
        provider,
        action: "set",
        api_key: value,
      });
      setRuntimeConfig(response.data);
      setApiKeyDrafts((current) => ({ ...current, [provider]: "" }));
      setRuntimeStatus(`${providerLabels[provider]} key 已保存，页面不会回显完整 key。`);
    } catch (error) {
      setRuntimeStatus(`保存失败：${toErrorMessage(error)}`);
    } finally {
      setSavingProvider("");
    }
  }

  async function clearApiKey(provider: RuntimeApiKeyProvider) {
    const confirmed = window.confirm(`确认清除 ${providerLabels[provider]} key？清除后相关能力会降级。`);
    if (!confirmed) return;
    setSavingProvider(provider);
    setRuntimeStatus(`正在清除 ${providerLabels[provider]} key...`);
    try {
      const response = await api.updateRuntimeApiKey({
        provider,
        action: "clear",
      });
      setRuntimeConfig(response.data);
      setApiKeyDrafts((current) => ({ ...current, [provider]: "" }));
      setRuntimeStatus(`${providerLabels[provider]} key 已清除。`);
    } catch (error) {
      setRuntimeStatus(`清除失败：${toErrorMessage(error)}`);
    } finally {
      setSavingProvider("");
    }
  }

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
      <section className="surface content-pad settings-overview">
        <div className="item-heading">
          <div>
            <div className="section-eyebrow">研究设置</div>
            <strong>研究偏好与资料库</strong>
          </div>
          <StatusPill tone={loading ? "neutral" : "success"}>{loading ? "加载中" : "已同步"}</StatusPill>
        </div>
        <div className="settings-overview-grid">
          <div>
            <span>可用工具</span>
            <strong>{tools.filter((tool) => tool.enabled).length}</strong>
          </div>
          <div>
            <span>研究策略模板</span>
            <strong>{skills.filter((skill) => skill.enabled).length}</strong>
          </div>
          <div>
            <span>当前策略</span>
            <strong>证据优先</strong>
          </div>
        </div>
        <div className="status-line">
          {status}
        </div>
      </section>

      <section className="surface content-pad runtime-config-panel">
        <div className="item-heading">
          <div>
            <div className="section-eyebrow">运行配置</div>
            <strong>API Key 与本地环境</strong>
          </div>
          <div className="button-row">
            <StatusPill tone={configTone(Boolean(runtimeConfig?.llm_available))}>
              {runtimeConfig?.llm_available ? "LLM 可用" : "LLM 未配置"}
            </StatusPill>
            <button className="secondary-button" type="button" onClick={() => refreshRuntimeConfig()}>
              刷新配置
            </button>
          </div>
        </div>

        <div className="runtime-config-summary">
          <div>
            <span>当前 Provider</span>
            <strong>{runtimeConfig?.active_provider ?? "unknown"}</strong>
          </div>
          <div>
            <span>默认模型</span>
            <strong>{runtimeConfig?.default_model || "未启用"}</strong>
          </div>
          <div>
            <span>论文详情 LLM</span>
            <strong>{runtimeConfig?.paper_brief_llm_enabled ? "已启用" : "未启用"}</strong>
          </div>
          <div>
            <span>Semantic Scholar</span>
            <strong>{runtimeConfig?.semantic_scholar_available ? "已配置" : "未配置"}</strong>
          </div>
        </div>

        <div className="runtime-api-key-grid">
          {(runtimeConfig?.api_keys ?? []).map((item) => (
            <article className="runtime-api-key-card" key={item.provider}>
              <div className="runtime-api-key-head">
                <div>
                  <strong>{item.label}</strong>
                  <span>{item.env_key}</span>
                </div>
                <StatusPill tone={item.configured ? "success" : "neutral"} compact>
                  {item.configured ? "已配置" : "未配置"}
                </StatusPill>
              </div>
              <p>{item.help_text}</p>
              <div className="runtime-api-key-meta">
                <span>来源：{sourceLabel(item.source)}</span>
                <span>指纹：{item.fingerprint || "无"}</span>
              </div>
              <div className="runtime-api-key-actions">
                <input
                  className="input"
                  type="password"
                  autoComplete="off"
                  placeholder={`粘贴新的 ${providerLabels[item.provider]} key`}
                  value={apiKeyDrafts[item.provider] ?? ""}
                  onChange={(event) =>
                    setApiKeyDrafts((current) => ({
                      ...current,
                      [item.provider]: event.target.value,
                    }))
                  }
                />
                <button
                  className="primary-button"
                  type="button"
                  disabled={savingProvider === item.provider}
                  onClick={() => saveApiKey(item.provider)}
                >
                  保存
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={savingProvider === item.provider || !item.configured}
                  onClick={() => clearApiKey(item.provider)}
                >
                  清除
                </button>
              </div>
            </article>
          ))}
        </div>

        <details className="runtime-flags-panel">
          <summary>查看功能开关与安全说明</summary>
          <div className="runtime-flags-grid">
            {(runtimeConfig?.runtime_flags ?? []).map((flag) => (
              <div className="runtime-flag-card" key={flag.key}>
                <strong>{flag.label}</strong>
                <span>{flag.key}</span>
                <code>{flag.effective_value || "未设置"}</code>
                <p>{flag.description}</p>
              </div>
            ))}
          </div>
          <ul className="runtime-safety-notes">
            {(runtimeConfig?.safety_notes ?? []).map((note) => (
              <li key={note}>{note}</li>
            ))}
            {runtimeConfig ? <li>配置文件：{runtimeConfig.env_file_path}</li> : null}
          </ul>
        </details>
        <div className="status-line">{runtimeStatus}</div>
      </section>

      <section className="settings-grid settings-grid-primary">
        <div className="pane">
          <KnowledgeLibraryPanel />
        </div>

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
      </section>

      <section className="settings-grid settings-grid-secondary">
        <div className="pane">
          <SectionHeader title="研究策略模板" eyebrow={`${skills.length} 项模板`} />
          <div className="data-table-wrap">
            {skills.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>建议配套工具</th>
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
                <div className="settings-empty-card">
                  <strong>{loading ? "正在加载研究策略模板..." : "暂未创建研究策略模板"}</strong>
                  <span>
                    模板用于沉淀常用研究方法和分析偏好，会影响研究规划与追问方式，但不会被当作论文证据。
                    可以先使用默认流程，后续在对话页的“工具能力”里创建模板。
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
