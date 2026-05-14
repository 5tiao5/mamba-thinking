import type {
  ContinueConversationPayload,
  ConversationResponsePayload,
  MessageItem,
  SkillItem,
  ToolItem,
  WorkspaceSnapshot,
} from "../types/api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  createConversation: (payload: { topic: string; title?: string }) =>
    request<{ success: boolean; data: ConversationResponsePayload }>("/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listMessages: (conversationId: string) =>
    request<{ success: boolean; data: { conversation_id: string; items: MessageItem[] } }>(
      `/conversations/${conversationId}/messages`
    ),
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
  }) =>
    request<{ success: boolean; data: ContinueConversationPayload }>("/conversations/continue", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
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
  runTask: (taskId: string) =>
    request<{ success: boolean; data: { task_id: string; topic: string; alignment_score: number } }>(
      `/research/tasks/${taskId}/run`,
      {
        method: "POST",
      }
    ),
  getWorkspace: (taskId: string) =>
    request<{ success: boolean; data: WorkspaceSnapshot }>(`/research/tasks/${taskId}/workspace`),
  listTools: () => request<{ success: boolean; data: ToolItem[] }>("/tools"),
  listSkills: () => request<{ success: boolean; data: SkillItem[] }>("/skills"),
};
