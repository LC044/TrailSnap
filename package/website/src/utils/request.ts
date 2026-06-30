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
        ElMessage.error(res.message || res.msg || '接口请求失败');
        return Promise.reject(res);
      }
      return res;
    }
    // 如果没有 code 字段，假设是直接返回数据（如 login 接口）
    return response;
  },
  async (error: AxiosError) => {
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
          const currentPath = router.currentRoute.value.path;
          const publicPages = ['/login', '/register', '/forgot-password'];
          const userStore = useUserStore();

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
        default:
          errorMsg = `请求错误（${(error.response?.data as any)?.detail || error.response?.statusText || error.message}）`;
      }
    } else if (error.request) {
      errorMsg = '请求超时，请检查网络';
    }
    ElMessage.error(errorMsg);
    return Promise.reject(error);
  }
);

export default service;