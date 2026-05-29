<template>
  <Transition name="fade">
    <div v-if="visible" class="fixed inset-0 z-[100] flex bg-black/95 backdrop-blur-sm" @click="close" @keydown.esc="close" tabindex="0">

      <!-- Top Toolbar (Mobile Adapted) -->
      <div class="fixed top-0 left-0 right-0 z-[102] p-2 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent pointer-events-none">
         <button
            @click.stop="close"
            class="pointer-events-auto w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0"
        >
            <X class="w-6 h-6" />
        </button>

        <div class="flex items-center gap-1 pointer-events-auto p-0">
            <!-- Zoom Controls -->
            <button @click.stop="zoomOut" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0">
                <ZoomOut class="w-6 h-6" />
            </button>
            <button @click.stop="zoomIn" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0">
                <ZoomIn class="w-6 h-6" />
            </button>

            <!-- Actions -->
            <button @click.stop="downloadImage" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" title="下载图片">
                <Download class="w-6 h-6" />
            </button>
             <button @click.stop="handleDelete" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors text-red-400 hover:text-red-300 bg-transparent p-0" title="删除图片">
                <Trash2 class="w-6 h-6" />
            </button>
            <button @click.stop="toggleOriginal" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" :class="{ 'text-primary-400': showOriginal }" title="查看原图">
                <Focus class="w-6 h-6" />
            </button>
            <button @click.stop="toggleSidebar" class="w-8 h-8 md:w-12 md:h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" :class="{ 'bg-white/20 text-white': showSidebar }" title="查看元数据">
                <Info class="w-6 h-6" />
            </button>

            <div @click.stop @mousedown.stop class="flex items-center">
                <el-dropdown trigger="click" @command="handleCommand">
                    <button class="w-12 h-12 flex items-center justify-center rounded-full text-white/90 hover:bg-white/10 transition-colors bg-transparent p-0" :class="{ 'bg-white/20 text-white': showOCR }">
                        <MoreHorizontal class="w-6 h-6" />
                    </button>
                    <template #dropdown>
                        <el-dropdown-menu class="w-36">
                            <el-dropdown-item command="ocr">
                                <div class="flex items-center gap-2">
                                    <ScanText class="w-4 h-4" />
                                    <span>{{ showOCR ? '关闭识别' : '文字识别' }}</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item command="addToAlbum">
                                <div class="flex items-center gap-2">
                                    <ImagePlus class="w-4 h-4" />
                                    <span>添加到相册</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item command="addToPerson">
                                <div class="flex items-center gap-2">
                                    <UserPlus class="w-4 h-4" />
                                    <span>添加到人物</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item command="moveToFolder">
                                <div class="flex items-center gap-2">
                                    <FolderOutput class="w-4 h-4" />
                                    <span>移动到目录</span>
                                </div>
                            </el-dropdown-item>
                            <el-dropdown-item command="viewDescription">
                                <div class="flex items-center gap-2">
                                    <FileText class="w-4 h-4" />
                                    <span>查看AI分析结果</span>
                                </div>
                            </el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                </el-dropdown>
            </div>
        </div>
      </div>

      <!-- Main Image Area -->
      <div class="flex-1 relative flex items-center justify-center h-full overflow-hidden group">

        <!-- Navigation -->
        <button 
            v-if="hasPrev"
            @click.stop="prev"
            class="absolute left-4 z-[101] w-12 h-12 flex items-center justify-center rounded-full hover:bg-black/40 text-white/90 transition-all p-0 bg-transparent"
        >
            <ChevronLeft class="w-8 h-8" />
        </button>
        <button 
            v-if="hasNext"
            @click.stop="next"
            class="absolute right-4 z-[101] w-12 h-12 flex items-center justify-center rounded-full hover:bg-black/40 text-white/90 transition-all p-0 bg-transparent"
        >
            <ChevronRight class="w-8 h-8" />
        </button>


        <div class="relative w-full h-full flex items-center justify-center overflow-hidden" @wheel.prevent="handleWheel">
            <div
              v-if="image && (!image.file_type || image.file_type === 'image' || image.file_type === 'live_photo')"
              class="relative w-full h-full transition-transform duration-200 ease-out origin-center select-none flex items-center justify-center"
              :style="{ transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)` }"
              @click.stop
              @mousedown="startDrag"
              @touchstart="startTouch"
            >
                <!-- Image Wrapper for Correct Overlay Positioning -->
                <div class="relative flex justify-center items-center h-full">
                    <img
                        ref="imageRef"
                        :src="displayImageSrc"
                        class="block w-full h-full object-contain pointer-events-none"
                        draggable="false"
                    />
                    
                    <!-- Face Highlight Overlay -->
                    <div 
                        v-if="highlightedFace && faceBoxStyle"
                        class="absolute border-2 border-yellow-400 z-20 shadow-[0_0_10px_rgba(255,215,0,0.5)] pointer-events-none"
                        :style="faceBoxStyle"
                    >
                         <div class="absolute -top-8 left-0 bg-black/70 backdrop-blur-sm text-white text-xs px-2 py-1 rounded whitespace-nowrap flex items-center gap-1">
                            <span class="font-bold">{{ highlightedFaceName }}</span>
                            <span v-if="highlightedFaceConfidence" class="text-yellow-400">
                                {{ highlightedFaceConfidence }}% {{ highlightedFaceRecognitionConfidence }}%
                            </span>
                        </div>
                    </div>

                    <!-- OCR Overlay -->
                    <div v-if="showOCR && ocrRecords.length > 0" class="absolute inset-0 z-10">
                        <svg viewBox="0 0 1 1" class="w-full h-full pointer-events-none" preserveAspectRatio="none">
                            <polygon
                                v-for="rec in ocrRecords"
                                :key="rec.id"
                                :points="getPolygonPoints(rec.polygon)"
                                class="fill-transparent stroke-primary-500 stroke-[0.002] cursor-pointer pointer-events-auto hover:fill-primary-500/20 hover:stroke-[0.004] transition-all"
                                :class="{ 'fill-primary-500/30 stroke-[0.004]': highlightedOCR?.id === rec.id }"
                                @click.stop="onPolygonClick(rec)"
                            />
                        </svg>
                    </div>

                    <!-- Live Photo Video Overlay -->
                    <video
                        v-if="isPlayingLive"
                        ref="liveVideoRef"
                        :key="image.id"
                        class="absolute inset-0 w-full h-full object-contain z-10 pointer-events-none"
                        :style="videoStyle"
                        autoplay
                        playsinline
                        x5-playsinline
                        webkit-playsinline
                        :loop="false"
                        @ended="onLiveEnded"
                        @loadedmetadata="onVideoLoaded"
                    >
                        <source :src="image.live_photo_video_url" type="video/mp4" />
                    </video>
                </div>
            </div>
            <!-- Live Photo Badge (Outside transform to keep position fixed relative to viewport or container?) 
                 Actually, usually badges are fixed on screen, not zooming with image. 
                 But here we are inside the zoomable container? No, the zoomable container is the div above.
                 Wait, if I put the badge inside the zoomable div, it zooms.
                 If I put it outside, it stays.
                 Let's put it outside the zoomable div but inside the relative container.
            -->
            <div v-if="image && image.file_type === 'live_photo'" 
                 class="absolute top-16 left-4 md:top-24 md:left-8 z-[101] cursor-pointer"
                 @click.stop="toggleLivePlayback">
                <div class="flex items-center gap-1 bg-gray-900/60 backdrop-blur-md rounded-full px-2 py-1 text-white/90 hover:bg-gray-800/80 transition-colors">
                    <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90" :class="{ 'animate-spin': isPlayingLive }"></span>
                    <span class="text-xs font-medium">LIVE</span>
                </div>
            </div>

            <div
              v-else-if="image && image.file_type === 'video'"
              class="relative w-full h-full flex items-center justify-center bg-black"
              @click.stop
            >
              <div ref="videoPlayer" class="w-full h-full"></div>
            </div>
        </div>
      </div>

      <!-- Sidebar (Metadata) -->
      <PhotoMetadataSidebar
        :visible="showSidebar"
        :image="image"
        :metadata="metadata"
        :loading="loading"
        @close="showSidebar = false"
        @update="handleSidebarUpdate"
        @delete="handleSidebarDelete"
        @highlight-face="handleHighlightFace"
      />

      <!-- OCR Panel (Separate) -->
      <PhotoOCRPanel
        :visible="showOCR"
        :loading="ocrLoading"
        :records="ocrRecords"
        :highlighted-record="highlightedOCR"
        @close="showOCR = false"
        @click-record="onOCRRecordClick"
      />

      <PersonSelector 
        v-model:visible="showPersonSelector"
        :submitting="isAddingPerson"
        @select="handlePersonSelected"
      />

      <el-dialog
        v-model="showDescription"
        title="AI智能分析"
        align-center
        class="rounded-xl w-[90%] md:w-[500px]"
        append-to-body
      >
        <div v-loading="descriptionLoading">
            <div v-if="imageDescription">
                <p v-if="imageDescription.narrative" class="mb-4 text-lg font-medium">{{ imageDescription.narrative }}</p>
                <p v-if="imageDescription.description" class="mb-2 text-gray-600 dark:text-gray-300">{{ imageDescription.description }}</p>
                
                <div class="flex gap-2 mt-4">
                    <el-tag v-if="imageDescription.memory_score !== null">回忆值: {{ imageDescription.memory_score }}</el-tag>
                    <el-tag v-if="imageDescription.quality_score !== null" type="success">质量分: {{ imageDescription.quality_score }}</el-tag>
                </div>
                 <div class="flex flex-wrap gap-2 mt-2" v-if="imageDescription.tags && imageDescription.tags.length">
                    <el-tag v-for="tag in imageDescription.tags" :key="tag" type="info" size="small">{{ tag }}</el-tag>
                </div>
                <p v-if="imageDescription.reason" class="mt-2 text-sm text-gray-500">评分理由: {{ imageDescription.reason }}</p>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
                暂无描述信息
            </div>
        </div>
      </el-dialog>

    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted, nextTick } from 'vue'
import {
    X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, FolderPlus, Info,
    ImagePlus,
    ScanText,
    MoreHorizontal,
    Image as ImageIcon,
    Trash2,
    Aperture,
    Maximize2,
    Focus,
    UserPlus,
    FileText,
    FolderOutput,
} from 'lucide-vue-next'
import Player from 'xgplayer'
import 'xgplayer/dist/index.min.css'
import { albumService } from '@/api/album'
import { ocrApi, type OCRRecord } from '@/api/ocr'
import { faceApi } from '@/api/face'
import type { PhotoMetadata, AlbumImage, CoverPhotoInfo } from '@/types/album'
import { ElMessageBox, ElMessage } from 'element-plus'
import PhotoMetadataSidebar from './PhotoMetadataSidebar.vue'
import PhotoOCRPanel from './PhotoOCRPanel.vue'
import PersonSelector from './PersonSelector.vue'


interface Props {
    visible: boolean
    image: AlbumImage | null
    hasPrev?: boolean
    hasNext?: boolean
    deleteTitle?: string
    deleteMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
    deleteTitle: '删除确认',
    deleteMessage: '确定要删除这张照片吗？此操作不可恢复。'
})

const showOriginal = ref(false)
const isPlayingLive = ref(false)
const liveVideoRef = ref<HTMLVideoElement | null>(null)
const videoStyle = ref<Record<string, string>>({})

const displayImageSrc = computed(() => {
    if (!props.image) return ''
    if (showOriginal.value) return props.image.url
    return props.image.preview || props.image.url
})

const onVideoLoaded = (e: Event) => {
    const video = e.target as HTMLVideoElement
    // Explicitly try to play (handling potential autoplay rejections)
    video.play().catch(err => {
        console.warn("Autoplay failed, trying muted play", err)
        video.muted = true
        video.play().catch(e => console.error("Muted autoplay also failed", e))
    })
}

const toggleLivePlayback = () => {
    if (isPlayingLive.value) {
        // Stop
        isPlayingLive.value = false
    } else {
        // Play
        isPlayingLive.value = true
    }
}

const onLiveEnded = () => {
    isPlayingLive.value = false
}

const toggleOriginal = () => {
    showOriginal.value = !showOriginal.value
}

const emit = defineEmits(['close', 'delete', 'update', 'prev', 'next', 'add-to-album', 'transfer'])

// State
const showSidebar = ref(false)
const loading = ref(false)
const metadata = ref<PhotoMetadata | null>(null)

// OCR State
const showOCR = ref(false)
const ocrLoading = ref(false)
const ocrRecords = ref<OCRRecord[]>([])
const highlightedOCR = ref<OCRRecord | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)

// Zoom & Pan State
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)

const startX = ref(0)
const startY = ref(0)
const initialDistance = ref(0)

// Video Player State
const videoPlayer = ref<HTMLElement | null>(null)
const player = ref<Player | null>(null)

const initPlayer = () => {
    if (videoPlayer.value && props.image) {
        if (player.value) {
            player.value.destroy()
            player.value = null
        }
        
        player.value = new Player({
            el: videoPlayer.value,
            url: props.image.url,
            poster: props.image.thumbnail,
            playsinline: true,
            autoplay: true,
            download: true,
            height: '100%',
            width: '100%',
            fitVideoSize: 'fixHeight',
            videoInit: true, // 初始化显示首帧
            lang: 'zh-cn',
            playbackRate: [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 5], // 倍速
            fluid: false, // 禁止流式布局，让width/height生效
            // 针对移动端的特殊配置
            commonStyle: {
                progressColor: '#1989fa',
                playedColor: '#1989fa',
            },
            // x5 内核适配
            x5: {
                type: 'h5',
                videoType: 'h5', 
                // orientation: 'landscape' 
            },
            fullscreen: {
                index: 1, // 全屏按钮位置
                rotateFullscreen: false // 旋转全屏
            },
            cssFullscreen: false, // 使用原生全屏
            controls: {
                mode: 'flex'
            },
            screenShot: {
                saveImg: true,
                quality: 0.92,
                type: 'image/png',
                format: '.png'
            },
            keyShortcut: true,
            keyShortcutStep: { //设置调整步长
                currentTime: 15, //播放进度调整步长，默认10秒
                volume: 0.2 //音量调整步长，默认0.1
            }
        })
    }
}

const disposePlayer = () => {
    if (player.value) {
        player.value.destroy()
        player.value = null
    }
}

onUnmounted(() => {
    disposePlayer()
})

const isDragging = ref(false)
watch(() => props.image, async (newImg, oldImg) => {
    // 1. Reset State
    showOriginal.value = false
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
    ocrRecords.value = []
    highlightedOCR.value = null
    highlightedFace.value = null
    videoStyle.value = {}
    isDragging.value = false // Ensure dragging is reset

    // 2. Handle Resource Cleanup & Initialization
    if (oldImg?.file_type === 'video') {
        disposePlayer()
    }

    if (newImg && props.visible) {
        // Auto play if live photo
        if (newImg.file_type === 'live_photo') {
            isPlayingLive.value = true
        } else {
            isPlayingLive.value = false
        }

        // Init new player if switching to video
        if (newImg.file_type === 'video') {
            await nextTick()
            initPlayer()
        }

        // Fetch Data
        // Don't await these to prevent blocking UI updates if they are slow
        fetchMetadata(newImg.id)
        
        if (showOCR.value) {
            fetchOCR(newImg.id)
        }
    } else {
        // If image is null (closed or cleared), dispose
        disposePlayer()
        isPlayingLive.value = false
    }
})

watch(() => props.visible, async (newVal) => {
    if (newVal && props.image) {
        document.body.style.overflow = 'hidden'
        resetZoom()
        
        if (props.image.file_type === 'live_photo') {
             isPlayingLive.value = true
        }

        if (props.image.file_type === 'video') {
            await nextTick()
            initPlayer()
        }
        
        if (!metadata.value || metadata.value.photo_id !== props.image.id) {
            await fetchMetadata(props.image.id)
        }
    } else {
        document.body.style.overflow = ''
        disposePlayer()
        isPlayingLive.value = false
        showPersonSelector.value = false
        showDescription.value = false
        showSidebar.value = false
        showOCR.value = false
    }
})

// Methods
const close = () => {
    emit('close')
}

const toggleSidebar = () => {
    showSidebar.value = !showSidebar.value
    if (showSidebar.value) {
        showOCR.value = false // Close OCR if Sidebar opens
    }
}

const handleCommand = (command: string) => {
    if (command === 'ocr') {
        toggleOCR()
    } else if (command === 'addToAlbum') {
        emit('add-to-album', props.image)
    } else if (command === 'addToPerson') {
        showPersonSelector.value = true
    } else if (command === 'moveToFolder') {
        emit('transfer', 'move')
    } else if (command === 'viewDescription') {
        if (props.image) {
            fetchDescription(props.image.id)
        }
    }
}

// Description State
const showDescription = ref(false)
const descriptionLoading = ref(false)
const imageDescription = ref<any>(null)

const fetchDescription = async (photoId: string) => {
    descriptionLoading.value = true
    showDescription.value = true
    imageDescription.value = null
    try {
        const res = await albumService.getImageDescription(photoId)
        imageDescription.value = res
    } catch (e) {
        console.error(e)
        // ElMessage.error('获取描述失败') // Fail silently or show empty state
    } finally {
        descriptionLoading.value = false
    }
}

// Person Selector State
const showPersonSelector = ref(false)
const isAddingPerson = ref(false)

const handlePersonSelected = async (person: any) => {
  if (!props.image) return
  try {
    isAddingPerson.value = true
    await faceApi.addPhotosToIdentity(person.id, [props.image.id])
    ElMessage.success('添加成功')
    showPersonSelector.value = false
    // Refresh metadata if needed
    fetchMetadata(props.image.id)
  } catch (e) {
    console.error(e)
    ElMessage.error('添加失败')
  } finally {
    isAddingPerson.value = false
  }
}

const fetchMetadata = async (photoId: string) => {
    loading.value = true
    try {
        const data = await albumService.getMetadata(photoId)
        metadata.value = data
    } catch (error) {
        console.error("Failed to fetch metadata", error)
    } finally {
        loading.value = false
    }
}

// OCR Methods
const toggleOCR = async () => {
    showOCR.value = !showOCR.value
    if (showOCR.value) {
        showSidebar.value = false // Close Sidebar if OCR opens
        if (props.image) {
            await fetchOCR(props.image.id)
        }
    }
}

const fetchOCR = async (photoId: string) => {
    ocrLoading.value = true
    try {
        const res = await ocrApi.getOCR(photoId)
        ocrRecords.value = res.records
    } catch (error) {
        console.error("Failed to fetch OCR records", error)
        ElMessage.error("获取OCR记录失败")
    } finally {
        ocrLoading.value = false
    }
}

const getPolygonPoints = (polygon: number[][]) => {
    return polygon.map(p => p.join(',')).join(' ')
}

const onPolygonClick = (record: OCRRecord) => {
    highlightedOCR.value = record
    if (!showOCR.value) {
        showOCR.value = true
        // Fetch OCR if not already (though if records exist, we likely fetched)
    }
}

const onOCRRecordClick = (record: OCRRecord) => {
    highlightedOCR.value = record
}

// Face Highlight Methods
const highlightedFace = ref<CoverPhotoInfo | null>(null)
const highlightedFaceName = ref('')
const highlightedFaceConfidence = ref<number | null>(null)
const highlightedFaceRecognitionConfidence = ref<number | null>(null)

const handleHighlightFace = (payload: { face: CoverPhotoInfo | null, name: string } | null) => {
    if (!payload || !payload.face) {
        highlightedFace.value = null
        highlightedFaceName.value = ''
        highlightedFaceConfidence.value = 0
        return
    }
    highlightedFace.value = payload.face
    highlightedFaceName.value = payload.name
    
    // Prefer recognize_confidence, fallback to face_confidence
    const conf = payload.face.face_confidence
    highlightedFaceConfidence.value = conf ? Math.round(conf * 100) : null
    highlightedFaceRecognitionConfidence.value = payload.face.recognize_confidence ? Math.round(payload.face.recognize_confidence * 100) : null
}

const faceBoxStyle = computed(() => {
    const face = highlightedFace.value
    if (!face || !face.face_rect) return null

    // face_rect is [x1, y1, x2, y2]
    const [x1, y1, x2, y2] = face.face_rect

    const left = x1 * 100
    const top = y1 * 100
    const width = (x2 - x1) * 100
    const height = (y2 - y1) * 100
    return {
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`
    }
})

// Sidebar Event Handlers
const handleSidebarUpdate = (updates: any) => {
    if (metadata.value && updates.id === metadata.value.photo_id) {
        // Update local metadata
        metadata.value = { ...metadata.value, ...updates }
        emit('update', updates)
    }
}

const handleSidebarDelete = (id: string) => {
    emit('delete', id)
    close()
}

// Zoom & Pan Methods
const resetZoom = () => {
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
    isDragging.value = false
}

const zoomIn = () => {
    scale.value = Math.min(scale.value + 0.5, 5)
}

const zoomOut = () => {
    scale.value = Math.max(scale.value - 0.5, 1)
    if (scale.value === 1) {
        translateX.value = 0
        translateY.value = 0
    }
}

const handleWheel = (e: WheelEvent) => {
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = Math.max(1, Math.min(5, scale.value + delta))
    scale.value = newScale
    if (scale.value === 1) {
        translateX.value = 0
        translateY.value = 0
    }
}

const startDrag = (e: MouseEvent) => {
    if (scale.value > 1) {
        isDragging.value = true
        startX.value = e.clientX - translateX.value
        startY.value = e.clientY - translateY.value
        window.addEventListener('mousemove', onDrag)
        window.addEventListener('mouseup', stopDrag)
    }
}

const onDrag = (e: MouseEvent) => {
    if (isDragging.value) {
        e.preventDefault()
        translateX.value = e.clientX - startX.value
        translateY.value = e.clientY - startY.value
    }
}

const stopDrag = () => {
    isDragging.value = false
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
}

// Touch Support (Pinch & Drag)
const startTouch = (e: TouchEvent) => {
    // Only handle pinch or drag if needed
    if (e.touches.length === 2) {
        // Pinch start
        const touch1 = e.touches[0]
        const touch2 = e.touches[1]
        initialDistance.value = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY)
        window.addEventListener('touchmove', onTouchMove, { passive: false })
        window.addEventListener('touchend', stopTouch)
        window.addEventListener('touchcancel', stopTouch)
    } else if (e.touches.length === 1 && scale.value > 1) {
        // Drag start
        isDragging.value = true
        startX.value = e.touches[0].clientX - translateX.value
        startY.value = e.touches[0].clientY - translateY.value
        window.addEventListener('touchmove', onTouchMove, { passive: false })
        window.addEventListener('touchend', stopTouch)
        window.addEventListener('touchcancel', stopTouch)
    }
}

const onTouchMove = (e: TouchEvent) => {
    if (e.touches.length === 2) {
        // Pinch move
        e.preventDefault()
        const touch1 = e.touches[0]
        const touch2 = e.touches[1]
        const currentDistance = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY)
        if (initialDistance.value > 0) {
            const delta = currentDistance / initialDistance.value
            // Smooth zoom adjustment
            const newScale = scale.value * delta
            scale.value = Math.max(1, Math.min(5, newScale))
            initialDistance.value = currentDistance // Reset for continuous zoom
        }
    } else if (e.touches.length === 1 && isDragging.value) {
        // Drag move
        e.preventDefault()
        translateX.value = e.touches[0].clientX - startX.value
        translateY.value = e.touches[0].clientY - startY.value
    }
}

const stopTouch = () => {
    isDragging.value = false
    initialDistance.value = 0
    window.removeEventListener('touchmove', onTouchMove)
    window.removeEventListener('touchend', stopTouch)
    window.removeEventListener('touchcancel', stopTouch)
}

const downloadImage = async () => {
    if (!props.image) return
    try {
        const response = await fetch(props.image.url)
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${props.image.filename}` || `photo_${props.image.id}.jpg` // Simple filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        ElMessage.success('下载开始')
    } catch (e) {
        console.error('Download failed', e)
        ElMessage.error('下载失败')
    }
}

const prev = () => {
    emit('prev')
}
const next = () => {
    emit('next')
}

const handleDelete = () => {
    if (!props.image) return
    ElMessageBox.confirm(
        '确定要删除这张照片吗？此操作不可恢复。',
        '删除确认',
        {
            confirmButtonText: '删除',
            cancelButtonText: '取消',
            type: 'warning',
        }
    )
    .then(() => {
        if (props.image) {
             emit('delete', props.image.id)
             close() // Close after delete, or let parent handle if it switches to next
        }
    })
}

</script>
