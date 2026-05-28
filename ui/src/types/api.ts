export type ConversationResponsePayload = {
  conversation_id: string;
  topic: string;
  title: string;
};

export type ConversationSummaryItem = {
  conversation_id: string;
  topic: string;
  title: string;
  status: string;
  latest_task_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationDetailItem = ConversationSummaryItem & {
  message_count: number;
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

export type ResearchTaskSummaryItem = {
  task_id: string;
  conversation_id: string;
  topic: string;
  status: string;
  mode: string;
  trigger_message_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ResearchTaskDetailItem = ResearchTaskSummaryItem;

export type ContinueConversationPayload = {
  conversation_id: string;
  next_focus: string;
  message: string;
  message_id?: string | null;
  context_preview: string[];
  knowledge_context: string[];
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

export type EvidenceTier = "strong" | "moderate" | "weak" | "candidate";

export type WorkspaceTaxonomyBranch = {
  branch_id: string;
  name: string;
  description: string;
  required_concepts: string[];
  paper_count: number;
  evidence_tier: EvidenceTier;
  coverage_score?: number;
  branch_confidence: number;
  matched_paper_ids?: string[];
  matched_gap_ids?: string[];
};

export type WorkspaceTaxonomyTreeNode = {
  branch_id: string;
  name: string;
  evidence_tier?: EvidenceTier;
  children: WorkspaceTaxonomyTreeNode[];
};

export type WorkspaceTaxonomyCoverage = Record<
  string,
  {
    paper_count: number;
    gap_count: number;
    coverage_score: number;
    evidence_tier: EvidenceTier;
    matched_paper_ids?: string[];
    matched_gap_ids?: string[];
  }
>;

export type WorkspaceTaxonomy = {
  branches: WorkspaceTaxonomyBranch[];
  tree: WorkspaceTaxonomyTreeNode[];
  coverage: WorkspaceTaxonomyCoverage;
  raw: unknown;
};

export type WorkspaceEvidenceStatus = {
  insufficient: boolean;
  total_papers: number;
  real_paper_count: number;
  fallback_paper_count: number;
  fallback_ratio: number;
  covered_branch_count: number;
  candidate_branches: string[];
  message: string;
};

export type WorkspaceSnapshot = {
  task_id: string;
  topic: string;
  summary: string;
  papers: WorkspacePaper[];
  taxonomy: WorkspaceTaxonomy;
  graph_edges: WorkspaceGraphEdge[];
  gaps: WorkspaceGap[];
  ideas: WorkspaceIdea[];
  alignment_score: number;
  evidence_status: WorkspaceEvidenceStatus;
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

export type DeleteConversationPayload = {
  conversation_id: string;
  deleted: boolean;
  deleted_messages: number;
  deleted_tasks: number;
  deleted_workspaces: number;
};

export type RunTaskPayload = {
  task_id: string;
  topic: string;
  alignment_score: number;
  trace_keys?: string[];
  assistant_message_id?: string | null;
};

export type KnowledgeDocumentItem = {
  document_id: string;
  title: string;
  source_task_id?: string | null;
  content: string;
  tags: string[];
  metadata: Record<string, unknown>;
};

export type CreateKnowledgeDocumentPayload = {
  title: string;
  content: string;
  tags?: string[];
  source_url?: string | null;
  source_task_id?: string | null;
  notes?: string | null;
};

export type KnowledgeSearchPayload = {
  items: KnowledgeDocumentItem[];
  query: string;
  total: number;
};
