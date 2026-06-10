export type ConversationResponsePayload = {
  conversation_id: string;
  topic: string;
  title: string;
};

export type KnowledgeScope = "none" | "conversation_only" | "shared";

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
  metadata: Record<string, unknown> & {
    kind?: string;
    task_id?: string;
    task_status?: string;
    topic?: string;
    knowledge_scope?: KnowledgeScope;
    source_trace?: WorkspaceSourceTrace | null;
    inherited_context?: WorkspaceInheritedContext | null;
  };
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
  knowledge_scope?: KnowledgeScope;
  selected_skill_ids?: string[];
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
  knowledge_scope_applied?: KnowledgeScope;
  knowledge_context: string[];
  knowledge_hits?: WorkspaceKnowledgeHit[];
  workspace_context?: string[];
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
  is_new_this_round: boolean;
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

export type WorkspaceKnowledgeHit = {
  title: string;
  snippet: string;
  scope: string;
  source_type: string;
  source_task_id?: string | null;
  score: number;
  evidence_level: string;
  matched_chunk_count: number;
  supporting_snippets: string[];
};

export type WorkspaceSourceTrace = {
  knowledge_scope: KnowledgeScope;
  retrieval_plan: string;
  retrieval_status: string;
  retrieval_message: string;
  filtered_out_count: number;
  fallback_used: boolean;
  refresh_triggered: boolean;
  novel_paper_count: number;
  reused_paper_count: number;
  knowledge_hit_count: number;
  knowledge_hits: WorkspaceKnowledgeHit[];
  workspace_hint_count: number;
  workspace_hints: string[];
  recent_turn_count: number;
  recent_user_turns: string[];
};

export type WorkspaceInheritedContext = {
  conversation_topic: string;
  workspace_summary: string;
  workspace_hints: string[];
  recent_turns: string[];
};

export type WorkspaceWorkingMemory = {
  current_focus: string;
  summary: string;
  stable_findings: string[];
  open_questions: string[];
  active_constraints: string[];
  supporting_task_ids: string[];
  source_task_id?: string | null;
  updated_at: string;
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
  source_trace?: WorkspaceSourceTrace | null;
  inherited_context?: WorkspaceInheritedContext | null;
  working_memory?: WorkspaceWorkingMemory | null;
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
  created_at?: string | null;
  updated_at?: string | null;
};

export type CreateSkillPayload = {
  skill_id: string;
  display_name: string;
  description?: string;
  required_tools?: string[];
  enabled?: boolean;
};

export type UpdateSkillPayload = {
  display_name?: string;
  description?: string;
  required_tools?: string[];
  enabled?: boolean;
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
  source_trace?: WorkspaceSourceTrace | null;
  inherited_context?: WorkspaceInheritedContext | null;
};

export type KnowledgeDocumentItem = {
  document_id: string;
  title: string;
  source_task_id?: string | null;
  conversation_id?: string | null;
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
  conversation_id?: string | null;
  notes?: string | null;
};

export type KnowledgeSearchPayload = {
  items: KnowledgeDocumentItem[];
  query: string;
  total: number;
};

export type PaperImportCandidateItem = {
  candidate_id: string;
  title: string;
  authors: string[];
  year?: number | null;
  abstract: string;
  source_url?: string | null;
  pdf_url?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  source: string;
  venue?: string | null;
  is_exact_match: boolean;
};

export type SearchPaperCandidatesPayload = {
  items: PaperImportCandidateItem[];
};
