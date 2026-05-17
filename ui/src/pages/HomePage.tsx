import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { StatusPill } from "../components/ui/StatusPill";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { api, toErrorMessage } from "../lib/api";
import {
  DEMO_CONVERSATION_ID,
  DEMO_WORKSPACE_TASK_ID,
  demoMessages,
  demoSkills,
  demoTools,
  demoWorkspace,
} from "../lib/demoData";
import type { ConversationResponsePayload } from "../types/api";

const modeOptions = [
  { value: "default", label: "Default" },
  { value: "fast", label: "Fast" },
  { value: "balanced", label: "Balanced" },
];

const apiContracts = [
  { method: "POST", path: "/conversations", surface: "Launch", status: "ready" },
  { method: "GET", path: "/conversations/{id}/messages", surface: "Conversation", status: "ready" },
  { method: "POST", path: "/conversations/continue", surface: "Conversation", status: "ready" },
  { method: "POST", path: "/research/tasks", surface: "Launch", status: "ready" },
  { method: "POST", path: "/research/tasks/{id}/run", surface: "Workspace", status: "ready" },
  { method: "GET", path: "/research/tasks/{id}/workspace", surface: "Workspace", status: "ready" },
  { method: "GET", path: "/tools", surface: "Settings", status: "ready" },
  { method: "GET", path: "/conversations", surface: "History", status: "missing" },
];

export function HomePage() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("AI Agent Tool Use");
  const [title, setTitle] = useState("Agent 调研");
  const [mode, setMode] = useState("balanced");
  const [useSharedKnowledge, setUseSharedKnowledge] = useState(false);
  const [conversation, setConversation] = useState<ConversationResponsePayload | null>(null);
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("填写主题后创建会话，随后可以进入对话页或直接创建研究任务。");
  const [loading, setLoading] = useState(false);
  const [taskLoading, setTaskLoading] = useState(false);

  async function handleCreateConversation() {
    if (!topic.trim()) {
      setStatus("请先填写研究主题。");
      return;
    }

    setLoading(true);
    setStatus("正在创建会话...");
    try {
      const response = await api.createConversation({
        topic: topic.trim(),
        title: title.trim() || undefined,
      });
      setConversation(response.data);
      setTaskId("");
      setStatus(`已创建会话：${response.data.conversation_id}`);
    } catch (error) {
      setStatus(`创建失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateTask() {
    if (!conversation) {
      setStatus("请先创建会话，再创建研究任务。");
      return;
    }

    setTaskLoading(true);
    setStatus("正在创建研究任务...");
    try {
      const response = await api.createTask({
        conversation_id: conversation.conversation_id,
        topic: conversation.topic,
        mode,
        use_shared_knowledge: useSharedKnowledge,
        enabled_tools: [],
      });
      setTaskId(response.data.task_id);
      setStatus(`已创建任务：${response.data.task_id}`);
    } catch (error) {
      setStatus(`创建任务失败：${toErrorMessage(error)}`);
    } finally {
      setTaskLoading(false);
    }
  }

  function openConversation() {
    if (!conversation) {
      setStatus("请先创建会话。");
      return;
    }
    navigate(`/conversation?conversation_id=${encodeURIComponent(conversation.conversation_id)}`);
  }

  return (
    <div className="dense-layout launch-page">
      <section className="launch-grid">
        <div className="pane">
          <SectionHeader
            actions={
              <StatusPill tone={conversation ? "success" : "neutral"}>
                {conversation ? "Session ready" : "Draft"}
              </StatusPill>
            }
            title="Research Command"
            eyebrow="Create"
          />
          <div className="content-pad launch-command">
            <label>
              <span className="field-label">研究主题</span>
              <input className="input" onChange={(event) => setTopic(event.target.value)} value={topic} />
            </label>
            <label>
              <span className="field-label">会话标题</span>
              <input className="input" onChange={(event) => setTitle(event.target.value)} value={title} />
            </label>
            <div className="form-row">
              <div>
                <span className="field-label">任务模式</span>
                <SegmentedControl label="任务模式" onChange={setMode} options={modeOptions} value={mode} />
              </div>
              <ToggleSwitch checked={useSharedKnowledge} label="使用共享知识" onChange={setUseSharedKnowledge} />
            </div>
            <div className="button-row">
              <button className="primary-button" disabled={loading} onClick={handleCreateConversation} type="button">
                {loading ? "创建中" : "创建会话"}
              </button>
              <button className="secondary-button" disabled={!conversation} onClick={openConversation} type="button">
                进入对话
              </button>
              <button
                className="secondary-button"
                disabled={!conversation || taskLoading}
                onClick={handleCreateTask}
                type="button"
              >
                {taskLoading ? "创建任务中" : "创建研究任务"}
              </button>
            </div>
            <div className="status-line">{status}</div>
          </div>
        </div>

        <div className="pane">
          <SectionHeader title="Workflow State" eyebrow="Main path" />
          <div className="workflow-steps">
            <div className="workflow-step">
              <div className="step-index">1</div>
              <div>
                <div className="item-heading">
                  <strong>Conversation</strong>
                  <StatusPill tone={conversation ? "success" : "neutral"} compact>
                    {conversation ? "created" : "pending"}
                  </StatusPill>
                </div>
                {conversation ? (
                  <>
                    <div className="fine-print">{conversation.title}</div>
                    <code>{conversation.conversation_id}</code>
                  </>
                ) : (
                  <div className="fine-print">等待 `POST /conversations` 返回会话上下文。</div>
                )}
              </div>
            </div>
            <div className="workflow-step">
              <div className="step-index">2</div>
              <div>
                <div className="item-heading">
                  <strong>Follow-up</strong>
                  <StatusPill tone={conversation ? "info" : "neutral"} compact>
                    conversation route
                  </StatusPill>
                </div>
                <div className="fine-print">进入多轮对话后，通过 `POST /conversations/continue` 创建追问任务。</div>
              </div>
            </div>
            <div className="workflow-step">
              <div className="step-index">3</div>
              <div>
                <div className="item-heading">
                  <strong>Research Task</strong>
                  <StatusPill tone={taskId ? "success" : "neutral"} compact>
                    {taskId ? "created" : "optional"}
                  </StatusPill>
                </div>
                {taskId ? (
                  <>
                    <code>{taskId}</code>
                    <div className="button-row" style={{ marginTop: 8 }}>
                      <Link className="secondary-button" to={`/workspace?task_id=${encodeURIComponent(taskId)}`}>
                        打开 Workspace
                      </Link>
                    </div>
                  </>
                ) : (
                  <div className="fine-print">可直接创建任务，也可以从追问生成 follow-up task。</div>
                )}
              </div>
            </div>
          </div>

          <SectionHeader title="Preview Shortcuts" eyebrow="Demo data" />
          <div className="content-pad button-row">
            <Link className="primary-button" to={`/conversation?conversation_id=${encodeURIComponent(DEMO_CONVERSATION_ID)}`}>
              演示对话
            </Link>
            <Link className="secondary-button" to={`/workspace?task_id=${encodeURIComponent(DEMO_WORKSPACE_TASK_ID)}`}>
              演示工作台
            </Link>
            <Link className="ghost-button" to="/settings">
              工具与 Skill
            </Link>
          </div>
        </div>
      </section>

      <section className="metrics-strip">
        <div className="metric-cell">
          <div className="metric-label">Ready APIs</div>
          <div className="metric-value">{apiContracts.filter((item) => item.status === "ready").length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">Demo Papers</div>
          <div className="metric-value">{demoWorkspace.papers.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">Research Gaps</div>
          <div className="metric-value">{demoWorkspace.gaps.length}</div>
        </div>
        <div className="metric-cell">
          <div className="metric-label">Tools / Skills</div>
          <div className="metric-value">
            {demoTools.length}/{demoSkills.length}
          </div>
        </div>
      </section>

      <section className="launch-ops-grid">
        <div className="pane">
          <SectionHeader title="API Contract Map" eyebrow="Frontend surfaces" />
          <div className="data-table-wrap">
            <table className="data-table launch-api-table">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Surface</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {apiContracts.map((contract) => (
                  <tr key={`${contract.method}-${contract.path}`}>
                    <td>{contract.method}</td>
                    <td>
                      <code>{contract.path}</code>
                    </td>
                    <td>{contract.surface}</td>
                    <td>
                      <StatusPill tone={contract.status === "ready" ? "success" : "warning"} compact>
                        {contract.status}
                      </StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="pane">
          <SectionHeader title="Demo Workspace Preview" eyebrow={demoWorkspace.topic} />
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Paper</th>
                  <th>Category</th>
                  <th>Cites</th>
                </tr>
              </thead>
              <tbody>
                {demoWorkspace.papers.map((paper) => (
                  <tr key={paper.paper_id}>
                    <td>
                      <div className="table-title">{paper.title}</div>
                      <div className="table-subline">{paper.source} · {paper.publish_date}</div>
                    </td>
                    <td>{paper.taxonomy_category}</td>
                    <td>{paper.citation_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="launch-ops-grid launch-ops-grid-three">
        <div className="pane">
          <SectionHeader title="Conversation Seed" eyebrow={`${demoMessages.length} demo messages`} />
          <ul className="compact-list">
            {demoMessages.map((message) => (
              <li className="compact-item" key={message.message_id}>
                <div className="item-heading">
                  <strong>{message.role}</strong>
                  <code>{message.message_id}</code>
                </div>
                <div className="fine-print">{message.content}</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="pane">
          <SectionHeader title="Research Gaps" eyebrow="Workspace signals" />
          <ul className="compact-list">
            {demoWorkspace.gaps.map((gap) => (
              <li className="compact-item" key={gap.summary}>
                <div className="item-heading">
                  <strong>{gap.summary}</strong>
                  <StatusPill tone={gap.severity === "high" ? "danger" : "warning"} compact>
                    {gap.severity}
                  </StatusPill>
                </div>
                <div className="fine-print">{gap.evidence.join(" / ")}</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="pane">
          <SectionHeader title="Tooling Readiness" eyebrow="Registered demo stack" />
          <ul className="compact-list">
            {demoTools.map((tool) => (
              <li className="compact-item" key={tool.tool_id}>
                <div className="item-heading">
                  <strong>{tool.display_name}</strong>
                  <StatusPill tone={tool.enabled ? "success" : "neutral"} compact>
                    {tool.enabled ? "enabled" : "disabled"}
                  </StatusPill>
                </div>
                <div className="fine-print">{tool.description}</div>
              </li>
            ))}
            {demoSkills.map((skill) => (
              <li className="compact-item" key={skill.skill_id}>
                <div className="item-heading">
                  <strong>{skill.display_name}</strong>
                  <StatusPill tone="info" compact>
                    skill
                  </StatusPill>
                </div>
                <div className="fine-print">依赖工具：{skill.required_tools.join(", ") || "无"}</div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
