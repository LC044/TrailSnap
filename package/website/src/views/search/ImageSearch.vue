<template>
  <div class="ts-page-background mx-auto w-full max-w-screen-2xl min-h-full px-[var(--ts-page-gutter)] pb-8">
    <header class="ts-browse-header flex items-center gap-3">
      <BackButton label="返回" @click="goBack" />
      <h1 class="journal-page-title">以图搜图</h1>
      <button v-if="photos.length && !gallery?.isSelectionMode" type="button"
        class="ts-button ts-button-secondary ml-auto" @click="gallery?.enterSelectionMode()">选择</button>
    </header>
    <section class="image-search-source" aria-label="搜索来源" @dragover.prevent @drop.prevent="dropFile">
      <div v-if="!previewUrl" class="image-search-mark" aria-hidden="true"><ScanSearch /></div>
      <p class="ts-muted text-sm">拖放图片、上传文件或从图库选择，查找相似画面。</p>
      <div class="flex flex-wrap gap-3">
        <button class="ts-button image-search-upload" :disabled="loading" @click="fileInput?.click()"><Upload class="h-4 w-4" />上传图片</button>
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
    <FlatPhotoGallery v-if="photos.length" ref="gallery" :photos="photos" :loading="loading" delete-label="移入回收站" context-add-to-album
      @click-photo="openPhoto" @add-to-album="addToAlbum" @batch-delete="deletePhotos"
      @batch-edit-time="editTime" @batch-edit-location="editLocation" />
    <PhotoLightbox :visible="visible" :initial-details="lightboxInitialDetails" :image="photos[index] ?? null" :images="photos" :current-index="index"
      :has-prev="index > 0" :has-next="index < photos.length - 1" @close="close" @prev="prev" @next="next" @select="value => index = value" />
    <ResponsiveDialog v-model="showPicker" title="选择搜索图片" max-width="64rem" mobile-mode="fullscreen" custom-mobile-header panel-class="image-search-picker">
      <div class="min-h-0 flex-1 md:h-[72dvh] md:flex-none"><PhotoSelector v-if="showPicker" title="选择搜索图片" is-selector single-select embedded mobile-dialog-header @select="selectPhoto" @cancel="showPicker = false" /></div>
    </ResponsiveDialog>
    <AlbumSelector v-model:visible="showAlbumSelector" :photo-ids="albumPhotoIds" @success="gallery?.exitSelectionMode()" />
    <TimeBatchEditor v-if="showTimeEditor" v-model="showTimeEditor" :photo-ids="editPhotoIds" @updated="search" />
    <LocationBatchEditor v-if="showLocationEditor" v-model="showLocationEditor" :photo-ids="editPhotoIds" :photos="photos" @success="search" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Upload, Images, ScanSearch } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import BackButton from '@/components/ui/BackButton.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PhotoSelector from '@/components/PhotoSelector.vue'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import TimeBatchEditor from '@/components/TimeBatchEditor.vue'
import LocationBatchEditor from '@/components/LocationBatchEditor.vue'
import { useAppBack } from '@/composables/useAppBack'
import { usePhotoViewer } from '@/composables/usePhotoViewer'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useUiStore } from '@/stores/uiStore'
import { thumbnailUrl } from '@/utils/mediaUrl'
import searchService from '@/api/search'
import { albumService } from '@/api/album'
import type { AlbumImage } from '@/types/album'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
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
const gallery = ref<InstanceType<typeof FlatPhotoGallery>>()
const showAlbumSelector = ref(false)
const albumPhotoIds = ref<string[]>([])
const editPhotoIds = ref<string[]>([])
const showTimeEditor = ref(false)
const showLocationEditor = ref(false)
const addToAlbum = (ids: string[]) => {
  albumPhotoIds.value = ids
  showAlbumSelector.value = true
}
const editTime = (ids: string[]) => {
  editPhotoIds.value = ids
  showTimeEditor.value = true
}
const editLocation = (ids: string[]) => {
  editPhotoIds.value = ids
  showLocationEditor.value = true
}
let deleting = false
const deletePhotos = async (ids: string[], preserveSelection = false) => {
  if (deleting || !ids.length) return
  deleting = true
  try {
    await ElMessageBox.confirm(`将选中的 ${ids.length} 张照片移入回收站？`, '移入回收站', {
      confirmButtonText: '移入回收站', cancelButtonText: '取消', type: 'warning',
    })
    await albumService.batchUpdatePhotos({ photo_ids: ids, action: 'delete' })
    const removed = new Set(ids)
    photos.value = photos.value.filter(photo => !removed.has(photo.id))
    if (!preserveSelection) gallery.value?.exitSelectionMode()
    ElMessage.success('已移入回收站')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('移入回收站失败')
  } finally {
    deleting = false
  }
}
const { visible, index, open, close, prev, next } = usePhotoViewer(photos)
const lightboxInitialDetails = ref(false)
const openPhoto = (photo: AlbumImage, details = false) => {
  lightboxInitialDetails.value = details
  open(photo)
}
let requestId = 0
let objectUrl = ''
const releasePreview = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = '' }

const search = async () => {
  const current = ++requestId
  loading.value = true
  error.value = ''
  close()
  gallery.value?.exitSelectionMode()
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
const selectFile = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void useSourceFile(file)
}
function dropFile(event: DragEvent) {
  if (loading.value) return
  const files = event.dataTransfer?.files
  if (!files?.length) return
  if (files.length === 1) void useSourceFile(files[0])
  else error.value = '一次只能搜索一张图片'
}
async function useSourceFile(file: File) {
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
onBeforeUnmount(() => {
  ++requestId
  if (gallery.value?.isSelectionMode) uiStore.setSelectionActive(false)
  releasePreview()
})
</script>

<style>
.image-search-picker .responsive-dialog-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}
</style>
<style scoped>
.image-search-source { display: grid; gap: 13px; justify-items: center; margin: 12px 0 22px; padding: clamp(24px, 5vw, 66px) 15px; border: 1px dashed var(--ts-color-border); border-radius: 21px; background: var(--ts-journal-rail); text-align: center; }
.image-search-mark { display: grid; width: 58px; height: 58px; place-items: center; border-radius: 17px; background: var(--ts-journal-active); color: var(--ts-journal-accent-text); }
.image-search-mark svg { width: 28px; height: 28px; }
.image-search-upload { background: var(--ts-journal-action); color: white; }
.image-search-upload:hover { background: var(--ts-journal-action-hover); }
.image-search-source .flex { justify-content: center; }
</style>
