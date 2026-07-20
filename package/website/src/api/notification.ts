import request from '@/utils/request';

export type NotificationType = 'TASK' | 'UPDATE' | 'SYSTEM';
export type NotificationLevel = 'info' | 'success' | 'warning' | 'error';

export interface AppNotification {
  id: string;
  user_id: string;
  type: string;
  level: NotificationLevel;
  title: string;
  body?: Record<string, any> | null;
  ref_type?: string | null;
  ref_id?: string | null;
  read: boolean;
  created_at?: string | null;
  read_at?: string | null;
}

export interface NotificationCreateInput {
  type?: NotificationType;
  level?: NotificationLevel;
  title: string;
  body?: Record<string, any> | null;
  ref_type?: string | null;
  ref_id?: string | null;
  user_ids?: string[];
  broadcast?: boolean;
}

const SSE_BASE = (import.meta.env.VITE_API_BASE_URL ?? '') || '';

/**
 * Build the URL for the notification SSE stream. EventSource cannot set
 * headers, so we pass the JWT as a query param — same pattern as the task
 * stream. This single channel carries both `task.*` (live, not persisted)
 * and `notification.*` (persisted) events.
 */
export function buildNotificationsEventsUrl(token: string | null | undefined): string {
  const base = SSE_BASE || '';
  const params = new URLSearchParams();
  if (token) params.set('token', token);
  const qs = params.toString();
  return `${base}/api/notifications/events${qs ? '?' + qs : ''}`;
}

export const notificationsApi = {
  async list(params: { type?: string; unread?: boolean; limit?: number; before_id?: string } = {}) {
    const res = await request.get<AppNotification[]>('/api/notifications', { params });
    return res.data;
  },

  async unreadCount() {
    const res = await request.get<{ count: number }>('/api/notifications/unread-count');
    return res.data;
  },

  async markRead(id: string) {
    const res = await request.post<{ read: boolean; unread_count: number }>(`/api/notifications/${id}/read`);
    return res.data;
  },

  async markAllRead() {
    const res = await request.post<{ marked: number }>('/api/notifications/read-all');
    return res.data;
  },

  /** Admin only: create + broadcast a notification. */
  async create(input: NotificationCreateInput) {
    const res = await request.post<{ created: string[]; count: number }>('/api/notifications', input);
    return res.data;
  },
};
