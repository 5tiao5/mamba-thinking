import type {
  ContinueConversationPayload,
  ConversationDetailItem,
  ConversationResponsePayload,
  ConversationSummaryItem,
  MessageItem,
  ResearchTaskDetailItem,
  ResearchTaskSummaryItem,
  SkillItem,
  ToolItem,
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

type ApiFailurePayload = {
  success: false;
  error?: {
    code?: string;
    message?: string;
  };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const payload = (await response.json()) as T | ApiFailurePayload;
  if (
    payload &&
    typeof payload === "object" &&
    "success" in payload &&
    payload.success === false
  ) {
    throw new Error(payload.error?.message ?? payload.error?.code ?? "Request failed");
  }

  return payload as T;
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  createConversation: (payload: { topic: string; title?: string }) =>
    request<{ success: boolean; data: ConversationResponsePayload }>("/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listConversations: (params?: { limit?: number }) => {
    const query = params?.limit ? `?limit=${params.limit}` : "";
    return request<{ success: boolean; data: { items: ConversationSummaryItem[] } }>(`/conversations${query}`);
  },
  getConversation: (conversationId: string) =>
    request<{ success: boolean; data: ConversationDetailItem }>(`/conversations/${conversationId}`),
  listMessages: (conversationId: string) => {
    if (conversationId === DEMO_CONVERSATION_ID) {
      return Promise.resolve({
        success: true,
        data: { conversation_id: conversationId, items: demoMessages },
      });
    }
    return request<{ success: boolean; data: { conversation_id: string; items: MessageItem[] } }>(
      `/conversations/${conversationId}/messages`
    );
  },
  createMessage: (conversationId: string, payload: { role?: string; content: string; metadata?: Record<string, unknown> }) =>
    request<{ success: boolean; data: MessageItem }>(`/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  continueConversation: (payload: {
    conversation_id: string;
    content: string;
    focus?: string;
    create_follow_up_task?: boolean;
    mode?: string;
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
    return request<{ success: boolean; data: ContinueConversationPayload }>("/conversations/continue", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  createTask: (payload: {
    conversation_id: string;
    topic: string;
    mode?: string;
    use_shared_knowledge?: boolean;
    enabled_tools?: string[];
  }) =>
    request<{ success: boolean; data: { task_id: string; conversation_id: string; status: string } }>(
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
    return request<{ success: boolean; data: { items: ResearchTaskSummaryItem[] } }>(
      `/research/tasks${query ? `?${query}` : ""}`
    );
  },
  getTask: (taskId: string) =>
    request<{ success: boolean; data: ResearchTaskDetailItem }>(`/research/tasks/${taskId}`),
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
    return request<{ success: boolean; data: { task_id: string; topic: string; alignment_score: number } }>(
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
    return request<{ success: boolean; data: WorkspaceSnapshot }>(`/research/tasks/${taskId}/workspace`);
  },
  listTools: async () => {
    try {
      return await request<{ success: boolean; data: ToolItem[] }>("/tools");
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
    return request<{ success: boolean; data: ToolItem }>(`/tools/${toolId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  listSkills: async () => {
    try {
      return await request<{ success: boolean; data: SkillItem[] }>("/skills");
    } catch {
      return { success: true, data: demoSkills };
    }
  },
};
