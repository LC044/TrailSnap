<template>
  <ReportPage>
    <div class="flex flex-col h-full w-full items-center justify-center text-center">
        <!-- Main Tag -->
        <div class="relative mb-8 animate-scale-in">
            <div class="absolute -inset-4 bg-primary-amber/10 rounded-full blur-xl"></div>
            <h2 class="relative text-[clamp(2.5rem,8vw,3.5rem)] font-bold text-primary-amber">
                {{ data.tags.main }}
            </h2>
        </div>

        <!-- Sub Tags -->
        <div class="flex flex-wrap gap-3 justify-center mb-10">
            <span 
                v-for="tag in data.tags.sub" 
                :key="tag"
                class="px-4 py-1.5 bg-white dark:bg-white/10 rounded-full text-sm text-light-text2 dark:text-gray-300 shadow-sm border border-gray-100 dark:border-gray-700"
            >
                {{ tag }}
            </span>
        </div>

        <!-- Best Photo -->
        <div class="relative w-64 h-64 md:w-72 md:h-72 mb-6 group">
            <div class="absolute inset-0 bg-primary-amber rounded-2xl rotate-3 opacity-20 group-hover:rotate-6 transition-transform"></div>
            <img 
                :src="toServerUrl(data.bestPhotoUrl)"
                class="relative w-full h-full object-cover rounded-2xl shadow-xl border-4 border-white dark:border-gray-700 transform transition-transform group-hover:-rotate-1"
                alt="Best Photo"
            />
            <div class="absolute -bottom-6 left-0 right-0 text-center">
                <span class="inline-block bg-white/90 dark:bg-black/60 backdrop-blur px-3 py-1 rounded-full text-xs text-gray-500 shadow-sm">
                    {{ data.bestPhotoDate }} · 年度最佳瞬间
                </span>
            </div>
        </div>

    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import { toServerUrl } from '@/config/server';
import type { EasterEgg } from '@/types/annualReport';
import { Quote } from 'lucide-vue-next';

const props = defineProps<{
  data: EasterEgg;
}>();
</script>

<style scoped>
.animate-scale-in {
  animation: scaleIn 0.8s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
}
@keyframes scaleIn {
  from { transform: scale(0.5); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
</style>
