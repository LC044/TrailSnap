<template>
  <div class="lm-home">
    <header class="lm-home-head">
      <div class="lm-home-heading">
        <p class="lm-eyebrow lm-home-date"><span class="lm-home-pulse" aria-hidden="true"></span><time :datetime="todayKey">{{ todayLabel }}</time></p>
        <h1 class="lm-display lm-home-title ts-mask" style="--ts-mask-delay: 80ms"><span>影像手记</span></h1>
      </div>
      <div class="lm-home-actions">
        <RouterLink to="/mobile-search" class="lm-home-round" aria-label="搜索照片" title="搜索照片"><Search /></RouterLink>
        <button type="button" class="lm-home-import lm-sheen" aria-label="导入照片" @click="uploadStore.open()"><Plus /><span>导入照片</span></button>
      </div>
    </header>

    <DisplayDiagnostics v-if="showDisplayDiagnostics" />

    <div class="lm-stage">
      <section
        ref="featuredElement"
        class="lm-hero"
        aria-label="精选影像"
        :aria-busy="mediaLoading"
        tabindex="0"
        @keydown.left.prevent="turnCover(-1)"
        @keydown.right.prevent="turnCover(1)"
        @pointermove="trackCoverPoint"
        @pointerenter="coverHovered = true"
        @pointerleave="onCoverLeave"
        @pointerdown="startCoverDrag"
      >
        <Transition :name="coverDirection > 0 ? 'lm-next' : 'lm-prev'">
          <div v-if="coverPhoto && coverSrc" :key="coverPhoto.id" class="lm-hero-plate">
            <img
              :src="coverSrc"
              :data-photo-id="coverPhoto.id"
              alt=""
              class="lm-hero-image"
              draggable="false"
              fetchpriority="high"
              @error="hideCoverThumbnail"
            />
          </div>
        </Transition>

        <div class="lm-hero-shade" aria-hidden="true"></div>
        <span class="lm-hero-glare" aria-hidden="true"></span>

        <!-- 章节进度：细线段，当前一段随计时器生长 -->
        <div v-if="featuredPhotos.length > 1" class="lm-hero-progress" role="group" aria-label="精选影像进度">
          <button
            v-for="(item, index) in featuredPhotos"
            :key="item.id"
            type="button"
            class="lm-hero-seg"
            :class="{ 'is-active': index === coverIndex, 'is-past': index < coverIndex }"
            :aria-label="`查看第 ${index + 1} 张精选影像`"
            :aria-current="index === coverIndex ? 'true' : undefined"
            @click.stop="selectCover(index)"
          >
            <i
              v-if="index === coverIndex && autoAdvance"
              :key="`${coverIndex}-${coverRunId}`"
              :style="{ animationDuration: `${COVER_INTERVAL}ms`, animationPlayState: (coverHovered || coverQuiet || coverAutoPaused) ? 'paused' : 'running' }"
            />
          </button>
        </div>

        <div v-if="mediaLoading && !coverPhoto" class="lm-hero-copy lm-hero-copy--idle" role="status">
          <h2 class="lm-display">正在翻开手记…</h2>
        </div>
        <div v-else :key="`copy-${coverIndex}`" class="lm-hero-copy">
          <p class="lm-hero-kicker">
            <span>{{ coverPhoto ? '精选影像' : mediaError ? '手记暂时无法打开' : '从这里开始' }}</span>
            <span v-if="coverAge" class="lm-hero-age">{{ coverAge }}</span>
            <span v-if="featuredPhotos.length > 1" class="lm-index">{{ String(coverIndex + 1).padStart(2, '0') }} / {{ String(featuredPhotos.length).padStart(2, '0') }}</span>
          </p>
          <h2 class="lm-display lm-hero-title">
            {{ coverPhoto ? (isAnniversary ? '那年今日' : '重看这一帧') : mediaError ? '稍后再试一次' : '把日子留在画面里' }}
          </h2>
          <p v-if="coverPhoto" class="lm-hero-meta">
            <span><CalendarDays />{{ formatPhotoDate(coverPhoto, true) || '拍摄日期未知' }}</span>
            <template v-if="coverPlace"><span class="lm-hero-meta-dot" aria-hidden="true"></span><span><MapPin />{{ coverPlace }}</span></template>
          </p>
          <p v-if="coverPhoto?.image_description?.narrative" class="lm-hero-narrative">{{ coverPhoto.image_description.narrative }}</p>
          <p v-else-if="!coverPhoto && !mediaError" class="lm-hero-narrative">导入照片或视频，开始记录你的故事。</p>
          <div class="lm-hero-actions">
            <button v-if="coverPhoto" type="button" class="lm-hero-cta" @click="openCover">打开影像 <ArrowUpRight /></button>
            <button v-else-if="mediaError" type="button" class="lm-hero-cta" @click="loadMedia">重试 <RotateCw /></button>
            <button v-else type="button" class="lm-hero-cta" @click="uploadStore.open()">导入影像 <ArrowUpRight /></button>
            <button
              v-if="autoAdvance"
              type="button"
              class="lm-hero-pause"
              :aria-label="coverAutoPaused ? '继续自动轮播' : '暂停自动轮播'"
              :aria-pressed="coverAutoPaused"
              @click.stop="coverAutoPaused = !coverAutoPaused"
            >
              <Play v-if="coverAutoPaused" class="h-3.5 w-3.5" />
              <Pause v-else class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div v-if="featuredPhotos.length > 1" class="lm-hero-nav" role="group" aria-label="精选影像切换">
          <button type="button" aria-label="上一张精选影像" @click.stop="turnCover(-1)"><ArrowLeft /></button>
          <button type="button" aria-label="下一张精选影像" @click.stop="turnCover(1)"><ArrowRight /></button>
        </div>
      </section>

      <!-- 桌面侧栏：一条竖直的底片夹 -->
      <aside v-if="featuredPhotos.length > 1" class="lm-contact" aria-label="精选影像列表">
        <p class="lm-eyebrow lm-contact-label">In this roll</p>
        <button
          v-for="(item, index) in featuredPhotos"
          :key="`strip-${item.id}`"
          type="button"
          class="lm-contact-item"
          :class="{ 'is-active': index === coverIndex }"
          :aria-label="`查看第 ${index + 1} 张精选影像：${formatPhotoDate(item, true) || '日期未知'}`"
          @click="selectCover(index)"
        >
          <span class="lm-contact-thumb">
            <img v-if="hasThumbnail(item)" :src="thumbnailUrl(item.id, 'small', item.owner_id)" alt="" loading="lazy" />
            <ImageIcon v-else class="h-4 w-4" />
          </span>
          <span class="lm-contact-copy">
            <strong>{{ formatPhotoDate(item, true) || '日期未知' }}</strong>
            <span>{{ [yearsAgo(item), item.metadata_info?.city].filter(Boolean).join(' · ') || '—' }}</span>
          </span>
        </button>
      </aside>
    </div>

    <section class="lm-tiles" aria-label="继续探索">
      <RouterLink v-reveal="{ delay: 120, y: 18 }" to="/footprint" class="lm-tile lm-tile--map">
        <span class="lm-map-art" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><MapPin /></span>
        <span class="lm-tile-body">
          <span class="lm-tile-icon"><MapPin class="h-4 w-4" /></span>
          <span class="lm-tile-text">
            <strong>足迹地图</strong>
            <span v-if="footprintData?.city_count">走过 {{ footprintData.city_count }} 座城市</span>
            <span v-else>按地点重温影像</span>
          </span>
          <ArrowUpRight class="lm-tile-arrow" aria-hidden="true" />
        </span>
      </RouterLink>
      <DailyFrameCard v-reveal="{ delay: 220, y: 18 }" />
      <RouterLink v-reveal="{ delay: 320, y: 18 }" to="/memories" class="lm-tile lm-tile--memory">
        <span class="lm-tile-body">
          <span class="lm-tile-icon"><BookHeart class="h-4 w-4" /></span>
          <span class="lm-tile-text">
            <strong>回忆</strong>
            <span>被串起来的日子</span>
          </span>
          <ArrowUpRight class="lm-tile-arrow" aria-hidden="true" />
        </span>
      </RouterLink>
    </section>

    <section v-reveal="{ y: 14 }" class="lm-block" aria-labelledby="lm-recent-title">
      <div class="lm-section-head">
        <div>
          <p class="lm-eyebrow">{{ recentImports ? '刚刚添加' : 'Last frames' }}</p>
          <h2 id="lm-recent-title" class="lm-title">{{ recentImports ? '最近导入' : '最近拍摄' }}</h2>
        </div>
        <RouterLink to="/photos" class="lm-more">全部照片 <ArrowRight /></RouterLink>
      </div>
      <HorizontalStrip v-if="recentPhotos.length" :label="recentImports ? '最近导入' : '最近拍摄'" strip-class="lm-filmstrip">
        <button
          v-for="(photo, index) in recentPhotos"
          :key="photo.id"
          type="button"
          class="lm-film"
          :style="{ '--i': index }"
          :aria-label="`打开 ${photo.filename || formatPhotoDate(photo, true) || '最近拍摄的影像'}`"
          @click="openPhoto(recentPhotos, index, $event)"
        >
          <span class="lm-film-frame">
            <img v-if="hasThumbnail(photo) && !missingThumbnails.has(photo.id)" :src="thumbnailUrl(photo.id, 'small', photo.owner_id)" alt="" loading="lazy" @error="missingThumbnails.add(photo.id)" />
            <ImageIcon v-else class="lm-film-placeholder" />
            <span v-if="photo.file_type === FileType.Video" class="lm-film-video" title="视频"><Play fill="currentColor" /></span>
          </span>
          <span class="lm-film-meta">
            <strong class="lm-num">{{ formatPhotoDate(photo) || '日期未知' }}</strong>
            <span v-if="photo.metadata_info?.city">{{ photo.metadata_info.city }}</span>
          </span>
        </button>
      </HorizontalStrip>
      <div v-else-if="mediaLoading" class="lm-filmstrip" aria-hidden="true">
        <div v-for="index in 5" :key="index" class="lm-film-skeleton"></div>
      </div>
      <div v-else class="lm-empty">
        <Images aria-hidden="true" />
        <span>{{ recentError ? '最近拍摄暂时无法加载' : '导入后的影像会出现在这里。' }}</span>
        <button v-if="recentError" type="button" class="lm-more" @click="loadMedia">重试 <RotateCw /></button>
        <RouterLink v-else to="/settings#external" class="lm-more">连接已有图库 <ArrowRight /></RouterLink>
      </div>
    </section>

    <MemoryDiscovery v-reveal="{ y: 16 }" class="lm-block" />

    <section v-reveal="{ y: 16 }" class="lm-block" aria-labelledby="lm-explore-title">
      <div class="lm-section-head">
        <div>
          <p class="lm-eyebrow">Ways in</p>
          <h2 id="lm-explore-title" class="lm-title">更多玩法</h2>
        </div>
      </div>
      <div class="lm-explore">
        <RouterLink v-for="item in exploreLinks" :key="item.href" :to="item.href" class="lm-explore-link">
          <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span><ArrowUpRight class="lm-explore-arrow" />
        </RouterLink>
      </div>
    </section>

    <details v-reveal="{ y: 12 }" class="lm-overview" @toggle="loadOverview">
      <summary>
        <span class="lm-overview-title">图库概览</span>
        <span v-if="dashboardData" class="lm-overview-count lm-num">{{ dashboardData.card.total_media.toLocaleString('zh-CN') }} 项影像</span>
        <ChevronDown />
      </summary>
      <div class="lm-overview-body">
        <div class="lm-overview-toolbar">
          <button type="button" class="lm-more" @click="showStorageDialog = true"><HardDrive /> 存储空间管理</button>
        </div>
        <p v-if="!dashboardData" class="lm-empty" role="status">
          {{ overviewLoading ? '正在加载图库概览…' : '图库概览暂时无法加载' }}
          <button v-if="!overviewLoading" type="button" class="lm-more" @click="fetchOverview">重试 <RotateCw /></button>
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
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, ArrowRight, ArrowUpRight, BookHeart, CalendarDays, ChevronDown, HardDrive,
  Image as ImageIcon, Images, MapPin, Pause, Play, Plus, RotateCw, Search, Ticket,
} from 'lucide-vue-next'
import { albumService } from '@/api/album'
import { dashboardApi, type DashboardResponse } from '@/api/dashboard'
import { locationService, type OverviewStats } from '@/api/location'
import { photoApi } from '@/api/photo'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useUploadStore } from '@/stores/uploadCenterStore'
import { FileType, type AlbumImage, type Photo } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { reducedMotion, spring } from '@/utils/motion'
import { aspectOf, flyPhotoBackTo, flyPhotoIntoViewer } from '@/utils/photoFlight'
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
/* Which way the last cover change travelled; drives the dissolve direction. */
const coverDirection = ref(1)
// Declared here because the cover's auto-advance watcher reads it eagerly.
const viewerIndex = ref<number | null>(null)
const mediaLoading = ref(true)
const recentError = ref(false)
const anniversaryError = ref(false)
const mediaError = computed(() => recentError.value || anniversaryError.value)
let loadingMedia = false
const pageActive = ref(false)

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

/* “16 年前” — the emotional distance, shown as a small chip on the cover. */
function yearsAgo(photo: Photo) {
  if (!photo.photo_time) return ''
  const date = new Date(photo.photo_time)
  if (Number.isNaN(date.getTime())) return ''
  const years = today.value.getFullYear() - date.getFullYear()
  return years > 0 ? `${years} 年前` : ''
}
const coverAge = computed(() => (coverPhoto.value ? yearsAgo(coverPhoto.value) : ''))

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

function turnCover(direction: number) {
  // Ignore the click a drag leaves behind.
  if (performance.now() < dragGuardUntil) return
  stepCover(direction)
}

function stepCover(direction: number) {
  const length = featuredPhotos.value.length
  if (length > 1) {
    coverDirection.value = direction
    coverIndex.value = (coverIndex.value + direction + length) % length
  }
}

/* Jump straight to a frame from the progress bar or the contact strip. */
function selectCover(index: number) {
  if (index === coverIndex.value || index < 0 || index >= featuredPhotos.value.length) return
  coverDirection.value = index > coverIndex.value ? 1 : -1
  coverIndex.value = index
  coverAutoPaused.value = false
  holdCover()
}

/* ---------------------------------------------------------------------------
 * Cover motion.
 *
 * The featured frame behaves like a print left on a desk: it slowly pushes in
 * (Ken Burns), catches the light as the pointer moves across it (glare +
 * parallax), and — unless the visitor is holding it — the journal turns to the
 * next memory on its own. Every effect is gated on reduced motion, on hover
 * pause, on an open viewer, and on the page actually being visible.
 * ------------------------------------------------------------------------- */

/* ---------------------------------------------------------------------------
 * Cover drag.
 *
 * The featured print can be dragged aside like a photograph on a desk: it
 * follows the finger with a rubber band, leans away from the direction of
 * travel and shrinks a touch as it lifts. Released short of the threshold it
 * springs back; released past it, the journal turns the page and the print
 * continues into the turn from wherever the finger left it.
 * ------------------------------------------------------------------------- */
const DRAG_COMMIT_RATIO = 0.18
const DRAG_WIDTH_SPAN = 0.55
let coverDrag: {
  pointerId: number
  startX: number
  startY: number
  lastX: number
  lastTime: number
  velocity: number
  axis: 'x' | 'y' | null
  plate: HTMLElement | null
  dx: number
} | null = null
let dragGuardUntil = 0

function startCoverDrag(event: PointerEvent) {
  holdCover()
  if (featuredPhotos.value.length < 2 || reducedMotion() || !event.isPrimary || event.button !== 0
    || (event.target instanceof Element && event.target.closest('button, a'))) return
  const plate = featuredElement.value?.querySelector<HTMLElement>('.lm-hero-plate') ?? null
  if (!plate) return
  coverDrag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    lastX: event.clientX,
    lastTime: performance.now(),
    velocity: 0,
    axis: null,
    plate,
    dx: 0,
  }
  window.addEventListener('pointerup', endCoverDrag)
  window.addEventListener('pointercancel', endCoverDrag)
}

function paintCoverDrag(plate: HTMLElement, dx: number) {
  const width = featuredElement.value?.clientWidth || 1
  const progress = Math.min(1, Math.abs(dx) / (width * DRAG_WIDTH_SPAN))
  plate.style.setProperty('--cover-drag-x', `${dx.toFixed(1)}px`)
  plate.style.setProperty('--cover-drag-r', `${(dx * 0.014).toFixed(2)}deg`)
  plate.style.setProperty('--cover-drag-s', `${(1 - progress * 0.04).toFixed(3)}`)
}

function moveCoverDrag(event: PointerEvent) {
  const drag = coverDrag
  if (!drag || event.pointerId !== drag.pointerId) return false
  const dx = event.clientX - drag.startX
  const dy = event.clientY - drag.startY
  if (!drag.axis) {
    // Lock to the horizontal axis only once the gesture is clearly sideways.
    if (Math.abs(dx) < 10 || Math.abs(dx) <= Math.abs(dy)) return true
    drag.axis = 'x'
    drag.plate?.classList.add('is-dragging')
  }
  const now = performance.now()
  const elapsed = Math.max(1, now - drag.lastTime)
  drag.velocity = (event.clientX - drag.lastX) / elapsed
  drag.lastX = event.clientX
  drag.lastTime = now

  const width = featuredElement.value?.clientWidth || 320
  const limit = width * DRAG_WIDTH_SPAN
  // A tanh curve: free near the middle, progressively heavier at the edges.
  drag.dx = limit * Math.tanh(dx / limit)
  if (drag.plate) paintCoverDrag(drag.plate, drag.dx)
  return true
}

function endCoverDrag() {
  const drag = coverDrag
  if (!drag) return
  coverDrag = null
  window.removeEventListener('pointerup', endCoverDrag)
  window.removeEventListener('pointercancel', endCoverDrag)
  const plate = drag.plate
  if (!plate) return
  if (drag.axis !== 'x') return
  const width = featuredElement.value?.clientWidth || 320
  dragGuardUntil = performance.now() + 360

  const committed = Math.abs(drag.dx) > width * DRAG_COMMIT_RATIO || Math.abs(drag.velocity) > 0.6

  if (committed) {
    // The print keeps its offset; the turn's own transition starts from there.
    plate.classList.remove('is-dragging')
    stepCover(drag.dx < 0 ? 1 : -1)
    return
  }

  plate.classList.remove('is-dragging')
  spring(drag.dx, 0, drag.velocity, value => paintCoverDrag(plate, value), () => {
    plate.style.removeProperty('--cover-drag-x')
    plate.style.removeProperty('--cover-drag-r')
    plate.style.removeProperty('--cover-drag-s')
  })
}
const COVER_INTERVAL = 9000
const coverHovered = ref(false)
/* A touch on the cover buys the reader quiet time, since touch devices never
   fire pointerleave to pause the rotation. */
const coverQuiet = ref(false)
/* Explicit user pause; the hairline at the foot of the cover is the control. */
const coverAutoPaused = ref(false)
const autoAdvance = computed(() => featuredPhotos.value.length > 1 && !reducedMotion())
const coverRunId = ref(0)
let coverTimer: number | undefined
let quietTimer: number | undefined

function clearCoverTimer() {
  if (coverTimer !== undefined) window.clearTimeout(coverTimer)
  coverTimer = undefined
}

function holdCover() {
  coverQuiet.value = true
  if (quietTimer !== undefined) window.clearTimeout(quietTimer)
  quietTimer = window.setTimeout(() => { coverQuiet.value = false }, 9000)
}

function scheduleCover() {
  clearCoverTimer()
  coverRunId.value += 1
  if (!autoAdvance.value || coverAutoPaused.value || coverHovered.value || coverQuiet.value
    || viewerIndex.value !== null || !pageActive.value || document.hidden) return
  coverTimer = window.setTimeout(() => stepCover(1), COVER_INTERVAL)
}

const onCoverVisibility = () => scheduleCover()
watch(
  [coverIndex, coverHovered, coverQuiet, coverAutoPaused, () => featuredPhotos.value.length, viewerIndex, pageActive],
  scheduleCover,
  { flush: 'post' },
)
onMounted(() => document.addEventListener('visibilitychange', onCoverVisibility))
onBeforeUnmount(() => {
  clearCoverTimer()
  if (quietTimer !== undefined) window.clearTimeout(quietTimer)
  document.removeEventListener('visibilitychange', onCoverVisibility)
})

/* Pointer glare: one rAF per frame, offsets in CSS px, eased by CSS. */
let glareFrame = 0
let glareX = 0
let glareY = 0

function trackCoverPoint(event: PointerEvent) {
  if (moveCoverDrag(event)) return
  if (event.pointerType === 'touch') return
  const element = featuredElement.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  glareX = event.clientX - rect.left
  glareY = event.clientY - rect.top
  if (glareFrame) return
  glareFrame = requestAnimationFrame(() => {
    glareFrame = 0
    element.style.setProperty('--cover-glare-x', `${glareX}px`)
    element.style.setProperty('--cover-glare-y', `${glareY}px`)
    // A gentle counter-move of the print under the pointer.
    const rx = (glareX / rect.width - .5) * 2
    const ry = (glareY / rect.height - .5) * 2
    element.style.setProperty('--cover-par-x', `${(-rx * 7).toFixed(2)}px`)
    element.style.setProperty('--cover-par-y', `${(-ry * 5).toFixed(2)}px`)
  })
}

function resetCoverPoint() {
  const element = featuredElement.value
  if (!element) return
  element.style.setProperty('--cover-par-x', '0px')
  element.style.setProperty('--cover-par-y', '0px')
}

function onCoverLeave() {
  coverHovered.value = false
  resetCoverPoint()
}

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
const organizeActions = ref<InstanceType<typeof PhotoOrganizeActions> | null>(null)
let viewerTrigger: HTMLElement | null = null
/* The frame a photo was lifted out of, so it can be put back on close. */
let viewerOrigin: HTMLElement | null = null
/* Return the print only when the viewer still shows the photo it was opened on. */
let viewerOriginPhotoId: string | null = null

/**
 * Opening always goes through the flight: the thumbnail is physically carried
 * into the viewer. Falling back to a plain open is handled inside the helper.
 */
function openPhoto(photos: Photo[], index: number, event?: MouseEvent) {
  const photo = photos[index]
  // A video has its own player entrance; only a print can be carried.
  if (photo?.file_type === FileType.Video) {
    viewerOrigin = null
    openViewer(photos, index)
    return
  }
  const source = (event?.currentTarget as HTMLElement | null) ?? featuredElement.value
  viewerOrigin = source
  flyPhotoIntoViewer(source, aspectOf(photo?.width, photo?.height), () => openViewer(photos, index))
}

function openCover() {
  // A drag that just ended must not also count as opening the photo.
  if (performance.now() < dragGuardUntil) return
  const source = featuredElement.value
  viewerOrigin = source
  flyPhotoIntoViewer(source, aspectOf(coverPhoto.value?.width, coverPhoto.value?.height), () => {
    openViewer(featuredPhotos.value, coverIndex.value)
  })
}

function openViewer(photos: Photo[], index: number) {
  viewerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  viewerImages.value = photos.map(mapPhotoToImage)
  viewerOriginPhotoId = photos[index]?.id ?? null
  selectViewer(index)
}

function selectViewer(index: number) {
  if (index >= 0 && index < viewerImages.value.length) viewerIndex.value = index
}

function closeViewer() {
  const current = viewerImages.value[viewerIndex.value ?? -1]
  if (current && current.id === viewerOriginPhotoId) flyPhotoBackTo(viewerOrigin, 0)
  viewerOrigin = null
  viewerOriginPhotoId = null
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
  pageActive.value = true
  void loadMedia()
  void fetchFootprint()
  if (dashboardData.value) void fetchOverview()
})
onDeactivated(() => { pageActive.value = false })
watch(() => uploadStore.running, (running, wasRunning) => {
  if (pageActive.value && wasRunning && !running && uploadStore.completed) void loadMedia()
})
</script>
