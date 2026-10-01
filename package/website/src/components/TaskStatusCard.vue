<template>
  <div v-if="task" class="mb-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
    <div class="mb-4 flex items-center justify-between">
      <h3 class="flex items-center gap-2 text-lg font-bold">
        <Loader2 v-if="isRunningTask(task)" class="h-5 w-5 animate-spin text-primary-500" />
        <CheckCircle2 v-else-if="task.status === 'completed'" class="h-5 w-5 text-green-500" />
        <XCircle v-else class="h-5 w-5 text-red-500" />
        任务状态: {{ taskStatusText(task.status, processingLabel) }}
      </h3>
      <span class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ task.processed_items || 0 }} / {{ task.total_items || 0 }}</span>
    </div>
    <el-progress :percentage="taskProgress(task)" :status="task.status === 'completed' ? 'success' : task.status === 'failed' ? 'exception' : ''" :stroke-width="12" striped :striped-flow="task.status === 'processing'" />
    <div v-if="task.status === 'failed' || task.error" class="mt-4 flex items-center justify-between rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
      <span>{{ task.error || '任务执行失败，未知错误' }}</span>
      <el-button v-if="task.status === 'failed'" type="danger" size="small" plain :loading="clearing" @click="$emit('clear')">清除失败任务</el-button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { Loader2, CheckCircle2, XCircle } from 'lucide-vue-next'
import type { Task } from '@/api/tasks'
import { isRunningTask, taskProgress, taskStatusText } from '@/composables/useTaskMonitor'
withDefaults(defineProps<{ task: Task | null; processingLabel?: string; clearing?: boolean }>(), { processingLabel: '处理中', clearing: false })
defineEmits<{ clear: [] }>()
</script>
