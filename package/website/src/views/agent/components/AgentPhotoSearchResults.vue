<template>
  <section ref="root" class="mt-3 w-full min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900" aria-label="照片搜索结果">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h4 class="m-0 text-sm font-medium text-slate-800 dark:text-slate-100">搜索结果 · {{ total }} 张</h4>
      <span v-if="photos.length" class="text-xs text-slate-500 dark:text-slate-400">已加载 {{ photos.length }} 张</span>
    </div>
    <p v-if="conditions" class="mb-3 break-words text-xs text-slate-500 dark:text-slate-400">{{ conditions }}</p>
    <p v-if="result.filters.description" class="mb-3 text-xs text-slate-500 dark:text-slate-400">画面按相似度匹配，结果可能存在偏差</p>
    <p v-if="result.filters.min_people != null || result.filters.max_people != null" class="mb-3 text-xs text-slate-500 dark:text-slate-400">人数基于已识别人脸，可能存在漏识别</p>
    <FlatPhotoGallery v-if="photos.length" :photos="photos" :scroll-container="scrollContainer" :show-action-bar="false" :selectable="false" relative-scroll @click-photo="openPhoto" />
    <p v-if="loading" class="py-3 text-center text-sm text-slate-500 dark:text-slate-400" role="status">正在加载照片…</p>
    <div v-else-if="error" class="py-3 text-center text-sm text-slate-600 dark:text-slate-300" role="alert">
      <p>{{ error }}</p><button type="button" class="ts-button ts-button-secondary mt-2" @click="loadMore">重试</button>
    </div>
    <p v-else-if="!photos.length" class="py-4 text-center text-sm text-slate-500 dark:text-slate-400">未找到符合条件的照片，可以继续补充或调整条件。</p>
    <button v-else-if="nextOffset !== null" type="button" class="ts-button ts-button-secondary mt-3 w-full" @click="loadMore">加载更多照片</button>
    <p v-else class="mt-3 text-center text-xs text-slate-500 dark:text-slate-400">已显示全部搜索结果</p>
    <PhotoLightbox :visible="lightboxOpen" :image="photos[photoIndex] ?? null" :images="photos" :current-index="photoIndex" :has-prev="photoIndex > 0" :has-next="photoIndex < photos.length - 1" @close="lightboxOpen = false" @prev="photoIndex--" @next="photoIndex++" @select="photoIndex = $event" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { agentApi, type AgentSearchResult } from '@/api/agent';
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import { mapPhotoToImage } from '@/stores/photoStore';
import type { AlbumImage } from '@/types/album';

const props = defineProps<{ result: AgentSearchResult }>();
const root = ref<HTMLElement | null>(null);
const scrollContainer = ref<HTMLElement | null>(null);
const photos = ref<AlbumImage[]>([]);
const total = ref(props.result.total);
const nextOffset = ref<number | null>(0);
const loading = ref(false);
const error = ref('');
const lightboxOpen = ref(false);
const photoIndex = ref(0);
let disposed = false;
const conditions = computed(() => {
  const f = props.result.filters;
  return [f.start_date || f.end_date ? `${f.start_date || '不限'} 至 ${f.end_date || '不限'}` : '',
    f.location, f.person_ids?.length ? `${f.person_ids.length}个人物${f.people_match === 'any' ? '任一出现' : '同时出现'}` : '',
    f.min_people != null ? `至少${f.min_people}人` : '', f.max_people != null ? `至多${f.max_people}人` : '',
    f.description, f.ocr_text ? `图片文字：${f.ocr_text}` : '', ...(f.tags || [])].filter(Boolean).join(' · ');
});
const loadMore = async () => {
  if (loading.value || nextOffset.value === null) return;
  loading.value = true;
  error.value = '';
  try {
    const response = await agentApi.getSearchResultPhotos(props.result.id, nextOffset.value);
    if (disposed) return;
    const page = response.data;
    const seen = new Set(photos.value.map(photo => photo.id));
    photos.value.push(...page.photos.map(mapPhotoToImage).filter(photo => !seen.has(photo.id)));
    total.value = page.total;
    nextOffset.value = page.next_offset;
  } catch {
    if (!disposed) error.value = '加载搜索结果失败，请重试';
  } finally {
    if (!disposed) loading.value = false;
  }
};
const openPhoto = (photo: AlbumImage) => {
  photoIndex.value = photos.value.findIndex(item => item.id === photo.id);
  lightboxOpen.value = photoIndex.value >= 0;
};
onMounted(() => {
  scrollContainer.value = root.value?.closest<HTMLElement>('.agent-chat-messages') || null;
  void loadMore();
});
onBeforeUnmount(() => { disposed = true; });
</script>
