<template>
  <div
    v-if="photos.length > 0"
    :class="['mb-6 animate-fade-in transition-all duration-300', isFullScreen ? 'fixed inset-0 z-[9999] bg-black mb-0' : '']"
  >
    <div v-if="!isFullScreen" class="flex items-center justify-between px-4 mb-3">
      <div class="flex items-center gap-2">
        <div class="flex h-10 w-10 items-center justify-center rounded-full bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
          <CalendarCheck class="w-6 h-6" />
        </div>
        <div>
          <h2 class="text-base font-bold text-gray-800 dark:text-white">那年今日</h2>
          <p class="text-xs text-gray-500 dark:text-gray-400">重温美好回忆</p>
        </div>
      </div>
    </div>

    <div v-if="isFullScreen" class="absolute right-4 top-4 z-[10000] sm:right-6 sm:top-6">
      <button
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-full bg-black/25 text-white/90 backdrop-blur-sm transition-colors hover:bg-black/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-black sm:h-10 sm:w-10"
        title="回忆操作"
        aria-label="回忆操作"
        :aria-expanded="memoryMenuOpen"
        aria-haspopup="menu"
        @click.stop="memoryMenuOpen = !memoryMenuOpen"
      >
        <EllipsisVertical class="h-5 w-5" />
      </button>

      <div
        v-if="memoryMenuOpen"
        class="absolute right-0 top-11 min-w-36 overflow-hidden rounded-xl border border-white/15 bg-black/65 p-1.5 text-white shadow-2xl backdrop-blur-xl sm:top-12"
        role="menu"
        aria-label="回忆操作菜单"
      >
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          role="menuitem"
          @click.stop="openPhotoViewer"
        >
          <Info class="h-4 w-4" />
          <span>查看详情</span>
        </button>
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          role="menuitem"
          @click.stop="exitMemoryView"
        >
          <LogOut class="h-4 w-4" />
          <span>退出回忆</span>
        </button>
      </div>
    </div>

    <div :class="isFullScreen ? 'w-full h-full' : 'px-4'">
      <el-carousel
        :key="isFullScreen ? 'fullscreen' : 'normal'"
        :interval="5000"
        :type="isFullScreen ? '' : carouselType"
        :height="isFullScreen ? '100vh' : carouselHeight"
        indicator-position="none"
        :autoplay="true"
        :arrow="isFullScreen ? 'never' : 'always'"
        :initial-index="currentIndex"
        class="overflow-hidden"
        :class="{ 'rounded-xl': !isFullScreen }"
        @change="handleCarouselChange"
      >
        <el-carousel-item
          v-for="(photo, index) in photos"
          :key="photo.id"
          :class="{ 'rounded-xl': !isFullScreen }"
        >
          <div
            class="group relative flex h-full w-full cursor-pointer items-center justify-center overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-inset"
            :class="{ 'rounded-xl': !isFullScreen }"
            role="button"
            :tabindex="isFullScreen ? -1 : 0"
            :aria-label="`打开 ${formatDate(photo)} 的回忆卡片`"
            @click="handleMemoryCardClick(index)"
            @keydown.enter="!isFullScreen && toggleFullScreen(index)"
            @keydown.space.prevent="!isFullScreen && toggleFullScreen(index)"
          >
            <div v-if="isFullScreen" class="absolute inset-0 z-0">
              <img
                :src="getThumbnailUrl(photo)"
                class="h-full w-full scale-110 object-cover opacity-50 blur-2xl"
              />
              <div class="absolute inset-0 bg-white/30 backdrop-blur-sm dark:bg-black/40"></div>
            </div>

            <div
              :class="[
                'relative z-10 transition-all duration-500',
                isFullScreen
                  ? 'p-4 xl:p-8 bg-white dark:bg-gray-800 shadow-2xl rounded-lg md:rounded-xl border-[8px] xl:border-[16px] border-gray-100 dark:border-gray-700 max-w-[95vw] md:max-w-[90vw] max-h-[85vh] md:max-h-[90vh] flex flex-col w-fit h-fit overflow-hidden'
                  : 'w-full h-full',
              ]"
              :style="isFullScreen ? { aspectRatio: 'auto' } : {}"
            >
              <img
                :src="isFullScreen ? getFullImageUrl(photo) : getThumbnailUrl(photo)"
                class="transition-transform duration-500"
                :class="[
                  isFullScreen
                    ? 'w-auto h-auto max-w-full max-h-[55vh] md:max-h-[70vh] object-contain mx-auto rounded-sm shadow-sm'
                    : 'w-full h-full object-cover group-hover:scale-105',
                ]"
                loading="lazy"
              />

              <div
                v-if="!isFullScreen"
                class="pointer-events-none absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/70 via-transparent to-transparent p-2 md:p-4"
              >
                <div class="flex flex-col gap-0.5">
                  <div v-if="getNarrative(photo)" class="mb-2 line-clamp-2 text-xs font-medium text-white shadow-sm md:text-sm">
                    {{ getNarrative(photo) }}
                  </div>
                  <div class="flex items-baseline gap-2 text-white">
                    <span class="text-xs font-bold shadow-sm md:text-lg">{{ formatDate(photo) }}</span>
                    <span class="text-xs font-medium opacity-90">({{ getTimeAgo(photo) }})</span>
                  </div>
                  <div v-if="getLocation(photo)" class="flex items-center gap-1 text-xs font-medium text-white/90 shadow-sm">
                    <MapPin class="w-4 h-4" />
                    {{ getLocation(photo) }}
                  </div>
                </div>
              </div>

              <div v-else class="mt-3 flex flex-col gap-1 px-1 text-gray-700 dark:text-gray-300 xl:mt-4 xl:px-2">
                <div class="flex flex-col justify-between gap-1 md:flex-row xl:items-center">
                  <div class="flex flex-wrap items-baseline gap-2">
                    <span class="whitespace-nowrap text-lg font-bold xl:text-xl">{{ formatDate(photo) }}</span>
                    <span class="whitespace-nowrap text-xs opacity-80 xl:text-sm">({{ getTimeAgo(photo) }})</span>
                  </div>
                  <div v-if="getLocation(photo)" class="flex items-center gap-1 text-xs font-medium opacity-70">
                    <i class="mgc_location_line"></i>
                    <span class="max-w-[200px] truncate">{{ getLocation(photo) }}</span>
                  </div>
                </div>
                <div
                  v-if="getNarrative(photo)"
                  class="mt-1 line-clamp-3 border-l-2 border-primary-500 py-1 pl-2 font-serif text-xs italic leading-relaxed opacity-90 xl:mt-0 xl:line-clamp-none xl:pl-3 xl:text-sm"
                >
                  {{ getNarrative(photo) }}
                </div>
              </div>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
    </div>
  </div>

  <PhotoLightbox
    :visible="selectedIndex !== null"
    :image="selectedImage"
    :images="lightboxImages"
    :current-index="selectedIndex ?? -1"
    :has-prev="hasPrev"
    :has-next="hasNext"
    :allow-edit="true"
    :allow-delete="true"
    :allow-add-to-album="true"
    :allow-add-to-person="true"
    :allow-move-to-folder="true"
    @close="closePhotoViewer"
    @delete="handleDelete"
    @update="fetchOnThisDay"
    @prev="showPrevious"
    @next="showNext"
    @select="index => (selectedIndex = index)"
    @add-to-album="image => organizeActions?.openAlbum(image.id)"
    @transfer="organizeActions?.openMove(selectedImage?.id || '')"
  />
  <PhotoOrganizeActions ref="organizeActions" @transfer-success="fetchOnThisDay" />
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { CalendarCheck, EllipsisVertical, Info, LogOut, MapPin } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { format } from 'date-fns'
import { photoApi } from '@/api/photo'
import { albumService } from '@/api/album'
import type { Photo } from '@/types/album'
import { useHotkeys } from '@/composables/useHotkeys'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { toServerUrl } from '@/config/server'
import { mapPhotoToImage } from '@/stores/photoStore'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import PhotoOrganizeActions from '@/components/PhotoOrganizeActions.vue'

const photos = ref<Photo[]>([])
const currentIndex = ref(0)
const isFullScreen = ref(false)
const selectedIndex = ref<number | null>(null)
const returnToMemoryView = ref(false)
const memoryMenuOpen = ref(false)
const organizeActions = ref<InstanceType<typeof PhotoOrganizeActions> | null>(null)
const carouselHeight = ref('480px')
const carouselType = ref<'' | 'card'>('card')

const selectedImage = computed(() => {
  if (selectedIndex.value === null) return null
  const photo = photos.value[selectedIndex.value]
  return photo ? mapPhotoToImage(photo) : null
})
// 灯箱轨道与缩略图条需要 AlbumImage 列表，与 selectedImage 同源映射以保证 id 对齐
const lightboxImages = computed(() => photos.value.map(mapPhotoToImage))
const hasPrev = computed(() => selectedIndex.value !== null && selectedIndex.value > 0)
const hasNext = computed(() => selectedIndex.value !== null && selectedIndex.value < photos.value.length - 1)

const updateCarouselHeight = () => {
  if (window.innerWidth < 768) {
    carouselHeight.value = '200px'
    carouselType.value = ''
  } else if (window.innerWidth < 1280) {
    carouselHeight.value = '360px'
    carouselType.value = ''
  } else {
    carouselHeight.value = '480px'
    carouselType.value = 'card'
  }
}

const fetchOnThisDay = async () => {
  try {
    photos.value = await photoApi.getOnThisDayPhotos({ limit: 10 })
  } catch (error) {
    console.error('Failed to fetch On This Day photos', error)
  }
}

const getThumbnailUrl = (photo: Photo) => toServerUrl(`/api/medias/${photo.id}/thumbnail?size=medium`)
const getFullImageUrl = (photo: Photo) => toServerUrl(`/api/medias/${photo.id}/file`)

const formatDate = (photo: Photo) => {
  const dateStr = photo.photo_time || photo.upload_time
  if (!dateStr) return ''
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd')
  } catch {
    return ''
  }
}

const getLocation = (photo: Photo) => {
  const meta = photo.metadata_info
  if (!meta) return ''
  return [meta.province, meta.city].filter(Boolean).join(' ')
}

const getNarrative = (photo: Photo) => photo.image_description?.narrative || ''

const getTimeAgo = (photo: Photo) => {
  const currentYear = new Date().getFullYear()
  const photoYear = new Date(photo.photo_time).getFullYear()
  const years = currentYear - photoYear
  return years <= 0 ? '今年' : `${years} 年前`
}

const toggleFullScreen = (index: number) => {
  memoryMenuOpen.value = false
  if (!isFullScreen.value) {
    currentIndex.value = index
    isFullScreen.value = true
    document.body.style.overflow = 'hidden'
  } else {
    isFullScreen.value = false
    document.body.style.overflow = ''
  }
}
useOverlayStack(isFullScreen, () => {
  if (isFullScreen.value) toggleFullScreen(currentIndex.value)
})

const handleMemoryCardClick = (index: number) => {
  if (isFullScreen.value) {
    memoryMenuOpen.value = false
    return
  }
  toggleFullScreen(index)
}

const exitMemoryView = () => {
  memoryMenuOpen.value = false
  toggleFullScreen(currentIndex.value)
}

const handleCarouselChange = (index: number) => {
  currentIndex.value = index
}

const openPhotoViewer = () => {
  memoryMenuOpen.value = false
  selectedIndex.value = currentIndex.value
  returnToMemoryView.value = true
  isFullScreen.value = false
}

const closePhotoViewer = async () => {
  selectedIndex.value = null
  if (returnToMemoryView.value && photos.value.length > 0) {
    isFullScreen.value = true
    await nextTick()
    document.body.style.overflow = 'hidden'
  }
}

const showPrevious = () => {
  if (hasPrev.value && selectedIndex.value !== null) {
    selectedIndex.value -= 1
    currentIndex.value = selectedIndex.value
  }
}

const showNext = () => {
  if (hasNext.value && selectedIndex.value !== null) {
    selectedIndex.value += 1
    currentIndex.value = selectedIndex.value
  }
}

const handleDelete = async (photoId: string) => {
  returnToMemoryView.value = false
  try {
    await albumService.deletePhoto(photoId)
    photos.value = photos.value.filter(photo => photo.id !== photoId)
    selectedIndex.value = null
    isFullScreen.value = false
    document.body.style.overflow = ''
    ElMessage.success('已移入回收站')
  } catch (error) {
    console.error('Failed to delete photo from On This Day', error)
    ElMessage.error('删除失败')
  }
}

useHotkeys([
  {
    key: 'Escape',
    handler: () => memoryMenuOpen.value ? (memoryMenuOpen.value = false) : toggleFullScreen(currentIndex.value),
    when: () => isFullScreen.value,
  },
], { priority: 0 })

onMounted(() => {
  fetchOnThisDay()
  updateCarouselHeight()
  window.addEventListener('resize', updateCarouselHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateCarouselHeight)
  document.body.style.overflow = ''
})
</script>

<style scoped>
:deep(.el-carousel__item--card) {
  border-radius: 0.75rem;
}
.animate-fade-in {
  animation: fadeIn 0.5s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
