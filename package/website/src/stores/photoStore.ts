// src/stores/photoStore.ts
// 定义照片相关的状态管理

import { defineStore } from 'pinia'
import { ref, reactive, watch, computed } from 'vue'
import { albumService } from '@/api/album'
import searchService, { type TextSearchRequest } from '@/api/search'
import type { Photo, TimelineStats, TimelineCover, AlbumImage, TimelineItem, FilterOptions, FilterState } from '@/types/album'
import { toServerUrl } from '@/config/server'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { normalizeMediaTypeFilters } from '@/utils/mediaTypeFilters'

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

export const mapPhotoToImage = (photo: TimelineCover): AlbumImage => {
    // 新 API 在 url 和 thumbnail_url 字段中返回相对地址
    const url = toServerUrl(`/api/medias/${photo.id}/file`);
    const ready = Boolean(photo.width && photo.height);
    const thumbnail = ready ? thumbnailUrl(photo.id, 'small', photo.owner_id)
        : 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
    // const thumbnail = `https://picsum.photos/seed/${photo.id}/400/600`
    const preview = ready ? thumbnailUrl(photo.id, 'medium', photo.owner_id) : thumbnail;

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
      ownerId: photo.owner_id,
      panorama_projection: photo.panorama_projection,
      panorama_override: photo.panorama_override,
      url,
      thumbnail,
      preview,
      srcset: '', // 暂不分发多尺寸，后端按需动态处理
      timestamp,
      hasPhotoTime,
      photoTime: photo.photo_time,
      uploadTime: photo.upload_time,
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
  const timeField = ref<'photo_time' | 'upload_time'>('photo_time')
  const browseEnabled = ref(false)
  const browseGranularity = ref<'year' | 'month' | 'day'>('day')
  const mapTimelinePhoto = (photo: TimelineCover): AlbumImage => {
      const image = mapPhotoToImage(photo)
      if (browseEnabled.value) {
          const raw = photo.time
          image.timestamp = raw ? new Date(raw).getTime() : NaN
          image.photoTime = timeField.value === 'photo_time' ? (raw ?? null) : undefined
          image.hasPhotoTime = photo.has_photo_time ?? (timeField.value === 'photo_time' && Boolean(raw))
      }
      return image
  }
  const compareImages = (a: AlbumImage, b: AlbumImage) =>
      (Number.isFinite(b.timestamp) ? b.timestamp : -Infinity) - (Number.isFinite(a.timestamp) ? a.timestamp : -Infinity)
      || (a.id < b.id ? 1 : a.id > b.id ? -1 : 0)
  const monthFilters = (year: number, month: number, filters = cleanFilters()) => browseEnabled.value
      ? { ...filters, browse_year: year, ...(year ? { browse_month: month } : {}) }
      : { ...filters, start_time: `${year}-${String(month).padStart(2, '0')}-01 00:00:00`,
          end_time: `${year}-${String(month).padStart(2, '0')}-${new Date(year, month, 0).getDate()} 23:59:59.999999` }
  // --- 状态 ---
  const images = ref<AlbumImage[]>([])
  const loading = ref(false)
  const hasMore = ref(true)
  const error = ref<string | null>(null)
  const isSearchMode = ref(false)
  const currentContext = ref<{ type: 'all' | 'album' | 'search', id?: string }>({ type: 'all' })
  const timelineStats = ref<TimelineStats>()
  const availableFilters = ref<FilterOptions | null>(null);
  const dataRevision = ref(0);
  const globalStaleRevision = ref(0);
  const albumStaleRevisions = reactive<Record<string, number>>({});
  const refreshedContextRevisions = reactive<Record<string, number>>({});
  const staleTaskTypes = ref<string[]>([]);
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

  const getContextKey = () => {
      if (currentContext.value.type === 'album' && currentContext.value.id) {
          return `album:${currentContext.value.id}`;
      }
      if (currentContext.value.type === 'search') return 'search';
      return `all:${folderPath.value || ''}:${folderDirect.value ? 'direct' : 'recursive'}`;
  }

  const getRequiredRevision = () => {
      const albumRevision = currentContext.value.type === 'album' && currentContext.value.id
          ? albumStaleRevisions[currentContext.value.id] || 0
          : 0;
      return Math.max(globalStaleRevision.value, albumRevision);
  }

  const dataStale = computed(() =>
      (refreshedContextRevisions[getContextKey()] || 0) < getRequiredRevision()
  );

  const acknowledgeContextRevision = (contextKey: string, revision: number) => {
      refreshedContextRevisions[contextKey] = Math.max(
          refreshedContextRevisions[contextKey] || 0,
          revision
      );
      if (!dataStale.value) staleTaskTypes.value = [];
  }

  // Task completion only signals that the data may have changed. Check the
  // visible context before rebuilding the gallery, since metadata tasks do
  // not necessarily add or remove photos.
  const hasCurrentContextPhotoCountChanged = async (): Promise<boolean> => {
      if (currentContext.value.type === 'search' || !timelineStats.value) return false;
      const contextKey = getContextKey();
      const targetRevision = getRequiredRevision();
      const previousCount = timelineStats.value.total_photos;
      const albumId = currentContext.value.type === 'album' ? currentContext.value.id : undefined;
      const stats = await albumService.getTimelineStats(albumId, cleanFilters());
      if (getContextKey() !== contextKey) return false;
      if (stats.total_photos !== previousCount ||
          JSON.stringify(stats.timeline) !== JSON.stringify(timelineStats.value?.timeline) ||
          staleTaskTypes.value.some(type => ['PROCESS_BASIC', 'EXTRACT_METADATA', 'REBUILD_METADATA'].includes(type))) return true;
      acknowledgeContextRevision(contextKey, targetRevision);
      return false;
  }

  // 筛选条件持久化到 trailsnap:selectedFilters，刷新/重开后恢复（P1 2.1.9 回归用例依赖）。
  {
      const FILTER_CACHE_KEY = 'selectedFilters'
      const cached = getLocalCache<FilterState & { is_panorama?: boolean }>(FILTER_CACHE_KEY)
      if (cached) {
          const { is_panorama, ...filters } = cached
          Object.assign(selectedFilters, filters, {
              file_types: normalizeMediaTypeFilters(filters.file_types, is_panorama),
          })
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
      if (browseEnabled.value) {
          filters.time_field = timeField.value
          filters.order_by = timeField.value
          filters.include_covers = true
      }
      return filters;
  }

  let timelineRequestId = 0;
  const fetchTimelineStats = async (albumId?: string): Promise<boolean> => {
    const requestId = ++timelineRequestId;
    loading.value = true;
    error.value = null;
    try {
      const filters = cleanFilters();
      const stats = await albumService.getTimelineStats(albumId, filters)
      if (requestId !== timelineRequestId || JSON.stringify(filters) !== JSON.stringify(cleanFilters())) return false;
      timelineStats.value = stats
      return true;
    } catch (e) {
      if (requestId !== timelineRequestId) return false;
      console.error("获取时间轴统计失败", e)
      error.value = '加载失败，请重试';
      return false;
    } finally {
      if (requestId === timelineRequestId) loading.value = false;
    }
  }

  const activeOffsets = new Set<number>();
  const loadedDates = reactive(new Set<string>());
  const photoOffsetMap = reactive(new Map<number, AlbumImage>());

  // 追踪活跃请求以支持取消
  let currentRequestId = 0;
  const activeRequests = new Map<number, AbortController>();
  const activeRequestDates = new Map<number, string>();
  const pendingMonthLoads = new Map<string, Promise<void>>();

  const getOffsetRangeForMonth = (year: number, month: number): { start: number, count: number } | null => {
      if (!timelineStats.value?.timeline) return null;

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

  const loadPhotosByMonthImpl = async (year: number, month: number, albumId?: string, refresh = false) => {
    const dateKey = `${year}-${String(month).padStart(2, '0')}`;
    // Check if already loaded or loading
    if (loadedDates.has(dateKey) && !refresh) return;

    // Get offset info for the whole month
    const offsetInfo = getOffsetRangeForMonth(year, month);
    // console.log('offsetInfo', offsetInfo)
    if (!offsetInfo || offsetInfo.count === 0) return;

    const filterKey = JSON.stringify(cleanFilters());
    const processPhotos = (photos: Photo[]) => {
        const newImages = photos.map(mapTimelinePhoto);

        // Populate PhotoOffsetMap
        newImages.forEach((img, index) => {
            photoOffsetMap.set(offsetInfo.start + index, img);
        });

        // Sync main list
        const existingIds = new Set(images.value.map(i => i.id));
        const toAdd = newImages.filter(i => !existingIds.has(i.id));

        if (toAdd.length > 0) {
            // Publish the merged, sorted list once. Watchers must not observe
            // each intermediate array index while sorting a large photo cache.
            images.value = [...images.value, ...toAdd].sort(compareImages);
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
    activeRequestDates.set(requestId, dateKey);

    try {
        let photosData: Photo[] = [];
        
        const filters = monthFilters(year, month);

        const count = offsetInfo.count;
        // console.log('count', count, year, month, cleanFilters())
        if (albumId) {
             photosData = await albumService.getPhotos(albumId, 0, count, filters);
        } else {
             photosData = await albumService.getAllPhotos(0, count, filters);
        }

        if (!activeRequests.has(requestId) || filterKey !== JSON.stringify(cleanFilters())) {
            return;
        }
        processPhotos(photosData);

    } catch (err) {
        if (!activeRequests.has(requestId) || filterKey !== JSON.stringify(cleanFilters())) return;
        loadedDates.delete(dateKey);
        if (err instanceof Error && err.name === 'AbortError') {
           console.log('请求已取消');
        } else {
           console.error("按月获取照片失败", err);
           error.value = '加载失败，请重试';
        }
    } finally {
        activeRequests.delete(requestId);
        activeRequestDates.delete(requestId);
        if (activeRequests.size === 0) {
            loading.value = false;
        }
    }
  }

  const loadPhotosByMonth = (year: number, month: number, albumId?: string, refresh = false): Promise<void> => {
      const key = JSON.stringify([year, month, albumId, cleanFilters()])
      const pending = pendingMonthLoads.get(key)
      if (pending) return pending
      const request = loadPhotosByMonthImpl(year, month, albumId, refresh).finally(() => {
          if (pendingMonthLoads.get(key) === request) pendingMonthLoads.delete(key)
      })
      pendingMonthLoads.set(key, request)
      return request
  }

  const cancelAllPendingLoads = () => {
      activeRequests.forEach(controller => controller.abort());
      activeRequestDates.forEach(dateKey => loadedDates.delete(dateKey));
      activeRequestDates.clear();
      activeRequests.clear();
      pendingMonthLoads.clear();
      activeOffsets.clear();
      loading.value = false;
  }

  const loadPhotos = async (reset: boolean = false) => {
      // Placeholder if needed, but loadPhotosByMonth is the main driver now
      if (reset) {
          cancelAllPendingLoads();
          images.value = [];
          photoOffsetMap.clear();
          loadedDates.clear();
          currentContext.value = { type: 'all' };
      }
      const contextKey = getContextKey();
      const targetRevision = getRequiredRevision();
      if (await fetchTimelineStats()) acknowledgeContextRevision(contextKey, targetRevision);
      // Logic to load initial view could go here
  }

  const loadAlbumPhotos = async (albumId: string, reset: boolean = false) => {
      if (reset) {
          cancelAllPendingLoads();
          images.value = [];
          photoOffsetMap.clear();
          loadedDates.clear();
      }
      currentContext.value = { type: 'album', id: albumId };
      const contextKey = getContextKey();
      const targetRevision = getRequiredRevision();
      if (await fetchTimelineStats(albumId)) acknowledgeContextRevision(contextKey, targetRevision);
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
      const contextKey = getContextKey();
      const targetRevision = getRequiredRevision();
      await fetchTimelineStats();
      acknowledgeContextRevision(contextKey, targetRevision);
  }

  /**
   * Refresh loaded months atomically, keeping the current gallery visible
   * while requests run. Preserve months loaded during the refresh as well.
   */
  const refreshCurrentContext = async () => {
      if (currentContext.value.type === 'search') return;

      const context = { ...currentContext.value };
      const contextKey = getContextKey();
      const targetRevision = getRequiredRevision();
      const monthsToReload = [...loadedDates];
      const filters = cleanFilters();
      const filterKey = JSON.stringify(filters);
      const stats = await albumService.getTimelineStats(
          context.type === 'album' ? context.id : undefined,
          filters
      );
      const refreshed = await Promise.all(monthsToReload.map(async (dateKey) => {
          const [year, month] = dateKey.split('-').map(Number);
          const monthQuery = monthFilters(year, month, filters);
          const count = stats.timeline.filter(day => day.year === year && day.month === month)
              .reduce((sum, day) => sum + day.count, 0);
          const photos = count === 0 ? [] : context.type === 'album' && context.id
              ? await albumService.getPhotos(context.id, 0, count, monthQuery)
              : await albumService.getAllPhotos(0, count, monthQuery);
          return { dateKey, images: photos.map(mapTimelinePhoto) };
      }));
      if (getContextKey() !== contextKey || JSON.stringify(cleanFilters()) !== filterKey) return;

      // Keep the old gallery until every request succeeds. Publish the new
      // timeline and cache together, without an empty frame or skeleton overlay.
      cancelAllPendingLoads();
      const replacements = new Map(refreshed.map(month => [month.dateKey, month.images]));
      const retained = images.value.filter(image => {
          const date = new Date(image.timestamp);
          return !replacements.has(Number.isFinite(image.timestamp) ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}` : '0-00');
      });
      const merged = [...retained, ...refreshed.flatMap(month => month.images)];
      images.value = [...new Map(merged.map(image => [image.id, image])).values()].sort(compareImages);
      timelineStats.value = stats;
      photoOffsetMap.clear();
      const cachedMonths = new Map<string, AlbumImage[]>();
      for (const image of images.value) {
          const date = new Date(image.timestamp);
          const dateKey = Number.isFinite(image.timestamp) ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}` : '0-00';
          const monthImages = cachedMonths.get(dateKey) || [];
          monthImages.push(image);
          cachedMonths.set(dateKey, monthImages);
      }
      for (const [dateKey, monthImages] of cachedMonths) {
          const [year, monthNumber] = dateKey.split('-').map(Number);
          const offset = getOffsetRangeForMonth(year, monthNumber);
          if (offset) monthImages.forEach((image, index) => photoOffsetMap.set(offset.start + index, image));
      }
      acknowledgeContextRevision(contextKey, targetRevision);
  }

  let sortRequestId = 0
  const changeTimeField = async (field: 'photo_time' | 'upload_time', anchor?: AlbumImage | null, isCurrent = () => true, loadDetail = true) => {
      const request = ++sortRequestId
      const filters = { ...cleanFilters(), time_field: field, order_by: field, include_covers: true }
      const filterKey = JSON.stringify(cleanFilters())
      const [stats, anchorRows] = await Promise.all([
          albumService.getTimelineStats(undefined, filters),
          anchor && field !== timeField.value
            ? albumService.getAllPhotos(0, 1, { time_field: field, order_by: field, ids: [anchor.id] })
            : Promise.resolve([])
      ])
      const raw = field === timeField.value && anchor?.timestamp
        ? new Date(anchor.timestamp).toISOString()
        : anchorRows[0]?.time
      const stamp = raw ? new Date(raw).getTime() : NaN
      const date = new Date(stamp)
      let year = Number.isFinite(stamp) ? date.getFullYear() : 0
      let month = Number.isFinite(stamp) ? date.getMonth() + 1 : 0
      if (!anchor || !stats.timeline.some(item => item.year === year && item.month === month)) {
          const nearest = [...stats.timeline].sort((a, b) => {
              const distance = (v: typeof a) => Math.abs(new Date(v.year || 9999, (v.month || 1) - 1, v.day || 1).getTime() - (Number.isFinite(stamp) ? stamp : Date.now()))
              return distance(a) - distance(b)
          })[0]
          year = nearest?.year ?? 0; month = nearest?.month ?? 0
      }
      const count = stats.timeline.filter(item => item.year === year && item.month === month).reduce((n, item) => n + item.count, 0)
      let photos: TimelineCover[]
      if (loadDetail) photos = count ? await albumService.getAllPhotos(0, count, { ...filters, browse_year: year, ...(year ? { browse_month: month } : {}) }) : []
      else {
          photos = anchorRows
          if (!photos.length) {
              const cover = stats.months?.find(item => item.year === year && item.month === month)?.cover ?? stats.months?.[0]?.cover
              photos = cover ? [cover] : []
          }
      }
      if (request !== sortRequestId || !isCurrent() || filterKey !== JSON.stringify(cleanFilters())) return false
      ++timelineRequestId
      cancelAllPendingLoads()
      loadedDates.clear()
      timeField.value = field
      images.value = photos.map(mapTimelinePhoto).sort(compareImages)
      timelineStats.value = stats
      photoOffsetMap.clear()
      const offset = getOffsetRangeForMonth(year, month)
      if (loadDetail && offset) images.value.forEach((photo, i) => photoOffsetMap.set(offset.start + i, photo))
      if (loadDetail) loadedDates.add(`${year}-${String(month).padStart(2, '0')}`)
      return true
  }

  const markDataStale = (taskType?: string, albumId?: string) => {
      dataRevision.value += 1;
      if (albumId) {
          albumStaleRevisions[albumId] = dataRevision.value;
      } else {
          globalStaleRevision.value = dataRevision.value;
      }
      if (taskType && !staleTaskTypes.value.includes(taskType)) {
          staleTaskTypes.value = [...staleTaskTypes.value, taskType];
      }
  }

  const removeLocalPhotos = (photoIds: string[]) => {
      const ids = new Set(photoIds);
      const removedPhotos = images.value.filter(img => ids.has(img.id));
      if (removedPhotos.length === 0) return;

      images.value = images.value.filter(img => !ids.has(img.id));
      for (const [key, val] of photoOffsetMap.entries()) {
          if (ids.has(val.id)) photoOffsetMap.delete(key);
      }

      // Keep the virtual timeline in sync without clearing the whole gallery.
      // A forced reload briefly collapses the virtual list and sends the user
      // back to the top after every delete.
      if (timelineStats.value) {
          const removedByDay = new Map<string, number>();
          removedPhotos.forEach((photo) => {
              const date = new Date(photo.timestamp);
              const key = Number.isFinite(photo.timestamp) ? `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}` : '0-0-0';
              removedByDay.set(key, (removedByDay.get(key) || 0) + 1);
          });

          timelineStats.value = {
              ...timelineStats.value,
              total_photos: Math.max(0, timelineStats.value.total_photos - removedPhotos.length),
              timeline: timelineStats.value.timeline
                  .map(item => ({
                      ...item,
                      count: Math.max(
                          0,
                          item.count - (removedByDay.get(`${item.year}-${item.month}-${item.day}`) || 0)
                      )
                  }))
                  .filter(item => item.count > 0)
          };
      }
  }

  const removeLocalPhoto = (photoId: string) => removeLocalPhotos([photoId])

  const deletePhoto = async (photoId: string) => {
      await deletePhotos([photoId])
  }

  const deletePhotos = async (photoIds: string[]) => {
      await albumService.batchUpdatePhotos({
          photo_ids: photoIds,
          action: 'delete'
      });
      removeLocalPhotos(photoIds);
      if (browseEnabled.value) await fetchTimelineStats();
  }
  const resetAll = () => {
      ++sortRequestId;
      ++timelineRequestId;
      cancelAllPendingLoads();
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
    timeField, browseEnabled, browseGranularity, changeTimeField, mapTimelinePhoto,
    images,
    loading,
    hasMore,
    mapPhotoToImage,
    currentContext,
    timelineStats,
    photoOffsetMap,
    availableFilters,
    dataStale,
    dataRevision,
    staleTaskTypes,
    selectedFilters,
    folderPath,
    folderDirect,
    provinceFilter,
    fetchAvailableFilters,
    fetchTimelineStats,
    loadPhotos,
    loadAlbumPhotos,
    loadFolderPhotos,
    refreshCurrentContext,
    hasCurrentContextPhotoCountChanged,
    markDataStale,
    loadPhotosByMonth,
    removeLocalPhoto,
    removeLocalPhotos,
    deletePhoto,
    deletePhotos,
    cancelAllPendingLoads,
    resetAll,
    error,
    isSearchMode,
    searchPhotos,
    getPickerSearchFilters: () => ({
      ...cleanFilters(),
      ...(currentContext.value.type === 'album' ? { album_id: currentContext.value.id } : {}),
    })
  }
}

export const usePhotoStore = defineStore('photo', photoStoreSetup)
// “全部照片”页长期缓存；其他照片视图使用独立的 store。
export const usePhotosPageStore = defineStore('photosPage', photoStoreSetup)

