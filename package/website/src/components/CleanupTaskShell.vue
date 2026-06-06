<!--
  工具箱任务页公共壳：头部、进度面板、起始/错误态、空结果态。
  颜色、图标、文案由父组件传入，差异点收敛到 props。
-->
<template>
  <div class="container mx-auto px-4 flex flex-col">
    <!-- Header -->
    <div class="sticky top-0 z-30 backdrop-blur-md">
      <div class="mx-auto px-4 py-3 flex items-center gap-4 justify-between flex-shrink-0">
        <div class="flex items-center gap-2">
          <button @click="onBack" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 dark:bg-gray-900 rounded-full transition-colors">
            <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
          </button>
          <h1 class="text-xl font-bold text-gray-800 dark:text-gray-100">{{ title }}</h1>
        </div>
        <div class="flex gap-2">
          <button
            v-if="canRescan"
            @click="onRescan"
            class="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg text-sm hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors shadow-sm"
          >
            重新扫描
          </button>
          <button
            v-if="canBulkAction"
            @click="onBulkAction"
            class="px-4 py-2 bg-red-500 text-white rounded-lg text-sm hover:bg-red-600 transition-colors shadow-sm"
          >
            {{ bulkActionLabel }}
          </button>
        </div>
      </div>
    </div>

    <!-- Task Progress -->
    <div v-if="isRunning" class="flex-1 flex flex-col items-center justify-center p-8">
      <div class="w-full max-w-md bg-white dark:bg-gray-800 p-8 rounded-2xl shadow-lg text-center">
        <div class="mb-6 relative">
          <div :class="['w-20 h-20 mx-auto rounded-full border-4 flex items-center justify-center', ringBgClass]">
            <div :class="['animate-spin rounded-full h-10 w-10 border-b-2', spinnerClass]"></div>
          </div>
        </div>
        <h3 class="text-xl font-bold text-gray-800 dark:text-white mb-2">{{ runningTitle }}</h3>
        <p class="text-gray-500 dark:text-gray-400 text-sm mb-6">{{ runningHint }}</p>

        <!-- Progress Bar -->
        <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 mb-2 overflow-hidden">
          <div
            :class="['h-2.5 rounded-full transition-all duration-500', barClass]"
            :style="{ width: progressPercentage + '%' }"
          ></div>
        </div>
        <div class="flex justify-between text-xs text-gray-500 mb-6">
          <span>{{ processedItems }} / {{ totalItems }}</span>
          <span>{{ progressPercentage }}%</span>
        </div>

        <button
          @click="onCancel"
          class="text-red-500 hover:text-red-600 text-sm font-medium hover:bg-red-50 dark:hover:bg-red-900/20 px-4 py-2 rounded-lg transition-colors"
        >
          取消任务
        </button>
      </div>
    </div>

    <!-- Error / Start State -->
    <div v-else-if="showStart" class="flex-1 flex flex-col items-center justify-center">
      <div v-if="taskStatus === 'failed'" class="text-red-500 mb-4">
        任务失败: {{ taskError }}
      </div>
      <div v-else-if="taskStatus === 'cancelled'" class="text-orange-500 mb-4">
        任务已取消
      </div>

      <div class="text-center max-w-sm">
        <div :class="['w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6 text-4xl', startIconBgClass]">
          {{ startIcon }}
        </div>
        <h2 class="text-xl font-bold text-gray-800 dark:text-gray-100 mb-2">{{ startTitle }}</h2>
        <p class="text-gray-500 dark:text-gray-400 mb-8">
          {{ startDescription }}
        </p>
        <button
          @click="onStart"
          :class="['px-8 py-3 text-white rounded-xl shadow-lg transition-all transform hover:scale-105 font-medium', startButtonClass]"
        >
          开始扫描
        </button>
      </div>
    </div>

    <!-- Empty Result -->
    <div v-else-if="showEmpty" class="flex-1 flex flex-col items-center justify-center text-gray-500 dark:text-gray-400">
      <i class="mgc_check_circle_line text-4xl mb-2 text-green-500"></i>
      <p>{{ emptyTitle }}</p>
      <p class="text-sm mt-2 opacity-70">{{ emptyHint }}</p>
      <button
        @click="onRescan"
        class="mt-6 px-6 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        重新扫描
      </button>
    </div>

    <!-- Actual Result Content (slot) -->
    <slot v-else />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ArrowLeft } from 'lucide-vue-next';

export type TaskColor = 'blue' | 'orange' | 'emerald' | 'rose' | 'violet';

const props = withDefaults(defineProps<{
  title: string;
  color?: TaskColor;
  // Header actions
  canRescan?: boolean;
  canBulkAction?: boolean;
  bulkActionLabel?: string;
  // Progress
  isRunning: boolean;
  runningTitle: string;
  runningHint?: string;
  processedItems: number;
  totalItems: number;
  // Start state
  showStart: boolean;
  startIcon: string;
  startTitle: string;
  startDescription: string;
  // Empty state
  showEmpty: boolean;
  emptyTitle: string;
  emptyHint?: string;
  // Task status (for failed/cancelled display)
  taskStatus?: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled' | null;
  taskError?: string | null;
}>(), {
  color: 'blue',
  canRescan: false,
  canBulkAction: false,
  bulkActionLabel: '一键清理',
  runningHint: '这可能需要几分钟，请耐心等待...',
  taskStatus: null,
  taskError: null,
  emptyHint: '您的相册很整洁！',
});

const emit = defineEmits<{
  (e: 'back'): void;
  (e: 'rescan'): void;
  (e: 'bulk-action'): void;
  (e: 'cancel'): void;
  (e: 'start'): void;
}>();

const progressPercentage = computed(() => {
  if (props.totalItems <= 0) return 0;
  return Math.min(100, Math.round((props.processedItems / props.totalItems) * 100));
});

const colorClassMap: Record<TaskColor, { ring: string; bar: string; iconBg: string; btn: string; spinner: string }> = {
  blue:    { ring: 'border-blue-100 dark:border-blue-900/30',   bar: 'bg-blue-600',   iconBg: 'bg-blue-50 dark:bg-blue-900/20 text-blue-500',     btn: 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/30',     spinner: 'border-blue-500' },
  orange:  { ring: 'border-orange-100 dark:border-orange-900/30', bar: 'bg-orange-500', iconBg: 'bg-orange-50 dark:bg-orange-900/20 text-orange-500', btn: 'bg-orange-500 hover:bg-orange-600 shadow-orange-500/30', spinner: 'border-orange-500' },
  emerald: { ring: 'border-emerald-100 dark:border-emerald-900/30', bar: 'bg-emerald-600', iconBg: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-500', btn: 'bg-emerald-600 hover:bg-emerald-700 shadow-emerald-500/30', spinner: 'border-emerald-500' },
  rose:    { ring: 'border-rose-100 dark:border-rose-900/30',   bar: 'bg-rose-600',   iconBg: 'bg-rose-50 dark:bg-rose-900/20 text-rose-500',     btn: 'bg-rose-600 hover:bg-rose-700 shadow-rose-500/30',     spinner: 'border-rose-500' },
  violet:  { ring: 'border-violet-100 dark:border-violet-900/30', bar: 'bg-violet-600', iconBg: 'bg-violet-50 dark:bg-violet-900/20 text-violet-500', btn: 'bg-violet-600 hover:bg-violet-700 shadow-violet-500/30', spinner: 'border-violet-500' },
};

const colorClasses = computed(() => colorClassMap[props.color]);
const ringBgClass = computed(() => colorClasses.value.ring);
const barClass = computed(() => colorClasses.value.bar);
const startIconBgClass = computed(() => colorClasses.value.iconBg);
const startButtonClass = computed(() => `${colorClasses.value.btn} ${colorClasses.value.spinner}`);
const spinnerClass = computed(() => colorClasses.value.spinner);

const onBack = () => emit('back');
const onRescan = () => emit('rescan');
const onBulkAction = () => emit('bulk-action');
const onCancel = () => emit('cancel');
const onStart = () => emit('start');
</script>
