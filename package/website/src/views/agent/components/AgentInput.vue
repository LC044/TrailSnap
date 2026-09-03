<template>
  <div class="agent-chat-input-area">
    <div class="w-full max-w-4xl mx-auto">
      <form @submit.prevent="handleSubmit" class="relative">
        <textarea
          ref="textareaRef"
          :value="modelValue"
          @input="handleInput"
          @keydown.enter="handleEnter"
          rows="1"
          :placeholder="placeholder"
          class="agent-input"
          :disabled="isSelectionMode"
        ></textarea>
        <button
          v-if="isGenerating"
          type="button"
          @click.prevent="emit('abort')"
          class="agent-stop-btn"
          title="终止"
        >
          <Square class="w-4 h-4 fill-current" />
        </button>
        <button
          v-else
          type="submit"
          class="agent-send-btn"
          :disabled="!modelValue.trim() || isSelectionMode"
        >
          <Send class="w-4 h-4" />
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue';
import { Send, Square } from 'lucide-vue-next';

const props = defineProps<{
  modelValue: string;
  isGenerating: boolean;
  isSelectionMode: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'send'): void;
  (e: 'abort'): void;
}>();

const textareaRef = ref<HTMLTextAreaElement | null>(null);

// 输入框最大高度（约 6 行），超出后内部滚动，避免撑高整个对话弹窗
const MAX_HEIGHT = 120;

/**
 * 触摸设备（手机 / 平板）上软键盘没有 Shift 键，若 Enter 直接发送，用户将永远无法输入多行。
 * 因此与 ChatGPT / Claude 移动端一致：触摸设备 Enter 换行，发送只走右侧按钮。
 * 用 hover/pointer 媒体查询判断，比 UA 嗅探可靠。
 */
const isTouchDevice =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(hover: none) and (pointer: coarse)').matches;

const placeholder = computed(() =>
  isTouchDevice
    ? '问问我关于您的照片或行程...'
    : '问问我关于您的照片或行程...（Shift + Enter 换行）'
);

/** 根据内容自适应高度：先归零再按 scrollHeight 回写，并限制上限 */
const resize = () => {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
};

const handleInput = (e: Event) => {
  const el = e.target as HTMLTextAreaElement;
  emit('update:modelValue', el.value);
  resize();
};

const handleSubmit = () => {
  if (!props.modelValue.trim() || props.isGenerating || props.isSelectionMode) return;
  emit('send');
};

const handleEnter = (e: KeyboardEvent) => {
  // 中文等输入法组合输入期间（选词时）按 Enter 属于确认候选词，不能当作发送
  if (e.isComposing) return;
  // 显式换行：Shift/Ctrl/Meta/Alt + Enter，以及触摸设备的裸 Enter
  if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || isTouchDevice) return;
  e.preventDefault();
  handleSubmit();
};

// 外部清空（发送成功后 AgentChat 会重置 inputMessage）或程序化填充（重新生成 / 编辑消息）
// 时同步高度，避免发送后输入框仍停留在多行高度。
watch(
  () => props.modelValue,
  () => nextTick(resize)
);

onMounted(resize);
</script>

<style scoped>
.agent-chat-input-area {
  @apply p-4 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800;
}

.agent-input {
  @apply w-full pl-4 pr-12 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-800 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed;
  /* 自适应高度由 JS 控制，这里禁用手动拖拽并隐藏初始滚动条 */
  @apply resize-none overflow-y-auto leading-6;
  max-height: 120px;
}

/* 输入框可变高，按钮改为贴底对齐（原先垂直居中会在多行时飘到中间） */
.agent-send-btn {
  @apply absolute right-2 bottom-2 p-2 bg-indigo-600 dark:bg-indigo-500 text-white rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors;
}

.agent-stop-btn {
  @apply absolute right-2 bottom-2 p-2 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors;
}
</style>
