<template>
  <div 
    :class="[isDarkMode ? 'dark' : '']"
    class="container mx-auto min-h-screen font-sans transition-colors duration-300 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200"
  >
    <TicketHeader
      v-model:searchQuery="searchQuery"
      @go-to-statistics="goToStatistics"
      @handle-export="handleExport"
      @open-ticket-modal="openTicketModal()"
      @handle-file-import="handleFileImport"
    />

    <main class="mx-auto px-4 py-4">
      <div class="flex flex-col xl:flex-row gap-6">
        <TicketStatsSidebar
          v-model:searchQuery="searchQuery"
          :unique-cities="uniqueCities"
          :total-duration="totalDuration"
          :total-distance="totalDistance"
          :unique-passengers="uniquePassengers"
          :selected-passenger="selectedPassenger"
          :loading="loading"
          :tickets="tickets"
          :stats-map="statsMap"
          @show-city-modal="showCityModal = true"
          @filter-by-passenger="filterByPassenger"
          @clear-passenger-filter="clearPassengerFilter"
        />

        <section class="flex-1 min-w-0">
          <TicketFilterBar
            v-model:filterType="filterType"
            v-model:sortType="sortType"
            v-model:viewMode="viewMode"
            :is-all-selected="isAllSelected"
            :is-indeterminate="isIndeterminate"
            :loading="loading"
            :selected-tickets="selectedTickets"
            :sort-options="sortOptions"
            @fetch-tickets="fetchTickets(true)"
            @change-sort-type="changeSortType"
            @toggle-select-all="toggleSelectAll"
            @batch-delete="batchDelete"
          />

          <TicketList
            :loading="loading"
            :error="error"
            :filtered-tickets="filteredTickets"
            :view-mode="viewMode"
            :selected-tickets="selectedTickets"
            :current-theme="currentTheme"
            @fetch-tickets="fetchTickets()"
            @toggle-select="toggleSelect"
            @edit="openTicketModal"
            @delete="confirmDelete"
            @view-paper="openPaperTicketModal"
            @view-photo="openPhotoLightbox"
            @open-ticket-modal="openTicketModal()"
          />
        </section>
      </div>
    </main>

    <TicketFormModal
      :is-open="isModalOpen"
      :is-editing="isEditing"
      :initial-data="currentTicket"
      :current-theme="currentTheme"
      :saving="saving"
      @save="handleModalSave"
      @cancel="closeModal"
    />

    <FlightTicketFormModal
      :is-open="isFlightModalOpen"
      :is-editing="isEditing"
      :initial-data="currentFlightTicket"
      :current-theme="currentTheme"
      :saving="saving"
      @save="handleFlightModalSave"
      @cancel="closeFlightModal"
    />

    <TicketTypeSelectorModal
      v-model:show="showTypeSelector"
      @select-type="selectTicketType"
    />

    <TicketCityStatsModal
      v-model:show="showCityModal"
      :unique-cities="uniqueCities"
      @filter-by-city="filterByCity"
    />

    <TicketPaperModal
      v-model:show="isPaperModalOpen"
      v-model:selectedStyle="selectedPaperStyle"
      :ticket="currentPaperTicket"
      @export="exportPaperTicket(currentPaperTicket!)"
    />

    <TicketExportModal
      v-model:show="isExportModalOpen"
      v-model:selectedStyle="selectedPaperStyle"
      :has-selected-tickets="selectedTickets.length > 0"
      :is-batch-exporting="isBatchExporting"
      :export-progress="exportProgress"
      @execute="executeExport"
    />

    <!-- 隐藏的导出专用组件 -->
    <div style="position: absolute; left: -9999px; top: -9999px; overflow: hidden;">
      <TrainTicket
        v-if="currentPaperTicket"
        ref="exportTicketRef"
        :ticket="currentPaperTicket"
        :ticket_style="selectedPaperStyle"
        style="width: 856px; height: 540px;"
      />
    </div>

    <!-- 查看照片 -->
    <PhotoLightbox
      :visible="isPhotoLightboxVisible"
      :image="currentPhoto"
      @close="closePhotoLightbox"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { storeToRefs } from 'pinia';
import { useTicketStore } from '@/stores/ticketStore';

// 导入自定义类型、服务和组件
import type {
  TicketFrontend,
  TicketFormData,
  FlightTicketFormData,
  SortType,
  TicketBackend,
  FlightTicketBackend
} from '@/types/ticket';
import { ticketService } from '@/api/ticketService';
import { formatTicketToFrontend, formatFormToBackend, debounce } from '@/utils/ticketFormatters';
import { injectTheme } from '@/composables/useTheme';
import { toPng } from 'html-to-image';

// 组件
import TicketHeader from './components/TicketHeader.vue';
import TicketStatsSidebar from './components/TicketStatsSidebar.vue';
import TicketFilterBar from './components/TicketFilterBar.vue';
import TicketList from './components/TicketList.vue';
import TicketTypeSelectorModal from './components/TicketTypeSelectorModal.vue';
import TicketCityStatsModal from './components/TicketCityStatsModal.vue';
import TicketPaperModal from './components/TicketPaperModal.vue';
import TicketExportModal from './components/TicketExportModal.vue';
import TicketFormModal from '@/components/TicketFormModal.vue';
import FlightTicketFormModal from '@/components/FlightTicketFormModal.vue';
import TrainTicket from '@/components/TrainTicket.vue';
import PhotoLightbox from '@/components/PhotoLightbox.vue';
import type { AlbumImage } from '@/types/album';

const { isDarkMode, currentTheme } = injectTheme();
const ticketStore = useTicketStore();
const router = useRouter();

// --- 状态定义 ---
// 使用 storeToRefs 保持响应性
const {
  tickets,
  searchQuery,
  filterType,
  sortType,
  selectedPassenger,
  viewMode,
  loading,
  error,
  statsMap
} = storeToRefs(ticketStore);

const selectedTickets = ref<(number | string)[]>([]);
const isModalOpen = ref(false);
const isFlightModalOpen = ref(false);
const isPaperModalOpen = ref(false);
// paperTicketRef is now inside the modal component, but we don't access it from here anymore
// const paperTicketRef = ref<any>(null); 
const exportTicketRef = ref<any>(null);
const currentPaperTicket = ref<TicketFrontend | null>(null);
const selectedPaperStyle = ref<'red' | 'blue'>('blue');
const isBatchExporting = ref(false);
const exportProgress = ref(0);
const isExportModalOpen = ref(false);
const showTypeSelector = ref(false);
const isEditing = ref(false);
const showCityModal = ref(false);
const saving = ref(false);

// 初始编辑对象，使用 Partial 或特定类型
const currentTicket = ref<Partial<TicketFormData>>({});
const currentFlightTicket = ref<Partial<FlightTicketFormData>>({});

const isPhotoLightboxVisible = ref(false);
const currentPhoto = ref<AlbumImage | null>(null);

// --- 统计与导入导出 ---
const goToStatistics = () => {
  router.push('/statistics');
};

const handleExport = () => {
  selectedPaperStyle.value = 'blue'; // 默认自动识别
  isExportModalOpen.value = true;
};

const executeExport = async (format: 'json' | 'csv' | 'png') => {
  if (format === 'json') {
    ticketStore.exportTickets('json');
    isExportModalOpen.value = false;
  } else if (format === 'csv') {
    ticketStore.exportTickets('csv');
    isExportModalOpen.value = false;
  } else if (format === 'png') {
    if (selectedTickets.value.length === 0) {
      ElMessage.warning('请先选择要导出的车票');
      return;
    }
    await batchExportPaperTickets();
    isExportModalOpen.value = false;
  }
};

const handleFileImport = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    const file = target.files[0];
    try {
      loading.value = true;
      const result = await ticketStore.importTickets(file);
      ElMessage.success(`导入成功: ${result.success} 条记录, 更新 ${result.details?.updated || 0} 条`);
      await fetchTickets(true);
    } catch (err: any) {
      ElMessage.error(err.message || '导入失败');
    } finally {
      loading.value = false;
      target.value = ''; // Reset input
    }
  }
};

// 监听车票变化，自动更新统计数据
watch(tickets, () => {
  ticketStore.fetchAndCacheStats();
}, { deep: true });

// 排序选项配置
const sortOptions: { label: string; value: SortType }[] = [
  { label: '日期', value: 'date' },
  { label: '里程', value: 'distance' },
  { label: '时长', value: 'duration' },
  { label: '票价', value: 'price' }
];

// --- 搜索防抖 ---
const debouncedFetchTickets = debounce(() => {
  fetchTickets();
}, 500);

// 这个其实在 TicketHeader 里被触发，更新了 searchQuery，然后 watch searchQuery 触发 debouncedFetchTickets？
// 不，searchQuery 是 v-model 绑定的。
// store 中的 searchQuery 变化时，我们需要触发搜索吗？
// 原来的代码是 handleSearchInput 调用 debouncedFetchTickets。
// 现在的 TicketHeader emit update:searchQuery。
// 当 searchQuery 变化时，我们需要监听它。
watch(searchQuery, () => {
  debouncedFetchTickets();
});

// --- 生命周期 ---
onMounted(() => {
  // 组件加载时获取数据（会自动检查缓存）
  fetchTickets();
});

onUnmounted(() => {
  debouncedFetchTickets.cancel?.();
  ticketStore.clearCache();
});

// --- 计算属性 ---

// 转换后的前端数据列表
const frontendTickets = computed<TicketFrontend[]>(() => {
  return tickets.value.map(formatTicketToFrontend);
});

const filteredTickets = computed<TicketFrontend[]>(() => {
  let res = [...frontendTickets.value];
  // 1. 本地搜索筛选
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    res = res.filter(t => 
      t.trainCode.toLowerCase().includes(q) || 
      t.from.toLowerCase().includes(q) || 
      t.to.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q)
    );
  }

  // 2. 列车类型筛选
  if (filterType.value !== 'all') {
    res = res.filter(t => {
      if (filterType.value === 'flight') {
        return t.type === 'flight';
      }
      
      // 如果选的是火车相关 (highspeed/normal)，排除飞机
      if (t.type === 'flight') return false;

      const firstChar = t.trainCode.charAt(0).toUpperCase();
      const isHighSpeed = ['G', 'D', 'C'].includes(firstChar);
      return filterType.value === 'highspeed' ? isHighSpeed : !isHighSpeed;
    });
  }

  // 3. 乘车人筛选 (本地)
  if (selectedPassenger.value) {
    res = res.filter(t => t.name === selectedPassenger.value);
  }

  // 4. 多维度排序
  return res.sort((a, b) => {
    switch (sortType.value) {
      case 'date':
        return new Date(b.dateTime).getTime() - new Date(a.dateTime).getTime();
      case 'distance':
        return b.distance - a.distance;
      case 'duration':
        return b.totalRunningTime - a.totalRunningTime;
      case 'price':
        return b.price - a.price;
      default:
        return 0;
    }
  });
});

const uniqueCities = computed(() => {
  const cities = new Set<string>();
  tickets.value.forEach(t => {
    if (t.type === 'flight') {
      const flight = t as FlightTicketBackend;
      cities.add(flight.departure_city);
      cities.add(flight.arrival_city);
    } else {
      const train = t as TicketBackend;
      cities.add(train.departure_station);
      cities.add(train.arrival_station);
    }
  });
  return Array.from(cities).sort();
});

const uniquePassengers = computed(() => {
  const passengers = new Set<string>();
  tickets.value.forEach(t => {
    if (t.name) passengers.add(t.name);
  });
  return Array.from(passengers).sort();
});

const totalDistance = computed(() => {
  // 优先使用 Store 中的 statsMap (仅火车票有)
  let sum = 0;
  for (const t of tickets.value) {
    if (t.type === 'flight') {
        // 飞机票直接累加 flight.total_mileage
        const flight = t as FlightTicketBackend;
        sum += Number(flight.total_mileage || 0);
    } else {
        // 火车票优先取 statsMap，否则取 ticket.total_mileage
        if (t.id && statsMap.value[t.id]) {
          sum += statsMap.value[t.id].distance_km;
        } else {
          sum += (t.total_mileage || 0);
        }
    }
  }
  return Math.round(sum);
});

const totalDuration = computed(() => {
  let totalMinutes = 0;
  for (const t of tickets.value) {
    if (t.id && statsMap.value[t.id]) {
      totalMinutes += statsMap.value[t.id].duration_minutes;
    } else {
      totalMinutes += (t.total_running_time || 0);
    }
  }
  
  return {
    hours: Math.floor(totalMinutes / 60),
    minutes: totalMinutes % 60
  };
});

// --- 全选逻辑 ---
const isAllSelected = computed({
  get: () => {
    return filteredTickets.value.length > 0 && selectedTickets.value.length === filteredTickets.value.length;
  },
  set: (val) => {
    // 这里的 set 其实不会被直接触发，因为我们用 @change 处理了
  }
});

const isIndeterminate = computed(() => {
  return selectedTickets.value.length > 0 && selectedTickets.value.length < filteredTickets.value.length;
});

const toggleSelectAll = (val: boolean | string | number) => {
  if (val) {
    selectedTickets.value = filteredTickets.value.map(t => t.id);
  } else {
    selectedTickets.value = [];
  }
};

// --- API 方法 ---

async function fetchTickets(force = false) {
  await ticketStore.fetchTickets(force);
}

const changeSortType = (type: SortType) => {
  sortType.value = type;
};

const filterByPassenger = (passenger: string) => {
  selectedPassenger.value = passenger;
};

const clearPassengerFilter = () => {
  selectedPassenger.value = '';
};

const filterByCity = (city: string) => {
  searchQuery.value = city;
  showCityModal.value = false;
};

// --- 事件处理 ---

const openTicketModal = (ticket: TicketFrontend | null = null) => {
  console.log(ticket);
  if (ticket?.type?.toLowerCase() === 'train') {
    isModalOpen.value = true;
    isEditing.value = true;
    // 需要把 Frontend 数据转回 FormData 格式供表单使用
    currentTicket.value = {
        id: ticket.id,
        from: ticket.from,
        to: ticket.to,
        train_code: ticket.trainCode,
        name: ticket.name,
        dateTime: ticket.dateTime,
        carriage: ticket.carriage,
        seatNumber: ticket.seatNumber,
        berthType: ticket.berthType,
        price: ticket.price,
        seatType: ticket.seatType,
        discountType: ticket.discountType,
        totalRunningTime: ticket.totalRunningTime,
        distance: ticket.distance,
        comments: ticket.comments
    };
  } else if (ticket?.type?.toLowerCase() === 'flight') {
    isFlightModalOpen.value = true;
    isEditing.value = true;
    // 需要把 Frontend 数据转回 FormData 格式供表单使用
    currentFlightTicket.value = {
        id: ticket.id,
        flight_code: ticket.trainCode,
        departure_city: ticket.from,
        arrival_city: ticket.to,
        date_time: ticket.dateTime,
        price: ticket.price,
        name: ticket.name,
        total_running_time: ticket.totalRunningTime,
        total_mileage: ticket.distance,
        comments: ticket.comments
    };
  }else {
    // 新增模式：显示类型选择器
    showTypeSelector.value = true;
  }
};

const selectTicketType = (type: 'train' | 'flight') => {
  showTypeSelector.value = false;
  isEditing.value = false;
  if (type === 'train') {
    currentTicket.value = {};
    isModalOpen.value = true;
  } else {
    currentFlightTicket.value = {};
    isFlightModalOpen.value = true;
  }
};

const closeFlightModal = () => {
  isFlightModalOpen.value = false;
  setTimeout(() => {
    currentFlightTicket.value = {};
  }, 300);
};

const handleFlightModalSave = async (formData: FlightTicketFormData) => {
  saving.value = true;
  try {
    const backendData = {
      ...formData,
      id: formData.id || undefined,
      date_time: formData.date_time ? new Date(formData.date_time).toISOString() : new Date().toISOString()
    };
    
    if (isEditing.value && formData.id) {
       // await ticketService.updateFlightTicket(formData.id, backendData);
    } else {
       await ticketService.createFlightTicket(backendData);
    }

    await fetchTickets(true);
    closeFlightModal();
    ElMessage.success(isEditing.value ? '更新成功' : '新增成功');
  } catch (err: any) {
    ElMessage.error(err.message || '保存失败');
    console.error('Save flight ticket error:', err);
  } finally {
    saving.value = false;
  }
};

const openPaperTicketModal = (ticket: TicketFrontend) => {
  currentPaperTicket.value = ticket;
  const isHighSpeed = ['G', 'D', 'C'].includes(ticket.trainCode.charAt(0).toUpperCase());
  isPaperModalOpen.value = true;
};

const openPhotoLightbox = (ticket: TicketFrontend) => {
  if (!ticket.photo_id) return;
  currentPhoto.value = {
    id: ticket.photo_id,
    url: `/api/medias/${ticket.photo_id}/file`,
    thumbnail: `/api/medias/${ticket.photo_id}/thumbnail`,
    preview: `/api/medias/${ticket.photo_id}/thumbnail?size=medium`,
    srcset: '',
    timestamp: new Date(ticket.dateTime).getTime(),
    albumIds: [],
    file_type: 'image',
    filename: ticket.photo_id,
  };
  isPhotoLightboxVisible.value = true;
};

const closePhotoLightbox = () => {
  isPhotoLightboxVisible.value = false;
  currentPhoto.value = null;
};

const exportPaperTicket = async (ticket: TicketFrontend) => {
  // 使用隐藏的导出专用组件
  if (!exportTicketRef.value) return;
  
  try {
    exportTicketRef.value.exporting = true;
    await new Promise(resolve => setTimeout(resolve, 100));
    
    const element = exportTicketRef.value.wrapper;
    if (!element) throw new Error('未找到票据元素');
    
    const dataUrl = await toPng(element, {
      quality: 1,
      pixelRatio: 2,
      backgroundColor: '#fff',
      width: 856,
      height: 540,
    });
    
    const link = document.createElement('a');
    link.download = `火车票_${ticket.from}_${ticket.to}_${ticket.trainCode}_${ticket.date}.png`;
    link.href = dataUrl;
    link.click();
    
    ElMessage.success('导出成功');
  } catch (err) {
    console.error('Export error:', err);
    ElMessage.error('导出失败');
  } finally {
    if (exportTicketRef.value) {
      exportTicketRef.value.exporting = false;
    }
  }
};

const batchExportPaperTickets = async () => {
  if (selectedTickets.value.length === 0) return;
  
  const ticketsToExport = frontendTickets.value.filter(t => 
    selectedTickets.value.includes(t.id) && t.type === 'train'
  );
  
  if (ticketsToExport.length === 0) {
    ElMessage.warning('选中的票据中没有火车票');
    return;
  }
  
  isBatchExporting.value = true;
  exportProgress.value = 0;
  
  try {
    for (let i = 0; i < ticketsToExport.length; i++) {
      const ticket = ticketsToExport[i];
      currentPaperTicket.value = ticket;
      
      await new Promise(resolve => setTimeout(resolve, 300));
      
      if (exportTicketRef.value) {
        exportTicketRef.value.exporting = true;
        await new Promise(resolve => setTimeout(resolve, 100));
        
        const element = exportTicketRef.value.wrapper;
        if (element) {
          const dataUrl = await toPng(element, {
            quality: 0.9,
            pixelRatio: 2,
            backgroundColor: '#fff',
            width: 856,
            height: 540,
          });
          
          const link = document.createElement('a');
          link.download = `火车票_${ticket.from}_${ticket.to}_${ticket.trainCode}_${ticket.date}.png`;
          link.href = dataUrl;
          link.click();
        }
        exportTicketRef.value.exporting = false;
      }
      
      exportProgress.value = Math.round(((i + 1) / ticketsToExport.length) * 100);
    }
    
    ElMessage.success(`批量导出完成，共 ${ticketsToExport.length} 张`);
  } catch (err) {
    console.error('Batch export error:', err);
    ElMessage.error('批量导出失败');
  } finally {
    isBatchExporting.value = false;
    currentPaperTicket.value = null;
  }
};

const closeModal = () => {
  isModalOpen.value = false;
  setTimeout(() => {
    currentTicket.value = {};
  }, 300);
};

const handleModalSave = async (formData: TicketFormData) => {
  saving.value = true;
  try {
    const backendData = formatFormToBackend(formData);
    
    if (isEditing.value && formData.id) {
      await ticketService.updateTicket(formData.id, backendData);
    } else {
      await ticketService.createTicket(backendData);
    }
    await fetchTickets(true);
    closeModal();
    ElMessage.success(isEditing.value ? '更新成功' : '新增成功');
  } catch (err: any) {
    ElMessage.error(err.message || '保存失败');
    console.error('Save ticket error:', err);
  } finally {
    saving.value = false;
  }
};

const toggleSelect = (id: number | string) => {
  if (selectedTickets.value.includes(id)) {
    selectedTickets.value = selectedTickets.value.filter(item => item !== id);
  } else {
    selectedTickets.value.push(id);
  }
};

const confirmDelete = async (id: number | string) => {
  const ticket = frontendTickets.value.find(t => t.id === id);
  if (!ticket) return;
  // 使用弹窗组件确认删除，不要用原生弹窗
  if (await ElMessageBox.confirm('确定要删除这张车票吗？删除后不可恢复')) {
    try {
      if (ticket.type === 'flight') {
         await ticketService.deleteFlightTicket(id as string);
      } else {
         await ticketService.deleteTicket(id);
      }
      
      ticketStore.removeLocalTickets([id]);
      selectedTickets.value = selectedTickets.value.filter(tid => tid !== id);
      ElMessage.success('删除成功');
    } catch (err: any) {
      ElMessage.error(err.message || '删除失败');
    }
  }
};

const batchDelete = async () => {
  if (selectedTickets.value.length === 0) return;
  if (await ElMessageBox.confirm(`确定删除选中的 ${selectedTickets.value.length} 张车票吗？删除后不可恢复`)) {
    try {
      const promises = selectedTickets.value.map(id => {
         const ticket = frontendTickets.value.find(t => t.id === id);
         if (ticket && ticket.type === 'flight') {
             return ticketService.deleteFlightTicket(id as string);
         } else {
             return ticketService.deleteTicket(id);
         }
      });
      
      await Promise.all(promises);
      
      ticketStore.removeLocalTickets(selectedTickets.value);
      selectedTickets.value = [];
      ElMessage.success('批量删除成功');
    } catch (err: any) {
      ElMessage.error(err.message || '批量删除失败');
    }
  }
};
</script>

<style>
/* 过渡动画 */
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
</style>
