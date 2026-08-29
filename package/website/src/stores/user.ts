import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { authService, type LoginParams, type UserInfo } from '@/api/auth';
import router from '@/router';

const PERSIST_KEY_PREFIXES = ['trailsnap:', 'ticket-', 'trailsnap-location-'];
const USER_INFO_KEY = 'user_info';

const clearPersistedState = () => {
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (PERSIST_KEY_PREFIXES.some(prefix => key.startsWith(prefix))) {
      localStorage.removeItem(key);
    }
  }
};

const loadUserInfo = (): UserInfo | null => {
  const raw = localStorage.getItem(USER_INFO_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
};

const persistUserInfo = (info: UserInfo | null) => {
  if (info) {
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(info));
  } else {
    localStorage.removeItem(USER_INFO_KEY);
  }
};

export const useUserStore = defineStore('user', () => {
  const token = ref<string | null>(localStorage.getItem('user_token') || null);
  const userInfo = ref<UserInfo | null>(loadUserInfo());

  // Keep localStorage in sync with userInfo across every mutation path
  // (getUserInfo, updateUserInfo, resetState, and the 401 interceptor in
  // utils/request.ts that assigns userStore.userInfo = null directly).
  watch(userInfo, (val) => persistUserInfo(val), { deep: true });

  const setToken = (newToken: string | null) => {
    token.value = newToken;
    if (newToken) {
      localStorage.setItem('user_token', newToken);
    } else {
      localStorage.removeItem('user_token');
    }
  };

  const login = async (loginData: LoginParams) => {
    try {
      const res = await authService.login(loginData);
      // Assuming res contains access_token directly or via data property depending on request.ts
      // With my proposed request.ts change, it returns the payload.
      if (res.access_token) {
        setToken(res.access_token);
        await getUserInfo();
        return true;
      }
      return false;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  const initializeDesktopSession = async () => {
    const session = await authService.createDesktopSession();
    setToken(session.access_token);
    await getUserInfo();
  };

  const getUserInfo = async () => {
    try {
      const res = await authService.getUserInfo();
      userInfo.value = res;
      return res;
    } catch (error) {
      console.error('Get user info failed:', error);
      // If 401, it might trigger logout via interceptor
      throw error;
    }
  };

  const updateUserInfo = (newData: Partial<UserInfo>) => {
    if (userInfo.value) {
      userInfo.value = { ...userInfo.value, ...newData };
    }
  };

  const resetState = () => {
    setToken(null);
    userInfo.value = null;
    clearPersistedState();
    router.push('/login');
  };

  // Server-unreachable handling must retain the configured server and local UI
  // state so the login screen can offer the same address for editing/retry.
  const clearSession = () => {
    setToken(null);
    userInfo.value = null;
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch (error) {
      console.warn('Logout API failed, forcing local logout', error);
    } finally {
      resetState();
    }
  };

  return {
    token,
    userInfo,
    login,
    initializeDesktopSession,
    logout,
    resetState,
    clearSession,
    getUserInfo,
    updateUserInfo
  };
});
