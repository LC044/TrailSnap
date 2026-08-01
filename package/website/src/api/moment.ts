import request from '@/utils/request';

export interface MomentDayCaption {
  id: number;
  user_id: string;
  scope_type: string;
  scope_id: string | null;
  day: string; // YYYY-MM-DD
  caption: string;
  source: 'ai' | 'manual';
  model_name: string | null;
  photo_count: number;
  created_at: string;
  updated_at: string;
}

export interface GenerateCaptionPayload {
  day: string; // YYYY-MM-DD（用户本地时区下的日期）
  timezone?: string;
  scope_type?: 'all';
  scope_id?: string | null;
  style?: string;
  force?: boolean;
  connection_id?: string;
  model_name?: string;
}

/** 单个位置条目（Top N 展开时使用）。 */
export interface MomentDayLocationItem {
  name: string;
  level: 'scene' | 'city' | 'district' | 'province' | 'unknown';
  count: number;
}

/** 按天聚合的位置。primary 即"日期后同一行展示的那段文字"的首选值。 */
export interface MomentDayLocations {
  day: string; // YYYY-MM-DD
  primary: string;
  level: 'scene' | 'city' | 'district' | 'province' | 'unknown';
  locations: MomentDayLocationItem[];
}

/** 朋友圈日精选中的单张照片（后端只返回渲染所需的最小字段）。 */
export interface MomentHighlightPhoto {
  id: string;
  photo_time: string | null;
  score: number;
  /** 该精选照片代表的 burst 组大小（含被相似去重掉的） */
  group_size: number;
}

/** 按天聚合的朋友圈精选照片。 */
export interface MomentDayHighlights {
  day: string; // YYYY-MM-DD
  photos: MomentHighlightPhoto[];
  total_candidates: number;
}

/** 获取浏览器时区（例如 'Asia/Shanghai'），失败回退 UTC。 */
export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch (e) {
    return 'UTC';
  }
}

export const momentApi = {
  listDayCaptions(params: {
    start: string;
    end: string;
    scope_type?: string;
    scope_id?: string | null;
  }) {
    return request.get<MomentDayCaption[]>('/api/moments/day-captions', { params });
  },

  listDayLocations(params: {
    start: string;
    end: string;
    timezone?: string;
    top_n?: number;
  }) {
    return request.get<MomentDayLocations[]>('/api/moments/day-locations', {
      params: {
        timezone: getBrowserTimezone(),
        top_n: 3,
        ...params,
      },
    });
  },

  /** 批量拉取一段日期区间内每一天的朋友圈精选照片（服务端完成去重与排序，无数据的天不返回）。 */
  listDayHighlights(params: {
    start: string;
    end: string;
    limit?: number;
  }) {
    return request.get<MomentDayHighlights[]>('/api/moments/day-highlights', {
      params: {
        limit: 9,
        ...params,
      },
    });
  },

  saveDayCaption(day: string, caption: string, scope_type: string = 'all', scope_id: string | null = null) {
    return request.put<MomentDayCaption>(`/api/moments/day-captions/${day}`, { caption }, {
      params: { scope_type, scope_id: scope_id ?? undefined },
    });
  },

  clearDayCaption(day: string, scope_type: string = 'all', scope_id: string | null = null) {
    return request.delete<{ deleted: boolean }>(`/api/moments/day-captions/${day}`, {
      params: { scope_type, scope_id: scope_id ?? undefined },
    });
  },

  /**
   * SSE 流式生成朋友圈日文案。
   * onChunk：每收到一小段正文文本就会被调用一次（最终文案内容）；
   * onReasoning：每收到一小段思考过程文本会被调用一次，仅用于生成期反馈，最终结果不含；
   * onDone：完整文案落库成功时回调，携带 server 返回的 MomentDayCaption 摘要；
   * onError：LLM 或后端错误。
   */
  async generateStream(
    payload: GenerateCaptionPayload,
    onChunk: (text: string) => void,
    onDone?: (info: { caption: string; source: string; updated_at?: string; cached?: boolean }) => void,
    onError?: (err: string) => void,
    onReasoning?: (text: string) => void,
    signal?: AbortSignal,
  ) {
    const userStore = (await import('@/stores/user')).useUserStore();
    const token = userStore.token;

    const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
    const url = `${baseUrl}/api/moments/day-captions/generate`;

    const body = {
      timezone: getBrowserTimezone(),
      scope_type: 'all',
      stream: true,
      ...payload,
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!response.ok) {
      let errorMsg = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) errorMsg = errorData.detail;
      } catch (e) {
        /* ignore */
      }
      throw new Error(errorMsg);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('Failed to get stream reader');
    const decoder = new TextDecoder('utf-8');

    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const dataStr = line.slice(6).trim();
        if (dataStr === '[DONE]') return;
        try {
          const parsed = JSON.parse(dataStr);
          if (parsed.error) {
            onError?.(parsed.error);
            continue;
          }
          if (parsed.content) {
            onChunk(parsed.content);
          }
          if (parsed.reasoning) {
            onReasoning?.(parsed.reasoning);
          }
          if (parsed.done) {
            onDone?.({
              caption: parsed.caption,
              source: parsed.source,
              updated_at: parsed.updated_at,
              cached: parsed.cached,
            });
          } else if (parsed.cached && parsed.content) {
            // 命中缓存的单帧回放
            onDone?.({ caption: parsed.content, source: 'existing', cached: true });
          }
        } catch (e) {
          console.error('Failed to parse moment stream chunk', e);
        }
      }
    }
  },
};
