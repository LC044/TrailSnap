<template>
  <el-dialog
    :model-value="visible"
    :fullscreen="isMobile"
    :z-index="90"
    class="similar-photo-compare-dialog"
    width="min(96vw, 1500px)"
    append-to-body
    destroy-on-close
    @close="emit('close')"
  >
    <template #header>
      <div class="pr-8">
        <div class="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
          <i class="mgc_pic_2_line text-primary-500"></i>
          照片对比
          <span class="text-sm font-normal text-gray-500 dark:text-gray-400">{{ photos.length }}/4</span>
        </div>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          点击照片可查看大图；确认不需要的照片后，可直接标记删除。
        </p>
      </div>
    </template>

    <div
      class="compare-grid"
      :class="{ 'compare-grid-single': photos.length === 1 }"
      :style="{ '--compare-count': Math.max(1, photos.length) }"
    >
      <article
        v-for="(photo, index) in photos"
        :key="photo.id"
        class="min-w-0 overflow-hidden rounded-xl border bg-gray-50 dark:bg-gray-900"
        :class="isMarkedForDeletion(photo.id)
          ? 'border-red-400 ring-2 ring-red-400/30'
          : 'border-gray-200 dark:border-gray-700'"
      >
        <button
          type="button"
          class="group relative block w-full overflow-hidden bg-gray-100 dark:bg-gray-800 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-inset focus-visible:outline-none"
          :aria-label="`查看大图：${photo.filename || `照片 ${index + 1}`}`"
          @click="emit('open-photo', photo)"
        >
          <img
            :src="photo.preview || photo.thumbnail"
            :alt="photo.filename || `对比照片 ${index + 1}`"
            class="compare-image w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
          />
          <span
            v-if="index === 0"
            class="absolute left-2 top-2 rounded-full bg-primary-500 px-2 py-1 text-xs font-medium text-white shadow-sm"
          >
            推荐保留
          </span>
          <span class="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-1 text-xs text-white">
            查看大图
          </span>
        </button>

        <div class="space-y-2 p-3">
          <div class="truncate text-sm font-medium text-gray-800 dark:text-gray-100" :title="photo.filename">
            {{ photo.filename || '未命名照片' }}
          </div>
          <dl class="grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
            <div class="min-w-0">
              <dt class="sr-only">拍摄时间</dt>
              <dd class="truncate">{{ formatDate(photo.timestamp) }}</dd>
            </div>
            <div class="text-right">
              <dt class="sr-only">文件大小</dt>
              <dd>{{ formatSize(photo.size) }}</dd>
            </div>
            <div v-if="photo.width && photo.height" class="col-span-2">
              <dt class="sr-only">分辨率</dt>
              <dd>{{ photo.width }} × {{ photo.height }}</dd>
            </div>
          </dl>

          <div class="flex gap-2 pt-1">
            <button
              type="button"
              class="flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-900"
              :class="isMarkedForDeletion(photo.id)
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-white text-red-500 ring-1 ring-inset ring-red-200 hover:bg-red-50 dark:bg-gray-800 dark:ring-red-900 dark:hover:bg-red-900/20'"
              @click="emit('toggle-delete', photo.id)"
            >
              <i :class="isMarkedForDeletion(photo.id) ? 'mgc_check_line' : 'mgc_delete_2_line'"></i>
              {{ isMarkedForDeletion(photo.id) ? '已标记删除' : '标记删除' }}
            </button>
            <button
              type="button"
              class="rounded-lg bg-white px-3 py-2 text-sm text-gray-600 ring-1 ring-inset ring-gray-200 transition-colors hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-gray-700 dark:focus-visible:ring-offset-gray-900"
              aria-label="移出对比"
              @click="emit('remove', photo.id)"
            >
              移出
            </button>
          </div>
        </div>
      </article>
    </div>

    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <span class="text-xs text-gray-500 dark:text-gray-400">
          已标记 {{ markedCount }} 张
        </span>
        <button
          type="button"
          class="rounded-lg bg-primary-500 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-gray-900"
          @click="emit('close')"
        >
          完成对比
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import type { AlbumImage } from '@/types/album';

const props = defineProps<{
  visible: boolean;
  photos: AlbumImage[];
  selectedForDeletion: Set<string>;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'toggle-delete', id: string): void;
  (e: 'remove', id: string): void;
  (e: 'open-photo', photo: AlbumImage): void;
}>();

const isMobile = useMediaQuery('(max-width: 767px)');
const markedCount = computed(() => props.photos.filter(photo => props.selectedForDeletion.has(photo.id)).length);
const isMarkedForDeletion = (id: string) => props.selectedForDeletion.has(id);

const formatSize = (size?: number) => {
  if (!size) return '大小未知';
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
};

const formatDate = (timestamp: number) => {
  if (!timestamp || Number.isNaN(timestamp)) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
};
</script>

<style scoped>
.compare-grid {
  display: grid;
  grid-template-columns: repeat(var(--compare-count), minmax(0, 1fr));
  gap: 0.75rem;
}

.compare-image {
  height: clamp(18rem, 55vh, 44rem);
}

@media (max-width: 767px) {
  .compare-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .compare-grid-single {
    grid-template-columns: minmax(0, 1fr);
  }

  .compare-image {
    height: clamp(7rem, 20vh, 11rem);
  }
}
</style>

<style>
@media (max-width: 767px) {
  .similar-photo-compare-dialog .el-dialog__body {
    padding: 0.5rem;
    overflow-y: auto;
  }

  .similar-photo-compare-dialog .el-dialog__header,
  .similar-photo-compare-dialog .el-dialog__footer {
    padding-left: 0.75rem;
    padding-right: 0.75rem;
  }
}
</style>
