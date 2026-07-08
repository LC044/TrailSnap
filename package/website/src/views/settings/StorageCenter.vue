<template>
  <div class="space-y-6 max-w-6xl mx-auto pb-10">
    <!-- Header Actions -->
    <div class="flex justify-end items-center mb-2 mt-4 md:mt-2">
      <button 
        class="px-5 py-2.5 bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 rounded-xl hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-all text-sm font-semibold flex items-center gap-2 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        @click="triggerScan"
        :disabled="loading || isScanning"
      >
        <i v-if="loading || isScanning" class="mgc_loading_4_line animate-spin text-lg"></i>
        <i v-else class="mgc_refresh_3_line text-lg"></i>
        {{ isScanning ? '扫描中...' : '重新扫描存储' }}
      </button>
    </div>

    <div v-if="loading && !overviewData" class="flex justify-center py-20">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>

    <div v-else-if="overviewData" class="space-y-6">
      <!-- 1. Top Section: Overview & Recoverable -->
      <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <!-- Overview Card -->
        <div class="xl:col-span-1 bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 relative overflow-hidden flex flex-col items-center">
          <div class="absolute top-0 right-0 w-32 h-32 bg-primary-500/10 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none"></div>
          <div class="absolute bottom-0 left-0 w-24 h-24 bg-blue-500/10 rounded-full blur-2xl -ml-8 -mb-8 pointer-events-none"></div>
          
          <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 w-full text-left mb-2 z-10">总占用空间</h3>
          <div class="text-center z-10 my-2">
            <p class="text-4xl font-black text-primary-500 tracking-tight">{{ formatSize(overviewData.total_size) }}</p>
          </div>
          
          <div ref="overviewChartRef" class="w-full h-[200px] z-10 -mt-4"></div>
          
          <div class="w-full grid grid-cols-2 gap-4 mt-2 pt-4 border-t border-gray-50 dark:border-gray-700/50 z-10">
            <div class="text-center bg-gray-50 dark:bg-gray-700/30 rounded-xl p-3">
              <p class="text-xs text-gray-500 dark:text-gray-400 mb-1">总文件数</p>
              <p class="font-bold text-gray-800 dark:text-gray-200">{{ overviewData.total_files.toLocaleString() }}</p>
            </div>
            <div class="text-center bg-gray-50 dark:bg-gray-700/30 rounded-xl p-3">
              <p class="text-xs text-gray-500 dark:text-gray-400 mb-1">最后扫描</p>
              <p class="font-bold text-gray-800 dark:text-gray-200 text-sm truncate" :title="formatDate(overviewData.scan_date)">{{ formatDateShort(overviewData.scan_date) }}</p>
            </div>
          </div>
        </div>

        <!-- Recoverable Space -->
        <div class="xl:col-span-2 bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 flex flex-col">
          <div class="flex items-center justify-between mb-6">
            <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <i class="mgc_magic_line text-amber-500 text-xl"></i>
              空间清理建议
            </h3>
            <span class="text-xs font-medium text-amber-600 bg-amber-50 dark:bg-amber-900/30 dark:text-amber-400 px-3 py-1 rounded-full">可回收预估</span>
          </div>
          
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1">
            <div 
              v-for="(item, key) in recoverableItems" 
              :key="key"
              class="group relative p-5 rounded-2xl border border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30 hover:bg-white dark:hover:bg-gray-750 hover:shadow-md hover:border-primary-200 dark:hover:border-primary-800/50 transition-all cursor-pointer overflow-hidden flex flex-col justify-between"
              @click="handleRecoverableClick(key)"
            >
              <div class="absolute right-0 top-0 h-full w-1.5 bg-transparent group-hover:bg-primary-500 transition-colors"></div>
              <div class="flex justify-between items-start mb-4">
                <div class="w-12 h-12 rounded-xl bg-white dark:bg-gray-700 shadow-sm flex items-center justify-center text-primary-500 group-hover:scale-110 group-hover:text-primary-600 transition-all">
                  <component :is="item.icon" class="w-6 h-6" />
                </div>
                <div class="text-right">
                  <p class="text-2xl font-bold text-gray-800 dark:text-gray-100 tracking-tight">{{ formatSize(item.size) }}</p>
                </div>
              </div>
              <div>
                <h4 class="font-bold text-gray-800 dark:text-gray-200 text-base">{{ item.label }}</h4>
                <p class="text-sm text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-1">
                  <i class="mgc_file_line"></i> {{ item.count }} 个文件可处理
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Distribution Block -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- By Type -->
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
          <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 mb-4 flex items-center gap-2">
            <i class="mgc_pie_chart_line text-blue-500 text-xl"></i> 文件类型分布
          </h3>
          <div ref="typeChartRef" class="w-full h-[280px]"></div>
        </div>
        <!-- By Device -->
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
          <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 mb-4 flex items-center gap-2">
            <i class="mgc_camera_line text-orange-500 text-xl"></i> 按拍摄设备分类
          </h3>
          <div ref="deviceChartRef" class="w-full h-[280px]"></div>
        </div>
      </div>
        <!-- By Time -->
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <i class="mgc_chart_bar_line text-indigo-500 text-xl"></i> 历史占用分布
            </h3>
            <div class="flex items-center gap-2">
              <!-- Date Range Selector -->
              <div v-if="timeGroup === 'day'" class="flex bg-gray-100 dark:bg-gray-700 p-1 rounded-lg">
                <button 
                  v-for="r in [{label: '30天', value: '30d'}, {label: '90天', value: '90d'}, {label: '半年', value: '180d'}]" 
                  :key="r.value"
                  class="px-2 py-1 text-xs font-medium rounded-md transition-colors"
                  :class="timeRange === r.value ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'"
                  @click="changeTimeRange(r.value)"
                >
                  {{ r.label }}
                </button>
              </div>

              <!-- Group By Selector -->
              <div class="flex bg-gray-100 dark:bg-gray-700 p-1 rounded-lg">
                <button 
                  v-for="g in ['day', 'month', 'year']" 
                  :key="g"
                  class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
                  :class="timeGroup === g ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'"
                  @click="changeTimeGroup(g)"
                >
                  {{ g === 'day' ? '按天' : g === 'month' ? '按月' : '按年' }}
                </button>
              </div>
            </div>
          </div>
          <div class="relative w-full h-[280px]">
            <div v-if="timeDistributionLoading" class="absolute inset-0 z-10 bg-white/50 dark:bg-gray-800/50 flex items-center justify-center">
              <i class="mgc_loading_4_line animate-spin text-2xl text-gray-400"></i>
            </div>
            <div ref="timeChartRef" class="w-full h-full"></div>
          </div>
        </div>

      <!-- Folder Treemap -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 mb-4 flex items-center gap-2">
          <i class="mgc_folder_2_line text-emerald-500 text-xl"></i> 文件夹占用比例
        </h3>
        <div ref="folderChartRef" class="w-full h-[360px]"></div>
      </div>

      <!-- 3. Top Large Files Block -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
        <h3 class="text-base font-bold text-gray-800 dark:text-gray-100 mb-4 flex items-center gap-2">
          <i class="mgc_layout_list_line text-rose-500 text-xl"></i> 空间占用 Top 20
        </h3>
        <div class="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-700">
          <table class="w-full text-sm text-left">
            <thead class="text-xs text-gray-500 uppercase bg-gray-50 dark:bg-gray-750 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
              <tr>
                <th scope="col" class="px-4 py-3">文件</th>
                <th scope="col" class="px-4 py-3">类型</th>
                <th scope="col" class="px-4 py-3">大小</th>
                <th scope="col" class="px-4 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(file, index) in topLargeFiles" :key="index" class="bg-white dark:bg-gray-800 border-b border-gray-50 dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                <td class="px-4 py-3 font-medium text-gray-900 dark:text-white max-w-[300px]">
                  <div class="flex items-center gap-3">
                    <img 
                      :src="`/api/medias/${file.id}/thumbnail?size=small`" 
                      class="w-10 h-10 object-cover rounded-lg cursor-pointer shrink-0 border border-gray-200 dark:border-gray-600 hover:opacity-80 transition-opacity"
                      @click="locateFile(file)"
                      alt="thumbnail"
                    />
                    <el-tooltip :content="file.path" placement="top" :show-after="300">
                      <span class="truncate cursor-default">{{ file.path }}</span>
                    </el-tooltip>
                  </div>
                </td>
                <td class="px-4 py-3 text-gray-500 dark:text-gray-400">
                  <span class="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded-md text-xs">{{ file.type }}</span>
                </td>
                <td class="px-4 py-3 text-primary-500 font-bold whitespace-nowrap">{{ formatSize(file.size) }}</td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <button @click="locateFile(file)" class="px-3 py-1.5 text-primary-600 bg-primary-50 hover:bg-primary-100 dark:text-primary-400 dark:bg-primary-900/30 dark:hover:bg-primary-900/50 rounded-lg mr-2 focus:outline-none transition-colors">查看</button>
                  <button @click="deleteFile(file)" class="px-3 py-1.5 text-red-600 bg-red-50 hover:bg-red-100 dark:text-red-400 dark:bg-red-900/30 dark:hover:bg-red-900/50 rounded-lg focus:outline-none transition-colors">删除</button>
                </td>
              </tr>
              <tr v-if="!topLargeFiles.length">
                <td colspan="4" class="px-4 py-8 text-center text-gray-500">暂无大文件记录</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    
    <ScreenshotCleanupDialog v-model="showScreenshotDialog" />
    
    <!-- Photo Lightbox for Locate -->
    <PhotoLightbox
        :image="currentLightboxImage"
        :has-prev="false"
        :has-next="false"
        :visible="lightbox.show"
        @close="lightbox.show = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, shallowRef, computed, reactive } from 'vue';
import { useRouter } from 'vue-router';
import * as echarts from 'echarts';
import { Copy, Image as ImageIcon, Smartphone, Video } from 'lucide-vue-next';
import { storageApi, type StorageOverview, type LargeFile } from '@/api/storage';
import { tasksApi } from '@/api/tasks';
import { ElMessage, ElMessageBox } from 'element-plus';
import ScreenshotCleanupDialog from './ScreenshotCleanupDialog.vue';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import type { AlbumImage } from '@/types/album';
import request from '@/utils/request';

const router = useRouter();
const loading = ref(false);
const isScanning = ref(false);

const overviewData = ref<any>(null);
const recoverableData = ref<any>(null);
const typeData = ref<any[]>([]);
const deviceData = ref<any[]>([]);
const folderData = ref<any[]>([]);
const topLargeFiles = ref<LargeFile[]>([]);

const showScreenshotDialog = ref(false);

const timeGroup = ref('month');
const timeRange = ref('30d');
const timeDistributionLoading = ref(false);

const changeTimeRange = async (range: string) => {
  timeRange.value = range;
  await fetchTimeDistribution();
};

const changeTimeGroup = async (group: string) => {
  timeGroup.value = group;
  await fetchTimeDistribution();
};

const fetchTimeDistribution = async () => {
  timeDistributionLoading.value = true;
  try {
    let startDate: string | undefined = undefined;
    let endDate: string | undefined = undefined;
    
    if (timeGroup.value === 'day') {
      const end = new Date();
      const start = new Date();
      if (timeRange.value === '30d') {
        start.setDate(end.getDate() - 30);
      } else if (timeRange.value === '90d') {
        start.setDate(end.getDate() - 90);
      } else if (timeRange.value === '180d') {
        start.setDate(end.getDate() - 180);
      }
      
      startDate = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
      endDate = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`;
    }

    const res = await storageApi.getTimeDistribution(timeGroup.value as any, startDate, endDate);
    renderTimeChart(res.data);
  } catch (e) {
    console.error(e);
  } finally {
    timeDistributionLoading.value = false;
  }
};

const overviewChartRef = shallowRef<HTMLElement | null>(null);
const typeChartRef = shallowRef<HTMLElement | null>(null);
const deviceChartRef = shallowRef<HTMLElement | null>(null);
const timeChartRef = shallowRef<HTMLElement | null>(null);
const folderChartRef = shallowRef<HTMLElement | null>(null);

let overviewChart: echarts.ECharts | null = null;
let typeChart: echarts.ECharts | null = null;
let deviceChart: echarts.ECharts | null = null;
let timeChart: echarts.ECharts | null = null;
let folderChart: echarts.ECharts | null = null;

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '从未扫描';
  return new Date(dateStr).toLocaleString();
};

const formatDateShort = (dateStr: string | null) => {
  if (!dateStr) return '从未扫描';
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}-${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
};

const recoverableItems = computed(() => {
  if (!recoverableData.value) return {};
  return {
    similar: { label: '相似照片', icon: Copy, size: recoverableData.value.similar?.size || 0, count: recoverableData.value.similar?.count || 0, route: '/toolbox/similar' },
    duplicate: { label: '完全重复', icon: Copy, size: recoverableData.value.duplicate?.size || 0, count: recoverableData.value.duplicate?.count || 0, route: '/toolbox/duplicate' },
    screenshot: { label: '截图与表情包', icon: Smartphone, size: recoverableData.value.screenshot?.size || 0, count: recoverableData.value.screenshot?.count || 0, action: 'screenshot' },
    video: { label: '大型视频', icon: Video, size: recoverableData.value.video?.size || 0, count: recoverableData.value.video?.count || 0, action: 'video' },
  };
});

const handleRecoverableClick = (key: string | number) => {
  const item = recoverableItems.value[key as keyof typeof recoverableItems.value];
  if (item.route) {
    router.push(item.route);
  } else if (item.action === 'screenshot') {
    showScreenshotDialog.value = true;
  } else if (item.action === 'video') {
    ElMessage.info('大型视频清理即将上线');
  }
};

const isCapacityWarning = computed(() => {
  if (!overviewData.value || !overviewData.value.disk_total_size) return false;
  const used = overviewData.value.disk_total_size - (overviewData.value.disk_free_size || 0);
  return (used / overviewData.value.disk_total_size) > 0.8;
});

const lightbox = reactive({
  show: false,
  file: null as LargeFile | null
});

const currentLightboxImage = computed((): AlbumImage | null => {
  if (!lightbox.file) return null;
  return {
    id: lightbox.file.id,
    url: `/api/medias/${lightbox.file.id}/file`,
    thumbnail: `/api/medias/${lightbox.file.id}/thumbnail?size=medium`,
    file_type: lightbox.file.type?.toLowerCase().includes('video') ? 'video' : 'image',
    filename: lightbox.file.filename || lightbox.file.path.split(/[\/\\]/).pop() || '',
    photo_time: '',
    size: lightbox.file.size,
    duration: ''
  };
});

const locateFile = (file: LargeFile) => {
  lightbox.file = file;
  lightbox.show = true;
};

const deleteFile = (file: LargeFile) => {
  ElMessageBox.confirm(
    `确定删除大文件 ${file.path.split(/[\/\\]/).pop()} 吗？此操作不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    }
  ).then(async () => {
    try {
      await request.delete('/api/photos/batch', {
        data: { photo_ids: [file.id] }
      });
      ElMessage.success('删除成功');
      // Optimistically remove from list
      topLargeFiles.value = topLargeFiles.value.filter(f => f.id !== file.id);
      fetchData(); // Optionally refresh data to update charts
    } catch (err) {
      console.error(err);
      ElMessage.error('删除失败');
    }
  }).catch(() => {});
};

const initCharts = () => {
  // Overview Chart (Ring)
  if (overviewChartRef.value && overviewData.value) {
    if (!overviewChart) overviewChart = echarts.init(overviewChartRef.value);
    
    const used = overviewData.value.total_size;
    const totalDisk = overviewData.value.disk_total_size || used;
    const freeDisk = overviewData.value.disk_free_size || 0;
    
    const data = [];
    if (totalDisk > used && freeDisk > 0) {
      data.push({ value: used, name: '相册占用', itemStyle: { color: '#3b82f6' } });
      data.push({ value: freeDisk, name: '磁盘剩余', itemStyle: { color: '#e5e7eb' } });
    } else {
      data.push({ value: used, name: '已用空间', itemStyle: { color: '#3b82f6' } });
    }

    overviewChart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => `${params.name}: ${formatSize(params.value)}`
      },
      series: [
        {
          type: 'pie',
          radius: ['65%', '90%'],
          avoidLabelOverlap: false,
          label: { show: false },
          labelLine: { show: false },
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          data: data
        }
      ]
    });
  }

  // Type Chart (Ring)
  if (typeChartRef.value && typeData.value.length > 0) {
    if (!typeChart) typeChart = echarts.init(typeChartRef.value);
    typeChart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => `${params.name}: ${formatSize(params.value)} (${params.percent}%)`
      },
      legend: { bottom: '0%', left: 'center' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          data: typeData.value.map(d => ({ value: d.size, name: d.name }))
        }
      ]
    });
  }

  // Device Chart (Ring/Pie)
  if (deviceChartRef.value && deviceData.value.length > 0) {
    if (!deviceChart) deviceChart = echarts.init(deviceChartRef.value);
    deviceChart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => `${params.name}: ${formatSize(params.value)} (${params.percent}%)`
      },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['40%', '50%'],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          data: deviceData.value.map(d => ({ value: d.size, name: d.name }))
        }
      ]
    });
  }
  
  // Folder Chart (Treemap)
  if (folderChartRef.value && folderData.value.length > 0) {
    if (!folderChart) folderChart = echarts.init(folderChartRef.value);
    folderChart.setOption({
      tooltip: {
        formatter: (info: any) => `${info.name}: ${formatSize(info.value)}`
      },
      series: [
        {
          type: 'treemap',
          width: '100%',
          height: '100%',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          data: folderData.value.map(d => ({ name: d.name, value: d.size }))
        }
      ]
    });
  }
};

const renderTimeChart = (data: any[]) => {
  if (!timeChartRef.value) return;
  
  // Create or clear chart
  if (!timeChart) {
    timeChart = echarts.init(timeChartRef.value);
  } else {
    timeChart.clear();
  }
  
  // Sort data chronologically (name is usually 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD')
  const sortedData = [...data].sort((a, b) => a.name.localeCompare(b.name));
  
  timeChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      formatter: (params: any) => {
        const val = params[0];
        return `${val.name}<br/>占用大小: ${formatSize(val.value)}`;
      }
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: sortedData.map(d => d.name),
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { 
        color: '#9ca3af',
        formatter: (value: string) => {
          // If YYYY-MM-DD, just show MM/DD
          if (value.length === 10 && value.includes('-')) {
            return value.substring(5).replace('-', '/');
          }
          return value;
        }
      }
    },
    yAxis: { 
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: '#f3f4f6' } },
      axisLabel: { formatter: (value: number) => formatSize(value), color: '#9ca3af' }
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: sortedData.map(d => d.size),
        itemStyle: { color: '#a855f7' }, // purple-500
        lineStyle: { width: 2, color: '#a855f7' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(168, 85, 247, 0.4)' }, // purple-500 light
            { offset: 1, color: 'rgba(168, 85, 247, 0.01)' }
          ])
        }
      }
    ]
  });
};

const triggerScan = async () => {
  await fetchData();
  ElMessage.success('已重新统计存储数据');
};

const fetchData = async () => {
  loading.value = true;
  try {
    const overviewRes = await storageApi.getOverview();
    overviewData.value = overviewRes.data;

    // Load others progressively
    storageApi.getStatsRecoverable().then(res => {
      recoverableData.value = res.data;
    });

    storageApi.getStatsByType().then(res => {
      typeData.value = res.data;
      nextTick(initCharts);
    });

    storageApi.getStatsByDevice().then(res => {
      deviceData.value = res.data;
      nextTick(initCharts);
    });

    storageApi.getStatsByFolder().then(res => {
      folderData.value = res.data;
      nextTick(initCharts);
    });

    storageApi.getTopLargeFiles().then(res => {
      topLargeFiles.value = res.data || [];
    });
    
    nextTick(() => {
      initCharts();
      fetchTimeDistribution();
    });
  } catch (error) {
    console.error(error);
    ElMessage.error('加载存储数据失败');
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchData();
  
  window.addEventListener('resize', () => {
    overviewChart?.resize();
    typeChart?.resize();
    deviceChart?.resize();
    timeChart?.resize();
    folderChart?.resize();
  });
});
</script>