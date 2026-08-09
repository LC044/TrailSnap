<template>
  <div class="w-full overflow-x-auto pb-2 no-scrollbar">
    <div class="flex space-x-3 px-4 min-w-max">
      <!-- Total Media Card -->
      <button
        type="button"
        class="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 w-[140px] h-[80px] flex flex-col justify-between cursor-pointer hover:scale-95 transition-transform duration-200 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @click="router.push({ name: 'Photos' })"
      >
        <div class="flex items-center space-x-2">
          <span class="text-xl">📸</span>
          <span class="text-lg font-bold text-gray-800 dark:text-gray-100">{{ data.total_media }}</span>
        </div>
        <div class="text-xs text-gray-500 dark:text-gray-400">照片+视频</div>
      </button>

      <!-- Recently Updated Card -->
      <button
        type="button"
        class="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 w-[140px] h-[80px] flex flex-col justify-between cursor-pointer hover:scale-95 transition-transform duration-200 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @click="openTodayUploads"
      >
        <div class="flex items-center space-x-2">
          <span class="text-xl">🆕</span>
          <span class="text-lg font-bold text-gray-800 dark:text-gray-100">{{ data.today_new }}</span>
        </div>
        <div class="text-xs text-gray-500 dark:text-gray-400">今日新增</div>
      </button>

      <!-- Storage Card -->
      <button
        type="button"
        class="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 w-[140px] h-[80px] flex flex-col justify-between cursor-pointer hover:scale-95 transition-transform duration-200 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @click="emit('showStorage')"
      >
        <div class="flex items-center space-x-2">
          <span class="text-xl">💾</span>
          <span class="text-lg font-bold text-gray-800 dark:text-gray-100">{{ data.storage_used }}</span>
        </div>
        <div class="text-xs text-gray-500 dark:text-gray-400">占用空间</div>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PropType } from 'vue';
import { useRouter } from 'vue-router';
import { DashboardCard } from '@/api/dashboard';

defineProps({
  data: {
    type: Object as PropType<DashboardCard>,
    required: true,
    default: () => ({ total_media: 0, today_new: 0, storage_used: '0GB' })
  }
});

const emit = defineEmits(['showStorage']);
const router = useRouter();

const formatLocalDateTime = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const openTodayUploads = () => {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  router.push({
    name: 'Photos',
    query: {
      uploaded_after: formatLocalDateTime(start),
      uploaded_before: formatLocalDateTime(end),
    },
  });
};
</script>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
