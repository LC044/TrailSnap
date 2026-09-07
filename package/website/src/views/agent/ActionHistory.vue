<template>
  <main class="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
    <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary-600">AI 安全与审计</p>
        <h1 class="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">操作记录</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">查看 Agent 提议、执行和撤销过的相册修改。</p>
      </div>
      <button type="button" class="self-start rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800" @click="loadPlans">
        <RefreshCw class="mr-1 inline h-4 w-4" />刷新
      </button>
    </header>

    <div class="mb-5 flex gap-2 overflow-x-auto pb-1">
      <button v-for="item in filters" :key="item.value" type="button" class="shrink-0 rounded-full px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" :class="status === item.value ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'" @click="status = item.value; loadPlans()">{{ item.label }}</button>
    </div>

    <div v-if="loading" class="py-16 text-center text-sm text-gray-500 dark:text-gray-400">正在加载操作记录…</div>
    <div v-else-if="plans.length" class="grid gap-4 lg:grid-cols-2">
      <article v-for="plan in plans" :key="plan.id" class="rounded-2xl border border-gray-200 bg-white p-1 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <AgentActionPlanCard :plan="plan" />
        <p class="px-3 pb-3 text-xs text-gray-400 dark:text-gray-500">创建于 {{ formatTime(plan.created_at) }} · 尝试 {{ plan.attempt_count || 0 }} 次</p>
      </article>
    </div>
    <div v-else class="rounded-2xl border border-dashed border-gray-300 bg-gray-50 py-20 text-center dark:border-gray-700 dark:bg-gray-900">
      <ShieldCheck class="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
      <p class="mt-3 text-gray-600 dark:text-gray-300">暂无符合条件的 Agent 操作</p>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { RefreshCw, ShieldCheck } from 'lucide-vue-next';
import { ElMessage } from 'element-plus';
import { agentApi, type AgentActionPlan } from '@/api/agent';
import AgentActionPlanCard from './components/AgentActionPlanCard.vue';

const plans = ref<AgentActionPlan[]>([]);
const loading = ref(false);
const status = ref('');
const filters = [
  { label: '全部', value: '' }, { label: '待确认', value: 'proposed' },
  { label: '已执行', value: 'executed' }, { label: '已撤销', value: 'undone' },
  { label: '已拒绝', value: 'rejected' }, { label: '执行失败', value: 'failed' }, { label: '已过期', value: 'expired' },
];
const formatTime = (value?: string) => value ? new Date(value).toLocaleString() : '—';
const loadPlans = async () => {
  loading.value = true;
  try {
    const response: any = await agentApi.listActionPlans({ status: status.value || undefined, limit: 100 });
    plans.value = response.data || [];
  } catch {
    ElMessage.error('加载 Agent 操作记录失败');
  } finally { loading.value = false; }
};
onMounted(loadPlans);
</script>
