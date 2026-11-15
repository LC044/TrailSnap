<template>
  <div class="task-row-main">
    <button type="button" class="task-details-trigger flex min-w-0 items-start gap-3 text-left" :aria-label="`${task.task_name}详情`" :aria-expanded="expanded" :aria-controls="`task-details-${task.category}`" @click="$emit('toggle-expand')">
      <span class="task-state-icon" :class="`task-state-${state}`" :data-active="state === 'pending' || null">
        <component :is="stateIcons[state]" class="h-5 w-5" />
      </span>
      <span class="min-w-0 flex-1">
        <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span class="text-[15px] font-semibold">{{ task.task_name }}</span>
          <span class="task-state-label" :class="`task-state-${state}`">{{ taskStateLabels[state] }}</span>
          <ChevronDown class="h-3.5 w-3.5 ts-muted transition-transform" :class="{ 'rotate-180': expanded }" />
        </span>
        <!-- 空闲行不再重复“暂无待处理任务”：徽章已表达 -->
        <span v-if="task.pending > 0" class="ts-muted mt-1 block text-sm">{{ remainingLabel }}</span>
        <span v-if="task.waiting_reason && task.pending > 0" class="task-waiting-reason mt-1 block text-xs leading-5">{{ task.waiting_reason }}</span>
      </span>
    </button>
    <div class="task-row-actions flex flex-wrap items-center justify-end gap-2">
      <button v-if="task.failed > 0" type="button" class="task-failure-link min-h-11 text-sm font-medium" :aria-label="`${task.task_name}：${task.failed} 项失败，查看详情`" @click="$emit('show-failed')">失败 {{ formatCount(task.failed) }} 项 <ChevronRight class="inline h-4 w-4" /></button>
      <!-- 暂停/继续仅对有排队的类型有意义：空闲行只保留菜单入口 -->
      <button v-if="task.pending > 0" type="button" class="ts-button ts-button-secondary ts-button-sm hidden md:inline-flex" :disabled="disabled" @click="$emit('category-command', task.status === 'paused' ? 'resume' : 'pause')">{{ task.status === 'paused' ? '继续' : '暂停' }}</button>
      <div class="shrink-0">
        <button class="ts-icon-button ts-button-ghost" :aria-label="`${task.task_name}操作`" :aria-expanded="menuOpen" aria-haspopup="menu" :disabled="disabled" @click="$emit('toggle-menu')"><MoreHorizontal class="h-5 w-5" /></button>
        <AdaptiveMenu :model-value="menuOpen" :title="`${task.task_name}操作`" close-on-action @update:model-value="value => $emit('update-menu', value)">
          <button v-if="isMobile" class="ts-action-row" @click="$emit('category-command', task.status === 'paused' ? 'resume' : 'pause')">{{ task.status === 'paused' ? '继续任务' : '暂停任务' }}</button>
          <button class="ts-action-row" @click="$emit('category-command', 'scan_missing')">{{ task.category === 'CLASSIFY_IMAGE_CLIP' ? '执行全库分类' : '执行缺失任务' }}</button>
          <button class="ts-action-row" :disabled="task.failed === 0" @click="$emit('category-command', 'retry')">重试失败任务</button>
          <button v-if="task.category === 'RECOGNIZE_TICKET'" class="ts-action-row" @click="$emit('category-command', 'recover_tickets')">恢复旧版未保存的票据</button>
          <button class="ts-action-row danger" :disabled="task.failed === 0" @click="$emit('category-command', 'delete_failed')">删除失败任务</button>
          <button class="ts-action-row danger" @click="$emit('category-command', 'rebuild')">强制重做此项</button>
        </AdaptiveMenu>
      </div>
    </div>
  </div>
  <div v-if="expanded" :id="`task-details-${task.category}`" class="task-details ts-muted text-sm leading-6">
    <p>{{ task.description }}</p>
    <p class="mt-1">调度优先级 {{ task.priority }} · 待处理 {{ formatCount(task.pending) }} 项 · 失败 {{ formatCount(task.failed) }} 项</p>
    <p v-if="task.status === 'paused'" class="mt-1">此类型已暂停，点击“继续”恢复调度；当前执行中的任务会先完成。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Circle, Clock3, MoreHorizontal, PauseCircle } from 'lucide-vue-next'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { getTaskState, taskStateLabels, type TaskGroup } from '@/utils/taskPresentation'

const props = defineProps<{
  task: TaskGroup
  expanded: boolean
  menuOpen: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  'toggle-expand': []
  'show-failed': []
  'toggle-menu': []
  'update-menu': [value: boolean]
  'category-command': [command: string]
}>()

const isMobile = useMediaQuery('(max-width: 767px)')
const state = computed(() => getTaskState(props.task))
const stateIcons = { paused: PauseCircle, waiting: Clock3, pending: Clock3, failed: AlertCircle, idle: Circle }
const formatCount = (count: number) => count.toLocaleString('zh-CN')
const remainingLabel = computed(() => {
  // 暂停类型的积压会恢复调度，等待类型受阻于外部条件，措辞区分开。
  if (props.task.status === 'paused') return `已暂停 · 积压 ${formatCount(props.task.pending)} 项`
  return `剩余 ${formatCount(props.task.pending)} 项`
})
</script>

<style scoped>
/* 从 TaskManagement.vue 迁移：徽章与状态点渲染在本组件内，样式须随之而来 */
.task-state-icon { display: flex; flex-shrink: 0; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 12px; background: var(--ts-color-surface-muted); color: var(--ts-color-text-secondary); }
.task-state-icon[data-active="true"] .lucide { animation: task-pulse 2.4s var(--ts-ease) infinite; }
@keyframes task-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
@media (prefers-reduced-motion: reduce) { .task-state-icon[data-active="true"] .lucide { animation: none; } }
.task-state-label { border-radius: 6px; padding: 2px 6px; font-size: 11px; line-height: 1.5; background: var(--ts-color-surface-muted); color: var(--ts-color-text-secondary); }
.task-state-pending { color: var(--theme-primary); background: rgba(var(--theme-rgb), .1); }
.task-state-paused, .task-state-waiting { color: #b45309; background: rgb(245 158 11 / 10%); }
.task-state-failed { color: var(--ts-color-danger); background: rgb(239 68 68 / 10%); }
.task-failure-link { color: var(--ts-color-danger); }
.task-waiting-reason { overflow-wrap: anywhere; color: var(--ts-color-text-secondary); }
.task-row-main { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.task-row-main:has(.task-failure-link) .task-row-actions { grid-column: 1 / -1; }
.task-details-trigger { padding-block: 4px; }
.task-details { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--ts-color-divider); }
button:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; border-radius: 8px; }
:global(.dark .task-state-paused), :global(.dark .task-state-waiting) { color: #fbbf24; }
@container task-management (min-width: 560px) {
  .task-row-main:has(.task-failure-link) .task-row-actions { grid-column: auto; }
}
</style>
