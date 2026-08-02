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
  async chatStream(data: ChatRequest, onMessage: (content: string) => void, onSessionId?: (id: string) => void, onTitleUpdate?: (title: string) => void, onReasoning?: (content: string) => void, signal?: AbortSignal) {
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
  }
};
