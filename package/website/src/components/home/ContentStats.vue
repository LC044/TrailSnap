<template>
  <div class="bg-gray-100 dark:bg-gray-800 rounded-lg mx-4 my-3 overflow-hidden transition-all duration-300">
    <!-- Header -->
    <button
      type="button"
      class="flex w-full justify-between items-center p-4 cursor-pointer focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      @click="isExpanded = !isExpanded"
      :aria-expanded="isExpanded"
    >
      <span class="text-base text-gray-800 dark:text-gray-100">内容细分</span>
      <span class="text-gray-500 transition-transform duration-300" :class="{ 'rotate-180': isExpanded }">
        ↓
      </span>
    </button>

    <!-- Content -->
    <div 
      v-show="isExpanded"
      class="px-4 pb-4 grid grid-cols-2 gap-4 text-xs text-gray-600 dark:text-gray-300"
    >
      <!-- Photos -->
      <RouterLink :to="{ name: 'Photos', query: { file_types: 'image' } }" class="col-span-2 rounded-lg p-2 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 sm:col-span-1 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        <div class="flex items-center space-x-2 mb-1">
          <span class="text-lg">📷</span>
          <span class="font-bold">照片：{{ data.photos.total }}</span>
        </div>
        <div class="pl-7 text-gray-500">
          {{ data.photos.sub_1_label }}: {{ data.photos.sub_1_count }} / {{ data.photos.sub_2_label }}: {{ data.photos.sub_2_count }}
        </div>
      </RouterLink>

      <!-- Videos -->
      <RouterLink :to="{ name: 'Photos', query: { file_types: 'video,live_photo' } }" class="col-span-2 rounded-lg p-2 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 sm:col-span-1 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        <div class="flex items-center space-x-2 mb-1">
          <span class="text-lg">🎬</span>
          <span class="font-bold">视频：{{ data.videos.total }}</span>
        </div>
        <div class="pl-7 text-gray-500">
          {{ data.videos.sub_1_label }}: {{ data.videos.sub_1_count }} / {{ data.videos.sub_2_label }}: {{ data.videos.sub_2_count }}
        </div>
      </RouterLink>

      <!-- Scenery -->
      <RouterLink :to="{ name: 'ClassificationDetail', params: { name: '风景' } }" class="col-span-1 rounded-lg p-2 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        <span class="text-lg">🏞️</span> 风景：{{ data.scenery_count }}
      </RouterLink>

      <!-- Food -->
      <RouterLink :to="{ name: 'ClassificationDetail', params: { name: '美食' } }" class="col-span-1 rounded-lg p-2 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        <span class="text-lg">🍜</span> 美食：{{ data.food_count }}
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, PropType } from 'vue';
import { DashboardContentStats } from '@/api/dashboard';

defineProps({
  data: {
    type: Object as PropType<DashboardContentStats>,
    required: true
  }
});

const isExpanded = ref(false);
</script>
