import request from '@/utils/request';
import { toServerUrl } from '@/config/server';

export interface ChatRequest {
  message: string;
  session_id?: string;
  stream?: boolean;
  connection_id?: string;
  model_name?: string;
}

export interface ChatResponse {
  response: string;
  session_id: string;
}

export interface AgentSession {
  id: string;
  user_id: string;
  title: string | null;
  status: string;
  context_summary: string | null;
  summary_update_time: string | null;
  is_pinned: boolean;
  created_at: string;
}

export interface AgentMessage {
  id: number;
  session_id: string;
  role: string;
  content: string;
  content_type: string;
  content_ext: any | null;
  reasoning?: string | null;
  tool_calls?: any | null;
  token_count: number;
  created_at: string;
}

export interface ToolProgressEvent {
  type: 'tool_start' | 'tool_end';
  tool_call_id?: string;
  tool_name?: string;
  status?: 'success' | 'error';
}

export interface AgentArtifactRef {
  id: string;
  type: string;
  title: string;
  status: string;
  url: string;
  photo_ids?: string[];
  has_html?: boolean;
}

export interface AIArtifact extends Omit<AgentArtifactRef, 'type' | 'url'> {
  user_id: string;
  artifact_type: string;
  content_json: Record<string, any>;
  html_content: string | null;
  html_config: {
    style_name?: string;
    custom_style?: string;
    server_api_access?: boolean;
    runtime?: string;
  };
  source_photo_ids: string[];
  source_ticket_ids: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AgentActionPlan {
  id: string;
  user_id?: string;
  session_id?: string | null;
  plan_type: string;
  title: string;
  summary?: string | null;
  status: 'proposed' | 'executed' | 'undone' | 'rejected' | 'expired' | 'failed' | string;
  attempt_count?: number;
  error_message?: string | null;
  operations?: Record<string, any>;
  preview: {
    mode?: 'create' | 'update' | 'repair';
    album_name?: string;
    current_album_name?: string | null;
    photo_count?: number;
    cover_photo_id?: string;
    tags?: string[];
    sample_photos?: Array<{ photo_id: string; thumbnail_url: string; photo_time?: string | null }>;
    notice?: string;
    artifact_id?: string | null;
    artifact_title?: string | null;
    artifact_url?: string | null;
    repair_count?: number;
    candidate_count?: number;
    affected_album_count?: number;
    selected_repair_ids?: string[];
    repairs?: Array<{
      id: string;
      kind: 'album_count' | 'album_cover';
      album_id: string;
      album_name: string;
      before: number | string | null;
      after: number | string;
      label: string;
      reason?: string;
      thumbnail_url?: string;
    }>;
  };
  result?: { album_id?: string; album_url?: string; album_name?: string; added_photo_count?: number; tag_relation_count?: number; artifact_id?: string | null; artifact_url?: string | null; applied_repair_count?: number; affected_album_count?: number; affected_album_ids?: string[] } | null;
  created_at?: string;
  updated_at?: string;
  expires_at?: string | null;
  executed_at?: string | null;
  failed_at?: string | null;
  undone_at?: string | null;
}

export type AgentStreamEvent = ToolProgressEvent | { type: 'artifact'; artifact: AgentArtifactRef } | { type: 'action_plan'; action_plan: AgentActionPlan };

export interface ProactiveMessage {
  id: number;
  content: string;
  anchor_date: string | null;
  created_at: string;
}

export interface ProactiveResult {
  messages: ProactiveMessage[];
  unread: number;
}

export interface CreateSessionRequest {
  id?: string;
  title?: string;
  status?: string;
  context_summary?: string;
  is_pinned?: boolean;
}

export const agentApi = {
  chat(data: ChatRequest) {
    return request.post<ChatResponse>(
      '/api/agent/chat',
      data
    );
  },
  async chatStream(data: ChatRequest, onMessage: (content: string) => void, onSessionId?: (id: string) => void, onTitleUpdate?: (title: string) => void, onReasoning?: (content: string) => void, signal?: AbortSignal, onEvent?: (event: AgentStreamEvent) => void) {
    const userStore = (await import('@/stores/user')).useUserStore();
    const token = userStore.token;
    
    const url = toServerUrl('/api/agent/chat');

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ ...data, stream: true }),
      signal
    });

    if (!response.ok) {
      let errorMsg = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          errorMsg = errorData.detail;
        }
      } catch (e) {
        // ignore JSON parse error
      }
      throw new Error(errorMsg);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder('utf-8');

    if (!reader) {
      throw new Error('Failed to get stream reader');
    }

    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim();
          if (dataStr === '[DONE]') {
            return;
          }
          try {
            const parsed = JSON.parse(dataStr);
            if (parsed.content) {
              onMessage(parsed.content);
            }
            if (parsed.reasoning && onReasoning) {
              onReasoning(parsed.reasoning);
            }
            if (parsed.session_id && onSessionId) {
              onSessionId(parsed.session_id);
            }
            if (parsed.title && onTitleUpdate) {
              onTitleUpdate(parsed.title);
            }
            if ((parsed.type === 'tool_start' || parsed.type === 'tool_end' || parsed.type === 'artifact' || parsed.type === 'action_plan') && onEvent) {
              onEvent(parsed);
            }
          } catch (e) {
            console.error('Failed to parse stream chunk', e);
          }
        }
      }
    }
  },
  getSessions(params?: { skip?: number; limit?: number }) {
    return request.get<AgentSession[]>('/api/agent/sessions', { params });
  },
  createSession(data: CreateSessionRequest) {
    return request.post<AgentSession>('/api/agent/sessions', data);
  },
  abortChat(sessionId: string) {
    return request.post<{ message: string }>(`/api/agent/chat/${sessionId}/abort`);
  },
  deleteSession(sessionId: string) {
    return request.delete<{ message: string }>(`/api/agent/sessions/${sessionId}`);
  },
  pinSession(sessionId: string, isPinned: boolean) {
    return request.put<AgentSession>(`/api/agent/sessions/${sessionId}/pin`, null, {
      params: { is_pinned: isPinned }
    });
  },
  getSessionMessages(sessionId: string, params?: { skip?: number; limit?: number }) {
    return request.get<AgentMessage[]>(`/api/agent/sessions/${sessionId}/messages`, { params });
  },
  deleteMessages(sessionId: string, messageIds?: number[]) {
    return request.delete<{ message: string }>('/api/agent/messages', {
      params: { 
        session_id: sessionId,
        message_ids: messageIds?.join(',')
      }
    });
  },
  // 主动式记忆（那年今日主动关怀）。后端返回 BaseResponse，需读取 .data
  getProactiveMessages() {
    return request.get<{ code: number; data: ProactiveResult }>('/api/agent/proactive');
  },
  markProactiveRead(messageId: number) {
    return request.post<{ code: number }>(`/api/agent/proactive/${messageId}/read`);
  },
  getArtifact(artifactId: string) {
    return request.get<{ code: number; data: AIArtifact }>(`/api/agent/artifacts/${artifactId}`);
  },
  updateArtifact(artifactId: string, data: { title?: string; content_json?: Record<string, any>; html_content?: string | null; html_config?: Record<string, any>; status?: string }) {
    return request.put<{ code: number; data: AIArtifact }>(`/api/agent/artifacts/${artifactId}`, data);
  },
  getActionPlan(planId: string) {
    return request.get<{ code: number; data: AgentActionPlan }>(`/api/agent/actions/${planId}`);
  },
  listActionPlans(params?: { session_id?: string; status?: string; limit?: number }) {
    return request.get<{ code: number; data: AgentActionPlan[] }>('/api/agent/actions', { params });
  },
  executeActionPlan(planId: string) {
    return request.post<{ code: number; data: AgentActionPlan }>(`/api/agent/actions/${planId}/execute`);
  },
  updateRepairSelection(planId: string, selectedRepairIds: string[]) {
    return request.patch<{ code: number; data: AgentActionPlan }>(`/api/agent/actions/${planId}`, {
      selected_repair_ids: selectedRepairIds
    });
  },
  rejectActionPlan(planId: string) {
    return request.post<{ code: number; data: AgentActionPlan }>(`/api/agent/actions/${planId}/reject`);
  },
  undoActionPlan(planId: string) {
    return request.post<{ code: number; data: AgentActionPlan }>(`/api/agent/actions/${planId}/undo`);
  }
};
