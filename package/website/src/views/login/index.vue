<template>
  <main class="auth-page auth-page--login">
    <div class="auth-stage">
      <!-- 封面：一句品牌主张，一张照片，留给第一次见面 -->
      <aside class="auth-story" aria-hidden="true">
        <div class="auth-story-photo"></div>
        <div class="auth-story-veil"></div>
        <div class="auth-story-inner">
          <div class="auth-story-brand">
            <img src="@/assets/logo.svg" alt="" />
            <span class="auth-story-word">行影集</span>
            <span class="auth-story-en">TRAILSNAP</span>
          </div>
          <h2 class="auth-story-title">
            <span>把日子</span>
            <span>留在画面里</span>
          </h2>
          <p class="auth-story-sub">照片自动成册的私人影像手记</p>
          <ul class="auth-story-points">
            <li><i></i>时间与地点，自动整理</li>
            <li><i></i>用一句话，找到那一张</li>
            <li><i></i>足迹地图与年度回忆</li>
          </ul>
        </div>
      </aside>

      <section class="auth-panel auth-panel--login" aria-labelledby="login-title">
        <div class="auth-content">
          <div class="auth-brand">
            <img src="@/assets/logo.svg" alt="" class="auth-brand-icon" />
            <span>行影集 <span class="auth-brand-en">TrailSnap</span></span>
          </div>
          <header class="auth-heading">
            <h1 id="login-title">欢迎回来</h1>
            <p>登录账号，继续记录每一段旅程</p>
          </header>
          <el-form ref="loginFormRef" :model="loginForm" :rules="rules" label-position="top" size="large" class="auth-form" @submit.prevent="handleLogin">
            <div v-if="demoMode" class="auth-notice" role="status" aria-live="polite">{{ loading ? '正在进入演示相册…' : '自动进入暂未成功，请点击「登录」重试。' }}</div>
            <div v-if="!isTauriApp() && authState !== 'ready'" class="auth-notice" role="status" aria-live="polite">
              {{ authState === 'checking' ? '正在连接服务…' : '暂时无法连接服务，首次启动可能需要一些时间。正在自动重试。' }}
              <el-button v-if="authState === 'unavailable'" link type="primary" @click="checkAuthStatus">重试当前服务器</el-button>
            </div>
            <el-form-item v-if="showServerAddress" label="TrailSnap 地址" prop="serverUrl">
              <el-autocomplete
                v-model="loginForm.serverUrl"
                :fetch-suggestions="suggestServerAddresses"
                :trigger-on-focus="true"
                clearable
                placeholder="与网页访问地址相同"
                class="w-full"
                data-testid="server-address"
                @select="({ value }) => loginForm.serverUrl = value"
              />
              <router-link :to="serverSettingsLocation" class="auth-helper-link">切换服务器（手动输入、扫码或自动查找）</router-link>
            </el-form-item>
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入用户名"
                :prefix-icon="User"
                autocomplete="username"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                autocomplete="current-password"
                show-password
              />
            </el-form-item>
            <div class="auth-options">
              <el-checkbox v-model="rememberMe">记住用户名</el-checkbox>
              <router-link to="/forgot-password" class="auth-link">忘记密码？</router-link>
            </div>
            <el-button type="primary" native-type="submit" class="auth-submit lm-sheen" :loading="loading" :disabled="!canLogIn">登录</el-button>
            <p v-if="allowRegistration" class="auth-switch">
              还没有账号？<router-link to="/register" class="auth-link">立即注册</router-link>
            </p>
            <p v-else-if="authState === 'ready' && hasUsers" class="auth-switch">没有账号？请联系管理员添加</p>
          </el-form>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { User, Lock } from '@element-plus/icons-vue';
import { useAuthStatus } from '@/composables/useAuthStatus';
import { createDemoEntry } from '@/composables/demoEntry';
import { safeAuthRedirect } from '@/router/authRedirect';
import { getServerHistory, getServerUrl, isMobileApp, isTauriApp } from '@/config/server';
import './auth.css';

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const loginFormRef = ref<FormInstance>();
const loading = ref(false);
const rememberMe = ref(false);
const hasUsers = ref(true);
const allowRegistration = ref(false);
const demoMode = ref(false);
const showServerAddress = isMobileApp();
const serverHistory = ref<string[]>([]);

const enterDemo = createDemoEntry(
  async () => {
    const entered = await userStore.login({ username: 'trailsnap', password: 'trailsnap' });
    if (!entered) throw new Error('Demo session was not created');
  },
  () => router.replace(safeAuthRedirect(route.query.redirect)),
);

const { state: authState, check: checkAuthStatus } = useAuthStatus(async (status) => {
  hasUsers.value = status.has_users;
  allowRegistration.value = !status.has_users || status.allow_registration;
  if (!status.has_users) {
    await router.replace('/register');
    return;
  }
  if (status.demo_mode) {
    loginForm.username = 'trailsnap';
    loginForm.password = 'trailsnap';
    demoMode.value = true;
    loading.value = true;
    try {
      if (route.query.demo_failed !== '1') await enterDemo(status);
    } catch {
      // Keep the prefilled form available; do not repeatedly retry a failed login.
      ElMessage.warning('暂时无法自动进入演示相册，请重试');
    } finally {
      loading.value = false;
    }
  }
});

const suggestServerAddresses = (
  _query: string,
  callback: (items: Array<{ value: string }>) => void,
) => callback(serverHistory.value.map(value => ({ value })));

const currentServerUrl = showServerAddress ? getServerUrl() : '';
const loginForm = reactive({
  serverUrl: currentServerUrl,
  username: '',
  password: ''
});
const canLogIn = computed(() => isTauriApp() || (
  authState.value === 'ready' && (!showServerAddress || loginForm.serverUrl.trim() === currentServerUrl)
));
const serverSettingsLocation = computed(() => ({
  name: 'ServerSettings',
  query: { url: loginForm.serverUrl.trim(), redirect: route.fullPath },
}));

const rules = reactive<FormRules>({
  serverUrl: showServerAddress
    ? [{ required: true, message: '请输入或选择 TrailSnap 地址', trigger: 'change' }]
    : [],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度至少为 3 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少为 6 个字符', trigger: 'blur' }
  ]
});

onMounted(async () => {
  if (isTauriApp()) {
    loading.value = true;
    try {
      await userStore.initializeDesktopSession();
      await router.replace(safeAuthRedirect(route.query.redirect));
    } catch (error: any) {
      ElMessage.error(error?.message || '本地会话恢复失败，请重启 TrailSnap');
    } finally {
      loading.value = false;
    }
    return;
  }

  const savedUsername = localStorage.getItem('remember_username');
  if (savedUsername) {
    loginForm.username = savedUsername;
    rememberMe.value = true;
  }

  if (showServerAddress) {
    serverHistory.value = await getServerHistory();
    if (!loginForm.serverUrl) return;
  }

  await checkAuthStatus();
});

const handleLogin = async () => {
  if (!loginFormRef.value || loading.value || !canLogIn.value) return;
  await loginFormRef.value.validate(async (valid) => {
    if (!valid || !canLogIn.value) return;
    loading.value = true;
    try {
      const entered = await userStore.login({
        username: loginForm.username,
        password: loginForm.password,
      });
      if (!entered) throw new Error('登录未成功，请重试');
      if (rememberMe.value) {
        localStorage.setItem('remember_username', loginForm.username);
      } else {
        localStorage.removeItem('remember_username');
      }
      ElMessage.success('登录成功');
      await router.replace(safeAuthRedirect(route.query.redirect));
    } catch (error: any) {
      console.error(error);
      const msg = error.response?.data?.detail || error.message || '登录失败，请检查用户名和密码';
      ElMessage.error(msg);
    } finally {
      loading.value = false;
    }
  });
};
</script>
