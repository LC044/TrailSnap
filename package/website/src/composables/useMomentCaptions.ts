import { reactive, ref, shallowRef } from 'vue';
import { momentApi, getBrowserTimezone, type MomentDayCaption } from '@/api/moment';

export interface CaptionState {
  caption: string;
  source: 'ai' | 'manual' | 'ai_streaming';
  streaming?: boolean;
  updated_at?: string;
}

/**
 * `dayKey` 格式：与 PhotoGallery.vue `groupedPhotos` 中一致 —— `${year}-${month}-${day}`
 * （注意月/日**不补零**，例如 `2025-8-5`）。这是前端的展示态；
 * 与后端交互时会转换成 `YYYY-MM-DD` 的 ISO 日期。
 */
function toIsoDay(dayKey: string): string {
  const [y, m, d] = dayKey.split('-').map((s) => parseInt(s, 10));
  const mm = String(m).padStart(2, '0');
  const dd = String(d).padStart(2, '0');
  return `${y}-${mm}-${dd}`;
}

function fromIsoDay(iso: string): string {
  const [y, m, d] = iso.split('-').map((s) => parseInt(s, 10));
  return `${y}-${m}-${d}`;
}

export function useMomentCaptions() {
  /** dayKey -> caption 状态 */
  const captionMap = reactive<Record<string, CaptionState>>({});

  /** 生成中的 dayKey 集合 */
  const loadingDays = ref<Set<string>>(new Set());

  /** 每个 day 对应的 AbortController，方便中止或组件卸载时统一 abort */
  const controllers = new Map<string, AbortController>();

  /** 已经批量拉过的月份，避免重复请求。key 格式 `YYYY-M` */
  const loadedMonths = new Set<string>();

  const setCaption = (dayKey: string, state: CaptionState | null) => {
    if (state === null) {
      delete captionMap[dayKey];
    } else {
      captionMap[dayKey] = state;
    }
  };

  /** 按可见月份批量拉取当月已有 caption。month 是 1-12。 */
  const loadMonth = async (year: number, month: number, refresh = false) => {
    // 守卫：跨页跳转时 timeline 尚未加载完，PhotoGallery 可能广播出
    // dummy 月份（year=0, month=0），若不拦截会向后端发送
    // `start=0-00-01` 之类非法参数，触发 422 并弹出「请求错误（[object Object]）」。
    if (!Number.isFinite(year) || !Number.isFinite(month)) return;
    if (year <= 0 || month < 1 || month > 12) return;

    const key = `${year}-${month}`;
    if (!refresh && loadedMonths.has(key)) return;
    loadedMonths.add(key);

    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    // 计算月末
    const endDate = new Date(year, month, 0); // month 是 1-12，month=8 → new Date(y,8,0)=8月31日
    const end = `${endDate.getFullYear()}-${String(endDate.getMonth() + 1).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}`;

    try {
      const res = await momentApi.listDayCaptions({ start, end });
      const list = (res as any).data ?? res;
      const arr: MomentDayCaption[] = Array.isArray(list) ? list : [];
      arr.forEach((c) => {
        setCaption(fromIsoDay(c.day), {
          caption: c.caption,
          source: c.source,
          updated_at: c.updated_at,
        });
      });
    } catch (e) {
      // 拉取失败不阻断视图；下次重新触发时会再试
      loadedMonths.delete(key);
      console.warn('[useMomentCaptions] load month failed', e);
    }
  };

  const generate = async (dayKey: string, opts: { force?: boolean; style?: string } = {}) => {
    if (loadingDays.value.has(dayKey)) return; // 已经在生成

    const previous = captionMap[dayKey];
    // 中止旧的（同一 day 上一次未完成的流）
    controllers.get(dayKey)?.abort();
    const controller = new AbortController();
    controllers.set(dayKey, controller);

    loadingDays.value = new Set([...loadingDays.value, dayKey]);
    setCaption(dayKey, { caption: '', source: 'ai_streaming', streaming: true });

    try {
      await momentApi.generateStream(
        {
          day: toIsoDay(dayKey),
          timezone: getBrowserTimezone(),
          force: opts.force ?? !!previous,
          style: opts.style,
        },
        (chunk) => {
          const cur = captionMap[dayKey];
          if (cur) {
            setCaption(dayKey, { ...cur, caption: cur.caption + chunk });
          }
        },
        (info) => {
          setCaption(dayKey, {
            caption: info.caption,
            source: (info.source as any) === 'existing' ? 'ai' : 'ai',
            streaming: false,
            updated_at: info.updated_at,
          });
        },
        (err) => {
          // 若报错时已有旧文案，恢复它
          if (previous) {
            setCaption(dayKey, previous);
          } else {
            setCaption(dayKey, null);
          }
          throw new Error(err);
        },
        controller.signal,
      );
    } catch (e) {
      if ((e as any)?.name === 'AbortError') {
        // 主动中止不视为错误
        if (previous) setCaption(dayKey, previous);
        else setCaption(dayKey, null);
        return;
      }
      throw e;
    } finally {
      const next = new Set(loadingDays.value);
      next.delete(dayKey);
      loadingDays.value = next;
      controllers.delete(dayKey);
    }
  };

  const save = async (dayKey: string, caption: string) => {
    const iso = toIsoDay(dayKey);
    const res = await momentApi.saveDayCaption(iso, caption);
    const data: MomentDayCaption = (res as any).data ?? res;
    setCaption(dayKey, {
      caption: data.caption,
      source: data.source,
      updated_at: data.updated_at,
    });
  };

  const clear = async (dayKey: string) => {
    const iso = toIsoDay(dayKey);
    await momentApi.clearDayCaption(iso);
    setCaption(dayKey, null);
  };

  const abort = (dayKey: string) => {
    controllers.get(dayKey)?.abort();
  };

  const abortAll = () => {
    controllers.forEach((c) => c.abort());
    controllers.clear();
  };

  return {
    captionMap,
    loadingDays,
    loadMonth,
    generate,
    save,
    clear,
    abort,
    abortAll,
  };
}
