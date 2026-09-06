<template>
  <section class="mt-3 w-full overflow-hidden rounded-xl border border-primary-500/30 bg-slate-50 dark:bg-slate-900" aria-label="Agent 操作计划">
    <header class="flex items-start gap-3 p-3">
      <div class="rounded-lg bg-primary-500/10 p-2 text-primary-600"><FolderPlus class="h-5 w-5" /></div>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2"><h3 class="font-medium text-slate-900 dark:text-white">{{ current.title }}</h3><span class="rounded-full px-2 py-0.5 text-xs" :class="statusClass">{{ statusLabel }}</span></div>
        <p v-if="current.summary" class="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">{{ current.summary }}</p>
      </div>
    </header>

    <div class="border-t border-slate-200 px-3 py-3 dark:border-slate-700">
      <div class="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div class="rounded-lg bg-white p-2 dark:bg-slate-800"><span class="block text-slate-500 dark:text-slate-400">操作</span><strong class="mt-0.5 block text-slate-800 dark:text-slate-100">{{ current.preview.mode === 'update' ? '更新相册' : '创建相册' }}</strong></div>
        <div class="rounded-lg bg-white p-2 dark:bg-slate-800"><span class="block text-slate-500 dark:text-slate-400">照片</span><strong class="mt-0.5 block text-slate-800 dark:text-slate-100">{{ current.preview.photo_count || 0 }} 张</strong></div>
        <div class="rounded-lg bg-white p-2 dark:bg-slate-800"><span class="block text-slate-500 dark:text-slate-400">标签</span><strong class="mt-0.5 block truncate text-slate-800 dark:text-slate-100">{{ tagsLabel }}</strong></div>
        <div class="rounded-lg bg-white p-2 dark:bg-slate-800"><span class="block text-slate-500 dark:text-slate-400">原文件</span><strong class="mt-0.5 block text-primary-600">不会修改</strong></div>
      </div>

      <div v-if="samplePhotos.length" class="mt-3 flex gap-1.5 overflow-x-auto pb-1">
        <img v-for="photo in samplePhotos" :key="photo.photo_id" :src="toServerUrl(photo.thumbnail_url)" class="h-14 w-14 shrink-0 rounded-lg object-cover" loading="lazy" alt="待整理照片" />
      </div>
      <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">{{ current.preview.notice }}</p>
      <p v-if="current.error_message" class="mt-2 rounded-lg bg-red-50 px-2.5 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">{{ current.error_message }}</p>

      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button v-if="current.status === 'proposed'" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-xs font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="execute">
          <LoaderCircle v-if="busy" class="h-3.5 w-3.5 animate-spin" /><CircleCheck v-else class="h-3.5 w-3.5" />确认执行
        </button>
        <button v-if="current.status === 'proposed'" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800" @click="reject"><XCircle class="h-3.5 w-3.5" />拒绝方案</button>
        <button v-if="current.status === 'executed'" type="button" class="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-700 hover:bg-white dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="openAlbum"><ExternalLink class="h-3.5 w-3.5" />打开相册</button>
        <button v-if="current.status === 'executed'" type="button" :disabled="busy" class="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-600 hover:bg-white disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="undo"><Undo2 class="h-3.5 w-3.5" />撤销操作</button>
        <button v-if="artifactUrl" type="button" class="inline-flex items-center gap-1.5 rounded-lg border border-primary-500/40 px-3 py-2 text-xs text-primary-600 hover:bg-primary-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="router.push(artifactUrl)"><BookOpen class="h-3.5 w-3.5" />查看旅行日志</button>
        <span v-if="current.status === 'undone'" class="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400"><Undo2 class="h-3.5 w-3.5" />修改已撤销</span>
        <span v-if="current.status === 'rejected'" class="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400"><XCircle class="h-3.5 w-3.5" />方案已拒绝，未执行任何修改</span>
        <span v-if="current.status === 'expired'" class="text-xs text-amber-700 dark:text-amber-300">计划已过期，请在 Agent 中重新生成</span>
        <span v-if="current.status === 'failed'" class="text-xs text-red-700 dark:text-red-300">执行失败，请在 Agent 中重新生成计划</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { BookOpen, CircleCheck, ExternalLink, FolderPlus, LoaderCircle, Undo2, XCircle } from 'lucide-vue-next';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useRouter } from 'vue-router';
import { agentApi, type AgentActionPlan } from '@/api/agent';
import { toServerUrl } from '@/config/server';

const props = defineProps<{ plan: AgentActionPlan }>();
const current = ref<AgentActionPlan>({ ...props.plan });
const busy = ref(false);
const router = useRouter();
const samplePhotos = computed(() => current.value.preview?.sample_photos || []);
const tagsLabel = computed(() => current.value.preview?.tags?.length ? current.value.preview.tags.join('、') : '不添加');
const artifactUrl = computed(() => current.value.result?.artifact_url || current.value.preview?.artifact_url || '');
const statusLabel = computed(() => ({ proposed: '等待确认', executed: '已执行', undone: '已撤销', rejected: '已拒绝', expired: '已过期', failed: '执行失败' }[current.value.status] || current.value.status));
const statusClass = computed(() => current.value.status === 'executed' ? 'bg-primary-500/10 text-primary-600' : current.value.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : ['undone', 'rejected'].includes(current.value.status) ? 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300');

const execute = async () => {
  try {
    await ElMessageBox.confirm(`将按计划整理 ${current.value.preview.photo_count || 0} 张照片。不会删除、移动或重命名原文件。`, '确认执行相册整理', { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' });
    busy.value = true;
    const response: any = await agentApi.executeActionPlan(current.value.id);
    current.value = response.data;
    ElMessage.success('相册整理完成，可随时撤销');
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('执行计划失败');
  } finally { busy.value = false; }
};

const reject = async () => {
  try {
    await ElMessageBox.confirm('拒绝后不会执行任何相册修改，且该方案不能再次确认。', '拒绝相册方案', { confirmButtonText: '确认拒绝', cancelButtonText: '返回查看' });
    busy.value = true;
    const response: any = await agentApi.rejectActionPlan(current.value.id);
    current.value = response.data;
    ElMessage.success('已拒绝方案，未修改相册');
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('拒绝方案失败');
  } finally { busy.value = false; }
};

const undo = async () => {
  try {
    await ElMessageBox.confirm('撤销本次相册关系、封面、简介和标签修改？原始照片不会受影响。', '撤销操作', { confirmButtonText: '确认撤销', cancelButtonText: '取消' });
    busy.value = true;
    const response: any = await agentApi.undoActionPlan(current.value.id);
    current.value = response.data;
    ElMessage.success('操作已撤销');
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('撤销失败');
  } finally { busy.value = false; }
};

const openAlbum = () => {
  const url = current.value.result?.album_url;
  if (url) router.push(url);
};

onMounted(async () => {
  try {
    const response: any = await agentApi.getActionPlan(current.value.id);
    current.value = response.data;
  } catch {
    // The message can still show its immutable preview if refreshing status fails.
  }
});
</script>
