<template>
  <div class="ts-browse-page mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)]">
    <!-- Navbar -->
    <div class="ts-browse-header sticky top-0 z-20 -mx-[var(--ts-page-gutter)] flex gap-2 py-2 items-center justify-between px-[var(--ts-page-gutter)]">
      <h1 class="ts-page-title text-gray-800 dark:text-white">首页</h1>
      <div class="ts-liquid-glass ts-glass-toolbar ml-auto flex items-center">
        <button class="ts-glass-button" aria-label="搜索照片" @click="router.push('/mobile-search')"><Search class="h-5 w-5" /></button>
        <button class="ts-glass-button" aria-label="回收站" @click="router.push('/recycle-bin')"><Trash2 class="h-5 w-5" /></button>
        <button class="ts-glass-button" aria-label="AI 助手" @click="uiStore.openAgent()"><Bot class="h-5 w-5" /></button>
        <button class="ts-glass-button" aria-label="更多首页操作" :aria-expanded="showHomeActions" aria-haspopup="menu" @click="showHomeActions = !showHomeActions"><MoreHorizontal class="h-5 w-5" /></button>
    <AdaptiveMenu mobile-presentation="popover" v-model="showHomeActions" title="首页快捷操作" glass>
      <button class="ts-action-row" @click="showHomeActions = false; router.push('/memories')"><BookHeart />回忆</button>
      <button class="ts-action-row" @click="showHomeActions = false; router.push('/daily-frame')"><Film />为今天留一个瞬间</button>
      <button class="ts-action-row" @click="showHomeActions = false; router.push('/annual-report')"><CalendarDays />年度回忆录</button>
      <button class="ts-action-row" @click="showHomeActions = false; router.push('/game')"><MapPin />猜城市</button>
      <button class="ts-action-row" @click="showHomeActions = false; showStorageDialog = true"><HardDrive />存储中心</button>
    </AdaptiveMenu>
      <div class="hidden items-center md:flex">
        <button class="ts-icon-button ts-button-ghost relative" @click="showStorageDialog = true" title="存储中心" aria-label="打开存储中心">
          <HardDrive class="h-5 w-5" />
          <span v-if="showStorageBadge" class="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>
      </div>
      </div>

    </div>


    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center min-h-[400px] h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>

    <!-- Content -->
    <div v-else-if="dashboardData" class="py-3 space-y-4">

      <OnThisDay />
      <MemoryDiscovery />
      <DailyFrameCard class="hidden md:flex" />
     <!-- Banners Area -->
      <div class="hidden md:grid md:grid-cols-2 gap-4">
        <!-- Annual Report Banner -->
        <div 
          class="p-4 rounded-xl bg-gradient-to-r from-orange-100 to-amber-50 dark:from-orange-900/30 dark:to-amber-900/20 border border-orange-200 dark:border-orange-800/50 flex items-center justify-between cursor-pointer hover:shadow-md transition-shadow"
          @click="$router.push('/annual-report')"
        >
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-orange-500 flex items-center justify-center text-white">
               <i class="mgc_calendar_line text-xl"></i>
            </div>
            <div>
              <h3 class="ts-card-title font-bold text-orange-800 dark:text-orange-200 text-sm">{{ annualYear }} 年度回忆录</h3>
              <p class="text-xs text-orange-600 dark:text-orange-300/80">一帧一画，定格步履与温柔</p>
            </div>
          </div>
          <div class="w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-white/10 text-orange-500">
             <i class="mgc_right_line"></i>
          </div>
        </div>

        <!-- Guess City Banner -->
        <div 
          class="p-4 rounded-xl bg-gradient-to-r from-primary-100 to-primary-50 dark:from-primary-900/30 dark:to-primary-900/20 border border-primary-200 dark:border-primary-800/50 flex items-center justify-between cursor-pointer hover:shadow-md transition-shadow"
          @click="$router.push('/game')"
        >
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-primary-500 flex items-center justify-center text-white">
               <i class="mgc_location_line text-xl"></i>
            </div>
            <div>
              <h3 class="ts-card-title font-bold text-primary-800 dark:text-primary-200 text-sm">猜城市</h3>
              <p class="text-xs text-primary-600 dark:text-primary-300/80">凭借零星线索，找回关于那座城的记忆</p>
            </div>
          </div>
          <div class="w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-white/10 text-primary-500">
             <i class="mgc_right_line"></i>
          </div>
        </div>
      </div>
      <div class="space-y-3">
        <OverviewCards
          :data="dashboardData.card"
          :content="dashboardData.content"
          @show-storage="showStorageDialog = true"
        />

        <div class="ts-surface p-4 md:p-6">
          <div class="flex flex-col xl:flex-row gap-6">
            <div class="w-full xl:w-64 flex-shrink-0 pt-4 xl:pt-0 border-t xl:border-t-0 border-gray-100 dark:border-gray-800">
              <TimeChart :data="dashboardData.time" />
            </div>
            <div class="flex-1 min-w-0 xl:border-r border-gray-100 dark:border-gray-800 xl:pr-6">
              <HeatmapSection />
            </div>
          </div>
        </div>
      </div>
      <div class="grid items-start gap-4 lg:grid-cols-2">
        <FootprintCard :data="footprintData" :loading="footprintLoading" @retry="fetchFootprint" />
        <FaceSection :data="dashboardData.face" />
      </div>
      <!-- <ToolsSection /> -->
    </div>
    <!-- Error State -->
    <div v-else class="flex flex-col items-center justify-center min-h-[400px] h-full text-gray-500 dark:text-gray-400">
      <i class="mgc_warning_line text-4xl mb-2"></i>
      <p>加载失败，请下拉刷新</p>
    </div>

    <ResponsiveDialog
      v-model="showStorageDialog"
      title="存储空间管理"
      max-width="75rem"
      mobile-mode="fullscreen"
      mobile-back
    >
      <StorageCenter />
    </ResponsiveDialog>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { Search, Trash2, Bot, MapPin, MoreHorizontal, BookHeart, Film, CalendarDays, HardDrive } from 'lucide-vue-next';
import { useUiStore } from '@/stores/uiStore';
const uiStore = useUiStore();
const router = useRouter();
const showHomeActions = ref(false);
import { ref, computed, onMounted, onActivated } from 'vue';
import { dashboardApi, DashboardResponse } from '@/api/dashboard';
import { locationService, type OverviewStats } from '@/api/location';
import { ElMessage } from 'element-plus';

defineOptions({
  name: 'HomePage'
});

// Components
import OverviewCards from '@/components/home/OverviewCards.vue';
import HeatmapSection from '@/components/home/HeatmapSection.vue';
import FaceSection from '@/components/home/FaceSection.vue';
import FootprintCard from '@/components/home/FootprintCard.vue';
import TimeChart from '@/components/home/TimeChart.vue';
import OnThisDay from '@/components/OnThisDay.vue';
import MemoryDiscovery from '@/components/home/MemoryDiscovery.vue';
import DailyFrameCard from '@/components/home/DailyFrameCard.vue';
import StorageCenter from '@/components/home/StorageCenter.vue';
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue';
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue';

const loading = ref(false);
const dashboardData = ref<DashboardResponse | null>(null);
const footprintData = ref<OverviewStats | null>(null);
const footprintLoading = ref(false);
const fetchFootprint = async () => {
  if (footprintLoading.value) return;
  footprintLoading.value = true;
  try {
    footprintData.value = await locationService.getOverview();
  } catch (error) {
    console.error('Failed to load home footprint statistics', error);
  } finally {
    footprintLoading.value = false;
  }
};
const showStorageDialog = ref(false);
const showStorageBadge = ref(false);
const annualYear = computed(() => new Date().getFullYear() - 1);

const fetchData = async (silent = false) => {
  void fetchFootprint();
  if (!silent) {
    loading.value = true;
  }
  try {
    const dashboardRes = await dashboardApi.getOverview();
    dashboardData.value = dashboardRes;
  } catch (error) {
    console.error(error);
    if (!silent) {
      ElMessage.error('加载数据失败');
    }
  } finally {
    if (!silent) {
      loading.value = false;
    }
  }
};

onMounted(() => {
  fetchData();
});

onActivated(() => {
  fetchData(true);
});
</script>
