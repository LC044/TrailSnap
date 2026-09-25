import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useStorage } from '@vueuse/core';
import type { TicketBackend, TicketQueryParams, UniversalTicket } from '@/types/ticket';
import { ticketService } from '@/api/ticketService';
import { railwayService, type TicketStats, type TicketItem } from '@/api/railway';

export const useTicketStore = defineStore('ticket', () => {
  // --- State Persistence (LocalStorage) ---
  // 视图模式
  const viewMode = useStorage<'timeline' | 'grid'>('ticket-view-mode', 'timeline');
  // 筛选状态
  const filterType = useStorage<'all' | 'highspeed' | 'normal' | 'flight'>('ticket-filter-type', 'all');
  const sortType = useStorage<'date' | 'distance' | 'duration' | 'price'>('ticket-sort-type', 'date');
  const selectedPassenger = useStorage<string>('ticket-selected-passenger', '');

  // 搜索状态
  const searchQuery = useStorage<string>('ticket-search-query', '');
  
  // 统计数据缓存 (ID -> Stats)
  const statsMap = useStorage<Record<string, TicketStats>>('ticket-stats-map', {});

  // --- Data Cache (In-Memory) ---
  const tickets = ref<UniversalTicket[]>([]);
  const lastFetchTime = ref<number>(0);
  const loading = ref(false);
  const error = ref('');

  // 缓存配置
  const CACHE_DURATION = 5 * 60 * 1000; // 5分钟缓存

  // --- Actions ---

  /**
   * 批量获取统计数据并更新缓存
   */
  async function fetchAndCacheStats() {
    if (tickets.value.length === 0) return;

    try {
      // 仅为火车票获取统计数据
      const trainItems: TicketItem[] = tickets.value
        .filter(t => !t.type || t.type === 'train')
        .map(t => {
           const trainTicket = t as TicketBackend;
           return {
            id: String(trainTicket.id),
            train_code: trainTicket.train_code,
            departure_station: trainTicket.departure_station,
            arrival_station: trainTicket.arrival_station,
            date_time: trainTicket.date_time
          };
        });

      if (trainItems.length === 0) return;

      const res = await railwayService.getBatchStats(trainItems);
      if (res.code === 200 && res.data) {
        // 更新缓存
        const newMap = { ...statsMap.value };
        res.data.forEach(stat => {
          if (stat.id) {
            newMap[stat.id] = stat;
          }
        });
        statsMap.value = newMap;
      }
    } catch (err) {
      console.error('Failed to fetch batch stats:', err);
      // 不抛出错误，以免影响主流程，仅记录日志
    }
  }

  /**
   * 获取车票数据
   * @param force 是否强制刷新
   */
  async function fetchTickets(force = false, startDate?: string | null, endDate?: string | null) {
    // 检查缓存是否有效 (如果带了时间筛选条件，强制刷新)
    const now = Date.now();
    const isCacheValid = now - lastFetchTime.value < CACHE_DURATION;

    if (!force && !startDate && !endDate && isCacheValid && tickets.value.length > 0) {
      return;
    }

    loading.value = true;
    error.value = '';

    try {
      const params: TicketQueryParams = {
        skip: 0,
        limit: 1000
      };

      if (startDate !== null) {
        params.start_date = startDate;
      }
      if (endDate !== null) {
        params.end_date = endDate;
      }

      // 并行请求火车票和飞机票
      const [trainRes, flightRes] = await Promise.allSettled([
        ticketService.getTickets(params),
        ticketService.getFlightTickets(params)
      ]);

      let allTickets: UniversalTicket[] = [];

      // 处理火车票结果
      if (trainRes.status === 'fulfilled') {
        // 显式标记类型
        const trainItems = (trainRes.value.items || []).map(t => ({ ...t, type: 'train' as const }));
        allTickets = allTickets.concat(trainItems);
      } else {
        console.error('Fetch train tickets failed:', trainRes.reason);
      }

      // 处理飞机票结果
      if (flightRes.status === 'fulfilled') {
        const flightItems = (flightRes.value.items || []).map(t => ({ ...t, type: 'flight' as const }));
        allTickets = allTickets.concat(flightItems);
      } else {
        console.error('Fetch flight tickets failed:', flightRes.reason);
      }

      // 按时间倒序合并
      tickets.value = allTickets.sort((a, b) => {
        return new Date(b.date_time).getTime() - new Date(a.date_time).getTime();
      });

      lastFetchTime.value = now;
      
    } catch (err: any) {
      error.value = err.response?.data?.detail || '获取车票失败，请重试';
      console.error('Fetch tickets error:', err);
      throw err;
    } finally {
      loading.value = false;
    }
  }

  /**
   * 手动刷新数据
   */
  async function refreshData(startDate?: string, endDate?: string) {
    await fetchTickets(true, startDate, endDate);
  }

  /**
   * 重置所有筛选和搜索状态
   */
  function resetFilters() {
    searchQuery.value = '';
    filterType.value = 'all';
    selectedPassenger.value = '';
    // sortType.value = 'date'; // 排序通常不需要重置，或者看需求
  }

  /**
   * 更新单条车票数据 (用于编辑/新增后的本地更新，避免立即全量刷新)
   * 当然也可以选择直接调用 refreshData()
   */
  function updateLocalTicket(ticket: UniversalTicket) {
    const index = tickets.value.findIndex(t => t.id === ticket.id);
    if (index !== -1) {
      tickets.value[index] = ticket;
    } else {
      tickets.value.unshift(ticket);
    }
    // 数据变更，更新缓存时间或保持不变？
    // 如果手动修改了数据，建议视为最新
    lastFetchTime.value = Date.now();
  }

  function removeLocalTickets(ids: (number | string)[]) {
    tickets.value = tickets.value.filter(t => !ids.includes(t.id));
    lastFetchTime.value = Date.now();
  }

  async function exportTickets(format: 'json' | 'csv' = 'json') {
    await ticketService.exportTickets(format);
  }

  async function importTickets(file: File) {
    return await ticketService.importTickets(file);
  }

  function clearCache() {
    statsMap.value = {};
  }

  return {
    // State
    viewMode,
    filterType,
    sortType,
    selectedPassenger,
    searchQuery,
    tickets,
    loading,
    error,
    lastFetchTime,
    statsMap,
    
    // Actions
    fetchTickets,
    refreshData,
    resetFilters,
    updateLocalTicket,
    removeLocalTickets,
    fetchAndCacheStats,
    exportTickets,
    importTickets,
    clearCache
  };
});
