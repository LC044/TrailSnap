<template>
  <div class="agent-history mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
    <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="journal-page-title">Agent 任务中心</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">查看待确认操作、后台进度、失败重试、安全清理与撤销记录。</p>
      </div>
      <button type="button" class="ts-button ts-button-secondary self-start border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800" @click="loadPlans">
        <RefreshCw class="mr-1 inline h-4 w-4" />刷新
      </button>
    </header>

    <nav class="agent-state-nav" aria-label="操作状态">
      <button v-for="item in filters" :key="item.value" type="button" :aria-pressed="status === item.value" @click="status = item.value; loadPlans()">{{ item.label }}</button>
    </nav>

    <div v-if="loading" class="py-16 text-center text-sm text-gray-500 dark:text-gray-400">正在加载操作记录…</div>
    <div v-else-if="failed" role="status" class="ts-surface p-5">
      <p>操作记录暂时无法加载</p>
      <button type="button" class="ts-button ts-button-secondary mt-3" @click="loadPlans">重试</button>
    </div>
    <div v-else-if="plans.length" class="agent-history-grid">
      <article v-for="plan in plans" :key="plan.id" class="ts-surface min-w-0 p-1">
        <AgentActionPlanCard :plan="plan" />
        <p class="px-3 pb-3 text-xs text-gray-400 dark:text-gray-500">创建于 {{ formatTime(plan.created_at) }} · 尝试 {{ plan.attempt_count || 0 }} 次</p>
      </article>
    </div>
    <div v-else class="rounded-2xl border border-dashed border-gray-300 bg-gray-50 py-20 text-center dark:border-gray-700 dark:bg-gray-900">
      <ShieldCheck class="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
      <p class="mt-3 text-gray-600 dark:text-gray-300">暂无符合条件的 Agent 操作</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { RefreshCw, ShieldCheck } from 'lucide-vue-next';
import { agentApi, type AgentActionPlan } from '@/api/agent';
import AgentActionPlanCard from './components/AgentActionPlanCard.vue';

const plans = ref<AgentActionPlan[]>([]);
const loading = ref(false);
const failed = ref(false);
let loadRevision = 0;
const status = ref('');
const filters = [
  { label: '全部', value: '' }, { label: '待确认', value: 'proposed' },
  { label: '已执行', value: 'executed' }, { label: '已撤销', value: 'undone' },
  { label: '已拒绝', value: 'rejected' }, { label: '执行失败', value: 'failed' }, { label: '已过期', value: 'expired' },
];
const formatTime = (value?: string) => value ? new Date(value).toLocaleString() : '—';
const loadPlans = async () => {
  const revision = ++loadRevision;
  loading.value = true;
  failed.value = false;
  try {
    const response: any = await agentApi.listActionPlans({ status: status.value || undefined, limit: 100 });
    if (revision === loadRevision) plans.value = response.data || [];
  } catch {
    if (revision === loadRevision) failed.value = true;
  } finally { if (revision === loadRevision) loading.value = false; }
};
onMounted(loadPlans);
</script>

<style scoped>
.agent-history-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.agent-state-nav { display: flex; gap: 6px; max-width: 100%; overflow: auto hidden; margin-bottom: 17px; padding: 3px 0 7px; }
.agent-state-nav button { min-height: 44px; padding: 0 13px; flex-shrink: 0; border-radius: 999px; font-size: 13px; background: var(--ts-color-surface); color: var(--ts-color-text-secondary); }
.agent-state-nav button[aria-pressed="true"] { background: var(--ts-journal-active); color: var(--ts-journal-accent-text); font-weight: 700; }
.agent-state-nav button:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: -2px; }
@media (min-width: 1024px) { .agent-history-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
