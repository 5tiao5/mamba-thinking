export type ConversationResponsePayload = {
  conversation_id: string;
  topic: string;
  title: string;
};

export type MessageItem = {
  message_id: string;
  conversation_id: string;
  role: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type FollowUpTaskItem = {
  task_id: string;
  topic: string;
  status: string;
  trigger_message_id?: string | null;
};

export type ContinueConversationPayload = {
  conversation_id: string;
  next_focus: string;
  message: string;
  message_id?: string | null;
  context_preview: string[];
  follow_up_task?: FollowUpTaskItem | null;
};

export type WorkspacePaper = {
  paper_id: string;
  title: string;
  publish_date: string;
  source: string;
  taxonomy_category: string;
  citation_count: number;
  url: string;
};

export type WorkspaceGraphEdge = {
  source: string;
  target: string;
  relationship: string;
  reasoning: string;
};

export type WorkspaceGap = {
  summary: string;
  severity: string;
  evidence: string[];
};

export type WorkspaceIdea = {
  title: string;
  motivation: string;
  approach: string;
  feasibility: string;
  contribution: string;
  raw_text: string;
};

export type WorkspaceSnapshot = {
  task_id: string;
  topic: string;
  summary: string;
  papers: WorkspacePaper[];
  taxonomy: Record<string, unknown>;
  graph_edges: WorkspaceGraphEdge[];
  gaps: WorkspaceGap[];
  ideas: WorkspaceIdea[];
  alignment_score: number;
  trace: {
    thought_trace: Array<Record<string, unknown>>;
    action_history: Array<Record<string, unknown>>;
    context_inputs: Array<Record<string, unknown>>;
  } | null;
};

export type ToolItem = {
  tool_id: string;
  display_name: string;
  description: string;
  enabled: boolean;
  config: Record<string, unknown>;
};

export type SkillItem = {
  skill_id: string;
  display_name: string;
  description: string;
  enabled: boolean;
  required_tools: string[];
};
