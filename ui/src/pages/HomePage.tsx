import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { CollapsibleSection } from "../components/ui/CollapsibleSection";
import { SectionHeader } from "../components/ui/SectionHeader";
import { SegmentedControl } from "../components/ui/SegmentedControl";
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

const workspaceSections = [
  { label: "论文线索", value: demoWorkspace.papers.length },
  { label: "研究空白", value: demoWorkspace.gaps.length },
  { label: "选题建议", value: demoWorkspace.ideas.length },
  { label: "关系线索", value: demoWorkspace.graph_edges.length },
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
      setStatus("研究任务已创建，可以查看本研究总览，也可以打开本次结果继续分析。");
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
    <div className="simple-page">
      <section className="simple-hero">
        <div>
          <div className="section-eyebrow">Start</div>
          <h1>创建一个研究任务</h1>
          <p>输入主题，系统会把它推进到对话、任务和工作台结果。</p>
        </div>
        <div className="button-row">
          <Link className="secondary-button" to={`/conversation?conversation_id=${encodeURIComponent(DEMO_CONVERSATION_ID)}`}>
            预览对话
          </Link>
          <Link
            className="secondary-button"
            to={`/workspace?conversation_id=${encodeURIComponent(DEMO_CONVERSATION_ID)}&task_id=${encodeURIComponent(DEMO_WORKSPACE_TASK_ID)}&view=conversation`}
          >
            预览研究总览
          </Link>
        </div>
      </section>

      <section className="launch-grid">
        <div className="pane">
          <SectionHeader
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
          <CollapsibleSection title="下一步" eyebrow="Workflow">
            <div className="simple-steps">
              <div className={conversation ? "simple-step simple-step-done" : "simple-step"}>
                <span>1</span>
                <div>
                  <strong>创建会话</strong>
                  <p>{conversation ? `${conversation.title} / ${conversation.topic}` : "保存研究主题与上下文。"}</p>
                </div>
              </div>
              <div className={conversation ? "simple-step simple-step-done" : "simple-step"}>
                <span>2</span>
                <div>
                  <strong>继续追问</strong>
                  <p>进入对话页，收窄问题并生成 follow-up task。</p>
                </div>
              </div>
              <div className={taskId ? "simple-step simple-step-done" : "simple-step"}>
                <span>3</span>
                <div>
                  <strong>查看研究结果</strong>
                  <p>总览看整个研究主题，本次结果看这一轮的具体增量。</p>
                  {taskId && conversation ? (
                    <div className="button-row">
                      <Link
                        className="ghost-button"
                        to={`/workspace?conversation_id=${encodeURIComponent(conversation.conversation_id)}&task_id=${encodeURIComponent(taskId)}&view=conversation`}
                      >
                        打开本研究总览
                      </Link>
                      <Link
                        className="ghost-button"
                        to={`/workspace?conversation_id=${encodeURIComponent(conversation.conversation_id)}&task_id=${encodeURIComponent(taskId)}&view=task`}
                      >
                        查看本次结果
                      </Link>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </CollapsibleSection>
        </div>
      </section>

      <section className="simple-metrics">
        {workspaceSections.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
          ))}
      </section>
    </div>
  );
}
