<template>
  <section class="ts-surface p-5 sm:p-6" aria-labelledby="home-people-title">
    <div class="mb-5 flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-500 dark:bg-primary-900/30"><Users class="h-5 w-5" aria-hidden="true" /></span>
        <div class="min-w-0">
          <h2 id="home-people-title" class="ts-section-title text-base font-bold text-gray-900 dark:text-gray-100">镜头里的陪伴</h2>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ data.total_identified ? `已整理 ${formatNumber(data.total_identified)} 位人物的照片` : '把熟悉的面孔，整理成相册' }}</p>
        </div>
      </div>
      <RouterLink to="/album/people" class="ts-button ts-button-ghost shrink-0 gap-1 px-2 text-xs text-primary-600 dark:text-primary-400">全部人物<ChevronRight class="h-3.5 w-3.5" aria-hidden="true" /></RouterLink>
    </div>
    <div v-if="data.top_faces.length" class="grid grid-cols-3 gap-3">
      <RouterLink v-for="face in data.top_faces.slice(0, 3)" :key="face.id" :to="`/album/people/${face.id}`" class="group flex min-w-0 flex-col items-center gap-1 rounded-xl p-2 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800/70" :aria-label="`查看${face.identity_name || '未命名人物'}的相册`">
        <PersonAvatar :person="face" class="!w-16 sm:!w-20 mb-1" />
        <span class="w-full truncate text-center text-sm font-medium text-gray-800 dark:text-gray-100">{{ face.identity_name || '未命名人物' }}</span>
        <span class="text-xs text-gray-500 dark:text-gray-400">{{ formatNumber(face.face_count) }} 张照片</span>
      </RouterLink>
    </div>
    <p v-else class="py-4 text-center text-sm text-gray-500 dark:text-gray-400">还没有人物相册，确认照片中的人脸后会展示在这里</p>
    <div v-if="data.pending_faces_count > 0" class="mt-4 flex items-center justify-between gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
      <p class="min-w-0 text-xs leading-relaxed text-gray-500 dark:text-gray-400">{{ formatNumber(data.unidentified_photos_count) }} 张照片中的人脸待确认</p>
      <RouterLink :to="{ path: '/album/people', query: { view: 'solo' } }" class="ts-button ts-button-ghost shrink-0 gap-1 px-2 text-xs text-primary-600 dark:text-primary-400">去确认<ChevronRight class="h-3.5 w-3.5" aria-hidden="true" /></RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChevronRight, Users } from 'lucide-vue-next';
import type { DashboardFace } from '@/api/dashboard';
import PersonAvatar from '@/components/PersonAvatar.vue';

defineProps<{ data: DashboardFace }>();
const formatNumber = (value: number) => value.toLocaleString('zh-CN');
</script>
