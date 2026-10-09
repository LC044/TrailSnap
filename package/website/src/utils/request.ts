import axios, { 
  AxiosInstance, 
  InternalAxiosRequestConfig, // 关键：导入内部请求配置类型
  AxiosResponse, 
  AxiosError,
  AxiosRequestHeaders // 导入请求头类型
} from 'axios';
import { ElMessage } from 'element-plus';
import router from '@/router';
import { useUserStore } from '@/stores/user';
import { getServerUrl, hasConfiguredServer, isNativeApp, isTauriApp } from '@/config/server';

declare module 'axios' {
  interface AxiosRequestConfig {
    silentError?: boolean;
    /** Set false for requests that must fail immediately. Only GET/HEAD are retried. */
    retry?: false;
    _networkRetryCount?: number;
  }
}

const MAX_NETWORK_RETRIES = 2;
const TRANSIENT_STATUSES = new Set([502, 503, 504]);
const TRANSIENT_CODES = new Set(['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT']);
let lastConnectionMessage = '';
let lastConnectionMessageAt = -Infinity;

function isTransientError(error: AxiosError): boolean {
  return error.response
    ? TRANSIENT_STATUSES.has(error.response.status)
    : TRANSIENT_CODES.has(error.code || '');
}

/** Abort during backoff as well as during the actual HTTP request. */
function waitForRetry(config: InternalAxiosRequestConfig, delay: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const signal = config.signal;
    const cleanup = () => {
      clearTimeout(timer);
      signal?.removeEventListener?.('abort', onAbort);
      config.cancelToken?.unsubscribe(onAbort);
    };
    const onAbort = () => {
      cleanup();
      reject(new axios.CanceledError('Request canceled', config));
    };
    const timer = setTimeout(() => { cleanup(); resolve(); }, delay);
    signal?.addEventListener?.('abort', onAbort);
    config.cancelToken?.subscribe(onAbort);
    if (signal?.aborted) onAbort();
  });
}

// 创建 Axios 实例（类型不变）
const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
  // headers: {
  //   'Content-Type': 'application/json'
  // },
  paramsSerializer: (params) => {
    const p = new URLSearchParams();
    for (const key in params) {
        const val = params[key];
        if (val === undefined || val === null) continue;
        if (Array.isArray(val)) {
            val.forEach(v => p.append(key, v));
        } else {
            p.append(key, val);
        }
    }
    return p.toString();
  }
});

// ------------------- 修正请求拦截器（核心修改）-------------------
service.interceptors.request.use(
  // 1. 参数类型改为 InternalAxiosRequestConfig
  (config: InternalAxiosRequestConfig) => {
    if ((isNativeApp() || hasConfiguredServer()) && getServerUrl()) {
      config.baseURL = getServerUrl();
    }
    // 2. 处理 headers 可选性：确保 headers 存在（避免 undefined 报错）
    const headers = config.headers as AxiosRequestHeaders; // 类型断言（或用可选链）
    
    // 或用可选链 + 空值合并（更安全）：
    // config.headers = config.headers ?? {}; // 若 headers 为 undefined，初始化为空对象

    // 添加 Token（从 Store 获取）
    const userStore = useUserStore();
    if (userStore.token) {
      headers.Authorization = `Bearer ${userStore.token}`;
    }

    // 添加自定义请求头（同样处理可选性）
    headers['X-Api-Version'] = 'v1';

    return config; // 返回类型自动匹配 InternalAxiosRequestConfig
  },
  (error: AxiosError) => {
    ElMessage.error('请求配置错误：' + error.message);
    return Promise.reject(error);
  }
);

// ------------------- 响应拦截器（无需修改，保持原样）-------------------
service.interceptors.response.use(
  (response: AxiosResponse) => {
    const res = response.data;
    // 兼容后端直接返回数据（无 code 字段）或标准结构（有 code 字段）
    // 如果是标准结构 { code, message, data }
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code !== 200 && res.code !== 0) {
        if (!response.config.silentError) ElMessage.error(res.message || res.msg || '接口请求失败');
        return Promise.reject(res);
      }
      return res;
    }
    // 如果没有 code 字段，假设是直接返回数据（如 login 接口）
    return response;
  },
  async (error: AxiosError) => {
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED' || error.config?.signal?.aborted) {
      return Promise.reject(error);
    }

    const config = error.config;
    const retryCount = config?._networkRetryCount || 0;
    if (config && config.retry !== false
      && ['get', 'head'].includes((config.method || 'get').toLowerCase())
      && isTransientError(error) && retryCount < MAX_NETWORK_RETRIES) {
      config._networkRetryCount = retryCount + 1;
      await waitForRetry(config, 500 * 2 ** retryCount);
      return service.request(config);
    }

    let errorMsg = '网络异常，请重试';
    if (error.response) {
      // When a request used responseType: 'blob' (e.g. file downloads), the
      // error body comes back as an unparsed Blob. Decode it so the switch
      // below can read the backend's `detail` message.
      const errData = error.response.data as any;
      if (errData instanceof Blob) {
        try {
          const text = await errData.text();
          error.response.data = JSON.parse(text);
        } catch {
          // Body wasn't JSON — leave as-is and fall through to status text.
        }
      }
      switch (error.response.status) {
        case 401: {
          // window.location rather than router.currentRoute: a background
          // request (nav items, auth status) can 401 while the initial
          // navigation is still resolving, when currentRoute is still "/" —
          // using it here misclassifies a public page as protected and bounces
          // the user to /login mid-onboarding.
          const currentPath = window.location.pathname;
          // Same allow-list as the router guard: /server-settings is where the
          // user goes to switch servers before logging in. A stale token there
          // must be cleared silently — redirecting to /login would bounce them
          // back ("登录已过期" while trying to reach the login flow).
          const publicPages = ['/login', '/register', '/forgot-password', '/server-settings'];
          const userStore = useUserStore();

          const originalRequest = error.config as (InternalAxiosRequestConfig & { _desktopSessionRetried?: boolean }) | undefined;
          if (isTauriApp() && originalRequest && !originalRequest._desktopSessionRetried) {
            originalRequest._desktopSessionRetried = true;
            try {
              await userStore.initializeDesktopSession();
              originalRequest.headers.Authorization = `Bearer ${userStore.token}`;
              return service.request(originalRequest);
            } catch {
              // Fall through to the normal expired-session handling. The
              // desktop login page also repairs the local session on mount.
            }
          }

          if (publicPages.some(p => currentPath.startsWith(p))) {
            // Already on a public page — just clear stale token silently
            localStorage.removeItem('user_token');
            userStore.token = null;
            userStore.userInfo = null;
            return Promise.reject(error);
          }

          errorMsg = '登录已过期，请重新登录';
          // Clear auth state and redirect to login
          userStore.resetState();
          break;
        }
        case 403:
          errorMsg = '暂无权限访问';
          break;
        case 404:
          errorMsg = '接口地址不存在';
          break;
        case 500:
          errorMsg = '服务器内部错误';
          break;
        case 502:
        case 503:
        case 504:
          errorMsg = '服务器暂时不可用，请稍后重试';
          break;
        default: {
          const raw = (error.response?.data as any)?.detail;
          let detailStr: string | undefined;
          if (typeof raw === 'string') {
            detailStr = raw;
          } else if (Array.isArray(raw)) {
            // FastAPI 校验错误 detail 是数组：[{loc, msg, type}, ...]
            detailStr = raw
              .map((it: any) => it?.msg || (typeof it === 'string' ? it : JSON.stringify(it)))
              .join('; ');
          } else if (raw && typeof raw === 'object') {
            detailStr = (raw as any).msg || JSON.stringify(raw);
          }
          errorMsg = `请求错误（${detailStr || error.response?.statusText || error.message}）`;
          break;
        }
      }
    } else if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      errorMsg = '请求超时，请稍后重试（登录状态已保留）';
    } else if (error.request) {
      // No HTTP response means the server or network is temporarily
      // unavailable; it says nothing about whether the token is valid.  In
      // particular, a backup upload can briefly saturate/restart a service.
      // Preserve the mobile session and current route so the user can retry
      // when connectivity returns.  A real HTTP 401 above still logs out.
      errorMsg = '无法连接服务器，请检查网络后重试（登录状态已保留）';
    }
    if (!error.config?.silentError || error.response?.status === 401) {
      // Concurrent page requests can all fail during the same brief outage.
      const connectionError = isTransientError(error) || (!error.response && !!error.request);
      const now = Date.now();
      if (!connectionError || errorMsg !== lastConnectionMessage || now - lastConnectionMessageAt >= 5000) {
        ElMessage.error(errorMsg);
        if (connectionError) {
          lastConnectionMessage = errorMsg;
          lastConnectionMessageAt = now;
        }
      }
    }
    return Promise.reject(error);
  }
);

export default service;
