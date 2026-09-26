<template>
  <div class="container mx-auto">
    <!-- Navbar -->
    <div class="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-gray-100 bg-gray-50/90 px-4 backdrop-blur-md transition-colors dark:border-gray-800 dark:bg-gray-900/90">
      <h1 class="text-lg font-bold text-gray-800 dark:text-white">首页</h1>
      <div class="hidden items-center md:flex">
        <button class="relative rounded-lg p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-gray-300 dark:hover:bg-gray-800" @click="showStorageDialog = true" title="存储中心" aria-label="打开存储中心">
          <i class="mgc_hard_drive_line text-2xl"></i>
          <span v-if="showStorageBadge" class="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center min-h-[400px] h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>

    <!-- Content -->
    <div v-else-if="dashboardData" class="py-3 space-y-2">
 
      <OnThisDay />
      <MemoryDiscovery />
     <!-- Banners Area -->
      <div class="mx-4 grid grid-cols-1 md:grid-cols-2 gap-4">
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
              <h3 class="font-bold text-orange-800 dark:text-orange-200 text-sm">{{ annualYear }} 年度回忆录</h3>
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
              <h3 class="font-bold text-primary-800 dark:text-primary-200 text-sm">猜城市</h3>
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

        <div class="mx-4 bg-white dark:bg-neutral-900 rounded-xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-shadow duration-300">
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
      <FaceSection :data="dashboardData.face" />
      <ContentStats :data="dashboardData.content" />
      <!-- <ToolsSection /> -->
    </div>
    <!-- Error State -->
    <div v-else class="flex flex-col items-center justify-center min-h-[400px] h-full text-gray-500">
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
import { ref, computed, onMounted, onActivated } from 'vue';
import { dashboardApi, DashboardResponse } from '@/api/dashboard';
import { ElMessage } from 'element-plus';

defineOptions({
  name: 'HomePage'
});

// Components
import OverviewCards from '@/components/home/OverviewCards.vue';
import HeatmapSection from '@/components/home/HeatmapSection.vue';
import FaceSection from '@/components/home/FaceSection.vue';
import ContentStats from '@/components/home/ContentStats.vue';
import TimeChart from '@/components/home/TimeChart.vue';
import OnThisDay from '@/components/OnThisDay.vue';
import MemoryDiscovery from '@/components/home/MemoryDiscovery.vue';
import StorageCenter from '@/components/home/StorageCenter.vue';
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue';

const loading = ref(false);
const dashboardData = ref<DashboardResponse | null>(null);
const showStorageDialog = ref(false);
const showStorageBadge = ref(false);
const annualYear = computed(() => new Date().getFullYear() - 1);

const fetchData = async (silent = false) => {
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
