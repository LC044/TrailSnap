// src/stores/photoStore.ts
// 定义照片相关的状态管理

import { defineStore } from 'pinia'
import { ref, reactive, watch } from 'vue'
import { albumService } from '@/api/album'
import searchService, { type TextSearchRequest } from '@/api/search'
import type { Photo, TimelineStats, AlbumImage, TimelineItem, FilterOptions, FilterState } from '@/types/album'
import { toServerUrl } from '@/config/server'

// --- 缓存工具 ---
const CACHE_PREFIX = 'trailsnap:';
const CACHE_TTL = 24 * 60 * 60 * 1000; // 24小时

interface CacheRecord<T> {
  timestamp: number;
  data: T;
}

const getLocalCache = <T>(key: string): T | null => {
  try {
    const json = localStorage.getItem(CACHE_PREFIX + key);
    if (!json) return null;
    const record = JSON.parse(json) as CacheRecord<T>;
    if (Date.now() - record.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_PREFIX + key);
      return null;
    }
    return record.data;
  } catch (e) {
    return null;
  }
}

const setLocalCache = <T>(key: string, data: T) => {
  try {
    const record: CacheRecord<T> = {
      timestamp: Date.now(),
      data
    };
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(record));
  } catch (e) {
    // QuotaExceededError
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
       try {
           // 清理所有相关缓存
           Object.keys(localStorage).forEach(k => {
               if (k.startsWith(CACHE_PREFIX)) localStorage.removeItem(k);
           });
           // 重试一次
           const recordToStore: CacheRecord<T> = {
               timestamp: Date.now(),
               data
           };
           localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(recordToStore));
       } catch (retryErr) {
           console.warn('缓存写入失败', retryErr);
       }
    }
  }
}

const formatDuration = (duration: number | null) => {
  if (!duration) return '00:00';
  const hours = Math.floor(duration / 3600);
  const minutes = Math.floor((duration % 3600) / 60);
  const seconds = Math.floor(duration % 60);
  return `${hours > 0 ? `${hours}:` : ''}${minutes}:${seconds < 10 ? `0${seconds}` : seconds}`;
}

export const mapPhotoToImage = (photo: Photo): AlbumImage => {
    // 新 API 在 url 和 thumbnail_url 字段中返回相对地址
    const url = toServerUrl(`/api/medias/${photo.id}/file`);
    const thumbnail = toServerUrl(`/api/medias/${photo.id}/thumbnail`);
    // const thumbnail = `https://picsum.photos/seed/${photo.id}/400/600`
    const preview = toServerUrl(`/api/medias/${photo.id}/thumbnail?size=medium`);

    // 优先使用 photo_time，其次 upload_time，最后取当前时间
    let timestamp = Date.now();
    let hasPhotoTime = false;
    if (photo.photo_time) {
        timestamp = new Date(photo.photo_time).getTime();
        hasPhotoTime = true;
    } else if (photo.upload_time) {
        timestamp = new Date(photo.upload_time).getTime();
    }

    // 尝试从 location 或 tags 中解析城市
    let city = 'Unknown';

    // Construct live photo video URL if applicable
    let live_photo_video_url = undefined;
    if (photo.file_type === 'live_photo') {
        live_photo_video_url = toServerUrl(`/api/medias/${photo.id}/video`);
    }

    return {
      id: photo.id,
      url,
      thumbnail,
      preview,
      srcset: '', // 暂不分发多尺寸，后端按需动态处理
      timestamp,
      hasPhotoTime,
      albumIds: photo.album_ids || [],
      width: photo.width || 300,
      height: photo.height || 300,
      size: photo.size || 0,
      filename: photo.filename || '',
      file_type: photo.file_type || 'image',
      duration: formatDuration(photo.duration ?? null) || '00:00',
      live_photo_video_url,
      has_live_video: live_photo_video_url !== undefined,
      file_path: photo.file_path || '',
      deleted_at: photo.deleted_at
    }
  }

export const photoStoreSetup = () => {
  // --- 状态 ---
  const images = ref<AlbumImage[]>([])
  const loading = ref(false)
  const hasMore = ref(true)
  const error = ref<string | null>(null)
  const isSearchMode = ref(false)
  const currentContext = ref<{ type: 'all' | 'album' | 'search', id?: string }>({ type: 'all' })
  const timelineStats = ref<TimelineStats>()
  const availableFilters = ref<FilterOptions | null>(null);
  // 文件夹浏览模式：设置后，timeline 统计与按月加载都会自动按该文件夹过滤（Issue #78）
  const folderPath = ref<string | null>(null);
  // 仅看「本层直属」照片（不含子目录）
  const folderDirect = ref<boolean>(false);
  // 瞬时省份过滤（不持久化）：拼图手动选择器默认只展示当前省份照片，
  // 与 selectedFilters 解耦，避免污染全局筛选缓存。置空则不过滤。
  const provinceFilter = ref<string | null>(null);
  const selectedFilters = reactive<FilterState>({
      years: [],
      cities: [],
      makes: [],
      models: [],
      image_types: [],
      file_types: []
  });

  // 筛选条件持久化到 trailsnap:selectedFilters，刷新/重开后恢复（P1 2.1.9 回归用例依赖）。
  {
      const FILTER_CACHE_KEY = 'selectedFilters'
      const cached = getLocalCache<FilterState>(FILTER_CACHE_KEY)
      if (cached) {
          Object.assign(selectedFilters, cached)
      }
      watch(selectedFilters, (val) => {
          setLocalCache(FILTER_CACHE_KEY, { ...val })
      }, { deep: true })
  }

  // --- 辅助函数 ---
  // mapPhotoToImage 已在文件顶部导出（避免重复实现导致列表/详情数据不一致）

  // --- 动作 ---
  const fetchAvailableFilters = async () => {
      try {
          availableFilters.value = await albumService.getFilterOptions();
      } catch (e) {
          console.error("Failed to fetch filter options", e);
      }
  }

  const cleanFilters = () => {
      const filters = { ...selectedFilters } as any;
      for (const key in filters) {
          if (Array.isArray(filters[key]) && filters[key].length === 0) {
              delete filters[key];
          }
      }
      // 文件夹浏览模式下注入 folder 过滤条件
      if (folderPath.value !== null) {
          filters.folder = folderPath.value;
      }
      if (folderDirect.value) {
          filters.folder_direct = true;
      }
      // 瞬时省份过滤（拼图手动选择器用），后端 /api/photos 已支持 province 参数
      if (provinceFilter.value) {
          filters.province = provinceFilter.value;
      }
      return filters;
  }

  const fetchTimelineStats = async (albumId?: string) => {
    try {
      timelineStats.value = undefined
      const filters = cleanFilters();
      const stats = await albumService.getTimelineStats(albumId, filters)
      timelineStats.value = stats
    } catch (e) {
      console.error("获取时间轴统计失败", e)
    }
  }

  const activeOffsets = new Set<number>();
  const loadedDates = reactive(new Set<string>());
  const photoOffsetMap = reactive(new Map<number, AlbumImage>());

  // 追踪活跃请求以支持取消
  let currentRequestId = 0;
  const activeRequests = new Map<number, AbortController>();

  const getOffsetRangeForMonth = (year: number, month: number): { start: number, count: number } | null => {
      if (!timelineStats.value?.timeline) return null;
      console.log('timelineStats', timelineStats.value)
      // Sort timeline to match gallery order
      const sortedTimeline = [...timelineStats.value.timeline].sort((a, b) => {
          if (a.year !== b.year) return b.year - a.year;
          if (a.month !== b.month) return b.month - a.month;
          return b.day - a.day;
      });

      let currentOffset = 0;
      let startOffset = -1;
      let totalCount = 0;

      for (const item of sortedTimeline) {
          if (item.year === year && item.month === month) {
              if (startOffset === -1) startOffset = currentOffset;
              totalCount += item.count;
          }
          currentOffset += item.count;
      }

      if (startOffset !== -1) {
          return { start: startOffset, count: totalCount };
      }
      return null;
  }

  const pruneCache = (centerOffset: number) => {
      const KEEP_RADIUS = 300; // 保留中心前后 300 张
      const min = centerOffset - KEEP_RADIUS;
      const max = centerOffset + KEEP_RADIUS;
      // 清理 Map
      for (const key of photoOffsetMap.keys()) {
          if (key < min || key > max) {
              photoOffsetMap.delete(key);
          }
      }
  }

  const loadPhotosByMonth = async (year: number, month: number, albumId?: string, refresh = false) => {
    const dateKey = `${year}-${String(month).padStart(2, '0')}`;
    // Check if already loaded or loading
    if (loadedDates.has(dateKey) && !refresh) return;

    // Get offset info for the whole month
    const offsetInfo = getOffsetRangeForMonth(year, month);
    // console.log('offsetInfo', offsetInfo)
    if (!offsetInfo || offsetInfo.count === 0) return;

    const processPhotos = (photos: Photo[]) => {
        const newImages = photos.map(mapPhotoToImage);

        // Populate PhotoOffsetMap
        newImages.forEach((img, index) => {
            photoOffsetMap.set(offsetInfo.start + index, img);
        });

        // Sync main list
        const existingIds = new Set(images.value.map(i => i.id));
        const toAdd = newImages.filter(i => !existingIds.has(i.id));

        if (toAdd.length > 0) {
            images.value.push(...toAdd);
            images.value.sort((a, b) => b.timestamp - a.timestamp);
        }
        // Prune cache around the loaded area
        pruneCache(offsetInfo.start + offsetInfo.count / 2);
    };

    loading.value = true;
    error.value = null;
    loadedDates.add(dateKey);

    const requestId = ++currentRequestId;
    const controller = new AbortController();
    activeRequests.set(requestId, controller);

    try {
        let photosData: Photo[] = [];
        
        // Calculate start and end time for the month
        const startDate = new Date(year, month - 1, 1);
        const endDate = new Date(year, month, 0, 23, 59, 59, 999); // Last day of month
        
        // Format to YYYY-MM-DD HH:mm:ss
        const formatDate = (d: Date) => {
             const pad = (n: number) => n.toString().padStart(2, '0');
             return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
        };

        const filters = {
            start_time: formatDate(startDate),
            end_time: formatDate(endDate),
            ...cleanFilters()
        };
        
        const count = offsetInfo.count;
        // console.log('count', count, year, month, cleanFilters())
        if (albumId) {
             photosData = await albumService.getPhotos(albumId, 0, count, filters);
        } else {
             photosData = await albumService.getAllPhotos(0, count, filters);
        }

        if (!activeRequests.has(requestId)) {
            loadedDates.delete(dateKey);
            return;
        }
        processPhotos(photosData);

    } catch (err) {
        loadedDates.delete(dateKey);
        if (err instanceof Error && err.name === 'AbortError') {
           console.log('请求已取消');
        } else {
           console.error("按月获取照片失败", err);
           error.value = '加载失败，请重试';
        }
    } finally {
        activeRequests.delete(requestId);
        if (activeRequests.size === 0) {
            loading.value = false;
        }
    }
  }

  const cancelAllPendingLoads = () => {
      activeRequests.forEach(controller => controller.abort());
      activeRequests.clear();
      activeOffsets.clear();
      loading.value = false;
  }

  const loadPhotos = async (reset: boolean = false) => {
      // Placeholder if needed, but loadPhotosByMonth is the main driver now
      if (reset) {
          images.value = [];
          photoOffsetMap.clear();
          loadedDates.clear();
          currentContext.value = { type: 'all' };
      }
      await fetchTimelineStats();
      // Logic to load initial view could go here
  }

  const loadAlbumPhotos = async (albumId: string, reset: boolean = false) => {
      if (reset) {
          images.value = [];
          photoOffsetMap.clear();
          loadedDates.clear();
      }
      currentContext.value = { type: 'album', id: albumId };
      await fetchTimelineStats(albumId);
  }

  const loadFolderPhotos = async (folder: string, reset: boolean = false, direct: boolean = false) => {
      if (reset) {
          images.value = [];
          photoOffsetMap.clear();
          loadedDates.clear();
      }
      folderPath.value = folder;
      folderDirect.value = direct;
      // 文件夹模式复用「全部照片」上下文（albumId 为空），由 cleanFilters 注入 folder 过滤
      currentContext.value = { type: 'all' };
      await fetchTimelineStats();
  }

  const removeLocalPhoto = (photoId: string) => {
      images.value = images.value.filter(img => img.id !== photoId);
      // Clean map
      for (const [key, val] of photoOffsetMap.entries()) {
          if (val.id === photoId) {
              photoOffsetMap.delete(key);
          }
      }
  }

  const deletePhoto = async (photoId: string) => {
      await deletePhotos([photoId])
  }

  const deletePhotos = async (photoIds: string[]) => {
      await albumService.batchUpdatePhotos({
          photo_ids: photoIds,
          action: 'delete'
      });
      // Remove locally
      images.value = images.value.filter(img => !photoIds.includes(img.id));
      // Also update map
      for (const [key, val] of photoOffsetMap.entries()) {
          if (photoIds.includes(val.id)) {
              photoOffsetMap.delete(key);
          }
      }
  }
  const resetAll = () => {
      timelineStats.value = { total_photos: 0, time_range: {start: null, end: null}, timeline: [] };
      images.value = [];
      photoOffsetMap.clear();
      loadedDates.clear();
      currentContext.value = { type: 'all' };
      folderPath.value = null;
      folderDirect.value = false;
      provinceFilter.value = null;
  }

  const fetchThumbnail = async (photoId: string) => {
    const thumbnail = await albumService.getThumbnail(photoId);
    return thumbnail;
  }

  const searchPhotos = async (query: string) => {
    const results = await searchService.searchByText({ text: query });
    return results;
  }

  return {
    images,
    loading,
    hasMore,
    mapPhotoToImage,
    currentContext,
    timelineStats,
    photoOffsetMap,
    availableFilters,
    selectedFilters,
    folderPath,
    folderDirect,
    provinceFilter,
    fetchAvailableFilters,
    fetchTimelineStats,
    loadPhotos,
    loadAlbumPhotos,
    loadFolderPhotos,
    loadPhotosByMonth,
    removeLocalPhoto,
    deletePhoto,
    deletePhotos,
    cancelAllPendingLoads,
    resetAll,
    error,
    isSearchMode,
    searchPhotos
  }
}

export const usePhotoStore = defineStore('photo', photoStoreSetup)

