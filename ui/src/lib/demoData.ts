import type {
  ContinueConversationPayload,
  MessageItem,
  SkillItem,
  ToolItem,
  WorkspaceSnapshot,
} from "../types/api";

export const DEMO_CONVERSATION_ID = "demo-conversation";
export const DEMO_FOLLOW_UP_TASK_ID = "demo-followup-task";
export const DEMO_WORKSPACE_TASK_ID = "demo-task";

export const demoMessages: MessageItem[] = [
  {
    message_id: "demo-msg-001",
    conversation_id: DEMO_CONVERSATION_ID,
    role: "user",
    content: "我想调研 AI Agent Tool Use 方向，重点关注工具调用评测和代码智能体。",
    metadata: { focus: "tool use evaluation" },
    created_at: "2026-05-17T09:00:00.000Z",
  },
  {
    message_id: "demo-msg-002",
    conversation_id: DEMO_CONVERSATION_ID,
    role: "assistant",
    content: "已建立初始研究范围：工具调用基准、长程任务规划、代码执行反馈、失败恢复策略。",
    metadata: { source: "demo" },
    created_at: "2026-05-17T09:00:18.000Z",
  },
  {
    message_id: "demo-msg-003",
    conversation_id: DEMO_CONVERSATION_ID,
    role: "user",
    content: "请进一步聚焦 benchmark 和 evaluation papers，找出还没被充分覆盖的研究空白。",
    metadata: { focus: "benchmark evaluation" },
    created_at: "2026-05-17T09:02:30.000Z",
  },
];

export const demoContinueResponse: ContinueConversationPayload = {
  conversation_id: DEMO_CONVERSATION_ID,
  next_focus: "benchmark evaluation",
  message: "请进一步聚焦 benchmark 和 evaluation papers，找出还没被充分覆盖的研究空白。",
  message_id: "demo-msg-004",
  context_preview: [
    "user: 我想调研 AI Agent Tool Use 方向，重点关注工具调用评测和代码智能体。",
    "assistant: 已建立初始研究范围：工具调用基准、长程任务规划、代码执行反馈、失败恢复策略。",
    "user: 请进一步聚焦 benchmark 和 evaluation papers，找出还没被充分覆盖的研究空白。",
  ],
  knowledge_context: [
    "[Knowledge] 既有调研摘要：工具调用评测需要同时关注成功率、恢复能力、成本和延迟。",
  ],
  follow_up_task: {
    task_id: DEMO_FOLLOW_UP_TASK_ID,
    topic: "AI Agent Tool Use: benchmark evaluation gaps",
    status: "created",
    trigger_message_id: "demo-msg-004",
  },
};

export const demoWorkspace: WorkspaceSnapshot = {
  task_id: DEMO_WORKSPACE_TASK_ID,
  topic: "AI Agent Tool Use: benchmark evaluation gaps",
  summary:
    "本次演示工作台聚焦 AI Agent 工具调用评测。模拟结果显示：当前研究已经覆盖静态工具选择、API 调用成功率和代码生成准确性，但对长程任务中的错误恢复、跨工具依赖、成本约束和人机协同评估仍然不足。",
  papers: [
    {
      paper_id: "paper-toolbench",
      title: "ToolBench: Towards Tool-Augmented Language Models",
      publish_date: "2023",
      source: "arXiv",
      taxonomy_category: "tool-use benchmark",
      citation_count: 820,
      url: "https://arxiv.org/abs/2307.16789",
    },
    {
      paper_id: "paper-swebench",
      title: "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
      publish_date: "2023",
      source: "arXiv",
      taxonomy_category: "code agent evaluation",
      citation_count: 1040,
      url: "https://arxiv.org/abs/2310.06770",
    },
    {
      paper_id: "paper-agentbench",
      title: "AgentBench: Evaluating LLMs as Agents",
      publish_date: "2023",
      source: "arXiv",
      taxonomy_category: "general agent benchmark",
      citation_count: 760,
      url: "https://arxiv.org/abs/2308.03688",
    },
    {
      paper_id: "paper-webarena",
      title: "WebArena: A Realistic Web Environment for Building Autonomous Agents",
      publish_date: "2023",
      source: "arXiv",
      taxonomy_category: "web task environment",
      citation_count: 690,
      url: "https://arxiv.org/abs/2307.13854",
    },
  ],
  taxonomy: {
    branches: [
      {
        branch_id: "tool-use-benchmark",
        name: "Tool-Use Benchmark",
        description: "围绕 API 调用、参数生成和执行反馈的评测设计。",
        required_concepts: ["API selection", "argument generation", "execution feedback"],
        paper_count: 1,
        evidence_tier: "strong",
        branch_confidence: 0.92,
      },
      {
        branch_id: "code-agent-evaluation",
        name: "Code Agent Evaluation",
        description: "围绕 issue reproduction、patch generation 和 test feedback 的评测。",
        required_concepts: ["issue reproduction", "patch generation", "test feedback"],
        paper_count: 1,
        evidence_tier: "strong",
        branch_confidence: 0.88,
      },
      {
        branch_id: "general-agent-benchmark",
        name: "General Agent Benchmark",
        description: "覆盖 planning、memory 与 environment interaction 的通用 benchmark。",
        required_concepts: ["planning", "memory", "environment interaction"],
        paper_count: 2,
        evidence_tier: "moderate",
        branch_confidence: 0.81,
      },
      {
        branch_id: "missing-dimensions",
        name: "Missing Dimensions",
        description: "当前 benchmark 中仍然覆盖不足的关键维度。",
        required_concepts: ["recovery", "cost awareness", "multi-tool dependency", "human handoff"],
        paper_count: 0,
        evidence_tier: "candidate",
        branch_confidence: 0.64,
      },
    ],
    tree: [
      {
        branch_id: "evaluation",
        name: "Evaluation",
        children: [
          { branch_id: "tool-use-benchmark", name: "Tool-Use Benchmark", children: [] },
          { branch_id: "code-agent-evaluation", name: "Code Agent Evaluation", children: [] },
          { branch_id: "general-agent-benchmark", name: "General Agent Benchmark", children: [] },
          { branch_id: "missing-dimensions", name: "Missing Dimensions", children: [] },
        ],
      },
    ],
    coverage: {
      "tool-use-benchmark": { paper_count: 1, gap_count: 0, coverage_score: 1, evidence_tier: "strong" },
      "code-agent-evaluation": { paper_count: 1, gap_count: 0, coverage_score: 1, evidence_tier: "strong" },
      "general-agent-benchmark": { paper_count: 2, gap_count: 1, coverage_score: 1, evidence_tier: "moderate" },
      "missing-dimensions": { paper_count: 0, gap_count: 3, coverage_score: 0, evidence_tier: "candidate" },
    },
    raw: {
      "tool-use benchmark": ["API selection", "argument generation", "execution feedback"],
      "code agent evaluation": ["issue reproduction", "patch generation", "test feedback"],
      "general agent benchmark": ["planning", "memory", "environment interaction"],
      "missing dimensions": ["recovery", "cost awareness", "multi-tool dependency", "human handoff"],
    },
  },
  graph_edges: [
    {
      source: "ToolBench",
      target: "AgentBench",
      relationship: "complements",
      reasoning: "ToolBench 偏工具调用 API，AgentBench 覆盖更广泛的 agent 任务场景。",
    },
    {
      source: "SWE-bench",
      target: "WebArena",
      relationship: "contrasts",
      reasoning: "SWE-bench 偏代码仓库修复，WebArena 偏浏览器和网页环境操作。",
    },
    {
      source: "tool-use benchmark",
      target: "missing dimensions",
      relationship: "reveals_gap",
      reasoning: "多数基准强调最终成功率，较少拆解失败恢复和工具链成本。",
    },
  ],
  gaps: [
    {
      summary: "缺少对工具调用失败后的恢复能力评估",
      severity: "high",
      evidence: ["多数 benchmark 只统计最终成功率", "错误分类与恢复路径没有稳定指标"],
    },
    {
      summary: "跨工具依赖和中间状态污染尚未被系统度量",
      severity: "medium",
      evidence: ["多步任务中工具输出会影响后续决策", "现有任务常把工具调用看作独立动作"],
    },
    {
      summary: "成本、延迟和 token 预算没有进入主评价指标",
      severity: "medium",
      evidence: ["同样成功率下不同 agent 的调用成本差异很大"],
    },
  ],
  ideas: [
    {
      title: "RecoveryBench: 面向工具失败恢复的 Agent 评测集",
      motivation: "真实工具调用经常失败，现有 benchmark 不足以评估 agent 是否能诊断并恢复。",
      approach: "构造 API 超时、参数缺失、权限失败、返回污染等场景，记录恢复路径和最终任务成功率。",
      feasibility: "可基于现有 ToolBench 任务扩展错误注入层。",
      contribution: "把工具失败恢复从隐性现象变成可比较指标。",
      raw_text: "",
    },
    {
      title: "Cost-Aware Tool Use Agent",
      motivation: "生产环境中工具调用成本和延迟会影响可用性。",
      approach: "在规划阶段加入预算约束，比较不同调用策略的成功率、成本和延迟。",
      feasibility: "可用现有工具调用日志模拟成本曲线。",
      contribution: "补足 agent benchmark 中成本敏感评估维度。",
      raw_text: "",
    },
  ],
  alignment_score: 0.82,
  evidence_status: {
    insufficient: false,
    total_papers: 4,
    real_paper_count: 4,
    fallback_paper_count: 0,
    fallback_ratio: 0,
    covered_branch_count: 3,
    candidate_branches: [
      "Tool-Use Benchmark",
      "Code Agent Evaluation",
      "General Agent Benchmark",
    ],
    message: "当前证据量足够支撑一版可解释的 taxonomy 草图。",
  },
  trace: {
    thought_trace: [
      { step: "scope", detail: "识别 AI Agent Tool Use 与 evaluation benchmark 的交集。" },
      { step: "cluster", detail: "按 tool-use、code agent、web environment 三类组织论文。" },
      { step: "audit", detail: "对比评测指标，定位恢复、成本和跨工具依赖缺口。" },
    ],
    action_history: [
      { action: "search", query: "AI agent tool use benchmark evaluation" },
      { action: "rank", rule: "citation_count + task relevance" },
      { action: "synthesize", target: "gaps and ideas" },
    ],
    context_inputs: [
      { role: "user", content: "重点关注 benchmark and evaluation papers" },
      { role: "system", content: "使用 demo 数据模拟工作台完整输出" },
    ],
  },
};

export const demoTools: ToolItem[] = [
  {
    tool_id: "semantic_scholar",
    display_name: "Semantic Scholar",
    description: "检索论文元数据、引用数和相关工作。",
    enabled: true,
    config: { max_results: 8, timeout_seconds: 20 },
  },
  {
    tool_id: "arxiv",
    display_name: "arXiv Search",
    description: "按主题检索 arXiv 论文。",
    enabled: true,
    config: { category_hint: "cs.AI" },
  },
];

export const demoSkills: SkillItem[] = [
  {
    skill_id: "paper_clustering",
    display_name: "论文聚类",
    description: "按研究问题、方法和评测对象组织论文集合。",
    enabled: true,
    required_tools: ["semantic_scholar", "arxiv"],
  },
  {
    skill_id: "gap_audit",
    display_name: "研究空白审计",
    description: "从 taxonomy 和 graph 中抽取潜在研究空白。",
    enabled: true,
    required_tools: ["semantic_scholar"],
  },
];
