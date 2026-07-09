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
        <!-- 底层卡片 (错位堆叠效果) -->
        <div 
          v-if="nextPhoto"
          class="absolute inset-0 m-auto w-[85vw] max-w-[360px] h-[68vh] max-h-[600px] bg-white dark:bg-slate-800 rounded-2xl shadow-md border border-slate-200 dark:border-slate-700 flex flex-col overflow-hidden transform-gpu rotate-[4deg] translate-x-3 translate-y-2 scale-[0.95] opacity-80 transition-all duration-300 pointer-events-none"
        >
          <!-- 模糊背景 -->
          <div class="absolute inset-0 z-0 pointer-events-none">
            <img :src="`/api/medias/${nextPhoto.id}/thumbnail?size=medium`" class="w-full h-full object-cover blur-2xl scale-125 opacity-50 dark:opacity-30" />
            <div class="absolute inset-0 bg-white/40 dark:bg-slate-900/60 backdrop-blur-[2px]"></div>
          </div>
          <!-- 占位主图 -->
          <div class="relative z-10 flex-1 w-full p-3 flex items-center justify-center overflow-hidden pointer-events-none">
            <img :src="`/api/medias/${nextPhoto.id}/thumbnail?size=medium`" class="w-full h-full object-contain drop-shadow-md" />
          </div>
          <!-- 占位信息区 -->
          <div class="relative z-10 bg-white/90 dark:bg-slate-800/90 backdrop-blur-md border-t border-slate-100 dark:border-slate-700 p-4 shrink-0 opacity-50">
             <div class="h-6 w-1/2 bg-slate-200 dark:bg-slate-700 rounded mb-2"></div>
             <div class="h-4 w-1/3 bg-slate-200 dark:bg-slate-700 rounded"></div>
          </div>
        </div>

        <!-- 当前卡片 -->
        <div 
          v-if="currentPhoto"
          ref="cardRef"
          class="absolute inset-0 m-auto w-[85vw] max-w-[360px] h-[68vh] max-h-[600px] bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 flex flex-col overflow-hidden cursor-grab active:cursor-grabbing transform-gpu will-change-transform"
          :style="cardStyle"
          @mousedown="startDrag"
          @touchstart="startDrag"
          @dblclick="openLightbox"
          @wheel="handleWheel"
        >
          <!-- 模糊背景 -->
          <div class="absolute inset-0 z-0 pointer-events-none">
            <img :src="`/api/medias/${currentPhoto.id}/thumbnail?size=medium`" class="w-full h-full object-cover blur-2xl scale-125 opacity-60 dark:opacity-40 transition-all duration-300" />
            <div class="absolute inset-0 bg-white/40 dark:bg-slate-900/60 backdrop-blur-[2px]"></div>
          </div>

          <!-- 缩放控制 (原为右上角按钮，现改为查看详情) -->
          <button 
            @click.stop="openLightbox"
            class="absolute top-4 right-4 z-20 p-2 rounded-full bg-black/30 text-white hover:bg-black/50 transition-colors backdrop-blur-md"
            title="查看详情"
          >
            <Maximize2 class="w-4 h-4" />
          </button>

          <!-- 叠加状态指示 (左滑红叉/右滑绿星) -->
          <div 
            class="absolute inset-0 z-20 pointer-events-none flex items-center justify-center transition-opacity"
            :style="{ opacity: statusOpacity }"
          >
            <div 
              v-if="dragOffset < 0" 
              class="w-32 h-32 rounded-full bg-red-500/20 flex items-center justify-center border-4 border-red-500/50 backdrop-blur-md transform rotate-[-15deg]"
            >
              <Trash2 class="w-16 h-16 text-red-500 drop-shadow-lg" />
            </div>
            <div 
              v-else-if="dragOffset > 0" 
              class="w-32 h-32 rounded-full bg-emerald-500/20 flex items-center justify-center border-4 border-emerald-500/50 backdrop-blur-md transform rotate-[15deg]"
            >
              <Heart class="w-16 h-16 text-emerald-500 drop-shadow-lg" />
            </div>
          </div>

          <!-- 主图片区 -->
          <div class="relative z-10 flex-1 w-full p-2 md:p-3 flex items-center justify-center overflow-hidden pointer-events-none">
            <img 
              :src="`/api/medias/${currentPhoto.id}/thumbnail?size=large`" 
              class="w-full h-full transition-all duration-300 drop-shadow-lg object-contain"
              draggable="false"
            />
          </div>

          <!-- 信息展示区 -->
          <div class="relative z-10 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border-t border-slate-100 dark:border-slate-700 p-4 shrink-0 transition-opacity duration-300 text-left">
             <div class="flex items-center justify-between gap-2">
                 <span class="font-bold text-lg text-slate-800 dark:text-slate-100">{{ formatDate(currentPhoto) }}</span>
                 <div v-if="getLocation(currentPhoto)" class="text-xs font-medium flex items-center gap-1 opacity-70 text-slate-600 dark:text-slate-300">
                     <MapPin class="w-3.5 h-3.5 shrink-0" />
                     <span class="truncate max-w-[120px] md:max-w-[160px]">{{ getLocation(currentPhoto) }}</span>
                 </div>
             </div>
             <div v-if="getNarrative(currentPhoto)" class="text-sm font-serif italic text-slate-600 dark:text-slate-300 opacity-90 leading-relaxed border-l-2 border-primary-500 pl-2 py-1 mt-2 line-clamp-2 md:line-clamp-3">
                 {{ getNarrative(currentPhoto) }}
             </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部操作栏 -->
    <footer class="flex-none pb-8 pt-4 px-6 flex items-center justify-center gap-8 z-20 bg-gradient-to-t from-slate-50 dark:from-slate-900 to-transparent">
      <button 
        @click="swipeLeft"
        :disabled="photos.length === 0"
        class="group w-16 h-16 rounded-full bg-white dark:bg-slate-800 text-red-500 hover:bg-red-500 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 border border-slate-200 dark:border-slate-700 disabled:opacity-50 disabled:active:scale-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="移至回收站 (左方向键)"
      >
        <Trash2 class="w-7 h-7 transition-transform group-hover:scale-110" />
      </button>
      
      <button 
        @click="swipeRight"
        :disabled="photos.length === 0"
        class="group w-16 h-16 rounded-full bg-white dark:bg-slate-800 text-emerald-500 hover:bg-emerald-500 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 border border-slate-200 dark:border-slate-700 disabled:opacity-50 disabled:active:scale-100 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        title="保留照片 (右方向键)"
      >
        <Heart class="w-7 h-7 transition-transform group-hover:scale-110" />
      </button>
    </footer>

    <PhotoLightbox 
      v-if="currentPhoto"
      :visible="isLightboxVisible"
      :image="mapPhotoToImage(currentPhoto)"
      :photos="photos"
      :initial-index="0"
      @close="isLightboxVisible = false"
      @delete="handleLightboxDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Trash2, Heart, Undo, Maximize2, CheckCircle, MapPin } from 'lucide-vue-next'
import { photoApi } from '@/api/photo'
import { albumService } from '@/api/album'
import { ElMessage } from 'element-plus'
import type { Photo } from '@/types/album'
import { format } from 'date-fns'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import { mapPhotoToImage } from '@/stores/photoStore'

const router = useRouter()

// 状态
const loading = ref(false)
const photos = ref<Photo[]>([])
const processedCount = ref(0)
const totalCount = ref(0)

// 撤销历史与待删除队列
interface ActionRecord {
  photo: Photo
  action: 'keep' | 'delete'
}
const actionHistory = ref<ActionRecord[]>([])
const pendingDeleteIds = ref<Set<string>>(new Set())

// 计算属性
const currentPhoto = computed(() => photos.value[0] || null)
const nextPhoto = computed(() => photos.value[1] || null)

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

// 拖拽状态
const cardRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const startX = ref(0)
const startY = ref(0)
const dragOffset = ref(0)
const dragOffsetY = ref(0)
const isAnimating = ref(false)

// Lightbox state
const isLightboxVisible = ref(false)

const openLightbox = () => {
  if (photos.value.length > 0) {
    isLightboxVisible.value = true
  }
}

const handleLightboxDelete = (deletedPhoto: Photo) => {
  // If user deletes photo from lightbox, we treat it as a "swipe left" (delete)
  if (currentPhoto.value && deletedPhoto.id === currentPhoto.value.id) {
    isLightboxVisible.value = false
    swipeLeft()
  }
}

// 拖拽常量
const SWIPE_THRESHOLD = 100 // 触发滑动的位移阈值
const MAX_ROTATION = 15 // 最大旋转角度

// 卡片样式计算
const cardStyle = computed(() => {
  if (isAnimating.value) {
    return {
      transform: `translate(${dragOffset.value}px, ${dragOffsetY.value}px) rotate(${dragOffset.value * 0.05}deg)`,
      transition: 'transform 0.3s ease-out'
    }
  }
  if (!isDragging.value) {
    return {
      transform: 'translate(0px, 0px) rotate(0deg)',
      transition: 'transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)' // 回弹动画
    }
  }
  
  const rotation = (dragOffset.value / window.innerWidth) * MAX_ROTATION * 2
  return {
    transform: `translate(${dragOffset.value}px, ${dragOffsetY.value}px) rotate(${rotation}deg)`,
    transition: 'none'
  }
})

// 状态透明度 (红叉/绿星)
const statusOpacity = computed(() => {
  if (!isDragging.value) return 0
  return Math.min(Math.abs(dragOffset.value) / SWIPE_THRESHOLD, 1)
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
const handleSwipe = (direction: 'left' | 'right') => {
  if (photos.value.length === 0 || isAnimating.value) return
  
  const photo = photos.value[0]
  isAnimating.value = true
  
  // 设置飞出动画目标位置
  const throwX = direction === 'left' ? -window.innerWidth : window.innerWidth
  dragOffset.value = throwX
  dragOffsetY.value = direction === 'left' ? 100 : -100 // 飞出时带点垂直位移更自然
  
  // 记录操作
  const action = direction === 'left' ? 'delete' : 'keep'
  actionHistory.value.push({ photo, action })
  
  if (action === 'delete') {
    pendingDeleteIds.value.add(photo.id)
  }
  
  // 动画结束后移除当前照片
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
  }, 300)
}

const swipeLeft = () => handleSwipe('left')
const swipeRight = () => handleSwipe('right')

const undo = () => {
  if (actionHistory.value.length === 0 || isAnimating.value) return
  
  const lastAction = actionHistory.value.pop()!
  
  if (lastAction.action === 'delete') {
    pendingDeleteIds.value.delete(lastAction.photo.id)
  }
  
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
  
  // 判断是否超过阈值触发滑动
  if (dragOffset.value > SWIPE_THRESHOLD) {
    swipeRight()
  } else if (dragOffset.value < -SWIPE_THRESHOLD) {
    swipeLeft()
  } else {
    // 未超过阈值，回弹 (依靠 computed 里的 CSS transition)
    dragOffset.value = 0
    dragOffsetY.value = 0
  }
}

// 快捷键处理
const handleKeydown = (e: KeyboardEvent) => {
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
  const ids = Array.from(pendingDeleteIds.value)
  if (ids.length > 0) {
    try {
      pendingDeleteIds.value.clear() // 先清空，防止多次触发
      await albumService.batchUpdatePhotos({
        photo_ids: ids,
        action: 'delete'
      })
      ElMessage.success(`已将 ${ids.length} 张照片移至回收站`)
    } catch (error) {
      console.error(error)
      // 失败后可以加回来，但因为可能页面已经关闭，所以可能意义不大
      ElMessage.error('批量删除照片失败')
    }
  }
}

const handleBack = async () => {
  await submitDeletions()
  router.back()
}

// 生命周期
onMounted(() => {
  fetchPhotos()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  // 如果用户直接关闭页面或切换路由而没有点击返回按钮，最好也能提交删除
  // 不过在 onUnmounted 中做异步请求可能不可靠，通常我们在 beforeRouteLeave 中处理
  // 这里简化处理，依赖 onUnmounted
  submitDeletions()
})
</script>
