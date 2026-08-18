<template>
  <div class="h-screen w-full bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200 flex flex-col overflow-hidden relative select-none">
    <!-- 顶部状态栏 -->
    <header class="flex-none h-14 flex items-center justify-between px-4 z-20 bg-gradient-to-b from-slate-50/80 dark:from-slate-900/80 to-transparent">
      <button
        @click="handleBack"
        class="p-2 rounded-full bg-slate-200/50 dark:bg-slate-800/50 text-slate-700 dark:text-white hover:bg-slate-300/50 dark:hover:bg-slate-700 transition-colors backdrop-blur-md focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="返回并清理已丢弃的照片"
      >
        <ArrowLeft class="w-5 h-5" />
      </button>
      <div class="flex flex-col items-center">
        <h1 class="text-sm font-semibold tracking-wider text-slate-800 dark:text-slate-100">照片筛选</h1>
        <span class="text-xs text-slate-500 dark:text-slate-400">
          {{ processedCount }} / {{ totalCount }}
        </span>
      </div>
      <button
        @click="undo"
        :disabled="actionHistory.length === 0"
        class="p-2 rounded-full bg-slate-200/50 dark:bg-slate-800/50 text-slate-700 dark:text-white hover:bg-slate-300/50 dark:hover:bg-slate-700 transition-colors backdrop-blur-md disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="撤销 (Ctrl+Z)"
      >
        <Undo class="w-5 h-5" />
      </button>
    </header>

    <!-- 居中图片卡片区 -->
    <main class="flex-1 relative flex items-center justify-center p-4 overflow-hidden">
      <div v-if="loading && photos.length === 0" class="flex flex-col items-center gap-4 text-slate-500 dark:text-slate-400">
        <div class="w-8 h-8 border-4 border-slate-300 dark:border-slate-600 border-t-primary-500 rounded-full animate-spin"></div>
        <span class="text-sm">加载中...</span>
      </div>

      <div v-else-if="photos.length === 0" class="flex flex-col items-center gap-4 text-slate-500 dark:text-slate-400">
        <CheckCircle class="w-16 h-16 text-emerald-500 opacity-80" />
        <span class="text-lg font-medium text-slate-800 dark:text-slate-100">太棒了，全部处理完毕！</span>
        <button 
          @click="fetchPhotos" 
          class="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        >
          再来一批
        </button>
      </div>

      <!-- 卡片堆叠 -->
      <div v-else class="relative w-full h-full flex items-center justify-center">
        <!-- 卡片堆叠 (键化卡片栈：滑走即移除顶层，下一张已在自己的 <img> 中预加载，弱网下不再闪旧图) -->
        <div
          v-for="(photo, index) in stack"
          :key="photo.id"
          class="absolute inset-0 m-auto w-[85vw] max-w-[360px] h-[68vh] max-h-[600px] bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 flex flex-col overflow-hidden transform-gpu will-change-transform touch-none"
          :class="index === 0
            ? 'cursor-grab active:cursor-grabbing'
            : 'pointer-events-none'"
          :style="cardStyleFor(index)"
          @mousedown="startDrag"
          @touchstart="startDrag"
          @dblclick="openLightbox"
          @wheel="handleWheel"
        >
          <!-- 模糊背景 (所有卡片均渲染，升顶时已就位，避免突然出现造成割裂感) -->
          <div class="absolute inset-0 z-0 pointer-events-none">
            <img :src="thumbUrl(photo.id)" class="w-full h-full object-cover blur-2xl scale-125 transition-opacity duration-300" :class="isThumbLoaded(photo.id) ? 'opacity-60 dark:opacity-40' : 'opacity-0'" draggable="false" decoding="async" />
            <div class="absolute inset-0 bg-white/60 dark:bg-slate-900/80"></div>
          </div>

          <!-- 查看详情按钮 (所有卡片均渲染，避免升层时闪现) -->
          <button
            @click.stop="openLightbox"
            class="absolute top-4 right-4 z-20 p-2 rounded-full bg-black/30 text-white hover:bg-black/50 transition-colors backdrop-blur-md focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
            title="查看详情"
          >
            <Maximize2 class="w-4 h-4" />
          </button>

          <!-- 叠加状态指示 (仅顶层, 左滑红叉/右滑绿星) -->
          <div
            v-show="index === 0"
            class="absolute inset-0 z-20 pointer-events-none flex items-center justify-center"
            :style="{ opacity: statusOpacity }"
          >
            <div
              class="absolute w-32 h-32 rounded-full bg-red-500/20 flex items-center justify-center border-4 border-red-500/50 transform rotate-[-15deg] transition-opacity duration-200"
              :style="{ opacity: dragOffset < 0 ? 1 : 0 }"
            >
              <Trash2 class="w-16 h-16 text-red-500 drop-shadow-lg" />
            </div>
            <div
              class="absolute w-32 h-32 rounded-full bg-emerald-500/20 flex items-center justify-center border-4 border-emerald-500/50 transform rotate-[15deg] transition-opacity duration-200"
              :style="{ opacity: dragOffset > 0 ? 1 : 0 }"
            >
              <Heart class="w-16 h-16 text-emerald-500 drop-shadow-lg" />
            </div>
          </div>

          <!-- 主媒体区 (图片 / 实况图 / 视频) -->
          <div class="relative z-10 flex-1 w-full p-2 md:p-3 flex items-center justify-center overflow-hidden pointer-events-none">
            <div class="relative w-full h-full flex items-center justify-center">
              <!-- 封面图 (统一使用 small 缩略图；加载完成后渐显，未加载时透明，避免旧图残留) -->
              <img
                :src="thumbUrl(photo.id)"
                class="w-full h-full transition-opacity duration-300 drop-shadow-lg object-contain"
                :class="isThumbLoaded(photo.id) ? 'opacity-100' : 'opacity-0'"
                draggable="false"
                decoding="async"
                @load="onThumbLoad(photo.id)"
              />
              <!-- 实况图动态视频叠加 (仅顶层；待封面加载完毕后播放一次，播完停在封面图，点击 LIVE 徽标重播) -->
              <video
                v-if="photo.file_type === 'live_photo' && index === 0 && livePlayRequested && currentThumbLoaded"
                :key="photo.id"
                class="absolute inset-0 w-full h-full object-contain pointer-events-none"
                autoplay
                muted
                playsinline
                webkit-playsinline
                x5-playsinline
                @ended="onLiveEnded"
              >
                <source :src="toServerUrl(`/api/medias/${photo.id}/video`)" type="video/mp4" />
              </video>
            </div>

            <!-- 实况图 LIVE 徽标 (点击切换播放/重播) -->
            <div
              v-if="photo.file_type === 'live_photo'"
              class="absolute top-3 left-3 z-20 flex items-center gap-1 bg-gray-900/60 backdrop-blur-md rounded-full px-2 py-1 text-white/90 transition-colors"
              :class="index === 0 ? 'cursor-pointer pointer-events-auto hover:bg-gray-800/80' : 'pointer-events-none'"
              :title="index === 0 ? (livePlayRequested ? '点击停止' : '点击播放实况') : ''"
              @click.stop="index === 0 && toggleLivePlayback()"
            >
              <span class="icon-[tabler--live-photo] w-3.5 h-3.5" :class="{ 'animate-pulse': index === 0 && livePlayRequested && currentThumbLoaded }"></span>
              <span class="text-[11px] font-medium tracking-wide">LIVE</span>
            </div>

            <!-- 视频时长徽标 -->
            <div
              v-if="photo.file_type === 'video' && formatDuration(photo)"
              class="absolute bottom-3 right-3 z-20 bg-black/60 backdrop-blur-md text-white text-xs font-medium px-2 py-0.5 rounded pointer-events-none tabular-nums"
            >
              {{ formatDuration(photo) }}
            </div>

            <!-- 视频播放按钮 (所有卡片均渲染以防闪现，但仅顶层可点击) -->
          <button
            v-if="photo.file_type === 'video'"
            @click.stop="openLightbox"
            class="absolute z-20 w-14 h-14 rounded-full bg-black/50 hover:bg-black/70 text-white flex items-center justify-center backdrop-blur-md transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
            :class="index === 0 ? 'pointer-events-auto' : 'pointer-events-none'"
            title="播放视频"
          >
            <Play class="w-7 h-7 ml-0.5" />
          </button>
          </div>

          <!-- 信息展示区 (所有卡片均渲染真实信息，升顶时无需替换，无割裂感) -->
          <div class="relative z-10 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border-t border-slate-100 dark:border-slate-700 p-4 shrink-0 text-left">
            <div class="flex items-center justify-between gap-2">
              <span class="font-bold text-lg text-slate-800 dark:text-slate-100">{{ formatDate(photo) }}</span>
              <div v-if="getLocation(photo)" class="text-xs font-medium flex items-center gap-1 opacity-70 text-slate-600 dark:text-slate-300">
                <MapPin class="w-3.5 h-3.5 shrink-0" />
                <span class="truncate max-w-[120px] md:max-w-[160px]">{{ getLocation(photo) }}</span>
              </div>
            </div>
            <div v-if="getNarrative(photo)" class="text-sm font-serif italic text-slate-600 dark:text-slate-300 opacity-90 leading-relaxed border-l-2 border-primary-500 pl-2 py-1 mt-2 line-clamp-2 md:line-clamp-3">
              {{ getNarrative(photo) }}
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部操作栏 -->
    <footer class="flex-none pt-4 px-6 flex items-center justify-center gap-8 z-20 bg-gradient-to-t from-slate-50 dark:from-slate-900 to-transparent pb-[calc(2rem+env(safe-area-inset-bottom))]">
      <button
        @click="swipeLeft"
        :disabled="photos.length === 0"
        class="group relative w-16 h-16 rounded-full bg-white dark:bg-slate-800 text-red-500 hover:bg-red-500 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 border border-slate-200 dark:border-slate-700 disabled:opacity-50 disabled:active:scale-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="移至回收站 (左方向键)"
      >
        <Trash2 class="w-7 h-7 transition-transform group-hover:scale-110" />
        <span
          v-if="deletedCount > 0"
          class="absolute -top-1.5 -right-1.5 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-[11px] font-bold flex items-center justify-center shadow ring-2 ring-slate-50 dark:ring-slate-900 tabular-nums"
        >
          {{ deletedCount }}
        </span>
      </button>

      <button
        @click="swipeRight"
        :disabled="photos.length === 0"
        class="group relative w-16 h-16 rounded-full bg-white dark:bg-slate-800 text-emerald-500 hover:bg-emerald-500 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 border border-slate-200 dark:border-slate-700 disabled:opacity-50 disabled:active:scale-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="保留照片 (右方向键)"
      >
        <Heart class="w-7 h-7 transition-transform group-hover:scale-110" />
        <span
          v-if="keptCount > 0"
          class="absolute -top-1.5 -right-1.5 min-w-[20px] h-5 px-1 rounded-full bg-emerald-500 text-white text-[11px] font-bold flex items-center justify-center shadow ring-2 ring-slate-50 dark:ring-slate-900 tabular-nums"
        >
          {{ keptCount }}
        </span>
      </button>
    </footer>

    <PhotoLightbox
      v-if="currentPhoto"
      :visible="isLightboxVisible"
      :image="mapPhotoToImage(currentPhoto)"
      :allow-delete="true"
      :photos="photos"
      :initial-index="0"
      @close="isLightboxVisible = false"
      @delete="handleLightboxDelete"
    />

    <!-- 首次使用引导 -->
    <Transition name="guide-fade">
      <div
        v-if="showGuide"
        class="absolute inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
        @click.self="dismissGuide"
      >
        <div class="relative w-full max-w-md bg-white dark:bg-slate-800 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
          <!-- 头部 -->
          <div class="bg-gradient-to-br from-primary-500 to-primary-600 px-6 py-5 text-white">
            <div class="flex items-center gap-2">
              <Sparkles class="w-5 h-5" />
              <h2 class="text-lg font-bold tracking-wide">照片筛选玩法</h2>
            </div>
            <p class="text-sm text-white/80 mt-1">左右滑动，快速整理你的相册</p>
          </div>

          <!-- 操作说明 -->
          <div class="px-6 py-5 space-y-4 text-sm">
            <div class="flex items-center gap-4">
              <div class="flex-none w-11 h-11 rounded-full bg-red-500/10 text-red-500 flex items-center justify-center">
                <Trash2 class="w-5 h-5" />
              </div>
              <div class="flex-1 text-slate-700 dark:text-slate-200">
                <p class="font-medium">向左滑动 · 丢弃</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">左滑卡片 / 按 ← / 点红色按钮，移至回收站</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <div class="flex-none w-11 h-11 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
                <Heart class="w-5 h-5" />
              </div>
              <div class="flex-1 text-slate-700 dark:text-slate-200">
                <p class="font-medium">向右滑动 · 保留</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">右滑卡片 / 按 → / 点绿色按钮，留在相册</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <div class="flex-none w-11 h-11 rounded-full bg-slate-500/10 text-slate-500 dark:text-slate-300 flex items-center justify-center">
                <Hand class="w-5 h-5" />
              </div>
              <div class="flex-1 text-slate-700 dark:text-slate-200">
                <p class="font-medium">拖动卡片</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">按住照片左右拖动，松手即触发</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <div class="flex-none w-11 h-11 rounded-full bg-primary-500/10 text-primary-500 flex items-center justify-center">
                <Maximize2 class="w-5 h-5" />
              </div>
              <div class="flex-1 text-slate-700 dark:text-slate-200">
                <p class="font-medium">查看大图</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">双击照片 / 按空格 / 点右上角放大</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <div class="flex-none w-11 h-11 rounded-full bg-slate-500/10 text-slate-500 dark:text-slate-300 flex items-center justify-center">
                <Undo class="w-5 h-5" />
              </div>
              <div class="flex-1 text-slate-700 dark:text-slate-200">
                <p class="font-medium">撤销与清理</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">Ctrl+Z 撤销；返回时自动清理已丢弃照片</p>
              </div>
            </div>
          </div>

          <!-- 底部按钮 -->
          <div class="px-6 pb-5">
            <button
              @click="dismissGuide"
              class="w-full py-3 bg-primary-600 hover:bg-primary-700 text-white rounded-full font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none dark:focus-visible:ring-offset-slate-800"
            >
              开始使用
            </button>
            <p class="text-center text-xs text-slate-400 dark:text-slate-500 mt-3">点击空白处或按钮均可关闭，仅显示一次</p>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { ArrowLeft, Trash2, Heart, Undo, Maximize2, CheckCircle, MapPin, Sparkles, Hand, Play } from 'lucide-vue-next'
import { photoApi } from '@/api/photo'
import { albumService } from '@/api/album'
import { ElMessage } from 'element-plus'
import type { Photo } from '@/types/album'
import { format } from 'date-fns'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import { mapPhotoToImage } from '@/stores/photoStore'
import { toServerUrl } from '@/config/server'

const router = useRouter()
const appBack = useAppBack('/toolbox')

// 状态
const loading = ref(false)
const photos = ref<Photo[]>([])
const processedCount = ref(0)
const totalCount = ref(0)

// 撤销历史与待删除队列
const MAX_UNDO = 30
const BATCH_SYNC_SIZE = 10
const OFFLINE_STORAGE_KEY = 'trailsnap:swipe-filter:offline-deletes'

interface ActionRecord {
  photo: Photo
  action: 'keep' | 'delete'
}
const actionHistory = ref<ActionRecord[]>([])
const pendingDeleteIds = ref<Set<string>>(new Set()) // 还在撤销栈内的删除
const syncQueue = ref<Set<string>>(new Set()) // 已超出撤销栈，等待后台提交的删除

// 统计计数 (代替之前的 computed，保证超出撤销栈后数字不掉)
const sessionDeletedCount = ref(0)
const sessionKeptCount = ref(0)

// 计算属性
const currentPhoto = computed(() => photos.value[0] || null)
const deletedCount = computed(() => sessionDeletedCount.value)
const keptCount = computed(() => sessionKeptCount.value)

// --- 本地离线缓存与静默提交 ---
const persistToStorage = () => {
  try {
    const allIds = [...syncQueue.value, ...pendingDeleteIds.value]
    if (allIds.length > 0) {
      localStorage.setItem(OFFLINE_STORAGE_KEY, JSON.stringify(allIds))
    } else {
      localStorage.removeItem(OFFLINE_STORAGE_KEY)
    }
  } catch (e) {}
}

const flushSyncQueue = async () => {
  if (syncQueue.value.size === 0) return
  const ids = Array.from(syncQueue.value)
  try {
    await albumService.batchUpdatePhotos({
      photo_ids: ids,
      action: 'delete'
    })
    // 成功后从队列移除
    ids.forEach(id => syncQueue.value.delete(id))
    persistToStorage()
  } catch (error) {
    // 失败了（如断网）就留在队列里，等待下次触发或退出时再试
    console.warn('Background sync failed, will retry later.', error)
  }
}

const recoverOfflineDeletes = async () => {
  try {
    const saved = localStorage.getItem(OFFLINE_STORAGE_KEY)
    if (saved) {
      const ids = JSON.parse(saved) as string[]
      if (ids.length > 0) {
        await albumService.batchUpdatePhotos({
          photo_ids: ids,
          action: 'delete'
        })
        localStorage.removeItem(OFFLINE_STORAGE_KEY)
        console.log(`Recovered and deleted ${ids.length} offline photos.`)
      }
    }
  } catch (e) {
    console.warn('Failed to recover offline deletes', e)
  }
}

// --- 键化卡片栈 ---
// 只渲染栈深 N 张卡片，每张 :key="photo.id"。滑走时 photos.shift() 移除顶层，
// Vue 按 key 复用其余卡片元素——下一张的 <img> 早已在自己元素里加载完成，
// 升为顶层后无需重绑 src、无需重新请求，弱网下也不会闪现旧图。
const STACK_DEPTH = 4 // 增加栈深至4，使最底层卡片以透明状态预先挂载，防止闪现
const stack = computed(() => photos.value.slice(0, STACK_DEPTH))

// 统一使用 medium 缩略图（保证清晰度）；弱网体验由键化卡片栈 + 静默预取 + 渐显兜底。
const thumbUrl = (id: string) => toServerUrl(`/api/medias/${id}/thumbnail?size=medium`)

// 缩略图加载状态：记录已加载完成的 photo id，用于渐显与"实况视频待封面就绪"判断。
// 由可见卡片 <img @load> 与下方静默预取共同写入。
const loadedThumbIds = ref<Set<string>>(new Set())
const onThumbLoad = (id: string) => {
  loadedThumbIds.value.add(id)
}
const isThumbLoaded = (id: string) => loadedThumbIds.value.has(id)
const currentThumbLoaded = computed(() =>
  currentPhoto.value ? loadedThumbIds.value.has(currentPhoto.value.id) : false
)

// --- 静默预取 ---
// 栈深之外的若干张缩略图用 new Image() 提前拉取并缓存，
// 确保它们进入栈时能命中浏览器缓存秒开（也为后续离线预缓存铺路）。
const PREFETCH_AHEAD = 4
const prefetchedIds = new Set<string>()
const prefetchAhead = () => {
  const list = photos.value
  for (let i = STACK_DEPTH; i < Math.min(STACK_DEPTH + PREFETCH_AHEAD, list.length); i++) {
    const id = list[i].id
    if (prefetchedIds.has(id) || loadedThumbIds.value.has(id)) continue
    prefetchedIds.add(id)
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => loadedThumbIds.value.add(id)
    img.src = thumbUrl(id)
  }
}
watch(() => photos.value.length, prefetchAhead)

// --- 弱网检测 ---
// 综合判定：Network Information API (2g/slow-2g/saveData) + 运行时若当前卡片封面 1.5s
// 仍未加载完成则判为弱网。弱网下关闭实况图自动播放，避免视频与缩略图争抢带宽。
const weakNetwork = ref(false)
const detectWeakNetwork = () => {
  try {
    const conn = (navigator as any).connection
    if (!conn) return
    const et = conn.effectiveType
    if (et === '2g' || et === 'slow-2g') weakNetwork.value = true
    if (conn.saveData) weakNetwork.value = true
  } catch {
    // 不可用时忽略，改由运行时慢加载兜底
  }
}
let currentLoadTimer: ReturnType<typeof setTimeout> | null = null
const armSlowLoadProbe = (id: string) => {
  if (currentLoadTimer) clearTimeout(currentLoadTimer)
  currentLoadTimer = setTimeout(() => {
    if (!loadedThumbIds.value.has(id)) weakNetwork.value = true
    currentLoadTimer = null
  }, 1500)
}

const formatDate = (photo: Photo) => {
  const dateStr = photo.photo_time || photo.upload_time
  if (!dateStr) return ''
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd HH:mm')
  } catch (e) {
    return ''
  }
}

const getLocation = (photo: Photo) => {
  const meta = photo.metadata_info
  if (!meta) return ''
  const parts = []
  if (meta.province) parts.push(meta.province)
  if (meta.city) parts.push(meta.city)
  if (parts.length === 0 && meta.address) return meta.address.substring(0, 10)
  return parts.join(' ')
}

const getNarrative = (photo: Photo) => {
  return photo.image_description?.narrative || ''
}

// 视频时长格式化 (秒 -> mm:ss)
const formatDuration = (photo: Photo) => {
  const dur = photo.duration
  if (!dur || dur <= 0) return ''
  const total = Math.floor(dur)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

// 实况图播放：仅顶层、且封面加载完毕后播放一次；播完停在封面图，点击 LIVE 徽标可重播。
const livePlayRequested = ref(false)
const toggleLivePlayback = () => {
  if (!currentPhoto.value || currentPhoto.value.file_type !== 'live_photo') return
  if (!currentThumbLoaded.value) return
  livePlayRequested.value = !livePlayRequested.value
}
// 视频自然播完：卸载视频回到封面图，等待用户点击重播。
const onLiveEnded = () => {
  livePlayRequested.value = false
}
watch(weakNetwork, (weak) => {
  if (weak && livePlayRequested.value) livePlayRequested.value = false
})

// 拖拽状态
const isDragging = ref(false)
const startX = ref(0)
const startY = ref(0)
const dragOffset = ref(0)
const dragOffsetY = ref(0)
const isAnimating = ref(false)

// Lightbox state
const isLightboxVisible = ref(false)

// 卡片切换：重置实况图播放意图，并对未就绪的当前封面启动弱网慢加载探测。
watch(currentPhoto, (photo) => {
  livePlayRequested.value = !weakNetwork.value && photo?.file_type === 'live_photo'
  if (photo && !loadedThumbIds.value.has(photo.id)) {
    armSlowLoadProbe(photo.id)
  } else if (currentLoadTimer) {
    clearTimeout(currentLoadTimer)
    currentLoadTimer = null
  }
})

// 首次使用引导
const GUIDE_STORAGE_KEY = 'trailsnap:swipe-filter:guide-seen'
const showGuide = ref(false)

const dismissGuide = () => {
  showGuide.value = false
  try {
    localStorage.setItem(GUIDE_STORAGE_KEY, '1')
  } catch (e) {
    // localStorage 不可用时静默忽略，下次仍会提示
  }
}

const openLightbox = () => {
  if (photos.value.length > 0) {
    isLightboxVisible.value = true
  }
}

const handleLightboxDelete = (deletedPhotoId: string) => {
  // If user deletes photo from lightbox, we treat it as a "swipe left" (delete)
  if (currentPhoto.value && deletedPhotoId === currentPhoto.value.id) {
    isLightboxVisible.value = false
    swipeLeft()
  }
}

// 拖拽常量
const SWIPE_THRESHOLD = 100 // 触发滑动的位移阈值上限 (桌面)
const FLICK_VELOCITY = 0.5 // 触发滑动的速度阈值 (px/ms，约 500px/s)
const MAX_ROTATION = 15 // 最大旋转角度

// 小屏单手操作时位移阈值更低，避免拇指滑不远而失效
const getSwipeThreshold = () => {
  const w = typeof window !== 'undefined' ? window.innerWidth : 1024
  return Math.min(SWIPE_THRESHOLD, Math.max(48, Math.round(w * 0.14)))
}

// 记录最近一次移动的位置与时间，用于松手时计算瞬时速度 (实现"轻甩即触发")
let lastMoveX = 0
let lastMoveTime = 0
let lastVelocity = 0 // px/ms，正值为向右

// 卡片过渡曲线：统一使用柔和的 ease-out（无 overshoot 回弹），整段动画一气呵成，避免弹簧感的生硬。
const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)'
const REST_DUR = 0.45
// 注意：transition 不含 box-shadow。box-shadow 是 paint 属性，逐帧变化会使卡片 GPU 层失效，
// 连带 filter:blur 的模糊背景一起重栅格化 → 闪烁。故阴影按"角色(层级)"静态取值，不在动画中插值。
const transitionFor = (dur: number) => `transform ${dur}s ${EASE}, opacity ${dur}s ${EASE}`
const CARD_TRANSITION = transitionFor(REST_DUR)

// 飞出动画时长：随松手速度动态调整（快速甩动更干脆，慢拖/按钮更从容）；
// 顶层飞出与下一张升起共用此时长，保证两者同步到位、交接严丝合缝。
const flyDuration = ref(REST_DUR)

// 顶层飞出旋转：与屏幕宽度无关的固定上限，避免宽屏上出现近 90° 的过度旋转。
const flyRotation = () => (dragOffset.value / window.innerWidth) * MAX_ROTATION

// 阴影海拔：随卡片缩放(越靠顶层越大)加深，飞出退远时同步变浅，强化空间层次。
// 结构固定（单层阴影、相同单位），便于浏览器在过渡时平滑插值。
const cardShadow = (scale: number) => {
  const t = Math.max(0, Math.min(1, (scale - 0.85) / 0.15)) // 0 (深藏) → 1 (顶层)
  const sy = (6 + t * 18).toFixed(1)    // 6 → 24
  const sb = (12 + t * 36).toFixed(1)   // 12 → 48
  const sa = (0.12 + t * 0.13).toFixed(3) // 0.12 → 0.25
  return `0 ${sy}px ${sb}px -8px rgba(0,0,0,${sa})`
}

// 卡片样式计算 (仅用于顶层 index===0)
// transform 统一为 translate scale rotate 顺序，与后层 cardStyleFor 一致，保证切换时矩阵插值平滑。
const cardStyle = computed(() => {
  if (isAnimating.value) {
    // 飞出退远：缩小 + 微淡（transform/opacity 均为合成器属性，不触发重栅格）。
    // 阴影保持顶层固定值，避免逐帧变化导致模糊背景重栅格闪烁。
    return {
      transform: `translate(${dragOffset.value}px, ${dragOffsetY.value}px) scale(0.94) rotate(${flyRotation()}deg)`,
      opacity: 0.85,
      zIndex: 20,
      boxShadow: cardShadow(1),
      transition: transitionFor(flyDuration.value)
    }
  }
  if (!isDragging.value) {
    return {
      transform: 'translate(0px, 0px) scale(1) rotate(0deg)',
      opacity: 1,
      zIndex: 20,
      boxShadow: cardShadow(1),
      transition: CARD_TRANSITION
    }
  }

  const rotation = (dragOffset.value / window.innerWidth) * MAX_ROTATION
  return {
    transform: `translate(${dragOffset.value}px, ${dragOffsetY.value}px) scale(1) rotate(${rotation}deg)`,
    opacity: 1,
    zIndex: 20,
    boxShadow: cardShadow(1),
    transition: 'none'
  }
})

// 后层卡片静态错位参数 (index -> 偏移/缩放/旋转/透明度)
const BEHIND_OFFSETS: Array<{ scale: number; rotate: number; tx: number; ty: number; opacity: number }> = [
  { scale: 1, rotate: 0, tx: 0, ty: 0, opacity: 1 }, // index 0 (占位，实际走 cardStyle)
  { scale: 0.94, rotate: 5, tx: 3, ty: 12, opacity: 0.85 },
  { scale: 0.87, rotate: -4, tx: -5, ty: 22, opacity: 0.5 },
  { scale: 0.80, rotate: 3, tx: 2, ty: 30, opacity: 0 }, // index 3 (全透明，作为新进入栈的预备层，防止闪现)
]

// 后层在顶层拖拽/飞出时向中心靠拢的进度上限（按 index）。
// index 1（即将接管的下一张）：满额 1.0——在顶层飞出的 0.32s 内"同步"升到中心，
//   顶层移除时它已就位，交接瞬间零位移，最丝滑（无落位动画）。
// index 2+（更深的卡片）：仅 0.15——飞出时几乎不动，避免先顶到中心、shift 后又反向回弹的生硬感；
//   它们的"上移"交给 shift 后的统一过渡顺滑完成。
const PROMOTION_CAPS = [1, 1, 0.15, 0]

// 按栈中 index 计算卡片样式：顶层用 cardStyle；后层用错位样式，
// 并随顶层拖拽/飞出进度向中心靠拢——顶层滑走时下一张顺势顶上，过渡自然。
const cardStyleFor = (index: number) => {
  if (index === 0) return cardStyle.value
  const base = BEHIND_OFFSETS[index] || BEHIND_OFFSETS[BEHIND_OFFSETS.length - 1]
  const winW = typeof window !== 'undefined' ? window.innerWidth : 1024
  const cap = PROMOTION_CAPS[index] ?? 0.15
  // 顶层移动幅度越大，后层越靠近中心 (0→cap)
  const progress = Math.min(Math.abs(dragOffset.value) / (winW * 0.5), cap)
  const scale = base.scale + (1 - base.scale) * progress
  const opacity = base.opacity + (1 - base.opacity) * progress
  const tx = base.tx * (1 - progress)
  const ty = base.ty * (1 - progress)
  const rotate = base.rotate * (1 - progress)
  return {
    transform: `translate(${tx}px, ${ty}px) scale(${scale}) rotate(${rotate}deg)`,
    opacity,
    // 阴影按层级静态取值(不随 live scale 变化)，避免拖拽/飞出时逐帧重栅格模糊背景而闪烁。
    boxShadow: cardShadow(base.scale),
    transition: isDragging.value ? 'none' : (isAnimating.value ? transitionFor(flyDuration.value) : CARD_TRANSITION),
    zIndex: 10 - index,
  }
}

// 状态透明度 (红叉/绿星)
const statusOpacity = computed(() => {
  if (!isDragging.value) return 0
  return Math.min(Math.abs(dragOffset.value) / getSwipeThreshold(), 1)
})

// 数据加载
const fetchPhotos = async () => {
  if (loading.value) return
  loading.value = true
  try {
    const res = await photoApi.getRandomPhotos(20)
    if (res && res.length > 0) {
      photos.value.push(...res)
      totalCount.value += res.length
    }
  } catch (error) {
    ElMessage.error('获取照片失败')
  } finally {
    loading.value = false
  }
}

// 交互操作
// velocity: 松手瞬时的水平速度 (px/ms，带方向)，用于让飞出时长随甩动速度变化，更有惯性。
const handleSwipe = (direction: 'left' | 'right', velocity = 0) => {
  if (photos.value.length === 0 || isAnimating.value) return

  const photo = photos.value[0]
  isAnimating.value = true

  // 根据松手速度决定飞出时长：越快越干脆 (0.45s → 0.30s)，按钮/慢拖则更从容。
  const v = Math.abs(velocity)
  const dur = Math.max(0.3, Math.min(0.45, 0.45 - v * 0.08))
  flyDuration.value = dur

  // 移动端轻触反馈，增强"甩出去"的实感。
  try { navigator.vibrate?.(8) } catch { /* 忽略不支持 */ }

  // 记录操作
  const action = direction === 'left' ? 'delete' : 'keep'
  actionHistory.value.push({ photo, action })
  
  if (action === 'delete') {
    sessionDeletedCount.value++
    pendingDeleteIds.value.add(photo.id)
  } else {
    sessionKeptCount.value++
  }

  // 防止撤销栈无限膨胀：超出 MAX_UNDO 后，锁定最老的记录并移出撤销栈
  if (actionHistory.value.length > MAX_UNDO) {
    const oldest = actionHistory.value.shift()!
    if (oldest.action === 'delete') {
      pendingDeleteIds.value.delete(oldest.photo.id)
      syncQueue.value.add(oldest.photo.id)
    }
  }

  persistToStorage()

  // 触发后台分批静默提交
  if (syncQueue.value.size >= BATCH_SYNC_SIZE) {
    flushSyncQueue()
  }

  // 保证 isAnimating=true 的 transition 先生效，下一帧再应用飞出 transform，避免偶发无动画闪切
  requestAnimationFrame(() => {
    const throwX = direction === 'left' ? -window.innerWidth : window.innerWidth
    dragOffset.value = throwX
    dragOffsetY.value = direction === 'left' ? 100 : -100 // 飞出时带点垂直位移更自然
  })

  // 动画结束后移除当前照片 (与飞出时长同步，避免提前/滞后裁切)
  setTimeout(() => {
    photos.value.shift()
    processedCount.value++

    // 重置状态
    isAnimating.value = false
    dragOffset.value = 0
    dragOffsetY.value = 0

    // 补充数据
    if (photos.value.length <= 5) {
      fetchPhotos()
    }
  }, dur * 1000)
}

const swipeLeft = () => handleSwipe('left')
const swipeRight = () => handleSwipe('right')

const undo = () => {
  if (actionHistory.value.length === 0 || isAnimating.value) return
  
  const lastAction = actionHistory.value.pop()!
  
  if (lastAction.action === 'delete') {
    sessionDeletedCount.value--
    pendingDeleteIds.value.delete(lastAction.photo.id)
  } else {
    sessionKeptCount.value--
  }
  
  persistToStorage()
  
  // 将照片插回队首
  photos.value.unshift(lastAction.photo)
  processedCount.value--
}

// 拖拽事件处理
const getClientPos = (e: MouseEvent | TouchEvent) => {
  if ('touches' in e) {
    return { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }
  return { x: e.clientX, y: e.clientY }
}

const startDrag = (e: MouseEvent | TouchEvent) => {
  if (isAnimating.value) return
  const pos = getClientPos(e)
  startX.value = pos.x
  startY.value = pos.y
  lastMoveX = pos.x
  lastMoveTime = performance.now()
  lastVelocity = 0
  isDragging.value = true

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('mouseup', endDrag)
  document.addEventListener('touchend', endDrag)
}

const onDrag = (e: MouseEvent | TouchEvent) => {
  if (!isDragging.value) return
  // 阻止默认滚动行为
  if (e.cancelable) e.preventDefault()

  const pos = getClientPos(e)
  const now = performance.now()
  const dt = now - lastMoveTime
  if (dt > 0) {
    lastVelocity = (pos.x - lastMoveX) / dt
  }
  lastMoveX = pos.x
  lastMoveTime = now
  dragOffset.value = pos.x - startX.value
  dragOffsetY.value = pos.y - startY.value
}

const endDrag = () => {
  if (!isDragging.value) return
  isDragging.value = false

  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('mouseup', endDrag)
  document.removeEventListener('touchend', endDrag)

  const offset = dragOffset.value
  const threshold = getSwipeThreshold()

  // 松手前若手指已停顿较久，则不计速度 (避免把"拖到位后停一下再松手"误判为甩动)
  const elapsedSinceMove = performance.now() - lastMoveTime
  const velocity = elapsedSinceMove > 120 ? 0 : lastVelocity

  // 超过位移阈值，或方向一致的快速甩动，均触发滑动
  const shouldSwipeRight = offset > threshold || (offset > 0 && velocity > FLICK_VELOCITY)
  const shouldSwipeLeft = offset < -threshold || (offset < 0 && velocity < -FLICK_VELOCITY)

  if (shouldSwipeRight) {
    handleSwipe('right', velocity)
  } else if (shouldSwipeLeft) {
    handleSwipe('left', velocity)
  } else {
    // 未超过阈值，回弹 (依靠 computed 里的 CSS transition)
    dragOffset.value = 0
    dragOffsetY.value = 0
  }
}

// 快捷键处理
const handleKeydown = (e: KeyboardEvent) => {
  // 引导展示期间禁用所有快捷键
  if (showGuide.value) return
  // 忽略输入框内的快捷键
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
  
  switch (e.key) {
    case 'ArrowLeft':
      swipeLeft()
      break
    case 'ArrowRight':
      swipeRight()
      break
    case ' ':
      e.preventDefault()
      openLightbox()
      break
    case 'z':
    case 'Z':
      if (e.ctrlKey || e.metaKey) {
        undo()
      }
      break
  }
}

// 滚轮缩放处理
const handleWheel = (e: WheelEvent) => {
  // 防止页面滚动
  e.preventDefault()
  if (e.deltaY < 0 && !isLightboxVisible.value) {
    openLightbox() // 向上滚动，打开 Lightbox
  }
}

// 退出前提交批量删除
const submitDeletions = async () => {
  const ids = Array.from(new Set([...syncQueue.value, ...pendingDeleteIds.value]))
  if (ids.length > 0) {
    try {
      syncQueue.value.clear()
      pendingDeleteIds.value.clear()
      await albumService.batchUpdatePhotos({
        photo_ids: ids,
        action: 'delete'
      })
      persistToStorage() // 提交成功后清除本地缓存
      ElMessage.success(`已将 ${ids.length} 张照片移至回收站`)
    } catch (error) {
      console.error(error)
      // 失败后将 id 重新加回离线队列并缓存，下次进页面时自动重试
      ids.forEach(id => syncQueue.value.add(id))
      persistToStorage()
      ElMessage.error('网络异常，删除操作已保存在本地，下次将自动重试')
    }
  }
}

const handleBack = () => {
  appBack()
}

onBeforeRouteLeave(async (to, from, next) => {
  await submitDeletions()
  next()
})

const handleBeforeUnload = () => {
  if (pendingDeleteIds.value.size > 0) {
    // 浏览器刷新/关闭标签页时，尽量尝试提交数据防丢失
    submitDeletions()
  }
}

// 生命周期
onMounted(() => {
  detectWeakNetwork()
  recoverOfflineDeletes() // 页面加载时恢复并提交离线期间的删除操作
  fetchPhotos()
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('beforeunload', handleBeforeUnload)
  // 首次打开时展示引导
  try {
    if (!localStorage.getItem(GUIDE_STORAGE_KEY)) {
      showGuide.value = true
    }
  } catch (e) {
    // localStorage 不可用时忽略
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (currentLoadTimer) {
    clearTimeout(currentLoadTimer)
    currentLoadTimer = null
  }
})
</script>

<style scoped>
.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.25s ease;
}
.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}
</style>
