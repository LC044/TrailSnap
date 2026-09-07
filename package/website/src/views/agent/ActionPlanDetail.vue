<template>
  <main class="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
    <button type="button" class="mb-5 inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-gray-300 dark:hover:bg-gray-800" @click="router.push('/agent/actions')">
      <ArrowLeft class="h-4 w-4" />操作记录
    </button>

    <header class="mb-5 rounded-2xl border border-primary-500/20 bg-primary-500/5 p-5">
      <div class="flex items-start gap-3">
        <div class="rounded-xl bg-primary-500/10 p-2.5 text-primary-600"><ShieldCheck class="h-6 w-6" /></div>
        <div>
          <p class="text-sm font-medium text-primary-600">需要你的确认</p>
          <h1 class="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">AI 相册整理方案</h1>
          <p class="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">Agent 只能提出方案。确认前不会创建相册、添加标签或修改照片关系；原始文件不会被删除、移动或重命名。</p>
        </div>
      </div>
    </header>

    <div v-if="loading" class="py-20 text-center text-sm text-gray-500 dark:text-gray-400">正在加载方案…</div>
    <div v-else-if="plan" class="rounded-2xl border border-gray-200 bg-white p-1 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <AgentActionPlanCard :plan="plan" />
      <p class="px-4 pb-4 text-xs text-gray-400 dark:text-gray-500">方案创建于 {{ formatTime(plan.created_at) }}，有效期至 {{ formatTime(plan.expires_at || undefined) }}</p>
    </div>
    <div v-else class="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-5 py-16 text-center dark:border-gray-700 dark:bg-gray-900">
      <p class="text-gray-700 dark:text-gray-200">无法加载该方案</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">方案可能不存在、已不属于当前账号，或链接无效。</p>
      <button type="button" class="mt-4 rounded-lg bg-primary-600 px-4 py-2 text-sm text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="loadPlan">重新加载</button>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ArrowLeft, ShieldCheck } from 'lucide-vue-next';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { agentApi, type AgentActionPlan } from '@/api/agent';
import AgentActionPlanCard from './components/AgentActionPlanCard.vue';

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const plan = ref<AgentActionPlan | null>(null);
const formatTime = (value?: string) => value ? new Date(value).toLocaleString() : '—';
const loadPlan = async () => {
  loading.value = true;
  try {
    const response: any = await agentApi.getActionPlan(String(route.params.id));
    plan.value = response.data;
  } catch {
    plan.value = null;
    ElMessage.error('加载 Agent 操作方案失败');
  } finally {
    loading.value = false;
  }
};
onMounted(loadPlan);
</script>
