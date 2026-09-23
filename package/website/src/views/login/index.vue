<template>
  <main class="auth-page auth-page--login">
    <section class="auth-panel auth-panel--login" aria-labelledby="login-title">
      <div class="auth-characters" aria-hidden="true">
        <LoginCharacters
          :focus-target="focusTarget"
          :is-celebrating="isCelebrating"
          :is-mocking="isMocking"
        />
      </div>
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
          <div v-if="demoMode" class="auth-notice">演示账号已填写，点击「登录」即可体验</div>
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
            <router-link to="/server-settings?redirect=/login" class="auth-helper-link">扫码或自动查找 TrailSnap</router-link>
          </el-form-item>
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="请输入用户名"
              :prefix-icon="User"
              autocomplete="username"
              @focus="focusTarget = 'username'"
              @blur="focusTarget = null"
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
              @focus="focusTarget = 'password'"
              @blur="focusTarget = null"
            />
          </el-form-item>
          <div class="auth-options">
            <el-checkbox v-model="rememberMe">记住用户名</el-checkbox>
            <router-link to="/forgot-password" class="auth-link">忘记密码？</router-link>
          </div>
          <el-button type="primary" native-type="submit" class="auth-submit" :loading="loading">登录</el-button>
          <p v-if="allowRegistration" class="auth-switch">
            还没有账号？<router-link to="/register" class="auth-link">立即注册</router-link>
          </p>
          <p v-else-if="hasUsers" class="auth-switch">没有账号？请联系管理员添加</p>
        </el-form>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { User, Lock } from '@element-plus/icons-vue';
import { authService } from '@/api/auth';
import { getServerHistory, getServerUrl, isMobileApp, isTauriApp, saveServerUrl } from '@/config/server';
import LoginCharacters from './components/LoginCharacters.vue';
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
const focusTarget = ref<'username' | 'password' | null>(null);
const isCelebrating = ref(false);
const isMocking = ref(false);

const suggestServerAddresses = (
  _query: string,
  callback: (items: Array<{ value: string }>) => void,
) => callback(serverHistory.value.map(value => ({ value })));

const loginForm = reactive({
  serverUrl: showServerAddress ? getServerUrl() : '',
  username: '',
  password: ''
});

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
      await router.replace((route.query.redirect as string) || '/');
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

  try {
    const status = await authService.getAuthStatus();
    hasUsers.value = status.has_users;
    allowRegistration.value = !status.has_users || status.allow_registration;
    if (!status.has_users) {
      router.replace('/register');
      return;
    }
    if (status.demo_mode) {
      loginForm.username = 'trailsnap';
      loginForm.password = 'trailsnap';
      demoMode.value = true;
    }
  } catch (error) {
    console.error('Failed to get auth status:', error);
  }
});

const handleLogin = async () => {
  if (!loginFormRef.value || loading.value) return;
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    isMocking.value = false;
    try {
      if (showServerAddress) {
        loginForm.serverUrl = await saveServerUrl(loginForm.serverUrl);
        serverHistory.value = await getServerHistory();
      }
      await userStore.login({
        username: loginForm.username,
        password: loginForm.password,
      });
      if (rememberMe.value) {
        localStorage.setItem('remember_username', loginForm.username);
      } else {
        localStorage.removeItem('remember_username');
      }
      ElMessage.success('登录成功');
      if (window.matchMedia('(min-width: 768px)').matches) {
        isCelebrating.value = true;
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      await router.push((route.query.redirect as string) || '/');
    } catch (error: any) {
      console.error(error);
      const msg = error.response?.data?.detail || error.message || '登录失败，请检查用户名和密码';
      ElMessage.error(msg);
      isMocking.value = true;
      setTimeout(() => { isMocking.value = false; }, 1000);
    } finally {
      loading.value = false;
    }
  });
};
</script>
