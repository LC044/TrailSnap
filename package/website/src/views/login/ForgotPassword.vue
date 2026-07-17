<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 px-4">
    <el-card class="w-full max-w-md shadow-lg">
      <template #header>
        <div class="text-center">
          <h2 class="text-xl font-bold text-gray-800 dark:text-white">找回密码</h2>
        </div>
      </template>

      <!-- 重置方式选择 -->
      <el-radio-group
        v-model="method"
        class="w-full mb-4"
        @change="handleMethodChange"
      >
        <el-radio-button label="security" class="w-1/2">安全问题</el-radio-button>
        <el-radio-button label="log" class="w-1/2">服务器验证码</el-radio-button>
      </el-radio-group>

      <!-- Step 1: Find User -->
      <div v-if="step === 1">
        <el-form
          ref="step1FormRef"
          :model="step1Form"
          :rules="step1Rules"
          label-position="top"
          size="large"
          @submit.prevent="handleStep1"
        >
          <el-form-item label="用户名或邮箱" prop="username">
            <el-input
              v-model="step1Form.username"
              placeholder="请输入用户名或邮箱"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              class="w-full"
              :loading="loading"
              @click="handleStep1"
            >
              {{ method === 'log' ? '发送验证码' : '下一步' }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 2: Security Question -->
      <div v-else-if="step === 2 && method === 'security'">
        <div class="mb-6 bg-blue-50 dark:bg-blue-900/20 p-4 rounded-md border border-blue-100 dark:border-blue-800">
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">安全问题：</p>
          <p class="text-lg font-medium text-blue-800 dark:text-blue-300">{{ securityQuestion }}</p>
        </div>

        <el-form
          ref="step2FormRef"
          :model="step2Form"
          :rules="step2Rules"
          label-position="top"
          size="large"
          @submit.prevent="handleResetPassword"
        >
          <el-form-item label="问题答案" prop="answer">
            <el-input
              v-model="step2Form.answer"
              placeholder="请输入答案"
            />
          </el-form-item>

          <el-form-item label="新密码" prop="password">
            <el-input
              v-model="step2Form.password"
              type="password"
              placeholder="请输入新密码"
              show-password
            />
          </el-form-item>

          <el-form-item label="确认新密码" prop="confirmPassword">
            <el-input
              v-model="step2Form.confirmPassword"
              type="password"
              placeholder="请再次输入新密码"
              show-password
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              class="w-full"
              :loading="loading"
              @click="handleResetPassword"
            >
              重置密码
            </el-button>
          </el-form-item>

          <el-button link class="w-full" @click="step = 1">返回上一步</el-button>
        </el-form>
      </div>

      <!-- Step 2: Server Log Code -->
      <div v-else-if="step === 2 && method === 'log'">
        <div class="mb-6 bg-amber-50 dark:bg-amber-900/20 p-4 rounded-md border border-amber-100 dark:border-amber-800">
          <p class="text-sm text-amber-800 dark:text-amber-300">
            验证码已写入服务器日志，请联系管理员查看日志获取（有效期 10 分钟）。
          </p>
        </div>

        <el-form
          ref="logStep2FormRef"
          :model="logStep2Form"
          :rules="logStep2Rules"
          label-position="top"
          size="large"
          @submit.prevent="handleResetPasswordByCode"
        >
          <el-form-item label="验证码" prop="code">
            <el-input
              v-model="logStep2Form.code"
              placeholder="请输入服务器日志中的验证码"
            />
          </el-form-item>

          <el-form-item label="新密码" prop="password">
            <el-input
              v-model="logStep2Form.password"
              type="password"
              placeholder="请输入新密码"
              show-password
            />
          </el-form-item>

          <el-form-item label="确认新密码" prop="confirmPassword">
            <el-input
              v-model="logStep2Form.confirmPassword"
              type="password"
              placeholder="请再次输入新密码"
              show-password
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              class="w-full"
              :loading="loading"
              @click="handleResetPasswordByCode"
            >
              重置密码
            </el-button>
          </el-form-item>

          <div class="flex justify-between w-full">
            <el-button link @click="step = 1">返回上一步</el-button>
            <el-button
              link
              :disabled="resendCountdown > 0 || loading"
              @click="handleResendCode"
            >
              {{ resendCountdown > 0 ? `${resendCountdown}s 后可重新发送` : '重新发送验证码' }}
            </el-button>
          </div>
        </el-form>
      </div>

      <div class="text-center mt-4">
        <router-link to="/login" class="text-blue-600 hover:underline text-sm">返回登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { authService } from '@/api/auth';

const router = useRouter();
const step = ref(1);
const loading = ref(false);
const method = ref<'security' | 'log'>('security');
const securityQuestion = ref('');
const resendCountdown = ref(0);
let resendTimer: ReturnType<typeof setInterval> | null = null;

const step1FormRef = ref<FormInstance>();
const step1Form = reactive({
  username: ''
});

const step2FormRef = ref<FormInstance>();
const step2Form = reactive({
  answer: '',
  password: '',
  confirmPassword: ''
});

const logStep2FormRef = ref<FormInstance>();
const logStep2Form = reactive({
  code: '',
  password: '',
  confirmPassword: ''
});

const step1Rules = reactive<FormRules>({
  username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }]
});

const validateConfirmPassword = (passwordRef: () => string) => (rule: any, value: any, callback: any) => {
  if (value !== passwordRef()) {
    callback(new Error('两次输入的密码不一致'));
  } else {
    callback();
  }
};

const step2Rules = reactive<FormRules>({
  answer: [{ required: true, message: '请输入答案', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '长度至少 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirmPassword(() => step2Form.password), trigger: 'blur' }
  ]
});

const logStep2Rules = reactive<FormRules>({
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '长度至少 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirmPassword(() => logStep2Form.password), trigger: 'blur' }
  ]
});

const startResendCountdown = () => {
  if (resendTimer) clearInterval(resendTimer);
  resendCountdown.value = 60;
  resendTimer = setInterval(() => {
    resendCountdown.value -= 1;
    if (resendCountdown.value <= 0) {
      if (resendTimer) {
        clearInterval(resendTimer);
        resendTimer = null;
      }
    }
  }, 1000);
};

onUnmounted(() => {
  if (resendTimer) clearInterval(resendTimer);
});

const handleMethodChange = () => {
  // 切换方式时回到第一步并清空第二步表单
  step.value = 1;
  step2Form.answer = '';
  step2Form.password = '';
  step2Form.confirmPassword = '';
  logStep2Form.code = '';
  logStep2Form.password = '';
  logStep2Form.confirmPassword = '';
};

const handleStep1 = async () => {
  if (!step1FormRef.value) return;
  await step1FormRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      if (method.value === 'security') {
        const res = await authService.checkResetUser({
          username_or_email: step1Form.username
        });
        securityQuestion.value = res.security_question;
        step.value = 2;
      } else {
        const res = await authService.sendLogResetCode({
          username_or_email: step1Form.username
        });
        ElMessage.success(res.msg || '验证码已写入服务器日志');
        startResendCountdown();
        step.value = 2;
      }
    } catch (error: any) {
      // 安全问题方式：后端用 HTTPException，读取 detail 提示
      if (method.value === 'security') {
        const msg = error.response?.data?.detail || '用户不存在或未设置安全问题';
        ElMessage.error(msg);
      }
      // 日志验证码方式：后端用 BaseResponse，响应拦截器已统一提示，这里不再重复弹窗
    } finally {
      loading.value = false;
    }
  });
};

const handleResendCode = async () => {
  loading.value = true;
  try {
    const res = await authService.sendLogResetCode({
      username_or_email: step1Form.username
    });
    ElMessage.success(res.msg || '验证码已重新写入服务器日志');
    startResendCountdown();
  } catch {
    // 响应拦截器已统一提示错误
  } finally {
    loading.value = false;
  }
};

const handleResetPassword = async () => {
  if (!step2FormRef.value) return;
  await step2FormRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await authService.resetPassword({
        username_or_email: step1Form.username,
        security_answer: step2Form.answer,
        new_password: step2Form.password
      });
      ElMessage.success('密码重置成功，请使用新密码登录');
      router.push('/login');
    } catch (error: any) {
      const msg = error.response?.data?.detail || '重置失败，请检查答案';
      ElMessage.error(msg);
    } finally {
      loading.value = false;
    }
  });
};

const handleResetPasswordByCode = async () => {
  if (!logStep2FormRef.value) return;
  await logStep2FormRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      const res = await authService.resetPasswordByCode({
        username_or_email: step1Form.username,
        code: logStep2Form.code,
        new_password: logStep2Form.password
      });
      ElMessage.success(res.msg || '密码重置成功，请使用新密码登录');
      router.push('/login');
    } catch {
      // 响应拦截器已统一提示错误（验证码错误/已过期等）
    } finally {
      loading.value = false;
    }
  });
};
</script>
