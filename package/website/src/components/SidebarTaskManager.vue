<template>
  <div v-if="shouldShow" class="mb-2 bg-slate-50 dark:bg-slate-800/50 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700/50 transition-all">
    <!-- Header / Toggle -->
    <div
      class="flex items-center px-3 py-2.5 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
      @click="toggleExpand"
      :title="isCollapsed ? '后台任务' : undefined"
    >
      <Loader2 v-if="hasPending" class="w-5 h-5 shrink-0 text-primary-500 animate-spin" />
      <CheckCircle2 v-else class="w-5 h-5 shrink-0 text-emerald-500" />
      
      <transition name="fade">
        <div v-if="!isCollapsed" class="ml-3 flex-1 flex items-center justify-between overflow-hidden">
          <span class="text-sm text-slate-700 dark:text-slate-300 truncate">
            {{ hasPending ? `处理中 (${totalPending})` : '任务已完成' }}
          </span>
          <ChevronDown
            class="w-4 h-4 text-slate-400 transition-transform duration-200 shrink-0"
            :class="{ 'rotate-180': expanded }"
          />
        </div>
      </transition>
    </div>

    <!-- Expanded Body -->
    <div v-show="!isCollapsed && expanded" class="px-3 pb-2 pt-2 max-h-48 overflow-y-auto custom-scrollbar border-t border-slate-100 dark:border-slate-700/50">
      <div v-if="activeCategories.length === 0" class="py-2 text-center text-xs text-slate-500">
        没有正在处理的任务
      </div>
      <div
        v-for="cat in activeCategories"
        :key="cat.category"
        class="py-1.5 flex flex-col gap-1"
      >
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-slate-600 dark:text-slate-300 truncate pr-2">
            {{ cat.task_name }}
          </span>
          <span class="text-xs text-slate-500 dark:text-slate-400 shrink-0">
            剩余 {{ cat.pending }}
          </span>
        </div>
        <el-progress
          :percentage="100"
          :show-text="false"
          :stroke-width="4"
          status="success"
          class="!my-0 task-progress-bar"
          :indeterminate="true"
        />
      </div>
      
      <div class="mt-2 pt-2 border-t border-slate-100 dark:border-slate-700/50 flex justify-between items-center">
        <span v-if="totalFailed > 0" class="text-xs text-red-500">
          {{ totalFailed }} 个任务失败
        </span>
        <span v-else></span>
        <button
          @click="goToTasks"
          class="text-xs text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 font-medium"
        >
          查看详情 →
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2, ChevronDown, CheckCircle2 } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useDebounceFn } from '@vueuse/core'
import { tasksApi } from '@/api/tasks'
import { useTaskNotifyStore } from '@/stores/taskNotifyStore'

// 定义数据类型，消灭 any
interface TaskCategoryStatus {
  category: string
  task_name: string
  pending: number
  failed: number
}

const props = defineProps<{
  isCollapsed: boolean
}>()

const router = useRouter()
const store = useTaskNotifyStore()

const expanded = ref(false)
const groupedStatus = ref<TaskCategoryStatus[]>([])
let pollTimer: number | null = null
let successTimer: number | null = null // 用于清理 success 定时器

const activeCategories = computed(() => {
  return groupedStatus.value.filter(cat => cat.pending > 0)
})

const totalPending = computed(() => {
  return activeCategories.value.reduce((sum, cat) => sum + cat.pending, 0)
})

const totalFailed = computed(() => {
  return groupedStatus.value.reduce((sum, cat) => sum + cat.failed, 0)
})

const hasPending = computed(() => totalPending.value > 0)
const wasPending = ref(false)
const showSuccess = ref(false)
const shouldShow = computed(() => hasPending.value || showSuccess.value)

const fetchStatus = async () => {
  try {
    const data = await tasksApi.getGroupedStatus()
    groupedStatus.value = data
    
    // Logic for completion
    if (totalPending.value > 0) {
      wasPending.value = true
      showSuccess.value = false
      if (successTimer) {
        window.clearTimeout(successTimer)
        successTimer = null
      }
    } else if (wasPending.value && totalPending.value === 0) {
      // Transitioned from pending to completed
      ElMessage.success('所有后台任务已处理完成')
      wasPending.value = false
      showSuccess.value = true
      expanded.value = false
      
      // 清理旧定时器，防止竞态条件导致状态异常
      if (successTimer) window.clearTimeout(successTimer)
      successTimer = window.setTimeout(() => {
        showSuccess.value = false
      }, 3000)
    }
  } catch (e) {
    // Ignore
  }
}

const toggleExpand = () => {
  if (props.isCollapsed) return // Do nothing if sidebar is collapsed
  expanded.value = !expanded.value
}

// 优化轮询机制：基于 setTimeout 的递归，避免网络阻塞时请求堆积
const startPolling = () => {
  if (pollTimer) return
  
  const loop = async () => {
    await fetchStatus()
    pollTimer = window.setTimeout(loop, 5000)
  }
  loop()
}

const stopPolling = () => {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
  if (successTimer) {
    window.clearTimeout(successTimer)
    successTimer = null
  }
}

// 监听后端事件推送，加上防抖，限制 1 秒内最多触发 1 次
const handleEvent = useDebounceFn(() => {
  // 收到推送说明状态有变，先停止当前轮询
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
  // 重新发起请求，并自动开启新一轮的 5 秒倒计时
  startPolling()
}, 1000)

watch(() => store.lastEventAt, () => {
  handleEvent()
})

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

const goToTasks = () => {
  router.push({ path: '/settings', query: { tab: 'tasks' } })
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #475569;
}

/* Make indeterminate progress bar move */
:deep(.task-progress-bar .el-progress-bar__inner) {
  background-image: linear-gradient(
    45deg,
    rgba(255, 255, 255, 0.15) 25%,
    transparent 25%,
    transparent 50%,
    rgba(255, 255, 255, 0.15) 50%,
    rgba(255, 255, 255, 0.15) 75%,
    transparent 75%,
    transparent
  );
  background-size: 1rem 1rem;
  animation: progress-stripes 1s linear infinite;
}

@keyframes progress-stripes {
  0% {
    background-position: 1rem 0;
  }
  100% {
    background-position: 0 0;
  }
}
</style>
