<template>
  <div class="min-h-screen w-full flex items-center justify-center bg-white dark:bg-gray-900">
    <!-- 外层容器：控制整体居中 -->
    <div class="w-full max-w-6xl mx-auto flex flex-col md:flex-row bg-white dark:bg-gray-900 rounded-xl shadow-xl overflow-hidden">
      <!-- Left Side: Characters (Desktop Only) -->
      <div class="hidden md:flex w-1/2 bg-gray-100 dark:bg-gray-800 items-center justify-center relative overflow-hidden min-h-[500px]">
        <LoginCharacters 
          :focus-target="focusTarget" 
          :is-celebrating="isCelebrating" 
          :is-mocking="isMocking"
        />
      </div>

      <!-- Right Side: Login Form -->
      <div class="w-full md:w-1/2 flex items-center justify-center p-8 md:p-12 bg-white dark:bg-gray-900">
        <div class="w-full max-w-md">
          <div class="mb-10 text-center md:text-left">
            <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">登录 行影集</h2>
            <p class="text-gray-500 dark:text-gray-400">欢迎回来，请输入您的账号密码</p>
          </div>
          
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="rules"
            label-position="top"
            size="large"
            class="space-y-6"
            @submit.prevent="handleLogin"
          >
            <!-- 演示模式：自动填充演示账号后的提示条 -->
            <div v-if="demoMode" class="rounded-lg bg-primary-50 dark:bg-primary-900/20 px-4 py-3 text-sm text-primary-600 dark:text-primary-300">
              演示模式：已为你自动填充演示账号，点击「登录」即可体验
            </div>
            <el-form-item v-if="showServerAddress" label="服务器地址" prop="serverUrl" class="!mb-4">
              <el-autocomplete
                v-model="loginForm.serverUrl"
                :fetch-suggestions="suggestServerAddresses"
                :trigger-on-focus="true"
                clearable
                placeholder="请输入或选择服务器地址"
                class="w-full !h-12"
                data-testid="server-address"
                @select="({ value }) => loginForm.serverUrl = value"
              />
              <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                例如 http://192.168.1.10:8800，登录时会记住该地址
              </p>
            </el-form-item>

            <el-form-item label="用户名" prop="username" class="!mb-4">
              <el-input 
                v-model="loginForm.username" 
                placeholder="请输入用户名"
                :prefix-icon="User"
                class="!h-12"
                @focus="focusTarget = 'username'"
                @blur="focusTarget = null"
              />
            </el-form-item>
            
            <el-form-item label="密码" prop="password" class="!mb-2">
              <!-- 按回车键触发登录 -->
              <el-input 
                v-model="loginForm.password" 
                type="password" 
                placeholder="请输入密码"
                :prefix-icon="Lock"
                show-password
                class="!h-12"
                @focus="focusTarget = 'password'"
                @blur="focusTarget = null"
                @keyup.enter="handleLogin"
              />
            </el-form-item>

            <div class="flex items-center justify-between mb-6">
              <el-checkbox v-model="rememberMe" size="large">记住我</el-checkbox>
              <router-link to="/forgot-password" class="text-sm text-blue-600 hover:underline">忘记密码?</router-link>
            </div>

            <el-button 
              type="primary" 
              class="w-full !bg-blue-500 hover:!bg-blue-600 !border-none !h-12 !text-lg !rounded-lg font-medium transition-colors duration-200" 
              :loading="loading" 
              @click="handleLogin"
            >
              登录
            </el-button>

            <div class="text-center mt-6" v-if="allowRegistration">
              <span class="text-gray-600 text-sm">还没有账号? </span>
              <router-link to="/register" class="text-blue-600 hover:underline text-sm font-medium">立即注册</router-link>
            </div>
            <div class="text-center mt-6" v-else-if="hasUsers">
              <span class="text-gray-500 dark:text-gray-400 text-sm">没有账号？请联系管理员添加</span>
            </div>
          </el-form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useUserStore } from '@/stores/user';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { User, Lock } from '@element-plus/icons-vue';
import { authService } from '@/api/auth';
import { getServerHistory, getServerUrl, isMobileApp, saveServerUrl } from '@/config/server';
import LoginCharacters from './components/LoginCharacters.vue';

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();

const loginFormRef = ref<FormInstance>();
const loading = ref(false);
const rememberMe = ref(false);
const hasUsers = ref(true)
const allowRegistration = ref(false);
const demoMode = ref(false);
const showServerAddress = isMobileApp();
const serverHistory = ref<string[]>([]);

const suggestServerAddresses = (
  _query: string,
  callback: (items: Array<{ value: string }>) => void,
) => {
  // History is capped at ten entries; always show all of it so focusing a
  // prefilled address still exposes the other servers for one-tap switching.
  callback(serverHistory.value.map(value => ({ value })));
};

// Character interaction state
const focusTarget = ref<'username' | 'password' | null>(null);
const isCelebrating = ref(false);
const isMocking = ref(false);

const loginForm = reactive({
  serverUrl: showServerAddress ? getServerUrl() : '',
  username: '',
  password: ''
});

const rules = reactive<FormRules>({
  serverUrl: showServerAddress
    ? [{ required: true, message: '请输入或选择服务器地址', trigger: 'change' }]
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
    // Show register link when: no users yet (first-time setup) OR registration is explicitly allowed
    allowRegistration.value = !status.has_users || status.allow_registration;
    // 初次使用（尚无任何用户）时直接跳转到注册页，不展示登录界面
    if (!status.has_users) {
      router.replace('/register');
      return;
    }
    // 演示模式：自动填充演示账号 trailsnap / trailsnap，游客无需手动输入
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
  if (!loginFormRef.value) return;
  
  await loginFormRef.value.validate(async (valid, fields) => {
    if (valid) {
      loading.value = true;
      try {
        if (showServerAddress) {
          loginForm.serverUrl = await saveServerUrl(loginForm.serverUrl);
          serverHistory.value = await getServerHistory();
        }

        await userStore.login({
          username: loginForm.username,
          password: loginForm.password,
        });

        // Celebration animation
        isCelebrating.value = true;
        
        if (rememberMe.value) {
          localStorage.setItem('remember_username', loginForm.username);
        } else {
          localStorage.removeItem('remember_username');
        }

        ElMessage.success('登录成功');

        // Redirect after a short delay to show animation
        setTimeout(() => {
            const redirect = route.query.redirect as string || '/';
            router.push(redirect);
        }, 1500);
        
      } catch (error: any) {
        console.error(error);
        const msg = error.response?.data?.detail || error.message || '登录失败，请检查用户名和密码';
        ElMessage.error(msg);
        
        // Mocking animation on error
        isMocking.value = true;
        setTimeout(() => {
          isMocking.value = false;
        }, 1000);
      } finally {
        // Wait for animation or immediate if error
        if (!isCelebrating.value) {
           loading.value = false;
        } else {
           // If celebrating, keep loading state until redirect? 
           // Or stop loading but keep celebrating.
           // Let's stop loading so button shows "Login" (or maybe "Success"?)
           // But we want to prevent double clicks.
           // Loading spinner is fine.
        }
      }
    } else {
      console.log('error submit!', fields);
    }
  });
};
</script>

<style scoped>
:deep(.el-form-item__label) {
  font-weight: 500;
  color: #374151; /* gray-700 */
}
.dark :deep(.el-form-item__label) {
  color: #d1d5db; /* gray-300 */
}

/* Customize input focus color */
:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #3b82f6 inset !important;
}
</style>
