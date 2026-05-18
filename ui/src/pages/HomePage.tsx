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
  demoWorkspace,
} from "../lib/demoData";
import type { ConversationResponsePayload } from "../types/api";

const modeOptions = [
  { value: "default", label: "标准" },
  { value: "fast", label: "快速" },
  { value: "balanced", label: "均衡" },
];

const researchPrompts = [
  "聚焦近两年的 benchmark 与 evaluation papers，归纳仍未覆盖的评测维度。",
  "比较 tool-use agent 和 code agent 在任务拆解、失败恢复、成本控制上的差异。",
  "从现有论文中提炼 3 个可落地的新研究选题，并说明动机和可行性。",
  "只保留高相关论文，按方法、场景、评价指标重新组织 taxonomy。",
];

const workspaceSections = [
  { label: "论文线索", value: demoWorkspace.papers.length },
  { label: "研究空白", value: demoWorkspace.gaps.length },
  { label: "选题建议", value: demoWorkspace.ideas.length },
  { label: "关系线索", value: demoWorkspace.graph_edges.length },
];

const outputPreviews = [
  {
    title: "论文线索",
    description: "整理和筛选主题相关论文，保留来源、年份、引用数和研究分类，方便快速判断阅读优先级。",
  },
  {
    title: "研究空白",
    description: "从论文集合中提炼尚未被充分覆盖的问题，并给出支撑证据，帮助你定位可继续深入的方向。",
  },
  {
    title: "选题建议",
    description: "基于已有论文和研究空白生成候选选题，补充动机、方法思路、可行性和预期贡献。",
  },
  {
    title: "研究过程",
    description: "保留本次研究使用过的上下文、检索动作和分析路径，方便后续回看、复用和继续追问。",
  },
];

export function HomePage() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("AI Agent 工具使用评测");
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
      setStatus("会话已创建，可以进入对话继续追问。");
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
      setStatus("研究任务已创建，可以打开工作台运行或查看结果。");
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
                {conversation ? "已准备" : "草稿"}
              </StatusPill>
            }
            title="新建研究"
            eyebrow="新建研究"
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
          <SectionHeader title="当前研究" eyebrow="研究流程" />
          <div className="workflow-steps">
            <div className="workflow-step">
              <div className="step-index">1</div>
              <div>
                <div className="item-heading">
                  <strong>研究会话</strong>
                  <StatusPill tone={conversation ? "success" : "neutral"} compact>
                    {conversation ? "已创建" : "待开始"}
                  </StatusPill>
                </div>
                {conversation ? (
                  <>
                    <div className="fine-print">{conversation.title}</div>
                    <div className="fine-print">{conversation.topic}</div>
                  </>
                ) : (
                  <div className="fine-print">创建会话后，系统会保存本次研究上下文。</div>
                )}
              </div>
            </div>
            <div className="workflow-step">
              <div className="step-index">2</div>
              <div>
                <div className="item-heading">
                  <strong>多轮追问</strong>
                  <StatusPill tone={conversation ? "info" : "neutral"} compact>
                    {conversation ? "可继续" : "等待会话"}
                  </StatusPill>
                </div>
                <div className="fine-print">围绕当前主题继续收窄问题，生成更具体的研究任务。</div>
              </div>
            </div>
            <div className="workflow-step">
              <div className="step-index">3</div>
              <div>
                <div className="item-heading">
                  <strong>研究工作台</strong>
                  <StatusPill tone={taskId ? "success" : "neutral"} compact>
                    {taskId ? "可打开" : "等待任务"}
                  </StatusPill>
                </div>
                {taskId ? (
                  <>
                    <div className="button-row" style={{ marginTop: 8 }}>
                      <Link className="secondary-button" to={`/workspace?task_id=${encodeURIComponent(taskId)}`}>
                        打开工作台
                      </Link>
                    </div>
                  </>
                ) : (
                  <div className="fine-print">工作台会集中展示论文、分类、研究空白和选题建议。</div>
                )}
              </div>
            </div>
          </div>

          <SectionHeader title="快速预览" eyebrow="示例研究" />
          <div className="content-pad button-row">
            <Link className="primary-button" to={`/conversation?conversation_id=${encodeURIComponent(DEMO_CONVERSATION_ID)}`}>
              预览对话
            </Link>
            <Link className="secondary-button" to={`/workspace?task_id=${encodeURIComponent(DEMO_WORKSPACE_TASK_ID)}`}>
              预览工作台
            </Link>
            <Link className="ghost-button" to="/settings">
              工具配置
            </Link>
          </div>
        </div>
      </section>

      <section className="metrics-strip">
        {workspaceSections.map((item) => (
          <div className="metric-cell" key={item.label}>
            <div className="metric-label">{item.label}</div>
            <div className="metric-value">{item.value}</div>
          </div>
        ))}
      </section>

      <section className="launch-ops-grid">
        <div className="pane">
          <SectionHeader title="研究方向建议" eyebrow="可直接套用" />
          <ul className="compact-list">
            {researchPrompts.map((prompt, index) => (
              <li className="compact-item prompt-item" key={prompt}>
                <button
                  className="ghost-button prompt-button"
                  onClick={() => {
                    setTopic("AI Agent 工具使用评测");
                    setTitle(`Agent 调研方向 ${index + 1}`);
                    setStatus("已填入一个推荐追问方向，可继续创建会话。");
                  }}
                  type="button"
                >
                  使用
                </button>
                <div>
                  <div className="table-title">方向 {index + 1}</div>
                  <div className="fine-print">{prompt}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="pane">
          <SectionHeader title="工作台预览" eyebrow={demoWorkspace.topic} />
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>论文</th>
                  <th>分类</th>
                  <th>引用</th>
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

      <section className="pane">
        <SectionHeader title="研究完成后你会得到什么" eyebrow="输出内容" />
        <div className="output-preview-grid">
          {outputPreviews.map((item, index) => (
            <article className="output-preview-item" key={item.title}>
              <div className="step-index">{index + 1}</div>
              <div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
