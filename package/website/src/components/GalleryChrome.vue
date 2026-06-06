<!--
  照片画廊公共壳：骨架屏 + 错误态。
  批量操作 bar 因 PhotoGallery / FlatPhotoGallery 行为有差异（是否含 transfer 菜单等），
  暂时留在各组件中，等统一时再上移。
-->
<template>
  <!-- Skeleton Loader (Initial Load) -->
  <div v-if="loading && photos.length === 0" class="absolute inset-0 z-10 bg-white dark:bg-gray-950 p-4">
    <div class="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      <div v-for="i in 20" :key="i" class="aspect-[3/2] bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse"></div>
    </div>
  </div>

  <!-- Error State -->
  <div v-if="error" class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white dark:bg-gray-950">
    <div class="text-center space-y-4">
      <p class="text-red-500 font-medium">{{ error }}</p>
      <button
        @click="$emit('retry')"
        class="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors group relative overflow-hidden"
      >
        <div class="absolute inset-0 rounded-lg animate-[pulse_2s_cubic-bezier(0.4,0,0.6,1)_infinite] bg-white/20"></div>
        <RefreshCcw class="w-4 h-4 group-hover:animate-[spin_1s_ease-in-out]" />
        <span class="relative z-10">重试</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RefreshCcw } from 'lucide-vue-next';

defineProps<{
  loading: boolean;
  error: string | null;
  photos: any[];
}>();

defineEmits<{
  (e: 'retry'): void;
}>();
</script>
