<template>
  <div class="journal-home">
    <header class="journal-masthead">
      <div>
        <p class="journal-date"><span aria-hidden="true"></span><time :datetime="todayKey">{{ todayLabel }}</time></p>
        <h1 class="journal-page-title">影像手记</h1>
      </div>
      <div class="journal-actions">
        <RouterLink to="/mobile-search" class="journal-icon" aria-label="搜索照片" title="搜索照片"><Search /></RouterLink>
        <button type="button" class="journal-import ts-glass-control" aria-label="导入照片" @click="uploadStore.open()"><Plus /><span>导入照片</span></button>
      </div>
    </header>

    <DisplayDiagnostics v-if="showDisplayDiagnostics" />

    <div class="journal-spread">
      <section
        ref="featuredElement"
        class="journal-cover"
        aria-label="精选影像"
        :aria-busy="mediaLoading"
        @keydown.left.prevent="stepCover(-1)"
        @keydown.right.prevent="stepCover(1)"
      >
        <Transition name="journal-dissolve">
          <img
            v-if="coverPhoto && coverSrc"
            :key="coverPhoto.id"
            :src="coverSrc"
            :data-photo-id="coverPhoto.id"
            alt=""
            class="journal-cover-image"
            fetchpriority="high"
            @error="hideCoverThumbnail"
          />
          <img v-else-if="!mediaLoading && !coverPhoto" key="cover" :src="journalCover" alt="" class="journal-cover-image" fetchpriority="high" />
        </Transition>
        <div class="journal-cover-shade" aria-hidden="true"></div>
        <div v-if="mediaLoading && !coverPhoto" class="journal-cover-content" role="status">正在翻开手记…</div>
        <div v-else class="journal-cover-content">
          <p v-if="coverPhoto" class="journal-cover-date"><CalendarDays />{{ formatPhotoDate(coverPhoto, true) || '拍摄日期未知' }}</p>
          <h2>{{ coverPhoto ? (isAnniversary ? '那年今日' : '重看这一帧') : mediaError ? '手记暂时无法打开' : '把日子留在画面里' }}</h2>
          <p v-if="coverPlace" class="journal-cover-location"><MapPin />{{ coverPlace }}</p>
          <p v-if="coverPhoto?.image_description?.narrative" class="journal-cover-narrative">{{ coverPhoto.image_description.narrative }}</p>
          <p v-else-if="!coverPhoto && !mediaError" class="journal-cover-description">导入照片或视频，开始记录你的故事。</p>
          <button v-if="coverPhoto" type="button" class="journal-cover-action" @click="openViewer(featuredPhotos, coverIndex)">打开影像 <ArrowUpRight /></button>
          <button v-else-if="mediaError" type="button" class="journal-cover-action" @click="loadMedia">重试 <RotateCw /></button>
          <button v-else type="button" class="journal-cover-action" @click="uploadStore.open()">导入影像 <ArrowUpRight /></button>
        </div>
        <div v-if="featuredPhotos.length > 1" class="journal-cover-controls" aria-label="精选影像切换" role="group">
          <button type="button" aria-label="上一张精选影像" @click="stepCover(-1)"><ArrowLeft /></button>
          <span aria-live="polite">{{ coverIndex + 1 }} / {{ featuredPhotos.length }}</span>
          <button type="button" aria-label="下一张精选影像" @click="stepCover(1)"><ArrowRight /></button>
        </div>
      </section>

      <aside class="journal-feature-links" aria-label="探索手记">
        <RouterLink to="/footprint" class="journal-feature journal-feature--map">
          <span class="journal-map-art" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><MapPin /></span>
          <MapPin class="journal-feature-icon" />
          <span class="journal-feature-copy">
            <strong>足迹地图</strong>
            <span v-if="footprintData?.city_count">走过 {{ footprintData.city_count }} 座城市</span>
            <span v-else>按地点重温影像</span>
          </span>
          <ArrowUpRight class="journal-feature-arrow" />
        </RouterLink>
        <DailyFrameCard />
      </aside>
    </div>

    <section class="journal-section" aria-labelledby="journal-recent-title">
      <div class="journal-section-heading">
        <h2 id="journal-recent-title">{{ recentImports ? '最近导入' : '最近拍摄' }}</h2>
        <RouterLink to="/photos" class="journal-text-link">全部照片 <ArrowRight /></RouterLink>
      </div>
      <HorizontalStrip v-if="recentPhotos.length" :label="recentImports ? '最近导入' : '最近拍摄'" strip-class="journal-filmstrip">
        <button
          v-for="(photo, index) in recentPhotos"
          :key="photo.id"
          type="button"
          class="journal-frame"
          :aria-label="`打开 ${photo.filename || formatPhotoDate(photo, true) || '最近拍摄的影像'}`"
          @click="openViewer(recentPhotos, index)"
        >
          <span class="journal-frame-image">
            <img v-if="hasThumbnail(photo) && !missingThumbnails.has(photo.id)" :src="thumbnailUrl(photo.id, 'small', photo.owner_id)" alt="" loading="lazy" @error="missingThumbnails.add(photo.id)" />
            <ImageIcon v-else class="journal-frame-placeholder" />
            <span v-if="photo.file_type === FileType.Video" class="journal-video-mark" title="视频"><Play fill="currentColor" /></span>
          </span>
          <span class="journal-frame-caption">
            <span>{{ formatPhotoDate(photo) || '日期未知' }}</span>
            <span v-if="photo.metadata_info?.city" class="journal-frame-location">{{ photo.metadata_info.city }}</span>
          </span>
        </button>
      </HorizontalStrip>
      <div v-else-if="mediaLoading" class="journal-filmstrip" aria-hidden="true">
        <div v-for="index in 5" :key="index" class="journal-frame-skeleton"></div>
      </div>
      <div v-else class="journal-empty">
        <Images aria-hidden="true" />
        <span>{{ recentError ? '最近拍摄暂时无法加载' : '导入后的影像会出现在这里。' }}</span>
        <button v-if="recentError" type="button" class="journal-text-link" @click="loadMedia">重试 <RotateCw /></button>
        <RouterLink v-else to="/settings#external" class="journal-text-link">连接已有图库 <ArrowRight /></RouterLink>
      </div>
    </section>

    <MemoryDiscovery class="journal-section" />

    <section class="journal-section" aria-labelledby="journal-explore-title">
      <div class="journal-section-heading"><h2 id="journal-explore-title">更多玩法</h2></div>
      <div class="journal-explore">
        <RouterLink v-for="item in exploreLinks" :key="item.href" :to="item.href" class="journal-explore-link">
          <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span><ArrowUpRight class="journal-explore-arrow" />
        </RouterLink>
      </div>
    </section>

    <details class="journal-section journal-overview" @toggle="loadOverview">
      <summary>
        <span class="journal-overview-title">图库概览</span>
        <span v-if="dashboardData" class="journal-overview-count">{{ dashboardData.card.total_media.toLocaleString('zh-CN') }} 项影像</span>
        <ChevronDown />
      </summary>
      <div class="journal-overview-body">
        <div class="journal-overview-toolbar">
          <button type="button" class="journal-text-link" @click="showStorageDialog = true"><HardDrive /> 存储空间管理</button>
        </div>
        <p v-if="!dashboardData" class="journal-empty" role="status">
          {{ overviewLoading ? '正在加载图库概览…' : '图库概览暂时无法加载' }}
          <button v-if="!overviewLoading" type="button" class="journal-text-link" @click="fetchOverview">重试 <RotateCw /></button>
        </p>
        <template v-else>
          <OverviewCards :data="dashboardData.card" :content="dashboardData.content" @show-storage="showStorageDialog = true" />
          <div class="ts-surface p-4 md:p-6">
            <div class="flex flex-col gap-6 xl:flex-row">
              <div class="w-full shrink-0 xl:w-64"><TimeChart :data="dashboardData.time" /></div>
              <div class="min-w-0 flex-1"><HeatmapSection /></div>
            </div>
          </div>
          <div class="grid gap-4 lg:grid-cols-2">
            <FootprintCard :data="footprintData" :loading="footprintLoading" @retry="fetchFootprint" />
            <FaceSection :data="dashboardData.face" />
          </div>
        </template>
      </div>
    </details>

    <PhotoLightbox
      :visible="viewerIndex !== null"
      :image="viewerIndex === null ? null : viewerImages[viewerIndex] ?? null"
      :images="viewerImages"
      :current-index="viewerIndex ?? -1"
      :has-prev="viewerIndex !== null && viewerIndex > 0"
      :has-next="viewerIndex !== null && viewerIndex < viewerImages.length - 1"
      allow-edit
      allow-delete
      allow-add-to-album
      allow-add-to-person
      allow-move-to-folder
      @close="closeViewer"
      @prev="selectViewer((viewerIndex ?? 0) - 1)"
      @next="selectViewer((viewerIndex ?? 0) + 1)"
      @select="selectViewer"
      @update="updateViewerPhoto"
      @delete="removeViewerPhoto"
      @add-to-album="image => organizeActions?.openAlbum(image.id)"
      @transfer="organizeActions?.openMove(viewerImages[viewerIndex ?? -1]?.id || '')"
    />
    <PhotoOrganizeActions ref="organizeActions" @transfer-success="loadMedia" />
    <ResponsiveDialog v-model="showStorageDialog" title="存储空间管理" max-width="75rem" mobile-mode="fullscreen" mobile-back>
      <StorageCenter />
    </ResponsiveDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, ref, shallowRef, watch } from 'vue'
import { useSwipe } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, ArrowRight, ArrowUpRight, BookHeart, CalendarDays, ChevronDown, HardDrive,
  Image as ImageIcon, Images, MapPin, Play, Plus, RotateCw, Search, Ticket,
} from 'lucide-vue-next'
import { albumService } from '@/api/album'
import { dashboardApi, type DashboardResponse } from '@/api/dashboard'
import { locationService, type OverviewStats } from '@/api/location'
import { photoApi } from '@/api/photo'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useUploadStore } from '@/stores/uploadCenterStore'
import { FileType, type AlbumImage, type Photo } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import journalCover from '@/assets/journal-cover.webp'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import PhotoOrganizeActions from '@/components/PhotoOrganizeActions.vue'
import DailyFrameCard from '@/components/home/DailyFrameCard.vue'
import DisplayDiagnostics from '@/components/home/DisplayDiagnostics.vue'
import FaceSection from '@/components/home/FaceSection.vue'
import FootprintCard from '@/components/home/FootprintCard.vue'
import HeatmapSection from '@/components/home/HeatmapSection.vue'
import MemoryDiscovery from '@/components/home/MemoryDiscovery.vue'
import OverviewCards from '@/components/home/OverviewCards.vue'
import StorageCenter from '@/components/home/StorageCenter.vue'
import TimeChart from '@/components/home/TimeChart.vue'
import HorizontalStrip from '@/components/ui/HorizontalStrip.vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import '@/styles/journal.css'

defineOptions({ name: 'HomePage' })

const uploadStore = useUploadStore()
const showDisplayDiagnostics = import.meta.env.DEV && new URLSearchParams(window.location.search).get('displayDiagnostics') === '1'
const showStorageDialog = ref(false)
const today = shallowRef(new Date())
const todayKey = computed(() => {
  const date = today.value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
})
const todayLabel = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(today.value))
const exploreLinks = [
  { href: '/memories', label: '回忆', icon: BookHeart },
  { href: '/annual-report', label: '年度回忆录', icon: CalendarDays },
  { href: '/ticket', label: '票夹', icon: Ticket },
  { href: '/game', label: '猜城市', icon: MapPin },
]

const featuredElement = ref<HTMLElement | null>(null)
const anniversaries = shallowRef<Photo[]>([])
const recentPhotos = shallowRef<Photo[]>([])
const recentImports = ref(false)
const missingThumbnails = ref(new Set<string>())
const missingCovers = ref(new Set<string>())
const coverIndex = ref(0)
const mediaLoading = ref(true)
const recentError = ref(false)
const anniversaryError = ref(false)
const mediaError = computed(() => recentError.value || anniversaryError.value)
let loadingMedia = false
let pageActive = false

const featuredPhotos = computed(() => {
  const pool = anniversaries.value.length ? anniversaries.value : recentPhotos.value
  const photos = pool.filter(photo => hasThumbnail(photo) && photo.file_type !== FileType.Video)
  // Prefer a landscape that can fill the cover with minimal cropping.
  const lead = photos.find(photo => (photo.width ?? 0) >= 1200 && (photo.width ?? 0) / (photo.height || 1) >= 1.35)
  if (lead) return [lead, ...photos.filter(photo => photo.id !== lead.id)].slice(0, 6)
  return (photos.length ? photos : pool).slice(0, 6)
})
const coverPhoto = computed(() => featuredPhotos.value[coverIndex.value])
const coverSrc = computed(() => {
  const photo = coverPhoto.value
  return photo && hasThumbnail(photo) && !missingCovers.value.has(photo.id) ? thumbnailUrl(photo.id, 'medium', photo.owner_id) : ''
})
const coverPlace = computed(() => {
  const location = coverPhoto.value?.metadata_info
  return location?.city || location?.district || location?.province
})
const isAnniversary = computed(() => {
  const photoTime = coverPhoto.value?.photo_time
  if (!photoTime) return false
  const date = new Date(photoTime)
  return date.getMonth() === today.value.getMonth() && date.getDate() === today.value.getDate()
    && date.getFullYear() < today.value.getFullYear()
})

function hasThumbnail(photo: Photo) {
  return Boolean(photo.width && photo.height)
}

function hideCoverThumbnail(event: Event) {
  const id = (event.currentTarget as HTMLImageElement).dataset.photoId
  if (id) missingCovers.value.add(id)
}

const shortDate = new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' })
const longDate = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
function formatPhotoDate(photo: Photo, long = false) {
  if (!photo.photo_time) return ''
  const date = new Date(photo.photo_time)
  if (Number.isNaN(date.getTime())) return ''
  return (long || date.getFullYear() !== today.value.getFullYear() ? longDate : shortDate).format(date)
}

function stepCover(direction: number) {
  const length = featuredPhotos.value.length
  if (length > 1) coverIndex.value = (coverIndex.value + direction + length) % length
}
useSwipe(featuredElement, {
  threshold: 46,
  onSwipeEnd: (_event, direction) => {
    if (direction === 'left') stepCover(1)
    if (direction === 'right') stepCover(-1)
  },
})

async function loadMedia() {
  if (loadingMedia) return
  loadingMedia = true
  if (!recentPhotos.value.length && !anniversaries.value.length) mediaLoading.value = true
  today.value = new Date()
  const date = today.value
  const currentCover = coverPhoto.value?.id
  try {
    const [recentResult, anniversaryResult] = await Promise.allSettled([
      fetchRecentPhotos(),
      photoApi.getOnThisDayPhotos({ limit: 10, day: date.getDate(), month: date.getMonth() + 1, year: date.getFullYear() }),
    ])
    recentError.value = recentResult.status === 'rejected'
    anniversaryError.value = anniversaryResult.status === 'rejected'
    if (recentResult.status === 'fulfilled') {
      recentPhotos.value = recentResult.value.photos
      recentImports.value = recentResult.value.byUpload
    }
    if (anniversaryResult.status === 'fulfilled') anniversaries.value = anniversaryResult.value
    missingThumbnails.value.clear()
    missingCovers.value.clear()
    coverIndex.value = Math.max(0, featuredPhotos.value.findIndex(photo => photo.id === currentCover))
  } finally {
    loadingMedia = false
    mediaLoading.value = false
  }
}

async function fetchRecentPhotos() {
  const photos = await albumService.getAllPhotos(0, 12, {
    order_by: 'photo_time',
    order_dir: 'desc',
    end_time: `${todayKey.value}T23:59:59.999`,
  })
  if (photos.length) return { photos, byUpload: false }
  const imports = await albumService.getAllPhotos(0, 12, { order_by: 'upload_time', order_dir: 'desc' })
  return { photos: imports, byUpload: imports.length > 0 }
}

const viewerImages = shallowRef<AlbumImage[]>([])
const viewerIndex = ref<number | null>(null)
const organizeActions = ref<InstanceType<typeof PhotoOrganizeActions> | null>(null)
let viewerTrigger: HTMLElement | null = null

function openViewer(photos: Photo[], index: number) {
  viewerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  viewerImages.value = photos.map(mapPhotoToImage)
  selectViewer(index)
}

function selectViewer(index: number) {
  if (index >= 0 && index < viewerImages.value.length) viewerIndex.value = index
}

function closeViewer() {
  viewerIndex.value = null
  const trigger = viewerTrigger
  viewerTrigger = null
  void nextTick(() => trigger?.focus({ preventScroll: true }))
}

async function removeViewerPhoto(id: string) {
  try {
    await albumService.deletePhoto(id)
    closeViewer()
    anniversaries.value = anniversaries.value.filter(photo => photo.id !== id)
    recentPhotos.value = recentPhotos.value.filter(photo => photo.id !== id)
    coverIndex.value = Math.min(coverIndex.value, Math.max(0, featuredPhotos.value.length - 1))
    ElMessage.success('已移入回收站')
    void loadMedia()
  } catch {
    ElMessage.error('删除失败')
  }
}

function updateViewerPhoto(event: { id: string; filename?: string; photo_time?: string | null }) {
  viewerImages.value = viewerImages.value.map(image => image.id === event.id ? {
    ...image,
    filename: event.filename ?? image.filename,
    photoTime: event.photo_time === undefined ? image.photoTime : event.photo_time,
    hasPhotoTime: event.photo_time === undefined ? image.hasPhotoTime : Boolean(event.photo_time),
    timestamp: event.photo_time ? new Date(event.photo_time).getTime() : image.timestamp,
  } : image)
  void loadMedia()
}

const dashboardData = shallowRef<DashboardResponse | null>(null)
const overviewLoading = ref(false)
const footprintData = shallowRef<OverviewStats | null>(null)
const footprintLoading = ref(false)

async function fetchFootprint() {
  if (footprintLoading.value) return
  footprintLoading.value = true
  try {
    footprintData.value = await locationService.getOverview()
  } catch {
    // The map link remains available when its city count is unavailable.
  } finally {
    footprintLoading.value = false
  }
}

async function fetchOverview() {
  if (overviewLoading.value) return
  overviewLoading.value = true
  try {
    dashboardData.value = await dashboardApi.getOverview()
  } catch {
    // Keep the previous overview visible when refreshing fails.
  } finally {
    overviewLoading.value = false
  }
}

function loadOverview(event: Event) {
  if ((event.currentTarget as HTMLDetailsElement).open && !dashboardData.value) void fetchOverview()
}

onActivated(() => {
  pageActive = true
  void loadMedia()
  void fetchFootprint()
  if (dashboardData.value) void fetchOverview()
})
onDeactivated(() => { pageActive = false })
watch(() => uploadStore.running, (running, wasRunning) => {
  if (pageActive && wasRunning && !running && uploadStore.completed) void loadMedia()
})
</script>
