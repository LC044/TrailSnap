<template>
  <div class="container mx-auto">
    <!-- Navbar -->
    <div class="sticky top-0 z-20 backdrop-blur-md border-b border-gray-100 dark:border-gray-800 h-14 flex items-center justify-between px-4 transition-opacity duration-300">
      <h1 class="text-lg font-bold text-[#333] dark:text-white">相册概览</h1>
      <div class="flex items-center space-x-4">
        <button class="text-[#666] dark:text-gray-300 dark:bg-gray-800 hover:text-[#4A90E2] transition-colors" @click="$router.push('/recycle-bin')" title="回收站">
          <i class="mgc_delete_2_line text-2xl"></i>
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
     <!-- Annual Report Banner -->
      <div 
        class="mx-4 p-4 rounded-xl bg-gradient-to-r from-orange-100 to-amber-50 dark:from-orange-900/30 dark:to-amber-900/20 border border-orange-200 dark:border-orange-800/50 flex items-center justify-between cursor-pointer hover:shadow-md transition-shadow"
        @click="$router.push('/annual-report')"
      >
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-orange-500 flex items-center justify-center text-white">
             <i class="mgc_calendar_line text-xl"></i>
          </div>
          <div>
            <h3 class="font-bold text-orange-800 dark:text-orange-200 text-sm">2025 年度回忆录</h3>
            <p class="text-xs text-orange-600 dark:text-orange-300/80">一帧一画，定格步履与温柔</p>
          </div>
        </div>
        <div class="w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-white/10 text-orange-500">
           <i class="mgc_right_line"></i>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { dashboardApi, DashboardResponse } from '@/api/dashboard';
import { ElMessage } from 'element-plus';

// Components
import OverviewCards from '@/components/home/OverviewCards.vue';
import HeatmapSection from '@/components/home/HeatmapSection.vue';
import FaceSection from '@/components/home/FaceSection.vue';
import ContentStats from '@/components/home/ContentStats.vue';
import TimeChart from '@/components/home/TimeChart.vue';
import OnThisDay from '@/components/OnThisDay.vue';

const loading = ref(false);
const dashboardData = ref<DashboardResponse | null>(null);
const showStorageDialog = ref(false);

const fetchData = async () => {
  loading.value = true;
  try {
    dashboardData.value = await dashboardApi.getOverview();
    // Toast success
    if (loading.value) { // only if triggered manually or first load
       // ElMessage.success('数据刷新成功');
    }
  } catch (error) {
    console.error(error);
    ElMessage.error('加载数据失败');
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
/* Any additional global overrides */
</style>
