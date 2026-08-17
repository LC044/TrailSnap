<!-- src/App.vue -->
<template>
  <el-config-provider :locale="zhCn">
    <!-- 动态渲染当前路由对应的布局 -->
    <component :is="currentLayout" />
    <PwaInstallPrompt />
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
// 导入所有布局组件
import MainLayout from '@/layouts/MainLayout.vue';
import BlankLayout from '@/layouts/BlankLayout.vue';
import { provideTheme } from '@/composables/useTheme';
import { provideNavItems } from '@/composables/useNavItems';
import { useUserStore } from '@/stores/user';
import { useNotificationStore } from '@/stores/notificationStore';
import { useAlbumStore } from '@/stores/albumStore';
import { usePhotoStore } from '@/stores/photoStore';
import { useNotificationSSE } from '@/composables/useNotificationSSE';
import PwaInstallPrompt from '@/components/PwaInstallPrompt.vue';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
// 🚨 关键：确保调用了 provideTheme()
const {
  isDarkMode,
  currentTheme,
  themeStyle,
  themeColors,
  setMode,
  setTheme
} = provideTheme();
provideNavItems();

const route = useRoute();

// 布局映射：路由 meta.layout 对应实际布局组件
const layoutMap = {
  main: MainLayout,   // 主布局（默认）
  blank: BlankLayout  // 空白布局
};

// 计算当前要渲染的布局（默认使用主布局）
const currentLayout = computed(() => {
  // 从路由 meta 中获取布局类型，未指定则默认主布局
  const layoutType = route.meta.layout as 'main' | 'blank' || undefined;
  return layoutMap[layoutType] || MainLayout;
});

// Wire the unified notification SSE channel. The token ref watches the Pinia
// user store, so a logout / re-login automatically disconnects / reconnects
// without us having to manage EventSource lifetimes by hand. This single
// channel carries both task.* (live) and notification.* (persisted) events.
const userStore = useUserStore();
const notifyStore = useNotificationStore();
const albumStore = useAlbumStore();
const photoStore = usePhotoStore();
const token = computed(() => userStore.token);
const sseEnabled = ref(false);
const PHOTO_DATA_TASKS = new Set([
  'SCAN_FOLDER',
  'PROCESS_BASIC',
  'EXTRACT_METADATA',
  'REBUILD_METADATA',
  'ORGANIZE_PHOTOS',
  'BATCH_RENAME',
  'BATCH_TIME_FROM_FILENAME',
  'RECOGNIZE_FACE',
  'OCR',
  'CLASSIFY_IMAGE',
  'VISUAL_DESCRIPTION',
  'IMAGE_EMBEDDING',
]);

watch(
  token,
  (val) => {
    sseEnabled.value = !!val;
    if (val) {
      // Pull persisted unread notifications on (re)login.
      notifyStore.fetchUnread();
    }
  },
  { immediate: true }
);

useNotificationSSE({
  token,
  enabled: sseEnabled,
  onEvent: (event, data) => {
    notifyStore.handleEvent(event, data);
    const taskCompleted =
      event.startsWith('task.') &&
      String(data?.status || '').toLowerCase() === 'completed';

    if (taskCompleted && PHOTO_DATA_TASKS.has(data?.type)) {
      photoStore.markDataStale(data?.type);
    }

    if (taskCompleted && data?.type === 'SCAN_ALBUM') {
      const albumId = data?.payload?.album_id;
      void albumStore.fetchAlbums();
      if (albumId) {
        photoStore.markDataStale(data?.type, albumId);
      }
    }
  },
});

</script>

<!-- 全局样式可移到 src/styles/main.scss，这里清空 -->
<style></style>
