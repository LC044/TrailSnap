import { reactive } from 'vue';
import { momentApi, type MomentDayLocations } from '@/api/moment';

/**
 * 朋友圈日位置：不落库，纯从 `photo_metadata` 实时聚合。
 *
 * 与 `useMomentCaptions` 保持相同的 dayKey 约定：
 *   `${year}-${month}-${day}`（月/日 **不补零**），与 `PhotoGallery.vue` 中
 *   `groupedPhotos` 的 dayKey 一致，例如 `2025-8-5`。
 *
 * 后端返回 ISO 日期（YYYY-MM-DD），进入 store 前会先转成 dayKey 形式。
 */

function fromIsoDay(iso: string): string {
  const [y, m, d] = iso.split('-').map((s) => parseInt(s, 10));
  return `${y}-${m}-${d}`;
}

export interface MomentLocationView {
  primary: string;
  level: MomentDayLocations['level'];
  /** 若 locations 长度 > 1，用户可以后续在 UI 里展开显示全部；本期直接拼接前 N 个作为 primary。 */
  locations: MomentDayLocations['locations'];
}

export function useMomentLocations() {
  /** dayKey -> 位置视图。空对象即"该天无位置数据"。 */
  const locationMap = reactive<Record<string, MomentLocationView>>({});

  /** 已经批量拉过的月份，避免重复请求。key 格式 `YYYY-M` */
  const loadedMonths = new Set<string>();

  const setLocation = (dayKey: string, view: MomentLocationView | null) => {
    if (view === null) {
      delete locationMap[dayKey];
    } else {
      locationMap[dayKey] = view;
    }
  };

  /** 按可见月份批量拉取当月已有位置。month 是 1-12。 */
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
      const res = await momentApi.listDayLocations({ start, end });
      const list = (res as any).data ?? res;
      const arr: MomentDayLocations[] = Array.isArray(list) ? list : [];
      arr.forEach((row) => {
        setLocation(fromIsoDay(row.day), {
          primary: row.primary,
          level: row.level,
          locations: row.locations,
        });
      });
    } catch (e) {
      // 拉取失败不阻断视图；下次触发时会再试一遍
      loadedMonths.delete(key);
      console.warn('[useMomentLocations] load month failed', e);
    }
  };

  return {
    locationMap,
    loadMonth,
  };
}
