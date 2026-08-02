<template>
  <div v-if="photos.length > 0" 
       :class="['mb-6 animate-fade-in transition-all duration-300', isFullScreen ? 'fixed inset-0 z-[9999] bg-black mb-0' : '']">
    
    <!-- Header (Hidden in Full Screen) -->
    <div v-if="!isFullScreen" class="flex items-center justify-between px-4 mb-3">
      <div class="flex items-center gap-2">
        <div class="w-10 h-10 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
           <CalendarCheck class="w-6 h-6" />
        </div>
        <div>
           <h2 class="text-base font-bold text-gray-800 dark:text-white">那年今日</h2>
           <p class="text-xs text-gray-500 dark:text-gray-400">重温美好回忆</p>
        </div>
      </div>
    </div>
    
    <!-- Close Button (Only in Full Screen) -->
    <button 
      v-if="isFullScreen"
      class="absolute top-6 right-6 z-[10000] w-10 h-10 flex items-center justify-center rounded-full bg-black/40 text-white hover:bg-black/60 transition-colors backdrop-blur-sm"
      @click="toggleFullScreen(currentIndex)"
    >
      <i class="mgc_close_line text-2xl"></i>
    </button>

    <div :class="isFullScreen ? 'w-full h-full' : 'px-4'">
      <el-carousel 
        :key="isFullScreen ? 'fullscreen' : 'normal'"
        :interval="5000" 
        :type="isFullScreen ? '' : 'card'"
        :height="isFullScreen ? '100vh' : carouselHeight" 
        :indicator-position="isFullScreen ? 'none' : 'none'"
        :autoplay="true"
        :arrow="isFullScreen ? 'never' : 'always'"
        :initial-index="currentIndex"
        @change="handleCarouselChange"
        class="overflow-hidden"
        :class="{'rounded-xl': !isFullScreen}"
      >
        <el-carousel-item v-for="(photo, index) in photos" :key="photo.id" :class="{'rounded-xl': !isFullScreen}">
           <div 
             class="relative w-full h-full overflow-hidden cursor-pointer group flex items-center justify-center"
             :class="{'rounded-xl': !isFullScreen}"
             @click="!isFullScreen && toggleFullScreen(index)"
           >
              <!-- Full Screen Background (Blurred) -->
              <div v-if="isFullScreen" class="absolute inset-0 z-0">
                  <img 
                    :src="getThumbnailUrl(photo)" 
                    class="w-full h-full object-cover blur-2xl opacity-50 scale-110"
                  />
                  <div class="absolute inset-0 bg-white/30 dark:bg-black/40 backdrop-blur-sm"></div>
              </div>

              <!-- Main Image (Framed in Full Screen) -->
              <div 
                :class="[
                  'relative z-10 transition-all duration-500',
                  isFullScreen ? 'p-4 xl:p-8 bg-white dark:bg-gray-800 shadow-2xl rounded-lg md:rounded-xl border-[8px] xl:border-[16px] border-gray-100 dark:border-gray-700 max-w-[95vw] md:max-w-[90vw] max-h-[85vh] md:max-h-[90vh] flex flex-col w-fit h-fit overflow-hidden' : 'w-full h-full'
                ]"
                :style="isFullScreen ? { aspectRatio: 'auto' } : {}"
              >
                <img 
                  :src="isFullScreen ? getFullImageUrl(photo) : getThumbnailUrl(photo)" 
                  class="transition-transform duration-500"
                  :class="[
                    isFullScreen ? 'w-auto h-auto max-w-full max-h-[55vh] md:max-h-[70vh] object-contain mx-auto rounded-sm shadow-sm' : 'w-full h-full object-cover group-hover:scale-105'
                  ]"
                  loading="lazy"
                />

                <!-- Info Overlay (Adjusted for Full Screen) -->
                <div 
                  v-if="!isFullScreen"
                  class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent flex flex-col justify-end p-2 md:p-4 pointer-events-none"
                >
                    <div class="flex flex-col gap-0.5">
                        <div v-if="getNarrative(photo)" class="text-white text-xs md:text-sm mb-2 line-clamp-2 shadow-sm font-medium">
                            {{ getNarrative(photo) }}
                        </div>
                        <div class="flex items-baseline gap-2 text-white">
                            <span class="font-bold text-xs md:text-lg shadow-sm">{{ formatDate(photo) }}</span>
                            <span class="text-xs opacity-90 font-medium">({{ getTimeAgo(photo) }})</span>
                        </div>
                        <div v-if="getLocation(photo)" class="text-white/90 text-xs font-medium flex items-center gap-1 shadow-sm">
                            <MapPin class="w-4 h-4" />
                            {{ getLocation(photo) }}
                        </div>
                    </div>
                </div>
                
                <!-- Info Overlay (Full Screen - Below Photo on Mat) -->
                 <div v-else class="mt-3 xl:mt-4 px-1 xl:px-2 flex flex-col gap-1 text-gray-700 dark:text-gray-300">
                    <div class="flex flex-col md:flex-row xl:items-center justify-between gap-1">
                        <div class="flex items-baseline gap-2 flex-wrap">
                             <span class="font-bold text-lg xl:text-xl whitespace-nowrap">{{ formatDate(photo) }}</span>
                             <span class="text-xs xl:text-sm opacity-80 whitespace-nowrap">({{ getTimeAgo(photo) }})</span>
                        </div>
                        <div v-if="getLocation(photo)" class="text-xs font-medium flex items-center gap-1 opacity-70">
                             <i class="mgc_location_line"></i>
                             <span class="truncate max-w-[200px]">{{ getLocation(photo) }}</span>
                        </div>
                    </div>
                    <div v-if="getNarrative(photo)" class="text-xs xl:text-sm font-serif italic opacity-90 leading-relaxed border-l-2 border-indigo-500 pl-2 xl:pl-3 py-1 mt-1 xl:mt-0 line-clamp-3 xl:line-clamp-none">
                        {{ getNarrative(photo) }}
                    </div>
                 </div>
              </div>
           </div>
        </el-carousel-item>
      </el-carousel>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { CalendarCheck, MapPin } from 'lucide-vue-next'
import { photoApi } from '@/api/photo';
import type { Photo } from '@/types/album';
import { format } from 'date-fns';
import { useHotkeys } from '@/composables/useHotkeys';
import { toServerUrl } from '@/config/server';

const photos = ref<Photo[]>([]);
const currentIndex = ref(0);
const isFullScreen = ref(false);
const carouselHeight = ref('480px');

const updateCarouselHeight = () => {
  if (window.innerWidth < 768) {
    carouselHeight.value = '200px';
  } else {
    carouselHeight.value = '480px';
  }
};

const fetchOnThisDay = async () => {
  try {
    const data = await photoApi.getOnThisDayPhotos({ limit: 10 });
    photos.value = data;
  } catch (error) {
    console.error('Failed to fetch On This Day photos', error);
  }
};

const getThumbnailUrl = (photo: Photo) => {
  return toServerUrl(`/api/medias/${photo.id}/thumbnail?size=medium`);
};

const getFullImageUrl = (photo: Photo) => {
    // Use the raw file endpoint for high quality in full screen
  return toServerUrl(`/api/medias/${photo.id}/file`);
};

const formatDate = (photo: Photo) => {
    const dateStr = photo.photo_time || photo.upload_time;
    if (!dateStr) return '';
    try {
        return format(new Date(dateStr), 'yyyy-MM-dd');
    } catch (e) {
        return '';
    }
};

const getLocation = (photo: Photo) => {
    const meta = photo.metadata_info;
    if (!meta) return '';
    const parts = [];
    if (meta.province) parts.push(meta.province);
    if (meta.city) parts.push(meta.city);
    return parts.join(' ');
};

const getNarrative = (photo: Photo) => {
    return photo.image_description?.narrative || '';
};

const getTimeAgo = (photo: Photo) => {
    const date = new Date(photo.photo_time);
    const currentYear = new Date().getFullYear();
    const photoYear = date.getFullYear();
    const years = currentYear - photoYear;
    if (years <= 0) return '今年';
    return `${years} 年前`;
};

const toggleFullScreen = (index: number) => {
    if (!isFullScreen.value) {
        currentIndex.value = index;
        isFullScreen.value = true;
        document.body.style.overflow = 'hidden'; // Prevent scrolling background
    } else {
        isFullScreen.value = false;
        document.body.style.overflow = ''; // Restore scrolling
    }
};

const handleCarouselChange = (index: number) => {
    currentIndex.value = index;
};

// Handle ESC key to exit full screen
useHotkeys([
  { key: 'Escape', handler: () => toggleFullScreen(currentIndex.value), when: () => isFullScreen.value },
], { priority: 0 });

onMounted(() => {
    fetchOnThisDay();
    updateCarouselHeight();
    window.addEventListener('resize', updateCarouselHeight);
});

onUnmounted(() => {
    window.removeEventListener('resize', updateCarouselHeight);
    document.body.style.overflow = '';
});
</script>

<style scoped>
/* Adjust carousel card width if needed */
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
