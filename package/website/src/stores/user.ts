import { defineStore } from 'pinia';
import { ref } from 'vue';
import { authService, type LoginParams, type UserInfo } from '@/api/auth';
import router from '@/router';

const PERSIST_KEY_PREFIXES = ['trailsnap:', 'ticket-', 'trailsnap-location-'];

const clearPersistedState = () => {
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (PERSIST_KEY_PREFIXES.some(prefix => key.startsWith(prefix))) {
      localStorage.removeItem(key);
    }
  }
};

export const useUserStore = defineStore('user', () => {
  const token = ref<string | null>(localStorage.getItem('user_token') || null);
  const userInfo = ref<UserInfo | null>(null);

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
    logout,
    resetState,
    getUserInfo,
    updateUserInfo
  };
});
