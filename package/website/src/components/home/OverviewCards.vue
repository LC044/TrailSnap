<template>
  <section
    class="group relative mx-4 overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm transition-all duration-300 hover:border-primary-100 hover:shadow-md dark:border-gray-800 dark:bg-neutral-900 dark:hover:border-primary-900/60"
    aria-labelledby="photo-overview-title"
  >
    <button
      type="button"
      class="absolute inset-0 z-0 w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
      aria-label="查看全部照片与视频"
      @click="router.push({ name: 'Photos' })"
    ></button>

    <div class="pointer-events-none relative z-10 p-5 pb-4 sm:p-6 sm:pb-4">
      <div class="mb-5 flex items-start justify-between gap-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-500 dark:bg-primary-900/30">
            <Images class="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h2 id="photo-overview-title" class="text-base font-bold text-gray-900 dark:text-gray-100">我的照片</h2>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">珍藏生活中的每一段时光</p>
          </div>
        </div>
        <ChevronRight class="mt-2 h-5 w-5 text-gray-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary-500 dark:text-gray-600" aria-hidden="true" />
      </div>

      <div class="md:flex md:items-end md:justify-between md:gap-10">
        <div class="mb-5 min-w-0 md:mb-0 md:w-[22rem]">
          <strong class="block text-[2rem] font-bold leading-none tracking-tight text-gray-900 dark:text-white sm:text-4xl">
            {{ formattedTotal }}
          </strong>
          <div class="mt-2 flex min-w-0 items-center justify-between gap-3">
            <span class="shrink-0 text-sm text-gray-500 dark:text-gray-400">照片与视频</span>
            <span class="truncate text-xs text-gray-400 dark:text-gray-500">
              {{ formattedPhotoCount }} 张照片 · {{ formattedVideoCount }} 个视频
            </span>
          </div>
        </div>

        <div class="pointer-events-auto grid grid-cols-2 divide-x divide-gray-100 border-t border-gray-100 pt-4 dark:divide-gray-800 dark:border-gray-800 sm:max-w-md md:w-[26rem] md:border-t-0 md:pt-0">
          <button
            type="button"
            class="-m-2 flex min-w-0 items-center gap-3 rounded-xl p-2 text-left transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800/70"
            aria-label="查看今日新增内容"
            @click="openTodayUploads"
          >
            <ImagePlus class="h-5 w-5 shrink-0 text-primary-500" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block text-sm font-semibold text-gray-800 dark:text-gray-100">+{{ data.today_new }}</span>
              <span class="block truncate text-xs text-gray-500 dark:text-gray-400">今日新增</span>
            </span>
          </button>

          <div class="flex min-w-0 items-center gap-3 pl-5">
            <HardDrive class="h-5 w-5 shrink-0 text-primary-500" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block truncate text-sm font-semibold text-gray-800 dark:text-gray-100">{{ formattedStorage }}</span>
              <span class="block text-xs text-gray-500 dark:text-gray-400">已占用空间</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="relative z-10 flex items-center justify-between border-t border-gray-100 px-5 py-3 dark:border-gray-800 sm:px-6">
      <span class="text-xs text-gray-400 dark:text-gray-500">当前媒体文件占用 {{ formattedStorage }}</span>
      <button
        type="button"
        class="flex shrink-0 items-center gap-1 rounded-md text-xs font-medium text-primary-600 transition-colors hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-primary-400 dark:hover:text-primary-300"
        @click="emit('showStorage')"
      >
        查看存储
        <ChevronRight class="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>

    <div class="pointer-events-none absolute -right-12 -top-12 h-40 w-40 rounded-full bg-primary-100/50 blur-3xl dark:bg-primary-900/20"></div>
  </section>
</template>

<script setup lang="ts">
import { computed, PropType } from 'vue';
import { useRouter } from 'vue-router';
import { DashboardCard, DashboardContentStats } from '@/api/dashboard';
import { ChevronRight, HardDrive, ImagePlus, Images } from 'lucide-vue-next';

const props = defineProps({
  data: {
    type: Object as PropType<DashboardCard>,
    required: true,
    default: () => ({ total_media: 0, today_new: 0, storage_used: '0GB' })
  },
  content: {
    type: Object as PropType<DashboardContentStats>,
    required: true
  }
});

const emit = defineEmits(['showStorage']);
const router = useRouter();
const numberFormatter = new Intl.NumberFormat('zh-CN');
const formattedTotal = computed(() => numberFormatter.format(props.data.total_media));
const formattedPhotoCount = computed(() => numberFormatter.format(props.content.photos.total));
const formattedVideoCount = computed(() => numberFormatter.format(props.content.videos.total));
const formattedStorage = computed(() => props.data.storage_used.replace(/([0-9])([A-Za-z])/, '$1 $2'));

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
