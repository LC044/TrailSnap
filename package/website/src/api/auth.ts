import request from '@/utils/request';
import { getDesktopSessionSecret } from '@/config/server';

export interface LoginParams {
  username?: string;
  password?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  nickname?: string;
  avatar?: string;
  is_active: boolean;
  is_superuser: boolean;
  failed_login_attempts?: number;
  last_failed_login?: string;
  lockout_until?: string;
}

export interface RegisterParams {
  username: string;
  nickname?: string;
  avatar?: string;
  email: string;
  password: string;
  security_question: string;
  security_answer: string;
}

export interface ResetCheckParams {
  username_or_email: string;
}

export interface ResetCheckResponse {
  security_question: string;
}

export interface ResetConfirmParams {
  username_or_email: string;
  security_answer: string;
  new_password: string;
}

export interface BaseResponseData<T = any> {
  code: number;
  msg: string;
  data: T | null;
}

export interface LogResetCodeConfirmParams {
  username_or_email: string;
  code: string;
  new_password: string;
}

export const authService = {
  async createDesktopSession() {
    const res = await request<LoginResponse>({
      url: '/api/auth/desktop-session',
      method: 'post',
      headers: {
        'X-TrailSnap-Desktop-Secret': getDesktopSessionSecret()
      }
    });
    return res.data as unknown as LoginResponse;
  },

  async login(data: LoginParams) {
    // API requires x-www-form-urlencoded
    const formData = new URLSearchParams();
    if (data.username) formData.append('username', data.username);
    if (data.password) formData.append('password', data.password);

    const res = await request<LoginResponse>({
      url: '/api/auth/login', // Adjusted from /api/v1/auth/login based on backend structure
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    });
    // Cast to LoginResponse because interceptor unwraps the response
    return res.data as unknown as LoginResponse;
  },

  async getUserInfo() {
    const res = await request<UserInfo>({
      url: '/api/users/me', // Adjusted from /api/v1/users/me based on backend structure
      method: 'get'
    });
    // Cast to UserInfo because interceptor unwraps the response
    return res.data as unknown as UserInfo;
  },
  
  async register(data: RegisterParams) {
    const res = await request({
      url: '/api/auth/register',
      method: 'post',
      data
    });
    return res.data;
  },

  async checkResetUser(data: ResetCheckParams) {
    const res = await request<ResetCheckResponse>({
      url: '/api/auth/check-reset-user',
      method: 'post',
      data
    });
    return res.data as unknown as ResetCheckResponse;
  },

  async resetPassword(data: ResetConfirmParams) {
    const res = await request({
      url: '/api/auth/reset-password',
      method: 'post',
      data
    });
    return res.data;
  },

  async sendLogResetCode(data: ResetCheckParams) {
    const res = await request<BaseResponseData>({
      url: '/api/auth/send-log-reset-code',
      method: 'post',
      data
    });
    // 响应拦截器已将 BaseResponse 透出：返回 { code, msg, data }
    return res as unknown as BaseResponseData;
  },

  async resetPasswordByCode(data: LogResetCodeConfirmParams) {
    const res = await request<BaseResponseData>({
      url: '/api/auth/reset-password-by-code',
      method: 'post',
      data
    });
    return res as unknown as BaseResponseData;
  },

  async getAuthStatus() {
    const res = await request<{has_users: boolean; allow_registration: boolean; demo_mode: boolean}>({
      url: '/api/auth/status',
      method: 'get'
    });
    return res.data;
  },

  logout() {
    // If there is a backend logout endpoint, call it here.
    // For JWT, usually client-side removal is enough, but some backends might blacklist tokens.
    // Assuming client-side only for now as no logout endpoint was seen in auth.py.
    return Promise.resolve();
  }
};
