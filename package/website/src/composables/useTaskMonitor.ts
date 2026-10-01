import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import { tasksApi, type Task } from '@/api/tasks'

export const isRunningTask = (task: Task | null) => !!task && ['pending', 'processing'].includes(task.status)
export const taskProgress = (task: Task | null) => task?.total_items
  ? Math.max(0, Math.min(100, Math.round((task.processed_items || 0) / task.total_items * 100))) : 0
export const taskStatusText = (status: string, processingLabel = '处理中') => ({
  pending: '等待中', processing: processingLabel, completed: '已完成', failed: '失败', cancelled: '已取消',
}[status] || status)

/** Each monitor owns its request sequence; late responses cannot replace a newer task. */
export function useTaskMonitor(options: {
  loadLatest: () => Promise<Task | null>
  taskType: string
  onCompleted?: (task: Task) => void
  onError?: (error: unknown) => void
}) {
  const activeTask = ref<Task | null>(null)
  const clearing = ref(false)
  const isTaskRunning = computed(() => isRunningTask(activeTask.value))
  let timer: ReturnType<typeof setTimeout> | undefined
  let version = 0
  let disposed = false

  const stop = () => { version++; clearTimeout(timer); timer = undefined }
  const poll = async (generation: number) => {
    const id = activeTask.value?.id
    if (!id || disposed || generation !== version) return
    try {
      const task = await tasksApi.getTask(id)
      if (disposed || generation !== version || activeTask.value?.id !== id) return
      activeTask.value = task
      if (task.status === 'completed') options.onCompleted?.(task)
    } catch (error) { options.onError?.(error) }
    if (!disposed && generation === version && isTaskRunning.value) {
      timer = setTimeout(() => poll(generation), 2000)
    }
  }
  watch(() => [activeTask.value?.id, isTaskRunning.value], () => {
    stop()
    if (isTaskRunning.value) {
      const generation = version
      timer = setTimeout(() => poll(generation), 2000)
    }
  }, { flush: 'sync' })
  const fetchLatestTask = async () => {
    const generation = version
    try {
      const task = await options.loadLatest()
      if (!disposed && generation === version) activeTask.value = task
    } catch (error) { options.onError?.(error) }
  }
  const clearFailedTask = async () => {
    const task = activeTask.value
    if (task?.status !== 'failed' || clearing.value) return
    clearing.value = true
    try {
      await tasksApi.deleteFailedTasks([options.taskType])
      if (activeTask.value?.id === task.id) activeTask.value = null
    } finally { clearing.value = false }
  }
  onMounted(fetchLatestTask)
  onScopeDispose(() => { disposed = true; stop() })
  return { activeTask, isTaskRunning, clearing, clearFailedTask, fetchLatestTask }
}
