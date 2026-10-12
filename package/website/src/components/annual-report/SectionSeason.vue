<template>
  <ReportPage class="section-season">
    <div ref="sectionRef" class="h-full flex flex-col p-3 w-full max-w-lg mx-auto">
      <!-- 1. 标题区 (20%) -->
      <div class="h-[20%] flex flex-col justify-center text-center opacity-0" :class="{ 'animate-fade-in-down': isActive }">
        <h2 class="text-2xl font-bold text-orange-500 mb-2 tracking-wide">
          四时之景 · 藏在季节里的岁岁欢喜
        </h2>
        <p class="text-sm text-slate-500 dark:text-slate-400 font-light leading-relaxed">
          春有嫩芽，夏有蝉鸣，秋有晚风，冬有暖意<br>
          你的四季，各有各的温柔
        </p>
      </div>

      <!-- 2. 四季模块区 (75%) -->
      <div class="flex-1 flex flex-col justify-center">
        <div class="grid grid-cols-2 gap-3 max-w-sm mx-auto">
           <div
             v-for="(season, index) in seasonList"
             :key="season.seasonName"
             class="relative group cursor-pointer transition-all duration-300 ease-out hover:scale-105 opacity-0"
             :class="[
               seasonStyles[season.seasonName].bg,
               seasonStyles[season.seasonName].border,
               isActive ? 'animate-fade-in-up' : '',
               'rounded-xl border p-3 flex flex-col aspect-[3/4] md:aspect-[1/1.4] overflow-hidden shadow-sm hover:shadow-md'
             ]"
             :style="{
               animationDelay: `${0.2 + index * 0.2}s`
             }"
             @click="openModal(season)"
           >
              <!-- Header: Icon & Name -->
              <div class="flex items-center gap-1.5 mb-2">
                 <component 
                   :is="seasonStyles[season.seasonName].icon" 
                   class="w-4 h-4 animate-breathe"
                   :class="seasonStyles[season.seasonName].text"
                 />
                 <span class="text-xs font-bold" :class="seasonStyles[season.seasonName].text">
                    {{ season.seasonName }} · {{ season.topTag }}
                 </span>
              </div>

              <!-- Photo Area -->
              <div class="flex-1 relative rounded-lg overflow-hidden mb-2 bg-white/50">
                 <img
                   :src="toServerUrl(season.representativePhoto)"
                   class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                   alt="Season Photo"
                 />
                 <!-- Hover Overlay -->
                 <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center p-2 text-center">
                    <span class="text-[10px] text-white bg-black/40 px-2 py-1 rounded-full backdrop-blur-sm">
                       {{ season.shootMonth }} · {{ season.photoCount }}张
                    </span>
                 </div>
              </div>

              <!-- Footer: Highlight -->
              <div class="relative">
                 <p class="text-[10px] leading-tight font-medium line-clamp-2" :class="seasonStyles[season.seasonName].textDark">
                    {{ season.highlight }}
                 </p>
              </div>
           </div>
        </div>
      </div>

      <!-- 底部提示 -->
      <div class="h-[5%] text-center opacity-0 animate-fade-in-delay">
          <span class="text-xs text-slate-500 dark:text-slate-400">点击卡片，聆听季节故事</span>
      </div>

    </div>

    <!-- 弹窗：季节故事 -->
    <Transition name="modal">
      <div v-if="selectedSeason" class="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/60 backdrop-blur-sm" @click.self="closeModal">
         <div 
           class="w-full max-w-sm bg-white dark:bg-slate-800 rounded-2xl overflow-hidden shadow-2xl transform transition-all p-6 relative"
           :class="seasonStyles[selectedSeason.seasonName].border"
         >
            <button class="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" @click="closeModal">
               <i class="mgc_close_line text-xl"></i>
            </button>

            <!-- 弹窗内容 -->
            <div class="flex flex-col gap-4">
               <div class="flex items-center gap-2">
                  <div class="p-2 rounded-full" :class="seasonStyles[selectedSeason.seasonName].bg">
                     <component :is="seasonStyles[selectedSeason.seasonName].icon" class="w-5 h-5" :class="seasonStyles[selectedSeason.seasonName].text" />
                  </div>
                  <h3 class="text-xl font-bold text-slate-800 dark:text-white">{{ selectedSeason.seasonName }}日独家记忆</h3>
               </div>

               <div class="aspect-video rounded-xl overflow-hidden relative">
                  <img :src="toServerUrl(selectedSeason.representativePhoto)" class="w-full h-full object-cover" />
                  <div class="absolute bottom-2 right-2 text-xs text-white bg-black/40 px-2 py-1 rounded backdrop-blur-md">
                     {{ selectedSeason.shootMonth }}
                  </div>
               </div>

               <!-- AI Story -->
               <div class="bg-slate-50 dark:bg-slate-700/50 p-4 rounded-xl border border-slate-100 dark:border-slate-700">
                  <div class="flex items-center gap-2 mb-2">
                     <i class="mgc_ai_line text-orange-500"></i>
                     <span class="text-xs font-bold text-orange-500">AI 时光旁白</span>
                  </div>
                  <p class="text-sm text-slate-600 dark:text-slate-300 leading-relaxed text-justify">
                     {{ getAiStory(selectedSeason) }}
                  </p>
               </div>
            </div>
         </div>
      </div>
    </Transition>

  </ReportPage>
</template>

<script setup lang="ts">
import { ref, computed,watch } from 'vue';
import ReportPage from './ReportPage.vue';
import { toServerUrl } from '@/config/server';
import type { SeasonMetrics, SeasonData } from '@/types/annualReport';
import { Sprout, Sun, Leaf, Snowflake } from 'lucide-vue-next';
import { useIntersectionObserver } from '@vueuse/core';
const props = defineProps<{
  data: SeasonMetrics;
}>();

const seasonList = computed(() => props.data.seasonList);
const selectedSeason = ref<SeasonData | null>(null);

// CountUp Logic
const displayValue = ref(0);
const isActive = ref(false);
const sectionRef = ref<HTMLElement | null>(null);

useIntersectionObserver(
  sectionRef,
  ([{ isIntersecting }]) => {
    if (isIntersecting && !isActive.value) {
      isActive.value = true;
    }
  },
  { threshold: 0.5 }
);

// 监听 isActive 触发动画
watch(isActive, (newVal) => {
  if (newVal) {
  }
});

// 季节样式映射
const seasonStyles: Record<string, any> = {
  '春': {
    icon: Sprout,
    bg: 'bg-green-50 dark:bg-green-900/20',
    border: 'border-green-200 dark:border-green-800/50',
    text: 'text-green-600 dark:text-green-400',
    textDark: 'text-green-800 dark:text-green-200'
  },
  '夏': {
    icon: Sun,
    bg: 'bg-orange-50 dark:bg-orange-900/20',
    border: 'border-orange-200 dark:border-orange-800/50',
    text: 'text-orange-600 dark:text-orange-400',
    textDark: 'text-orange-800 dark:text-orange-200'
  },
  '秋': {
    icon: Leaf,
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    border: 'border-amber-200 dark:border-amber-800/50',
    text: 'text-amber-600 dark:text-amber-400',
    textDark: 'text-amber-800 dark:text-amber-200'
  },
  '冬': {
    icon: Snowflake,
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-200 dark:border-blue-800/50',
    text: 'text-blue-600 dark:text-blue-400',
    textDark: 'text-blue-800 dark:text-blue-200'
  }
};

// AI 故事生成 (Mock)
const getAiStory = (season: SeasonData) => {
  const stories = {
    '春': `2024年的春日午后，风里裹着花香。${season.topTag}刚冒头，你便迫不及待地去拥抱自然。${season.highlight}，那些笑声都藏在这一季的温柔里，成为了唤醒万物的序曲。`,
    '夏': `热烈的夏天如约而至，${season.topTag}声声入耳。${season.highlight}，我们在晚风中举杯，定格了无数个滚烫的瞬间。这一季的欢聚，比阳光还要耀眼。`,
    '秋': `秋意渐浓，${season.topTag}铺满了街道。${season.highlight}，镜头下的金黄与温柔，是你对这个世界最深情的注视。这一季的沉淀，让时光变得格外柔软。`,
    '冬': `岁末将至，${season.topTag}带来了限定的浪漫。${season.highlight}，我们在寒冷中寻找彼此的温度。这一季的守候，温暖了整个漫长的冬天。`
  };
  return stories[season.seasonName] || '季节流转，美好常在。';
};

const openModal = (season: SeasonData) => {
  selectedSeason.value = season;
};

const closeModal = () => {
  selectedSeason.value = null;
};
</script>

<style scoped>
.animate-fade-in-down {
  animation: fadeInDown 1s ease-out forwards;
}

.animate-fade-in-up {
  animation: fadeInUp 0.8s ease-out forwards;
}

.animate-fade-in-delay {
  animation: fadeIn 1s ease-out forwards;
  animation-delay: 1.5s;
}

.animate-breathe {
  animation: breathe 3s ease-in-out infinite;
}

@keyframes fadeInDown {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes fadeInDown {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

/* Modal Transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .transform,
.modal-leave-active .transform {
  transition: transform 0.3s ease;
}

.modal-enter-from .transform,
.modal-leave-to .transform {
  transform: scale(0.95) translateY(10px);
}
</style>
