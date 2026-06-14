import type {
  BatchPdfImportPayload,
  ContinueConversationPayload,
  ConversationDetailItem,
  CreateSkillPayload,
  CreateKnowledgeDocumentPayload,
  DeleteConversationPayload,
  KnowledgeScope,
  KnowledgeDocumentItem,
  KnowledgeSearchPayload,
  ConversationResponsePayload,
  ConversationSummaryItem,
  MessageItem,
  ResearchPaperItem,
  ResearchPaperStatus,
  ResearchMode,
  ResearchTaskDetailItem,
  ResearchTaskSummaryItem,
  RunTaskPayload,
  SkillItem,
  SearchPaperCandidatesPayload,
  ToolItem,
  UpdateSkillPayload,
  WorkspaceSnapshot,
} from "../types/api";
import {
  DEMO_CONVERSATION_ID,
  DEMO_FOLLOW_UP_TASK_ID,
  DEMO_WORKSPACE_TASK_ID,
  demoContinueResponse,
  demoMessages,
  demoSkills,
  demoTools,
  demoWorkspace,
} from "./demoData";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_BASE_URLS = [API_BASE_URL, "http://127.0.0.1:8001"].filter(
  (url, index, urls) => urls.indexOf(url) === index
);

type ApiFailurePayload = {
  success: false;
  error?: {
    code?: string;
    message?: string;
  };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let lastError: unknown = null;

  for (const baseUrl of API_BASE_URLS) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        headers: {
          "Content-Type": "application/json",
          ...(init?.headers ?? {}),
        },
        ...init,
      });

      if (!response.ok) {
        lastError =
          response.status === 405
            ? new Error("当前后端未启用这个接口，请重启后端或确认已拉取最新后端代码。")
            : new Error(`HTTP ${response.status}`);
        if (response.status === 404 || response.status === 405 || response.status >= 500) {
          continue;
        }
        throw lastError;
      }

      const payload = (await response.json()) as T | ApiFailurePayload;
      if (
        payload &&
        typeof payload === "object" &&
        "success" in payload &&
        payload.success === false
      ) {
        const error = new Error(payload.error?.message ?? payload.error?.code ?? "Request failed");
        if (payload.error?.code === "not_found") {
          lastError = error;
          continue;
        }
        throw error;
      }

      return payload as T;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Request failed");
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

type ApiResponse<T> = { success: boolean; data: T };

export const api = {
  health: () => request<{ status: string }>("/health"),
  createConversation: (payload: { topic: string; title?: string }) =>
    request<ApiResponse<ConversationResponsePayload>>("/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listConversations: (params?: { limit?: number }) => {
    const query = params?.limit ? `?limit=${params.limit}` : "";
    return request<ApiResponse<{ items: ConversationSummaryItem[] }>>(`/conversations${query}`);
  },
  getConversation: (conversationId: string) =>
    request<ApiResponse<ConversationDetailItem>>(`/conversations/${conversationId}`),
  deleteConversation: (conversationId: string) =>
    request<ApiResponse<DeleteConversationPayload>>(`/conversations/${conversationId}`, {
      method: "DELETE",
    }),
  getConversationWorkspace: (conversationId: string) =>
    request<ApiResponse<WorkspaceSnapshot>>(`/conversations/${conversationId}/workspace`),
  listMessages: (conversationId: string) => {
    if (conversationId === DEMO_CONVERSATION_ID) {
      return Promise.resolve({
        success: true,
        data: { conversation_id: conversationId, items: demoMessages },
      });
    }
    return request<ApiResponse<{ conversation_id: string; items: MessageItem[] }>>(
      `/conversations/${conversationId}/messages`
    );
  },
  createMessage: (conversationId: string, payload: { role?: string; content: string; metadata?: Record<string, unknown> }) =>
    request<ApiResponse<MessageItem>>(`/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  continueConversation: (payload: {
    conversation_id: string;
    content: string;
    focus?: string;
    create_follow_up_task?: boolean;
    mode?: string;
    knowledge_scope?: KnowledgeScope;
    research_mode?: ResearchMode;
    selected_skill_ids?: string[];
  }) => {
    if (payload.conversation_id === DEMO_CONVERSATION_ID) {
      return Promise.resolve({
        success: true,
        data: {
          ...demoContinueResponse,
          message: payload.content,
          next_focus: payload.focus || demoContinueResponse.next_focus,
          follow_up_task: payload.create_follow_up_task === false ? null : demoContinueResponse.follow_up_task,
        },
      });
    }
    return request<ApiResponse<ContinueConversationPayload>>("/conversations/continue", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  createTask: (payload: {
    conversation_id: string;
    topic: string;
    mode?: string;
    use_shared_knowledge?: boolean;
    knowledge_scope?: KnowledgeScope;
    research_mode?: ResearchMode;
    enabled_tools?: string[];
    selected_skill_ids?: string[];
  }) =>
    request<ApiResponse<{ task_id: string; conversation_id: string; status: string; knowledge_scope?: KnowledgeScope; research_mode?: ResearchMode }>>(
      "/research/tasks",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  listTasks: (params?: { conversation_id?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.conversation_id) {
      search.set("conversation_id", params.conversation_id);
    }
    if (params?.limit) {
      search.set("limit", String(params.limit));
    }
    const query = search.toString();
    return request<ApiResponse<{ items: ResearchTaskSummaryItem[] }>>(
      `/research/tasks${query ? `?${query}` : ""}`
    );
  },
  getTask: (taskId: string) =>
    request<ApiResponse<ResearchTaskDetailItem>>(`/research/tasks/${taskId}`),
  runTask: (taskId: string) => {
    if (taskId === DEMO_FOLLOW_UP_TASK_ID || taskId === DEMO_WORKSPACE_TASK_ID) {
      return Promise.resolve({
        success: true,
        data: {
          task_id: taskId,
          topic: demoWorkspace.topic,
          alignment_score: demoWorkspace.alignment_score,
        },
      });
    }
    return request<ApiResponse<RunTaskPayload>>(
      `/research/tasks/${taskId}/run`,
      {
        method: "POST",
      }
    );
  },
  getWorkspace: (taskId: string) => {
    if (taskId === DEMO_FOLLOW_UP_TASK_ID || taskId === DEMO_WORKSPACE_TASK_ID) {
      return Promise.resolve({
        success: true,
        data: { ...demoWorkspace, task_id: taskId },
      });
    }
    return request<ApiResponse<WorkspaceSnapshot>>(`/research/tasks/${taskId}/workspace`);
  },
  listTools: async () => {
    try {
      return await request<ApiResponse<ToolItem[]>>("/tools");
    } catch {
      return { success: true, data: demoTools };
    }
  },
  updateTool: (toolId: string, payload: { enabled: boolean; config: Record<string, unknown> }) => {
    const demoTool = demoTools.find((tool) => tool.tool_id === toolId);
    if (demoTool) {
      return Promise.resolve({
        success: true,
        data: { ...demoTool, enabled: payload.enabled, config: payload.config },
      });
    }
    return request<ApiResponse<ToolItem>>(`/tools/${toolId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  listSkills: async () => {
    try {
      return await request<ApiResponse<SkillItem[]>>("/skills");
    } catch {
      return { success: true, data: demoSkills };
    }
  },
  createSkill: (payload: CreateSkillPayload) =>
    request<ApiResponse<SkillItem>>("/skills", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSkill: (skillId: string, payload: UpdateSkillPayload) =>
    request<ApiResponse<SkillItem>>(`/skills/${skillId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteSkill: (skillId: string) =>
    request<ApiResponse<{ skill_id: string; deleted: boolean }>>(`/skills/${skillId}`, {
      method: "DELETE",
    }),
  listKnowledgeDocuments: () =>
    request<ApiResponse<{ items: KnowledgeDocumentItem[] }>>("/knowledge/documents"),
  createKnowledgeDocument: (payload: CreateKnowledgeDocumentPayload) =>
    request<ApiResponse<KnowledgeDocumentItem>>("/knowledge/documents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  searchPaperCandidates: (payload: { query: string; limit?: number }) =>
    request<ApiResponse<SearchPaperCandidatesPayload>>("/knowledge/paper-candidates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importPaperCandidate: (payload: {
    candidate_id: string;
    conversation_id?: string;
    notes?: string;
    tags?: string[];
  }) =>
    request<ApiResponse<KnowledgeDocumentItem>>("/knowledge/paper-candidates/import", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listResearchPapers: (conversationId: string, status?: ResearchPaperStatus) => {
    const search = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<ApiResponse<{ items: ResearchPaperItem[]; total: number }>>(
      `/conversations/${conversationId}/papers${search}`
    );
  },
  updateResearchPaper: (
    conversationId: string,
    paperEntryId: string,
    status: ResearchPaperStatus
  ) =>
    request<ApiResponse<ResearchPaperItem>>(
      `/conversations/${conversationId}/papers/${paperEntryId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }
    ),
  importResearchPdfs: (
    conversationId: string,
    files: File[],
    status: ResearchPaperStatus = "candidate"
  ) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return request<ApiResponse<BatchPdfImportPayload>>(
      `/conversations/${conversationId}/papers/import-pdfs?status=${encodeURIComponent(status)}`,
      {
        method: "POST",
        headers: {},
        body: formData,
      }
    );
  },
  deleteKnowledgeDocument: (documentId: string) =>
    request<ApiResponse<{ document_id: string; deleted: boolean }>>(`/knowledge/documents/${documentId}`, {
      method: "DELETE",
    }),
  searchKnowledge: (params?: { q?: string; by?: "keyword" | "tags"; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.q) {
      search.set("q", params.q);
    }
    if (params?.by) {
      search.set("by", params.by);
    }
    if (params?.limit) {
      search.set("limit", String(params.limit));
    }
    const query = search.toString();
    return request<ApiResponse<KnowledgeSearchPayload>>(`/knowledge/search${query ? `?${query}` : ""}`);
  },
};
