<template>
  <div class="container mx-auto">
    <!-- Navbar -->
    <div class="sticky top-0 z-20 backdrop-blur-md border-b border-gray-100 dark:border-gray-800 h-14 flex items-center justify-between px-4 transition-opacity duration-300">
      <h1 class="text-lg font-bold text-[#333] dark:text-white">相册概览</h1>
      <div class="flex items-center space-x-4">
        <button class="text-[#666] dark:text-gray-300 dark:bg-gray-800 hover:text-[#4A90E2] transition-colors" @click="$router.push('/recycle-bin')" title="回收站">
          <i class="mgc_delete_2_line text-2xl"></i>
        </button>
        <button class="text-[#666] dark:text-gray-300 dark:bg-gray-800 hover:text-[#4A90E2] transition-colors relative" @click="showStorageDialog = true" title="存储中心">
          <i class="mgc_hard_drive_line text-2xl"></i>
          <!-- Badge can be controlled by storage usage state if we fetch it -->
          <span v-if="showStorageBadge" class="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>
        <button class="text-[#666] dark:text-gray-300 dark:bg-gray-800 hover:text-[#4A90E2] transition-colors md:hidden" @click="$router.push('/settings')" title="设置">
          <i class="mgc_settings_4_line text-2xl"></i>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center min-h-[400px] h-full">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-[#4A90E2]"></div>
    </div>

    <!-- Content -->
    <div v-else-if="dashboardData" class="py-3 space-y-2">
 
      <OnThisDay />
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
      <OverviewCards :data="dashboardData.card" @show-storage="showStorageDialog = true" />
      
      <div class="mx-4 my-3 bg-white dark:bg-neutral-900 rounded-xl p-5 border border-gray-100 dark:border-gray-800 shadow-sm hover:shadow-md transition-shadow duration-300">
        <div class="flex flex-col lg:flex-row gap-6">
          <div class="w-full lg:w-64 flex-shrink-0 pt-4 lg:pt-0 border-t lg:border-t-0 border-gray-100 dark:border-gray-800">
             <TimeChart :data="dashboardData.time" />
          </div>
          <div class="flex-1 overflow-hidden lg:border-r border-gray-100 dark:border-gray-800 lg:pr-6">
             <HeatmapSection />
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

    <!-- Storage Center Dialog -->
    <el-dialog
      v-model="showStorageDialog"
      width="92%"
      top="4vh"
      :show-close="false"
      class="storage-dialog"
      destroy-on-close
    >
      <template #header="{ close }">
        <div class="flex justify-between items-center px-2">
          <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
            <i class="mgc_hard_drive_line text-primary-500"></i>
            存储空间管理
          </h2>
          <button @click="close" class="w-10 h-10 md:w-12 md:h-12 flex items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors group">
            <i class="mgc_close_line text-xl md:text-2xl text-gray-500 dark:text-gray-400 group-hover:text-gray-800 dark:group-hover:text-white transition-colors"></i>
          </button>
        </div>
      </template>
      <div class="h-[80vh] overflow-y-auto scrollbar-hide px-4 md:px-6 bg-gray-50/50 dark:bg-gray-900/50">
        <StorageCenter />
      </div>
    </el-dialog>
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
import StorageCenter from '@/components/home/StorageCenter.vue';

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

<style scoped>
:deep(.storage-dialog) {
  border-radius: 24px;
  overflow: hidden;
  max-width: 1200px;
}
:deep(.storage-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 24px 24px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
:deep(.storage-dialog .el-dialog__body) {
  padding: 0;
}
</style>

<style scoped>
/* Any additional global overrides */
</style>
