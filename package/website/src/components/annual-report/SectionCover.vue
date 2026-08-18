<template>
  <ReportPage>
    <div class="flex flex-col items-center justify-center h-full relative text-center">
      <!-- Background Watermark -->
      <div class="absolute inset-0 opacity-5 pointer-events-none flex items-center justify-center">
         <div class="w-full h-full bg-[url('/icon/Report.svg')] bg-repeat opacity-10"></div>
      </div>

      <!-- Main Content -->
      <div class="z-10 flex flex-col items-center gap-6 animate-fade-in-up">
        <!-- Logo/Icon -->
        <div class="w-16 h-16 bg-primary-amber rounded-2xl flex items-center justify-center shadow-lg mb-4">
           <Camera class="w-10 h-10 text-white" />
        </div>

        <!-- Titles -->
        <div class="space-y-2">
            <h1 class="text-[clamp(2rem,5vw,2.8rem)] font-bold text-primary-amber tracking-wider">
              TrailSnap
            </h1>
            <p class="text-lg font-light text-light-text3 dark:text-dark-blue-gray">
              一帧一画，定格步履与温柔
            </p>
        </div>

        <!-- User Info -->
        <div class="flex items-center gap-4 mt-8 bg-white/50 dark:bg-black/20 p-4 rounded-full backdrop-blur-sm border border-white/20">
            <img 
              :src="toServerUrl(user.avatarUrl || defaultAvatar)"
              class="w-16 h-16 rounded-full border-2 border-primary-amber shadow-sm object-cover"
              alt="Avatar"
            />
            <div class="text-left pr-4">
                <div class="text-sm text-light-text3 dark:text-gray-400">时光旅人</div>
                <div class="text-xl font-bold text-light-text1 dark:text-white">{{ user.nickname }}</div>
            </div>
        </div>
        
        <!-- Year -->
        <div class="text-6xl font-black text-light-text1/10 dark:text-white/10 mt-4">
            {{ year }}
        </div>
      </div>

      <!-- Bottom Hint -->
      <div class="absolute bottom-10 flex flex-col items-center gap-2 animate-bounce">
        <p class="text-xs text-light-text3 dark:text-gray-400">向上滑动，开启你的时光回忆录</p>
        <ArrowUp class="w-5 h-5 text-primary-amber" />
      </div>
    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import { computed } from 'vue';
import type { UserInfo } from '@/types/annualReport';
import { Camera, ArrowUp } from 'lucide-vue-next';
import { toServerUrl } from '@/config/server';

const props = defineProps<{
  user: UserInfo;
  year: number;
}>();

const defaultAvatar = '/avatar.png'; // Placeholder
</script>

<style scoped>
.animate-fade-in-up {
  animation: fadeInUp 1s ease-out forwards;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
