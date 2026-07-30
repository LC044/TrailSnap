import { reactive } from 'vue';
import { momentApi, type MomentDayHighlights, type MomentHighlightPhoto } from '@/api/moment';

/**
 * 朋友圈日精选：不落库，服务端每次实时计算。
 *
 * 与 `useMomentCaptions` / `useMomentLocations` 保持相同的 dayKey 约定：
 *   `${year}-${month}-${day}`（月/日 **不补零**），与 `PhotoGallery.vue` 中
 *   `groupedPhotos` 的 dayKey 一致，例如 `2025-8-5`。
 *
 * 后端返回 ISO 日期（YYYY-MM-DD），进入 store 前先转成 dayKey 形式；
 * ``photoIds`` 顺序即建议展示顺序（score desc, photo_time desc）。
 */

function fromIsoDay(iso: string): string {
  const [y, m, d] = iso.split('-').map((s) => parseInt(s, 10));
  return `${y}-${m}-${d}`;
}

export interface MomentHighlightView {
  /** 精选照片 ID 列表（顺序即展示顺序） */
  photoIds: string[];
  /** 该天参与精选池的候选照片总数（不含视频） */
  totalCandidates: number;
  /** 原始 photos 详情，供 UI 需要 photo_time / score 时查阅 */
  photos: MomentHighlightPhoto[];
}

export function useMomentHighlights() {
  /** dayKey -> 精选视图 */
  const highlightMap = reactive<Record<string, MomentHighlightView>>({});

  /** 已经批量拉过的月份，避免重复请求。key 格式 `YYYY-M` */
  const loadedMonths = new Set<string>();

  const setHighlight = (dayKey: string, view: MomentHighlightView | null) => {
    if (view === null) {
      delete highlightMap[dayKey];
    } else {
      highlightMap[dayKey] = view;
    }
  };

  /** 按可见月份批量拉取当月已有精选。month 是 1-12。 */
  const loadMonth = async (year: number, month: number, refresh = false) => {
    // 与 useMomentCaptions 相同的守卫：跨页跳转 timeline 广播 dummy 月份时不发请求
    if (!Number.isFinite(year) || !Number.isFinite(month)) return;
    if (year <= 0 || month < 1 || month > 12) return;

    const key = `${year}-${month}`;
    if (!refresh && loadedMonths.has(key)) return;
    loadedMonths.add(key);

    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    // 月末：new Date(y, month, 0) 会得到该月的最后一天
    const endDate = new Date(year, month, 0);
    const end = `${endDate.getFullYear()}-${String(endDate.getMonth() + 1).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}`;

    try {
      const res = await momentApi.listDayHighlights({ start, end });
      const list = (res as any).data ?? res;
      const arr: MomentDayHighlights[] = Array.isArray(list) ? list : [];
      arr.forEach((row) => {
        setHighlight(fromIsoDay(row.day), {
          photoIds: row.photos.map((p: MomentHighlightPhoto) => p.id),
          totalCandidates: row.total_candidates,
          photos: row.photos,
        });
      });
    } catch (e) {
      // 拉取失败不阻断视图；下次触发时会再试一遍
      loadedMonths.delete(key);
      console.warn('[useMomentHighlights] load month failed', e);
    }
  };

  /** 强制清空缓存并重拉某月（比如用户删/修改了照片后需要刷新） */
  const invalidate = (year?: number, month?: number) => {
    if (year && month) {
      loadedMonths.delete(`${year}-${month}`);
    } else {
      loadedMonths.clear();
      Object.keys(highlightMap).forEach((k) => delete highlightMap[k]);
    }
  };

  return {
    highlightMap,
    loadMonth,
    invalidate,
  };
}
