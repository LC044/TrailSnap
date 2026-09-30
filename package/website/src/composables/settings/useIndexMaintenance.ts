import { ref, onMounted, onUnmounted } from 'vue';
import { settingsApi } from '@/api/settings';
import { ElMessage } from 'element-plus';
export function useIndexMaintenance() {
  const indexStatus = ref({ running: false, progress: 0, added: 0, deleted: 0, errors: 0, message: '', current_task: '' });
  const logs = ref<any[]>([]);
  let pollTimer: number | null = null;
  const rebuildIndex = async () => {
    try {
      await settingsApi.rebuildIndex();
      ElMessage.success('索引重建任务已启动');
      pollStatus();
    }
    catch {
      ElMessage.error('启动失败');
    }
  };
  const fetchStatus = async () => {
    try {
      indexStatus.value = await settingsApi.getIndexStatus();
    }
    catch (e) { }
  };
  const pollStatus = async () => {
    await fetchStatus();
    await fetchLogs();
    if (indexStatus.value.running) {
      pollTimer = window.setTimeout(pollStatus, 2000);
    }
  };
  const fetchLogs = async () => {
    try {
      logs.value = await settingsApi.getIndexLogs(50);
    }
    catch (e) { }
  };
  onMounted(pollStatus);
  onUnmounted(() => { if (pollTimer)
    clearTimeout(pollTimer); });
  return { indexStatus, logs, rebuildIndex, fetchStatus, pollStatus, fetchLogs };
}
