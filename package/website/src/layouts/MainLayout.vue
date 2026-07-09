<!-- src/layouts/MainLayout.vue -->
<template>
  <div
    :class="[isDarkMode ? 'dark' : '']"
    :style="themeStyle"
    class="h-screen w-full flex font-sans transition-colors duration-300 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200 overflow-hidden"
  >
    <!-- 左侧导航栏 -->
    <Sidebar class="hidden md:flex" />

    <!-- 右侧主体内容区 -->
    <div class="flex-1 flex flex-col min-w-0 transition-all duration-300 relative" id="main-content-wrapper">
      <!-- 顶部导航 -->
      <NavBar class="flex md:hidden" />

      <!-- 页面内容 -->
      <main class="flex-1 overflow-y-auto bg-slate-50 dark:bg-gray-900 box-border dark:from-gray-900 dark:to-gray-800 relative pt-[60px] md:pt-0">
        <transition name="fade-slide" mode="out-in">
          <router-view />
        </transition>
      </main>
    </div>

    <!-- 悬浮的 Agent 助手按钮（可全屏拖动，靠近左右边缘自动半隐藏，鼠标悬浮再出现） -->
    <!-- 外层为固定不动的透明热区，hover 监听在它身上，避免按钮位移导致光标脱离而抖动 -->
    <div
      v-show="!isAgentOpen && showAgentFab"
      class="fixed z-50"
      :style="fabZoneStyle"
      @mouseenter="isFabHovering = true"
      @mouseleave="isFabHovering = false"
    >
      <button
        ref="fabRef"
        :style="fabBtnStyle"
        @pointerdown="onFabPointerDown"
        @click="onFabClick"
        class="w-14 h-14 bg-primary-600 hover:bg-primary-700 text-white rounded-full shadow-lg shadow-primary-500/30 flex items-center justify-center active:scale-95 group touch-none select-none"
        :class="isFabDragging ? 'cursor-grabbing' : 'cursor-grab'"
        aria-label="打开 AI 助手"
      >
        <Bot class="w-6 h-6 group-hover:animate-bounce" />
      </button>
    </div>

    <!-- Agent 聊天弹窗 -->
    <AgentChat v-model="isAgentOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
// 导入导航栏、侧边栏
import NavBar from '@/layouts/NavBar.vue';
import Sidebar from '@/layouts/Sidebar.vue';
import AgentChat from '@/views/agent/AgentChat.vue';
import { Bot } from 'lucide-vue-next';
// 从根组件注入主题（避免重复 provide 导致主题状态分裂）
import { injectTheme } from '@/composables/useTheme';

const isAgentOpen = ref(false);

// 注入由 App.vue 提供的主题状态
const {
  isDarkMode,
  currentTheme,
  themeStyle,
  themeColors,
  setMode,
  setTheme
} = injectTheme();

// 只在主布局页面下显示 Agent 悬浮按钮；blank 布局（登录/年度报告/注册等）不渲染 MainLayout，
// 因此这里用 meta.layout 判断更稳健。
const route = useRoute();
const showAgentFab = computed(() => route.meta.layout !== 'blank');

/* ----------------------- 悬浮助手按钮：拖动 + 边缘半隐藏 ----------------------- */
const FAB_SIZE = 56;            // w-14 h-14 = 56px
const EDGE_MARGIN = 20;         // 默认距视口边缘的留白
const DOCK_THRESHOLD = 70;      // 距左右边缘小于该值则自动靠边半隐藏
const DOCK_HIDE_RATIO = 0.32;   // 靠边时隐藏的比例（约三分之一，留足可见部分）
const HOVER_PEEK = 26;          // 悬浮时再往内探出的像素，完全脱离边缘/滚动条

const fabRef = ref<HTMLElement | null>(null);
// 按钮左上角坐标（基于 fixed 定位）
const fabPos = ref({ x: 0, y: 0 });
// 当前是否吸附到某条边（半隐藏状态）
const fabDockedEdge = ref<'left' | 'right' | null>(null);
const isFabDragging = ref(false);
const isFabHovering = ref(false);

// 拖动过程中的临时状态
let dragOrigin = { mouseX: 0, mouseY: 0, posX: 0, posY: 0 };
let dragMoved = false;

const clampPos = (x: number, y: number) => ({
  x: Math.max(0, Math.min(x, window.innerWidth - FAB_SIZE)),
  y: Math.max(0, Math.min(y, window.innerHeight - FAB_SIZE)),
});

const initFabPosition = () => {
  // 默认右下角
  fabPos.value = clampPos(
    window.innerWidth - FAB_SIZE - EDGE_MARGIN,
    window.innerHeight - FAB_SIZE - EDGE_MARGIN
  );
};

const onFabPointerDown = (e: PointerEvent) => {
  // 仅响应主键，避免右键干扰
  if (e.button !== 0) return;
  isFabDragging.value = true;
  dragMoved = false;
  dragOrigin = {
    mouseX: e.clientX,
    mouseY: e.clientY,
    posX: fabPos.value.x,
    posY: fabPos.value.y,
  };
  window.addEventListener('pointermove', onFabPointerMove);
  window.addEventListener('pointerup', onFabPointerUp);
};

const onFabPointerMove = (e: PointerEvent) => {
  if (!isFabDragging.value) return;
  const dx = e.clientX - dragOrigin.mouseX;
  const dy = e.clientY - dragOrigin.mouseY;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    // 真正开始拖动时才脱离吸附，避免点击瞬间产生位移闪烁
    if (!dragMoved) fabDockedEdge.value = null;
    dragMoved = true;
  }
  fabPos.value = clampPos(dragOrigin.posX + dx, dragOrigin.posY + dy);
};

const onFabPointerUp = () => {
  isFabDragging.value = false;
  window.removeEventListener('pointermove', onFabPointerMove);
  window.removeEventListener('pointerup', onFabPointerUp);
  // 松手后判断是否靠边半隐藏
  const { x } = fabPos.value;
  if (x <= DOCK_THRESHOLD) {
    fabDockedEdge.value = 'left';
  } else if (x >= window.innerWidth - FAB_SIZE - DOCK_THRESHOLD) {
    fabDockedEdge.value = 'right';
  } else {
    fabDockedEdge.value = null;
  }
};

const onFabClick = () => {
  // 拖动产生的位移不触发打开
  if (dragMoved) return;
  isAgentOpen.value = true;
};

const onWindowResize = () => {
  // 视口变化时把按钮拉回可视范围
  fabPos.value = clampPos(fabPos.value.x, fabPos.value.y);
};

// 外层热区：固定不动，覆盖按钮从“半隐藏”到“悬浮探出”的整个活动范围，
// 这样光标在范围内移动不会因按钮位移而触发 mouseleave，消除抖动。
const fabZoneStyle = computed(() => {
  const y = fabPos.value.y;
  const w = FAB_SIZE + HOVER_PEEK;
  if (fabDockedEdge.value === 'left') {
    return { left: '0px', top: `${y}px`, width: `${w}px`, height: `${FAB_SIZE}px` };
  }
  if (fabDockedEdge.value === 'right') {
    const maxX = Math.max(0, window.innerWidth - FAB_SIZE);
    return { left: `${maxX - HOVER_PEEK}px`, top: `${y}px`, width: `${w}px`, height: `${FAB_SIZE}px` };
  }
  // 自由位置：热区即按钮本身
  return {
    left: `${fabPos.value.x}px`,
    top: `${y}px`,
    width: `${FAB_SIZE}px`,
    height: `${FAB_SIZE}px`,
  };
});

// 内层按钮：在热区内做位移（半隐藏 / 悬浮探出），用 transform 避免触发布局
const fabBtnStyle = computed(() => {
  const hideOffset = FAB_SIZE * DOCK_HIDE_RATIO;
  let tx = 0;
  let opacity = 1;

  if (fabDockedEdge.value === 'left') {
    tx = isFabHovering.value ? HOVER_PEEK : -hideOffset;
    opacity = isFabHovering.value ? 1 : 0.7;
  } else if (fabDockedEdge.value === 'right') {
    // 热区左边相对按钮基础位置向内缩了 HOVER_PEEK，故隐藏时需多偏移 HOVER_PEEK
    tx = isFabHovering.value ? 0 : hideOffset + HOVER_PEEK;
    opacity = isFabHovering.value ? 1 : 0.7;
  }

  return {
    transform: `translateX(${tx}px)`,
    opacity,
    transition: isFabDragging.value
      ? 'none'
      : 'transform 0.28s ease, opacity 0.28s ease',
  };
});

onMounted(() => {
  initFabPosition();
  window.addEventListener('resize', onWindowResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize);
  window.removeEventListener('pointermove', onFabPointerMove);
  window.removeEventListener('pointerup', onFabPointerUp);
});
</script>

<style scoped>

/* 页面过渡动画（原 App.vue 中的样式） */
.fade-slide-enter-active {
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.fade-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>