<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 px-4">
    <el-card class="w-full max-w-md shadow-lg">
      <template #header>
        <div class="text-center">
          <h2 class="text-xl font-bold text-gray-800 dark:text-white">注册 TrailSnap 账号</h2>
        </div>
      </template>
      
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent="handleRegister"
      >
        <el-form-item label="用户名" prop="username">
          <el-input 
            v-model="form.username" 
            placeholder="请输入用户名"
          />
        </el-form-item>

        <el-form-item label="昵称" prop="nickname">
          <el-input 
            v-model="form.nickname" 
            placeholder="请输入昵称"
          />
        </el-form-item>

        <el-form-item label="电子邮箱" prop="email">
          <el-input 
            v-model="form.email" 
            placeholder="请输入电子邮箱"
          />
        </el-form-item>
        
        <el-form-item label="密码" prop="password">
          <el-input 
            v-model="form.password" 
            type="password" 
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input 
            v-model="form.confirmPassword" 
            type="password" 
            placeholder="请再次输入密码"
            show-password
          />
        </el-form-item>

        <el-divider>安全问题（用于找回密码）</el-divider>

        <el-form-item label="安全问题" prop="security_question">
          <el-select v-model="form.security_question" placeholder="请选择安全问题" class="w-full">
            <el-option label="你第一所小学的名字是？" value="你第一所小学的名字是？" />
            <el-option label="你出生的城市是？" value="你出生的城市是？" />
            <el-option label="你最喜欢的电影是？" value="你最喜欢的电影是？" />
            <el-option label="你母亲的姓氏是？" value="你母亲的姓氏是？" />
            <el-option label="自定义问题" value="custom" />
          </el-select>
        </el-form-item>

        <el-form-item 
          v-if="form.security_question === 'custom'" 
          label="自定义问题" 
          prop="custom_question"
        >
          <el-input 
            v-model="form.custom_question" 
            placeholder="请输入自定义问题"
          />
        </el-form-item>

        <el-form-item label="问题答案" prop="security_answer">
          <el-input 
            v-model="form.security_answer" 
            placeholder="请输入答案"
          />
        </el-form-item>

        <el-form-item>
          <el-button 
            type="primary" 
            class="w-full" 
            :loading="loading" 
            @click="handleRegister"
          >
            注册
          </el-button>
        </el-form-item>

        <div class="text-center mt-4">
          <router-link to="/login" class="text-blue-600 hover:underline text-sm">已有账号？立即登录</router-link>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { authService } from '@/api/auth';

const router = useRouter();
const formRef = ref<FormInstance>();
const loading = ref(false);

onMounted(async () => {
  try {
    const status = await authService.getAuthStatus();
    // Block registration only when there are already users AND registration is disabled
    if (status.has_users && !status.allow_registration) {
      ElMessage.warning('注册已关闭，请联系管理员添加账号。');
      router.push('/login');
    }
  } catch (error) {
    console.error('Failed to get auth status:', error);
  }
});

const form = reactive({
  username: '',
  nickname: '',
  email: '',
  password: '',
  confirmPassword: '',
  security_question: '',
  custom_question: '',
  security_answer: ''
});

const validateConfirmPassword = (rule: any, value: any, callback: any) => {
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'));
  } else {
    callback();
  }
};

const rules = reactive<FormRules>({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '长度至少 3 个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '长度至少 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ],
  security_question: [
    { required: true, message: '请选择安全问题', trigger: 'change' }
  ],
  custom_question: [
    { 
      validator: (rule, value, callback) => {
        if (form.security_question === 'custom' && !value) {
          callback(new Error('请输入自定义问题'));
        } else {
          callback();
        }
      }, 
      trigger: 'blur' 
    }
  ],
  security_answer: [
    { required: true, message: '请输入答案', trigger: 'blur' }
  ]
});

const handleRegister = async () => {
  if (!formRef.value) return;
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true;
      try {
        const question = form.security_question === 'custom' ? form.custom_question : form.security_question;
        
        await authService.register({
          username: form.username,
          nickname: form.nickname,
          email: form.email,
          password: form.password,
          security_question: question,
          security_answer: form.security_answer
        });
        
        ElMessage.success('注册成功，请登录');
        router.push('/login');
      } catch (error: any) {
        const msg = error.response?.data?.detail || '注册失败';
        ElMessage.error(msg);
      } finally {
        loading.value = false;
      }
    }
  });
};
</script>
