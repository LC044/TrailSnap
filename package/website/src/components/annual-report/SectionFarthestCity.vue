<template>
  <ReportPage class="section-farthest-city" :class="{ 'animate-in': isActive }">
    <div class="h-full w-full flex flex-col p-0 overflow-hidden" ref="sectionRef">
      
      <!-- 1. Upper Part: Core Data Area (30%) -->
      <div class="h-[30%] flex flex-col justify-center items-center text-center relative z-10 px-4 mt-6">
        
        <!-- Main Title -->
        <h2 class="text-2xl font-bold text-[#8B5A2B] dark:text-[#D4A373] mb-4 tracking-wide font-handwriting opacity-0" 
            :class="{ 'animate-fade-in-up': isActive }"
            style="animation-delay: 0.2s">
          远方的风 · 今年你奔赴的最远城市
        </h2>

        <!-- Core Data -->
        <div v-if="hasData" class="flex flex-col items-center gap-1 opacity-0"
             :class="{ 'animate-fade-in-up': isActive }"
             style="animation-delay: 0.4s">
          <div class="flex items-baseline gap-2">
            <span class="text-[clamp(1.8rem,4vw,2.2rem)] font-bold text-[#F97316]">{{ data.farthestCity }}</span>
            <span class="text-xl font-light text-[#A07E5E] dark:text-[#A89F91]">{{ data.farthestDistance }}km</span>
          </div>
        </div>
        <div v-else class="flex flex-col items-center gap-1 opacity-0"
             :class="{ 'animate-fade-in-up': isActive }"
             style="animation-delay: 0.4s">
             <span class="text-xl font-light text-[#A07E5E] dark:text-[#A89F91]">0km · 待出发</span>
        </div>

        <!-- Warm Sentence -->
        <p v-if="hasData" class="text-sm text-[#9CA3AF] font-light mt-3 opacity-0"
           :class="{ 'animate-fade-in-up': isActive }"
           style="animation-delay: 0.6s">
           跨越{{ data.farthestDistance }}km的风，藏着这座城的独家温柔
        </p>
        <p v-else class="text-sm text-[#9CA3AF] font-light mt-3 opacity-0"
           :class="{ 'animate-fade-in-up': isActive }"
           style="animation-delay: 0.6s">
           远方待解锁，下一年的风正等你奔赴
        </p>
      </div>

      <!-- 2. Lower Part: Corkboard Photo Wall (70%) -->
      <div class="h-[88%] w-full mx-auto relative mb-6 opacity-0"
           :class="{ 'animate-fade-in-up': isActive }"
           style="animation-delay: 0.8s">
        
        <!-- Corkboard Background -->
        <div class="absolute inset-0 bg-[#E8DCC4] dark:bg-[#3E3328] rounded-xl shadow-[inset_0_0_20px_rgba(0,0,0,0.1)] overflow-hidden border-8 border-[#D4B996] dark:border-[#5C4D3C]">
           <!-- Texture overlay -->
           <div class="cork-texture absolute inset-0 opacity-30 mix-blend-multiply dark:mix-blend-overlay"></div>
           
           <!-- Shadow edge -->
           <div class="absolute inset-0 shadow-[inset_0_0_30px_rgba(0,0,0,0.15)] pointer-events-none z-10 rounded-lg"></div>
        </div>

        <!-- Photos Container -->
        <div v-if="hasData && displayPhotos.length > 0" 
             class="absolute inset-0 flex flex-wrap content-center justify-center overflow-y-auto custom-scrollbar z-20"
             :class="containerLayoutClass">
           <div v-for="(photo, index) in displayPhotos" 
                :key="index"
                class="relative group cursor-pointer transition-transform duration-300 hover:z-50"
                :class="[photoWrapperClass, { 'animate-pin-in': isActive }]"
                :style="{
                    '--rotation': `${getRandomRotation(index)}deg`,
                    'animation-delay': `${1 + index * 0.1}s`,
                    opacity: 0
                }"
                @click="previewPhoto(photo, index)"
           >
              <!-- Photo Frame -->
              <div class="bg-white shadow-md group-hover:shadow-xl group-hover:scale-105 group-hover:ring-2 group-hover:ring-[#F97316] transition-all duration-300 rounded-sm transform-gpu backface-hidden"
                   :class="photoFrameClass">
                  <div class="overflow-hidden bg-gray-100 relative" :class="photoSizeClass">
                     <img :src="getPhotoUrl(photo)" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" loading="lazy" />
                     <!-- Inner shadow/glare for realism -->
                     <div class="absolute inset-0 shadow-[inset_0_0_10px_rgba(0,0,0,0.1)] pointer-events-none"></div>
                  </div>
              </div>

              <!-- Pin (Appears after photo) -->
              <div class="absolute left-1/2 -translate-x-1/2 rounded-full shadow-sm z-30 transition-transform duration-300 group-hover:-translate-y-1"
                   :class="pinClass"
                   :style="{
                      backgroundColor: getRandomPinColor(index),
                      animation: isActive ? `pinPop 0.3s ease-out forwards ${1.3 + index * 0.1}s` : 'none'
                   }"
              >
                 <!-- Pin shadow -->
                 <div class="absolute top-1 left-1 w-full h-full bg-black/20 rounded-full -z-10 blur-[1px]"></div>
              </div>
           </div>
        </div>

        <!-- Empty State Illustration -->
        <div v-else class="absolute inset-0 flex flex-col items-center justify-center z-20 text-[#8B5A2B]/60 dark:text-[#D4A373]/60">
           <div class="w-32 h-32 mb-4 opacity-50 bg-[url('/icon/backpack.svg')] bg-contain bg-no-repeat bg-center"></div> 
           <!-- Using lucide icon as fallback if svg not found, implemented below -->
           <Backpack v-if="true" class="w-24 h-24 mb-4 opacity-40 stroke-1" />
           <p class="font-handwriting text-lg">下一站，去远方看看吧</p>
        </div>

      </div>

    </div>

    <!-- Photo Preview Modal -->
    <div v-if="showPreview" class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4" @click="showPreview = false">
       <div class="relative max-w-4xl w-full max-h-[90vh] flex flex-col items-center" @click.stop>
          <img :src="currentPreviewPhoto" class="max-w-full max-h-[80vh] object-contain rounded-lg shadow-2xl border-4 border-white" />
          <div class="mt-4 text-white/90 text-center font-light tracking-wide">
             <p v-if="hasData">{{ data.farthestCity }} · 远方的独家记忆</p>
          </div>
          <button class="absolute -top-12 right-0 p-2" @click="showPreview = false">
             <X class="w-8 h-8" />
          </button>
       </div>
    </div>

  </ReportPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import ReportPage from './ReportPage.vue';
import type { LocationMetrics } from '@/types/annualReport';
import { useIntersectionObserver } from '@vueuse/core';
import { Backpack, X } from 'lucide-vue-next';

import { Photo } from '@/types/album';
import { toServerUrl } from '@/config/server';
import { thumbnailUrl } from '@/utils/mediaUrl';

const props = defineProps<{
  data: LocationMetrics;
}>();

const isActive = ref(false);
const sectionRef = ref<HTMLElement | null>(null);
const isMobile = ref(false);

isMobile.value = window.innerWidth <= 768;

useIntersectionObserver(
  sectionRef,
  ([{ isIntersecting }]) => {
    if (isIntersecting && !isActive.value) {
      isActive.value = true;
    }
  },
  { threshold: 0.3 }
);

const hasData = computed(() => !!props.data.farthestCity && props.data.farthestDistance > 0);

// Limit photos to 20 for 'dense' mode
const displayPhotos = computed(() => {
   if (isMobile.value) {
      return props.data.farthestCityPhotos ? props.data.farthestCityPhotos.slice(0, 15) : [];
   }
   return props.data.farthestCityPhotos ? props.data.farthestCityPhotos.slice(0, 16) : [];
});

// Layout Mode Calculation
const layoutMode = computed(() => {
    const count = displayPhotos.value.length;
    if (count <= 4) return 'sparse';
    if (count <= 9) return 'medium';
    return 'dense';
});

// CSS Classes based on Layout Mode
const containerLayoutClass = computed(() => {
    switch (layoutMode.value) {
        case 'sparse': return 'p-4 sm:p-8 gap-6 sm:gap-10';
        case 'medium': return 'p-3 sm:p-6 gap-3 sm:gap-5';
        case 'dense': return 'p-2 sm:p-4 gap-2 sm:gap-3';
        default: return '';
    }
});

const photoSizeClass = computed(() => {
    switch (layoutMode.value) {
        case 'sparse': return 'w-32 h-32 sm:w-40 sm:h-40 md:w-48 md:h-48';
        case 'medium': return 'w-20 h-20 sm:w-28 sm:h-28 md:w-32 md:h-32';
        case 'dense': return 'w-14 h-14 sm:w-16 sm:h-16 md:w-20 md:h-20';
        default: return '';
    }
});

const photoFrameClass = computed(() => {
    switch (layoutMode.value) {
        case 'sparse': return 'p-3 pb-8 md:pb-10';
        case 'medium': return 'p-2 pb-6 md:pb-8';
        case 'dense': return 'p-1.5 pb-4 md:pb-6';
        default: return '';
    }
});

const pinClass = computed(() => {
     switch (layoutMode.value) {
        case 'sparse': return '-top-4 w-5 h-5';
        case 'medium': return '-top-3 w-4 h-4';
        case 'dense': return '-top-2 w-3 h-3';
        default: return '';
    }
});

const photoWrapperClass = computed(() => {
    // Maybe add some margin adjustments if needed, but gap handles most
    return '';
});

const getRandomRotation = (index: number) => {
  // 公式：Math.random()*(最大值-最小值) + 最小值
  // 取值范围：-6° 至 6° 之间的任意随机数
  return Math.random() * 8 - 4;
};

// Random pin colors
const pinColors = ['#93C5FD', '#FCA5A5', '#86EFAC', '#FDE047']; // light blue, red, green, yellow
const getRandomPinColor = (index: number) => {
    return pinColors[index % pinColors.length];
};

// Preview Logic
const showPreview = ref(false);
const currentPreviewPhoto = ref('');

const previewPhoto = (photo: Photo, index: number) => {
    currentPreviewPhoto.value = thumbnailUrl(photo.id, 'medium', photo.owner_id);
    showPreview.value = true;
};

const getPhotoUrl = (photo: Photo) => {
  // return `https://picsum.photos/seed/${photo.id}/400/600`;
    return thumbnailUrl(photo.id, 'small', photo.owner_id);
}

</script>

<style scoped>
.font-handwriting {
  font-family: 'Comic Sans MS', 'Chalkboard SE', 'Marker Felt', sans-serif; /* Fallback to system handwriting fonts */
  /* Ideally we would import a webfont like 'Caveat' or 'Ma Shan Zheng' */
}

.cork-texture {
  background-image:
    radial-gradient(circle at 20% 30%, rgba(120, 90, 55, 0.28) 0 1px, transparent 1.5px),
    radial-gradient(circle at 75% 65%, rgba(255, 255, 255, 0.28) 0 1px, transparent 1.5px);
  background-size: 11px 13px, 17px 19px;
}

/* Animations */
.animate-fade-in-up {
  animation: fadeInUp 0.8s ease-out forwards;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes pinIn {
  from { opacity: 0; transform: scale(1.5) rotate(var(--rotation)); }
  to { opacity: 1; transform: scale(1) rotate(var(--rotation)); }
}

@keyframes pinPop {
  0% { opacity: 0; transform: scale(0) translateX(-50%); }
  60% { transform: scale(1.2) translateX(-50%); }
  100% { opacity: 1; transform: scale(1) translateX(-50%); }
}

/* Custom Scrollbar for photos container if needed */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0,0,0,0.1);
  border-radius: 4px;
}

.animate-pin-in {
  animation: pinIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
}

.animate-pin-pop {
  animation: pinPop 0.3s ease-out forwards;
}
</style>
