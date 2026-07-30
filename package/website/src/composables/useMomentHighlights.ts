import { reactive } from 'vue';
import { momentApi, type MomentDayHighlights, type MomentHighlightPhoto } from '@/api/moment';

/**
 * 朋友圈日精选：服务端已完成相似去重 + 分数排序，不落库。dayKey 格式
 * `${year}-${month}-${day}`（月/日 **不补零**），与 `PhotoGallery.vue` `groupedPhotos`
 * 一致。``photoIds`` 顺序即展示顺序。
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
  photos: MomentHighlightPhoto[];
}

export function useMomentHighlights() {
  const highlightMap = reactive<Record<string, MomentHighlightView>>({});

  /** 已拉过的月份，避免重复请求。key: `YYYY-M` */
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
    // 守卫：跨页跳转时 timeline 尚未加载完，可能广播 dummy 月份（year=0, month=0）
    if (!Number.isFinite(year) || !Number.isFinite(month)) return;
    if (year <= 0 || month < 1 || month > 12) return;

    const key = `${year}-${month}`;
    if (!refresh && loadedMonths.has(key)) return;
    loadedMonths.add(key);

    const start = `${year}-${String(month).padStart(2, '0')}-01`;
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

  return {
    highlightMap,
    loadMonth,
  };
}
