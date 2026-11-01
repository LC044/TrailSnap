<template>
  <div class="ts-page-background mx-auto w-full max-w-screen-2xl min-h-full px-[var(--ts-page-gutter)] pb-8">
    <header class="ts-browse-header flex items-center gap-3">
      <BackButton label="返回" @click="goBack" />
      <h1 class="ts-page-title">以图搜图</h1>
    </header>
    <section class="ts-surface mb-6 space-y-4 p-4 sm:p-6" aria-label="搜索来源">
      <p class="ts-muted text-sm">上传图片或选择图库照片，查找画面相似的照片。</p>
      <div class="flex flex-wrap gap-3">
        <button class="ts-button ts-button-primary" :disabled="loading" @click="fileInput?.click()"><Upload class="h-4 w-4" />上传图片</button>
        <button class="ts-button ts-button-secondary" :disabled="loading" @click="showPicker = true"><Images class="h-4 w-4" />从图库选择</button>
        <input ref="fileInput" class="hidden" type="file" accept="image/*" aria-label="上传搜索图片" @change="selectFile" />
      </div>
      <div v-if="previewUrl" class="flex items-center gap-3">
        <img :src="previewUrl" alt="搜索来源图片" class="h-20 w-20 rounded-xl object-cover" />
        <p class="ts-muted min-w-0 break-all text-sm">{{ sourceName }}</p>
      </div>
      <p v-if="loading" role="status" class="ts-muted">正在查找相似照片…</p>
      <div v-else-if="error" role="alert" class="text-sm text-[var(--ts-color-danger)]">
        {{ error }}<button v-if="sourceFile || photoId" class="ts-button ts-button-ghost ml-2" @click="search">重试</button>
      </div>
      <p v-else-if="searched" role="status" class="ts-muted text-sm">{{ photos.length ? `找到 ${photos.length} 张相似照片，按相似度排序（最多 100 张）` : '未找到相似照片，请尝试其他图片' }}</p>
      <p v-else class="ts-muted text-xs">支持不超过 20 MB 的图片，上传仅用于本次搜索。</p>
    </section>
    <FlatPhotoGallery v-if="photos.length" :photos="photos" :loading="loading" :show-action-bar="false" @click-photo="openPhoto" />
    <PhotoLightbox :visible="visible" :image="photos[index] ?? null" :images="photos" :current-index="index"
      :has-prev="index > 0" :has-next="index < photos.length - 1" @close="close" @prev="prev" @next="next" @select="value => index = value" />
    <ResponsiveDialog v-model="showPicker" title="选择搜索图片" max-width="64rem" mobile-mode="fullscreen" mobile-back panel-class="image-search-picker">
      <div class="min-h-0 flex-1 md:h-[72dvh] md:flex-none"><PhotoSelector v-if="showPicker" is-selector single-select embedded @select="selectPhoto" @cancel="showPicker = false" /></div>
    </ResponsiveDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Upload, Images } from 'lucide-vue-next'
import BackButton from '@/components/ui/BackButton.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import { useAppBack } from '@/composables/useAppBack'
import { usePhotoViewer } from '@/composables/usePhotoViewer'
import { mapPhotoToImage } from '@/stores/photoStore'
import { thumbnailUrl } from '@/utils/mediaUrl'
import searchService from '@/api/search'
import type { AlbumImage } from '@/types/album'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/mobile-search')
const fileInput = ref<HTMLInputElement | null>(null)
const showPicker = ref(false)
const sourceFile = ref<File | null>(null)
const photoId = ref('')
const sourceName = ref('')
const previewUrl = ref('')
const photos = ref<AlbumImage[]>([])
const loading = ref(false)
const searched = ref(false)
const error = ref('')
const { visible, index, open, close, prev, next } = usePhotoViewer(photos)
const openPhoto = (photo: AlbumImage) => open(photos.value.findIndex(item => item.id === photo.id))
let requestId = 0
let objectUrl = ''
const releasePreview = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = '' }

const search = async () => {
  const current = ++requestId
  loading.value = true
  error.value = ''
  photos.value = []
  searched.value = false
  try {
    const results = sourceFile.value
      ? await searchService.searchByImage(sourceFile.value, 100)
      : await searchService.searchByPhoto(photoId.value)
    if (current !== requestId) return
    photos.value = results.map(item => mapPhotoToImage(item.photo))
    searched.value = true
  } catch {
    if (current === requestId) error.value = '搜索失败，请确认图片可用且 AI 图片模型已就绪后重试。'
  } finally {
    if (current === requestId) loading.value = false
  }
}
const selectFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/') || file.size === 0 || file.size > 20 * 1024 * 1024) {
    error.value = '请选择不超过 20 MB 的有效图片'
    return
  }
  releasePreview()
  sourceFile.value = file
  photoId.value = ''
  sourceName.value = file.name
  objectUrl = URL.createObjectURL(file)
  previewUrl.value = objectUrl
  if (route.query.photo) await router.replace({ path: '/search/image' })
  void search()
}
const selectPhoto = (ids: string[]) => {
  if (!ids[0]) return
  showPicker.value = false
  if (ids[0] === photoId.value && !sourceFile.value) void search()
  else void router.replace({ path: '/search/image', query: { photo: ids[0] } })
}
watch(() => route.query.photo, (value) => {
  if (typeof value !== 'string' || !value) return
  close()
  releasePreview()
  sourceFile.value = null
  photoId.value = value
  sourceName.value = '图库照片'
  previewUrl.value = thumbnailUrl(value, 'small')
  void search()
}, { immediate: true })
onUnmounted(() => { ++requestId; releasePreview() })
</script>

<style>
.image-search-picker .responsive-dialog-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}
</style>
