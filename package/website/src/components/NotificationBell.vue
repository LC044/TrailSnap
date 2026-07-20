<template>
  <!-- 通知铃铛按钮。抽屉/设置弹窗由 NotificationDrawer.vue 承载（全局只挂一份）。
       variant="icon"：顶栏小图标按钮；variant="row"：侧边栏整行导航样式。 -->
  <button
    v-if="variant === 'icon'"
    type="button"
    @click="store.openDrawer()"
    class="relative bg-transparent p-2 text-slate-600 dark:text-slate-300 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
    title="通知"
    aria-label="通知"
  >
    <Bell class="w-4 h-4" />
    <span
      v-if="store.unreadCount > 0"
      class="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center text-[10px] font-semibold text-white bg-primary-500 rounded-full ring-2 ring-white dark:ring-slate-900"
    >
      {{ store.unreadCount > 99 ? '99+' : store.unreadCount }}
    </span>
  </button>

  <button
    v-else
    type="button"
    @click="store.openDrawer()"
    :title="collapsed ? '通知' : undefined"
    class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group relative w-full focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
  >
    <div class="relative shrink-0">
      <Bell class="w-5 h-5" />
      <span
        v-if="store.unreadCount > 0"
        class="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 flex items-center justify-center text-[10px] font-semibold text-white bg-primary-500 rounded-full ring-2 ring-white dark:ring-slate-900"
      >
        {{ store.unreadCount > 99 ? '99+' : store.unreadCount }}
      </span>
    </div>
    <transition name="fade">
      <span v-if="!collapsed" class="ml-3 truncate">通知</span>
    </transition>
  </button>
</template>

<script setup lang="ts">
import { Bell } from 'lucide-vue-next';
import { useNotificationStore } from '@/stores/notificationStore';

withDefaults(defineProps<{
  variant?: 'icon' | 'row';
  collapsed?: boolean;
}>(), {
  variant: 'icon',
  collapsed: false,
});

const store = useNotificationStore();
</script>
