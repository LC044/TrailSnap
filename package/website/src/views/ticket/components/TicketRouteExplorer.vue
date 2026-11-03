<template>
  <SurfaceCard ref="card" class="route-explorer" padding="none">
    <div class="explorer-heading">
      <h2>出行路线</h2>
      <div class="explorer-actions">
        <div class="map-tabs" aria-label="地图视图">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            :aria-pressed="mode === tab.key"
            :class="{ active: mode === tab.key }"
            @click="mode = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
        <button
          class="ts-icon-button ts-button-secondary ts-button-sm"
          aria-label="放大地图"
          @click="expanded = true"
        >
          <Maximize2 class="h-4 w-4" />
        </button>
      </div>
    </div>
    <MapContent v-if="!expanded" />
    <ResponsiveDialog
      v-model="expanded"
      title="出行路线"
      max-width="min(1500px, 96vw)"
      mobile-mode="fullscreen"
      mobile-back
      :glass="false"
      panel-class="route-map-dialog"
      history
    >
      <div class="expanded-toolbar">
        <slot name="filters" />
        <div class="map-tabs" aria-label="放大地图视图">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            :aria-pressed="mode === tab.key"
            :class="{ active: mode === tab.key }"
            @click="mode = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>
      <div class="expanded-map-shell"><MapContent :large="true" /></div>
    </ResponsiveDialog>
  </SurfaceCard>
</template>

<script setup lang="ts">
import {
  computed,
  ref,
  shallowRef,
  watch,
  onMounted,
  onBeforeUnmount,
  defineComponent,
  h,
} from "vue";
import { RouterLink } from "vue-router";
import { useMediaQuery } from "@vueuse/core";
import type { EChartsCoreOption } from "echarts/core";
import {
  Maximize2,
  Plus,
  Minus,
  LocateFixed,
  Globe2,
  X,
  ChevronDown,
  ChevronUp,
} from "lucide-vue-next";
import SurfaceCard from "@/components/ui/SurfaceCard.vue";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import StatisticsChart from "./StatisticsChart.vue";
import { injectTheme } from "@/composables/useTheme";
import { echarts } from "@/utils/echarts";
import { ticketStatisticsApi } from "@/api/ticketStatistics";
import {
  normalizeTicketCity,
  formatTravelDuration,
  type TicketStatistics,
} from "@/utils/ticketStatistics";
import { ticketLink, contextLink } from "@/types/ticketWallet";
import {
  featureCenter,
  fitMapViewport,
  nationalViewport,
  mapSelectionDetail,
  sameMapSelection,
  directionalMapRoutes,
  type MapSelection,
  type MapViewport,
} from "@/utils/ticketMap";

const props = defineProps<{
  summary: TicketStatistics;
  selection: MapSelection;
}>();
const emit = defineEmits<{ "update:selection": [value: MapSelection] }>();
const { currentTheme, isDarkMode } = injectTheme();
const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
const expanded = ref(false);
const mode = ref<"routes" | "cities" | "heat">("routes");
const tabs = [
  { key: "routes", label: "路线" },
  { key: "cities", label: "城市" },
  { key: "heat", label: "热力" },
] as const;
const coordinates = shallowRef(new Map<string, [number, number]>());
const featureNames = shallowRef(new Map<string, string>());
const ready = ref(false),
  failed = ref(false);
const viewport = ref<MapViewport>(nationalViewport());
const detailOpen = ref(true);
const detail = computed(() =>
  mapSelectionDetail(props.summary, props.selection),
);
const selectionTitle = computed(() =>
  !props.selection
    ? ""
    : props.selection.type === "city"
      ? props.selection.name
      : `${props.selection.from} ${props.selection.directional ? "→" : "↔"} ${props.selection.to}`,
);
const nf = (value: number) =>
  value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
let disposed = false,
  pending = false;
let mapAspect = 1.8;
const abort = new AbortController();
const mappedCities = computed(() =>
  props.summary.cities.filter((city) => coordinates.value.has(city.name)),
);
function fit() {
  const cities = props.selection
    ? detail.value.cities
    : props.summary.cities.map((city) => city.name);
  viewport.value = fitMapViewport(
    cities.flatMap((name) => {
      const point = coordinates.value.get(name);
      return point ? [point] : [];
    }),
    mapAspect,
  );
}
function choose(selection: MapSelection) {
  emit(
    "update:selection",
    sameMapSelection(props.selection, selection) ? null : selection,
  );
  detailOpen.value = true;
}
watch(
  () => props.selection,
  () => {
    fit();
    detailOpen.value = true;
  },
  { flush: "post" },
);
watch(
  () => props.summary,
  () => {
    if (
      props.selection &&
      (!mapSelectionDetail(props.summary, props.selection).count ||
        (props.selection.type === "route" &&
          props.selection.directional === props.summary.mergeReturns))
    )
      emit("update:selection", null);
    fit();
  },
  { flush: "post" },
);
async function loadMap() {
  if (disposed || pending) return;
  pending = true;
  failed.value = false;
  try {
    const map = await ticketStatisticsApi.map(abort.signal);
    if (disposed) return;
    if (!map.features?.length) throw Error("Empty map");
    echarts.registerMap(
      "ticket-route-explorer",
      map as Parameters<typeof echarts.registerMap>[1],
    );
    const points = new Map<string, [number, number]>(),
      names = new Map<string, string>();
    for (const feature of map.features) {
      const center = featureCenter(feature),
        original = feature.properties?.name || feature.properties?.fullname;
      if (center && original) {
        const name = normalizeTicketCity(original);
        points.set(name, center);
        names.set(name, original);
      }
    }
    coordinates.value = points;
    featureNames.value = names;
    ready.value = true;
    fit();
  } catch {
    if (!disposed) failed.value = true;
  } finally {
    pending = false;
    let mapAspect = 1.8;
  }
}
function clicked(item: { name: string; data: unknown; seriesType?: string }) {
  const route = (item.data as { selection?: MapSelection } | undefined)
    ?.selection;
  if (route) return choose(route);
  const name = normalizeTicketCity(item.name);
  if (props.summary.cities.some((city) => city.name === name))
    choose({ type: "city", name });
}
const mapOption = computed<EChartsCoreOption>(() => {
  const dark = isDarkMode.value,
    colour = currentTheme.value.primary,
    rgb = currentTheme.value.rgb;
  const selected = new Set(props.selection ? detail.value.cities : []);
  const pointData = mappedCities.value.map((city, index) => {
    const active = !props.selection || selected.has(city.name);
    return {
      name: city.name,
      value: [...coordinates.value.get(city.name)!, city.count],
      itemStyle: { opacity: active ? 1 : 0.15 },
      label: { show: props.selection ? active : index < 9 },
    };
  });
  const lines = props.summary.routes.flatMap((route) => {
    const fromName = normalizeTicketCity(route.from),
      toName = normalizeTicketCity(route.to);
    const from = coordinates.value.get(fromName),
      to = coordinates.value.get(toName);
    if (!from || !to || fromName === toName) return [];
    const selection: MapSelection = {
      type: "route",
      from: route.from,
      to: route.to,
      directional: props.summary.mergeReturns === false,
    };
    const active =
      !props.selection ||
      (props.selection.type === "city"
        ? fromName === props.selection.name || toName === props.selection.name
        : sameMapSelection(props.selection, selection));
    return [
      {
        name: `${route.from} ↔ ${route.to}`,
        coords: [from, to],
        value: route.count,
        selection,
        lineStyle: {
          width: active ? Math.min(5, 1.3 + Math.sqrt(route.count) * 0.5) : 0.6,
          opacity: active ? 0.7 : 0.06,
        },
      },
    ];
  });
  const regions = props.summary.cities.flatMap((city) => {
    const name = featureNames.value.get(city.name);
    if (!name) return [];
    const max = Math.max(1, ...props.summary.cities.map((city) => city.count));
    return [
      {
        name,
        itemStyle: {
          areaColor:
            mode.value === "heat"
              ? `rgba(${rgb}, ${0.12 + (city.count / max) * 0.72})`
              : undefined,
        },
      },
    ];
  });
  const flowLines = directionalMapRoutes(props.summary).flatMap((flow) => {
    const base = lines.find(
      (line) =>
        (line.selection.from === flow.from && line.selection.to === flow.to) ||
        (props.summary.mergeReturns &&
          line.selection.from === flow.to &&
          line.selection.to === flow.from),
    );
    if (!base || base.lineStyle.opacity < 0.1) return [];
    const reverse = base.selection.from !== flow.from;
    return [
      {
        name: `${flow.from} → ${flow.to}`,
        value: flow.count,
        coords: reverse ? [...base.coords].reverse() : base.coords,
        lineStyle: { curveness: reverse ? -0.16 : 0.16 },
      },
    ];
  });
  return {
    animation: false,
    tooltip: {
      confine: true,
      backgroundColor: dark ? "#202938" : "#fff",
      borderColor: dark ? "#3b495c" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#334155", fontSize: 12 },
      formatter: (item: { name: string; value?: number | number[] }) => {
        const count =
          (Array.isArray(item.value) ? item.value[2] : item.value) ??
          props.summary.cities.find(
            (city) => city.name === normalizeTicketCity(item.name),
          )?.count;
        const name = echarts.format.encodeHTML(item.name || "");
        return Number.isFinite(count) ? `${name}<br/>${count} 次` : name;
      },
    },
    geo: {
      map: "ticket-route-explorer",
      roam: true,
      center: viewport.value.center,
      zoom: viewport.value.zoom,
      layoutCenter: ["50%", "50%"],
      layoutSize: "100%",
      scaleLimit: { min: 0.7, max: 12 },
      selectedMode: false,
      label: { show: false },
      regions,
      itemStyle: {
        areaColor: dark ? "#1e293b" : `rgba(${rgb}, .025)`,
        borderColor: dark ? "#3b495c" : `rgba(${rgb}, .2)`,
        borderWidth: 0.6,
      },
      emphasis: {
        label: { show: false },
        itemStyle: { areaColor: `rgba(${rgb}, .2)` },
      },
    },
    series: [
      {
        type: "lines",
        coordinateSystem: "geo",
        lineStyle: { color: colour, curveness: 0.16 },
        data: mode.value === "routes" ? lines : [],
        emphasis: { lineStyle: { width: 6, opacity: 1 } },
        z: 2,
      },
      {
        type: "effectScatter",
        coordinateSystem: "geo",
        showEffectOn: "emphasis",
        symbolSize: (value: number[]) =>
          5 + Math.min(11, Math.sqrt(value[2]) * 1.3),
        label: {
          position: "right",
          formatter: "{b}",
          fontSize: 11,
          color: dark ? "#cbd5e1" : "#536176",
        },
        labelLayout: { hideOverlap: true },
        itemStyle: { color: colour },
        data: mode.value === "heat" ? [] : pointData,
        z: 3,
        zlevel: 2,
      },
      {
        id: "route-flow-arrows",
        type: "lines",
        coordinateSystem: "geo",
        silent: true,
        zlevel: 1,
        lineStyle: { color: colour, width: 0, curveness: 0.16 },
        effect: {
          show: !reducedMotion.value && mode.value === "routes",
          period: 5.5,
          trailLength: 0.06,
          symbol: "arrow",
          symbolSize: 7,
          color: colour,
        },
        data: mode.value === "routes" && !reducedMotion.value ? flowLines : [],
      },
    ],
  };
});

// Render the same state in the overview and the expanded dialog, with one active canvas.
const MapContent = defineComponent({
  props: { large: Boolean },
  setup(contentProps) {
    const chart = ref<InstanceType<typeof StatisticsChart>>();
    const host = ref<HTMLElement>();
    let sizeObserver: ResizeObserver | undefined;
    onMounted(() => {
      if (host.value) {
        sizeObserver = new ResizeObserver(([entry]) => {
          if (entry.contentRect.height)
            mapAspect = entry.contentRect.width / entry.contentRect.height;
        });
        sizeObserver.observe(host.value);
      }
    });
    onBeforeUnmount(() => sizeObserver?.disconnect());
    const button = (label: string, icon: unknown, action: () => void) =>
      h(
        "button",
        {
          class: "ts-icon-button ts-button-secondary ts-button-sm",
          "aria-label": label,
          title: label,
          onClick: action,
        },
        [h(icon as typeof Plus, { class: "h-4 w-4" })],
      );
    return () =>
      h(
        "div",
        {
          class: [
            "explorer-content",
            {
              "is-large": contentProps.large,
              "has-selection": !!props.selection,
            },
          ],
        },
        [
          h(
            "div",
            {
              class: [
                "explorer-canvas",
                { "heat-mode": mode.value === "heat" },
              ],
              ref: host,
            },
            [
              ready.value
                ? h(StatisticsChart, {
                    ref: chart,
                    option: mapOption.value,
                    label: "出行城市与路线地图",
                    onItemSelect: clicked,
                    onViewport: (value: MapViewport) => {
                      viewport.value = value;
                    },
                  })
                : h(
                    "div",
                    { class: "map-state" },
                    failed.value
                      ? [
                          h("span", "地图加载失败"),
                          h(
                            "button",
                            {
                              class:
                                "ts-button ts-button-secondary ts-button-sm",
                              onClick: loadMap,
                            },
                            "重试",
                          ),
                        ]
                      : [
                          h("span", {
                            class: "map-spinner",
                            role: "status",
                            "aria-label": "正在加载地图",
                          }),
                        ],
                  ),
              h("div", { class: "map-controls" }, [
                button("放大一级", Plus, () => chart.value?.zoom(1.3)),
                button("缩小一级", Minus, () => chart.value?.zoom(1 / 1.3)),
                button("适配路线", LocateFixed, fit),
                button("全国视角", Globe2, () => {
                  viewport.value = nationalViewport();
                }),
              ]),
              h("div", { class: "map-counts" }, [
                h("span", `${props.summary.cityCount} 座城市`),
                h("span", `${props.summary.count} 段行程`),
                h("span", `${props.summary.routes.length} 条路线`),
              ]),
              mode.value === "heat"
                ? h(
                    "div",
                    { class: "heat-key", "aria-label": "城市出行次数色阶" },
                    [
                      h("span", "0"),
                      h("span", {
                        class: "heat-gradient",
                        style: {
                          background: `linear-gradient(90deg, rgba(${currentTheme.value.rgb}, .12), rgba(${currentTheme.value.rgb}, .84))`,
                        },
                      }),
                      h(
                        "span",
                        `${Math.max(0, ...props.summary.cities.map((city) => city.count))} 次`,
                      ),
                    ],
                  )
                : null,
            ],
          ),
          props.selection
            ? h(
                "aside",
                {
                  class: ["map-detail", { collapsed: !detailOpen.value }],
                  "aria-label": "地图选择详情",
                },
                [
                  h("div", { class: "detail-heading" }, [
                    h("h3", selectionTitle.value),
                    h(
                      "button",
                      {
                        class:
                          "detail-toggle ts-icon-button ts-button-ghost ts-button-sm",
                        "aria-label": detailOpen.value
                          ? "收起明细"
                          : "展开明细",
                        "aria-expanded": detailOpen.value,
                        onClick: () => {
                          detailOpen.value = !detailOpen.value;
                        },
                      },
                      [
                        h(detailOpen.value ? ChevronDown : ChevronUp, {
                          class: "h-4 w-4",
                        }),
                      ],
                    ),
                    button("取消地图选择", X, () =>
                      emit("update:selection", null),
                    ),
                  ]),
                  h("div", { class: "detail-body" }, [
                    h("div", { class: "detail-metrics" }, [
                      h("div", [
                        h("strong", nf(detail.value.count)),
                        h("span", "行程段"),
                      ]),
                      h("div", [
                        h("strong", nf(detail.value.distance)),
                        h("span", "km"),
                      ]),
                      h("div", [
                        h("strong", nf(detail.value.amount)),
                        h("span", "元"),
                      ]),
                      h("div", [
                        h(
                          "strong",
                          formatTravelDuration(detail.value.duration),
                        ),
                        h("span", "乘坐时长"),
                      ]),
                    ]),
                    h("h4", `票据 · ${detail.value.tickets.length}`),
                    h(
                      "ul",
                      { class: "map-ticket-list" },
                      detail.value.tickets.map((ticket) =>
                        h("li", { key: ticket.key }, [
                          h(
                            RouterLink,
                            {
                              to: ticketLink(ticket),
                              class: "map-ticket-link",
                            },
                            () => [
                              h("div", [
                                h("strong", ticket.code),
                                h(
                                  "time",
                                  ticket.date_time
                                    ?.replace("T", " ")
                                    .slice(0, 16) || "—",
                                ),
                              ]),
                              h("span", `${ticket.from} → ${ticket.to}`),
                              h(
                                "small",
                                [
                                  ticket.name,
                                  ticket.price ? `${nf(ticket.price)} 元` : "",
                                ]
                                  .filter(Boolean)
                                  .join(" · "),
                              ),
                            ],
                          ),
                          ...ticket.memories.slice(0, 2).map((memory) =>
                            h(
                              RouterLink,
                              {
                                to: contextLink(memory),
                                class: "map-memory-link",
                              },
                              () => memory.title,
                            ),
                          ),
                        ]),
                      ),
                    ),
                  ]),
                ],
              )
            : h(
                "aside",
                { class: "map-overview", "aria-label": "地图城市排行" },
                [
                  h("h3", "到达城市"),
                  ...props.summary.arrivals.slice(0, 8).map((city, index) =>
                    h(
                      "button",
                      {
                        class: "city-shortcut",
                        onClick: () =>
                          choose({ type: "city", name: city.name }),
                        "aria-label": `在地图选择${city.name}`,
                      },
                      [
                        h("small", String(index + 1).padStart(2, "0")),
                        h("span", city.name),
                        h("strong", `${city.count} 次`),
                      ],
                    ),
                  ),
                ],
              ),
        ],
      );
  },
});
onMounted(() => {
  void loadMap();
});
onBeforeUnmount(() => {
  disposed = true;
  abort.abort();
});
defineExpose({
  focus: () =>
    (card.value as unknown as { $el?: HTMLElement })?.$el?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "center",
    }),
});
const card = ref();
</script>

<style scoped>
.route-explorer {
  margin-bottom: 20px;
  overflow: hidden;
}
.explorer-heading,
.explorer-actions,
.expanded-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.explorer-heading {
  justify-content: space-between;
  padding: 18px 22px 0;
}
.explorer-heading h2 {
  font-size: 16px;
  font-weight: 650;
}
.map-tabs {
  display: flex;
  flex-shrink: 0;
  gap: 3px;
  padding: 3px;
  border-radius: 10px;
  background: var(--ts-color-surface-muted);
}
.map-tabs button {
  min-height: 36px;
  padding: 0 15px;
  border-radius: 8px;
  color: var(--ts-color-text-secondary);
  font-size: 12px;
}
.map-tabs button.active {
  background: var(--ts-color-surface);
  color: var(--theme-primary);
  font-weight: 600;
  box-shadow: 0 1px 4px rgb(0 0 0 / 5%);
}
.expanded-toolbar {
  flex-wrap: wrap;
  justify-content: space-between;
  margin-bottom: 14px;
}
/* MapContent is a local render component; deep selectors keep its DOM scoped here. */
:deep(.explorer-content) {
  display: flex;
  min-width: 0;
  height: 460px;
}
:deep(.explorer-canvas) {
  position: relative;
  min-width: 0;
  flex: 1;
  height: 100%;
}
:deep(.map-controls) {
  position: absolute;
  left: 16px;
  bottom: 44px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
:deep(.map-controls button),
:deep(.detail-heading button) {
  width: 38px;
  height: 38px;
  min-height: 38px;
  box-shadow: var(--ts-shadow-card);
}
:deep(.map-counts) {
  position: absolute;
  left: 20px;
  bottom: 13px;
  display: flex;
  gap: 18px;
  pointer-events: none;
  font-size: 11px;
  color: var(--ts-color-text-secondary);
}
:deep(.heat-key) {
  position: absolute;
  right: 16px;
  bottom: 13px;
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--ts-color-text-secondary);
  font-size: 10px;
  pointer-events: none;
}
:deep(.heat-gradient) {
  width: 65px;
  height: 6px;
  border-radius: 4px;
}
:deep(.heat-mode .map-counts) {
  bottom: 33px;
}
:deep(.heat-mode .map-controls) {
  bottom: 66px;
}
:deep(.map-detail) {
  flex: 0 0 310px;
  min-width: 0;
  border-left: 1px solid var(--ts-color-divider);
  display: flex;
  flex-direction: column;
}
:deep(.detail-heading) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ts-color-divider);
}
:deep(.detail-heading h3) {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.detail-toggle) {
  display: none;
}
:deep(.detail-body) {
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  flex: 1;
  overscroll-behavior: contain;
}
:deep(.detail-metrics) {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px 12px;
  margin-bottom: 22px;
}
:deep(.detail-metrics > div) {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
:deep(.detail-metrics strong) {
  font-size: 18px;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
:deep(.detail-metrics span) {
  font-size: 10px;
  color: var(--ts-color-text-secondary);
}
:deep(.detail-body h4) {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 12px;
}
:deep(.map-ticket-list) {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
:deep(.map-ticket-list li) {
  border-top: 1px solid var(--ts-color-divider);
  padding-top: 10px;
}
:deep(.map-ticket-link) {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12px;
  border-radius: 6px;
  padding: 3px;
}
:deep(.map-ticket-link > div) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
:deep(.map-ticket-link time),
:deep(.map-ticket-link small) {
  font-size: 10px;
  color: var(--ts-color-text-secondary);
}
:deep(.map-ticket-link:hover),
:deep(.map-memory-link:hover) {
  color: var(--theme-primary);
}
:deep(.map-memory-link) {
  display: block;
  margin-top: 7px;
  padding-inline: 3px;
  color: var(--theme-primary);
  font-size: 11px;
}
:deep(.map-state) {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 12px;
  color: var(--ts-color-text-secondary);
}
:deep(.map-spinner) {
  width: 25px;
  height: 25px;
  border: 3px solid var(--ts-color-border);
  border-top-color: var(--theme-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
:deep(.is-large) {
  height: 100%;
}
:deep(button:focus-visible),
:deep(a:focus-visible) {
  outline: 2px solid var(--theme-primary);
  outline-offset: 2px;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  :deep(.map-spinner) {
    animation: none;
  }
}
@media (max-width: 767px) {
  .explorer-heading {
    padding: 12px 12px 0;
    gap: 8px;
  }
  .explorer-heading h2 {
    font-size: 14px;
  }
  .explorer-actions {
    gap: 8px;
  }
  .map-tabs button {
    padding: 0 10px;
    min-height: 40px;
  }
  .map-tabs {
    gap: 1px;
  }
  :deep(.explorer-content) {
    height: auto;
    flex-direction: column;
  }
  :deep(.explorer-canvas) {
    flex: none;
    width: 100%;
    height: 340px;
  }
  :deep(.map-controls) {
    left: 12px;
    bottom: 46px;
  }
  :deep(.map-controls button),
  :deep(.detail-heading button) {
    width: 44px;
    height: 44px;
    min-height: 44px;
  }
  :deep(.map-detail) {
    border-left: 0;
    border-top: 1px solid var(--ts-color-divider);
    flex: none;
    max-height: 290px;
  }
  :deep(.detail-toggle) {
    display: inline-flex;
  }
  :deep(.map-detail.collapsed .detail-body) {
    display: none;
  }
  :deep(.map-counts) {
    left: 14px;
    gap: 12px;
    font-size: 10px;
  }
  :deep(.is-large) {
    height: 100%;
    min-height: 0;
  }
  :deep(.is-large .explorer-canvas) {
    flex: 1;
    height: auto;
    min-height: 200px;
  }
  :deep(.is-large .map-detail) {
    max-height: 42%;
    flex-shrink: 0;
  }
  :deep(.map-overview) {
    display: none;
  }
  .expanded-toolbar {
    gap: 10px;
  }
}

.expanded-map-shell {
  flex: 1;
  min-height: 0;
}
.expanded-toolbar {
  flex-shrink: 0;
}
:global(.route-map-dialog .responsive-dialog-body) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
:deep(.map-overview) {
  width: 245px;
  flex: 0 0 245px;
  border-left: 1px solid var(--ts-color-divider);
  padding: 12px 20px;
  overflow-y: auto;
}
:deep(.map-overview h3) {
  font-size: 13px;
  font-weight: 600;
  padding-block: 10px;
}
:deep(.city-shortcut) {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  width: 100%;
  padding: 8px;
  border-radius: 8px;
  text-align: left;
  font-size: 12px;
}
:deep(.city-shortcut:hover) {
  background: rgba(var(--theme-rgb), 0.07);
  color: var(--theme-primary);
}
:deep(.city-shortcut small) {
  color: var(--ts-color-text-tertiary);
  font-size: 10px;
}
:deep(.city-shortcut strong) {
  margin-left: auto;
  color: var(--ts-color-text-secondary);
  font-size: 11px;
  font-weight: 500;
}
@media (min-width: 768px) {
  :global(.route-map-dialog) {
    height: min(90dvh, 1000px);
  }
}
@media (max-width: 767px) {
  :deep(.map-overview) {
    display: none;
  }
}
</style>
