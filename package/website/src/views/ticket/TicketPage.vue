<template>
  <div
    class="ticket-wallet ts-browse-page mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)] pb-8 pt-0 sm:py-6"
  >
    <header
      class="ts-browse-header mb-5 flex items-center justify-between gap-3"
    >
      <div class="min-w-0"><h1 class="ts-page-title">票夹</h1></div>
      <div class="ts-liquid-glass ts-glass-toolbar flex shrink-0">
        <button
          class="ts-glass-button"
          aria-label="搜索票据"
          :aria-expanded="showSearch"
          @click="showSearch = !showSearch"
        >
          <Search class="h-5 w-5" />
        </button>
        <button
          class="ts-glass-button"
          aria-label="新增票据"
          @click="typeOpen = true"
        >
          <Plus class="h-5 w-5" />
        </button>
        <div class="relative">
          <button
            class="ts-glass-button"
            aria-label="更多票夹操作"
            :aria-expanded="moreOpen"
            @click="moreOpen = !moreOpen"
          >
            <MoreHorizontal class="h-5 w-5" />
          </button>
          <AdaptiveMenu
            v-model="moreOpen"
            title="票夹操作"
            mobile-presentation="popover"
            glass
          >
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                viewMode = viewMode === 'timeline' ? 'grid' : 'timeline';
              "
            >
              <LayoutGrid v-if="viewMode === 'timeline'" /><ListTree v-else />{{
                viewMode === "timeline" ? "切换卡片视图" : "按月浏览"
              }}
            </button>
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                beginSelection();
              "
            >
              <CheckSquare />选择票据
            </button>
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                inputFile?.click();
              "
            >
              <Upload />导入票据
            </button>
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                exportOpen = true;
              "
            >
              <Download />导出票据
            </button>
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                router.push('/statistics');
              "
            >
              <BarChart2 />交通统计
            </button>
            <button
              class="ts-action-row"
              @click="
                moreOpen = false;
                store.fetch();
              "
            >
              <RefreshCw />刷新
            </button>
          </AdaptiveMenu>
        </div>
      </div>
    </header>
    <input
      v-if="showSearch"
      v-model="search"
      type="search"
      aria-label="搜索票据"
      placeholder="搜索地点、车次、航班或乘车人"
      class="ts-input w-full mb-4"
    />
    <input
      ref="inputFile"
      type="file"
      accept=".json,.csv"
      class="hidden"
      @change="importFile"
    />
    <div
      v-if="contextId || journey"
      class="ts-surface p-3 mb-4 flex items-center gap-3 text-sm"
    >
      <span class="min-w-0 break-words">{{
        journey ? "旅程候选 · 时间相近，尚未确认" : "当前经历的相关票据"
      }}</span
      ><button
        class="ts-button ts-button-ghost ml-auto shrink-0"
        @click="clearContext"
      >
        查看全部
      </button>
    </div>
    <div
      class="mb-5 flex items-center justify-between gap-2 border-b border-gray-200 dark:border-gray-800"
    >
      <nav class="flex min-w-0 gap-4 sm:gap-6" aria-label="票据类型">
        <button
          v-for="tab in typeTabs"
          :key="tab.value"
          class="-mb-px min-h-11 whitespace-nowrap border-b-2 px-0.5 text-sm font-medium"
          :class="
            activeType === tab.value
              ? 'border-primary-500 text-primary-600 dark:text-primary-400'
              : 'border-transparent text-gray-500 dark:text-gray-400'
          "
          :aria-pressed="activeType === tab.value"
          @click="filters.type = tab.value"
        >
          {{ tab.label }}
        </button>
      </nav>
      <button
        class="flex min-h-11 shrink-0 items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400"
        @click="openFilters"
      >
        <SlidersHorizontal class="h-4 w-4" />筛选<span v-if="filterCount"
          >({{ filterCount }})</span
        >
      </button>
    </div>
    <div v-if="filterCount" class="flex flex-wrap gap-2 mb-3">
      <button
        v-for="chip in chips"
        :key="chip.key"
        class="ts-button ts-button-sm ts-button-secondary"
        :aria-label="`移除${chip.label}筛选`"
        @click="removeFilter(chip.key)"
      >
        {{ chip.label }} ×</button
      ><button class="ts-button ts-button-ghost" @click="resetFilters">
        清空筛选
      </button>
    </div>

    <div
      v-if="selecting"
      class="ts-surface p-3 mb-4 flex flex-wrap items-center justify-between gap-2"
    >
      <span class="text-sm">已选择 {{ selected.length }} 张</span
      ><button
        class="ts-button ts-button-ghost"
        @click="
          selected =
            selected.length === filtered.length
              ? []
              : filtered.map((item) => item.key)
        "
      >
        全选当前结果 {{ filtered.length }} 张</button
      ><button
        class="ts-button ts-button-secondary"
        @click="
          selecting = false;
          selected = [];
        "
      >
        退出
      </button>
    </div>
    <div v-if="store.error" class="ts-surface p-4 mb-4 text-sm">
      <p>
        {{ store.error
        }}{{ store.items.length ? "，当前显示上次加载的内容" : "" }}
      </p>
      <button class="ts-button ts-button-secondary mt-2" @click="store.fetch()">
        重试
      </button>
    </div>
    <p
      v-if="store.loading && !store.items.length"
      class="py-16 text-center text-gray-500 dark:text-gray-400"
    >
      正在加载票夹…
    </p>
    <div v-else-if="filtered.length" class="space-y-7">
      <section
        v-for="group in visibleGroups"
        :key="group.key"
        :aria-label="group.title"
      >
        <div class="mb-3 flex items-center justify-between gap-3">
          <h2 class="ts-section-title text-gray-900 dark:text-white">
            {{ group.title }}
          </h2>
          <span class="shrink-0 text-xs text-gray-500 dark:text-gray-400"
            >{{ group.total }} 张</span
          >
        </div>
        <div class="grid gap-2.5 lg:grid-cols-2 xl:grid-cols-3">
          <WalletTicketCard
            v-for="ticket in group.items"
            :key="ticket.key"
            :ticket="ticket"
            :selecting="selecting"
            :selected="selected.includes(ticket.key)"
            @open="openDetail(ticket)"
            @select="toggle(ticket.key)"
            @associate="associate([ticket])"
            @edit="editTicket(ticket)"
            @delete="deleteTickets([ticket])"
          />
        </div>
      </section>
    </div>
    <div v-else-if="!store.error" class="py-12 text-center">
      <Ticket class="h-12 w-12 mx-auto text-primary-500 mb-4" />
      <h2 class="text-lg font-semibold">
        {{
          store.items.length || filterCount || contextId || journey
            ? "没有符合条件的票据"
            : "还没有票据"
        }}
      </h2>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
        留下一张票据，找回一段经历
      </p>
      <button
        v-if="store.items.length"
        class="ts-button ts-button-secondary mt-4"
        @click="
          resetFilters();
          clearContext();
        "
      >
        清空条件</button
      ><button
        v-else
        class="ts-button ts-button-primary mt-4"
        @click="typeOpen = true"
      >
        新增票据
      </button>
    </div>
    <button
      v-if="filtered.length > visibleLimit"
      class="ts-button ts-button-secondary w-full mt-4"
      @click="visibleLimit += 50"
    >
      加载更多（{{ Math.min(visibleLimit, filtered.length) }} /
      {{ filtered.length }}）
    </button>
    <div
      v-if="selecting"
      class="fixed inset-x-3 bottom-[calc(1rem_+_var(--ts-safe-area-bottom))] z-40 ts-surface p-3 flex flex-wrap justify-center gap-2 shadow-lg"
    >
      <button
        class="ts-button ts-button-primary"
        :disabled="!selected.length || busy"
        @click="associate(selectedItems)"
      >
        关联</button
      ><button
        class="ts-button ts-button-secondary"
        :disabled="!selected.length || busy"
        @click="exportOpen = true"
      >
        导出</button
      ><button
        class="ts-button ts-button-secondary text-red-600 dark:text-red-400"
        :disabled="!selected.length || busy"
        @click="deleteTickets(selectedItems)"
      >
        删除 {{ selected.length || "" }}
      </button>
    </div>
    <ResponsiveDialog history v-model="filterOpen" title="筛选与排序">
      <div class="space-y-4">
        <label class="block text-sm"
          >类型<select v-model="draft.type" class="ts-input mt-2 w-full">
            <option value="all">全部票据</option>
            <option value="transport">全部交通票据</option>
            <option value="train">火车票</option>
            <option value="highspeed">高铁/动车</option>
            <option value="normal">普速列车</option>
            <option value="flight">机票</option>
          </select></label
        >
        <div class="grid grid-cols-2 gap-3">
          <label class="text-sm"
            >开始日期<input
              v-model="draft.start"
              class="ts-input mt-2 w-full min-w-0"
              type="date" /></label
          ><label class="text-sm"
            >结束日期<input
              v-model="draft.end"
              class="ts-input mt-2 w-full min-w-0"
              type="date"
          /></label>
        </div>
        <label class="block text-sm"
          >关联状态<select v-model="draft.linked" class="ts-input mt-2 w-full">
            <option value="all">全部</option>
            <option value="yes">已关联</option>
            <option value="no">未关联</option>
          </select></label
        >
        <label class="block text-sm"
          >关联相册<select v-model="draft.album" class="ts-input mt-2 w-full">
            <option value="">全部相册</option>
            <option
              v-for="context in albumChoices"
              :key="context.id"
              :value="context.id"
            >
              {{ context.title }}
            </option>
          </select></label
        >
        <label class="block text-sm"
          >关联回忆<select v-model="draft.memory" class="ts-input mt-2 w-full">
            <option value="">全部回忆</option>
            <option
              v-for="context in memoryChoices"
              :key="context.id"
              :value="context.id"
            >
              {{ context.title }}
            </option>
          </select></label
        >
        <label class="block text-sm"
          >乘车/乘机人<select
            v-model="draft.person"
            class="ts-input mt-2 w-full"
          >
            <option value="">全部</option>
            <option v-for="person in passengers" :key="person">
              {{ person }}
            </option>
          </select></label
        >
        <label class="block text-sm"
          >排序<select v-model="draft.sort" class="ts-input mt-2 w-full">
            <option
              v-for="(label, value) in availableSortLabels"
              :key="value"
              :value="value"
            >
              {{ label }}
            </option>
          </select></label
        >
      </div>
      <template #footer
        ><div class="flex gap-3">
          <button
            class="ts-button ts-button-secondary"
            @click="draft = defaults()"
          >
            重置</button
          ><button
            class="ts-button ts-button-primary flex-1"
            @click="applyFilters"
          >
            应用
          </button>
        </div></template
      >
    </ResponsiveDialog>
    <ResponsiveDialog history v-model="typeOpen" title="新增票据"
      ><div class="grid grid-cols-2 gap-3">
        <button
          v-for="type in supportedTypes"
          :key="type"
          class="ts-surface p-6 min-h-24 text-primary-600 dark:text-primary-400"
          @click="startNew(type)"
        >
          <component
            :is="type === 'train' ? TrainFront : Plane"
            class="h-8 w-8 mx-auto mb-3"
          />{{ ticketLabel(type) }}
        </button>
      </div></ResponsiveDialog
    >
    <TicketFormModal
      :is-open="trainOpen"
      :is-editing="!!editing"
      :initial-data="trainInitial"
      :current-theme="currentTheme"
      :saving="saving"
      @save="saveTrain"
      @cancel="trainOpen = false"
    />
    <FlightTicketFormModal
      :is-open="flightOpen"
      :is-editing="!!editing"
      :initial-data="flightInitial"
      :current-theme="currentTheme"
      :saving="saving"
      @save="saveFlight"
      @cancel="flightOpen = false"
    />
    <TicketDetailDialog
      v-model="detailOpen"
      :reference="detailRef"
      @edit="editTicket"
      @delete="(item) => deleteTickets([item])"
      @paper="openPaper"
      @export="exportSingle"
      @photo="openPhoto"
    />
    <TicketAssociationDialog
      v-model="associationOpen"
      :tickets="associationTickets"
      :existing="
        associationTickets.length === 1
          ? store.items.find(
              (item) => item.key === ticketKey(associationTickets[0]!),
            )
          : undefined
      "
    />
    <ResponsiveDialog history v-model="exportOpen" title="导出票据"
      ><p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
        {{
          exportOnly.length
            ? `这张票据`
            : selected.length
              ? `已选 ${selected.length} 张`
              : `当前筛选 ${filtered.length} 张`
        }}。纪念 PNG 支持
        {{ exportItems.filter((item) => item.type === "train").length }}
        张火车票，其他
        {{ exportItems.filter((item) => item.type !== "train").length }}
        张将跳过。
      </p>
      <div class="space-y-2">
        <button
          class="ts-action-row"
          :disabled="busy"
          @click="exportData('json')"
        >
          <Download />票据备份（JSON）</button
        ><button
          class="ts-action-row"
          :disabled="busy"
          @click="exportData('csv')"
        >
          <Download />表格数据（CSV）</button
        ><button
          class="ts-action-row"
          :disabled="busy || !exportItems.some((item) => item.type === 'train')"
          @click="exportPng()"
        >
          <Ticket />{{
            busy ? `导出中 ${exportProgress}%` : "火车票纪念票面（PNG）"
          }}
        </button>
      </div></ResponsiveDialog
    >
    <ResponsiveDialog
      history
      v-model="paperOpen"
      title="纪念票面"
      max-width="58rem"
      ><p class="mb-4 text-xs text-gray-500 dark:text-gray-400">
        仅用于纪念展示，不可作为乘车凭证。
      </p>
      <TrainTicket
        v-if="paperTicket"
        :ticket="legacyTicket(paperTicket)"
        :ticket_style="paperStyle"
      /><label class="block mt-4 text-sm"
        >票面样式<select v-model="paperStyle" class="ts-input ml-3">
          <option value="blue">蓝票</option>
          <option value="red">红票</option>
        </select></label
      ><template #footer
        ><button
          class="ts-button ts-button-primary"
          :disabled="busy"
          @click="paperTicket && exportPng([paperTicket])"
        >
          导出图片
        </button></template
      ></ResponsiveDialog
    >
    <div class="fixed -left-[9999px] top-0 w-[856px]" aria-hidden="true">
      <TrainTicket
        v-if="exportTicket"
        ref="paperRef"
        :ticket="legacyTicket(exportTicket)"
        :ticket_style="paperStyle"
      />
    </div>
    <PhotoLightbox
      class="wallet-photo-viewer"
      :visible="photoOpen"
      :image="photo"
      @close="photoOpen = false"
    />
  </div>
</template>
<script setup lang="ts">
import {
  computed,
  ref,
  toRef,
  watch,
  onMounted,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
  nextTick,
} from "vue";
import { useRoute, useRouter, onBeforeRouteLeave } from "vue-router";
import { useStorage } from "@vueuse/core";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Search,
  Plus,
  MoreHorizontal,
  CheckSquare,
  Upload,
  Download,
  BarChart2,
  RefreshCw,
  SlidersHorizontal,
  LayoutGrid,
  ListTree,
  Ticket,
  TrainFront,
  Plane,
} from "lucide-vue-next";
import { toPng } from "html-to-image";
import AdaptiveMenu from "@/components/ui/AdaptiveMenu.vue";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import TicketFormModal from "@/components/TicketFormModal.vue";
import FlightTicketFormModal from "@/components/FlightTicketFormModal.vue";
import TrainTicket from "@/components/TrainTicket.vue";
import PhotoLightbox from "@/components/PhotoLightbox.vue";
import WalletTicketCard from "./components/WalletTicketCard.vue";
import TicketDetailDialog from "./components/TicketDetailDialog.vue";
import TicketAssociationDialog from "./components/TicketAssociationDialog.vue";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import { useUiStore } from "@/stores/uiStore";
import { ticketWalletApi } from "@/api/ticketWallet";
import { ticketService } from "@/api/ticketService";
import { injectTheme } from "@/composables/useTheme";
import { toServerUrl } from "@/config/server";
import { thumbnailUrl } from "@/utils/mediaUrl";
import {
  ticketKey,
  ticketLabel,
  type WalletTicket,
  type TicketRef,
  type SupportedTicketType,
} from "@/types/ticketWallet";
import type { AlbumImage } from "@/types/album";
import type { TicketFormData, FlightTicketFormData } from "@/types/ticket";
const store = useTicketWalletStore(),
  ui = useUiStore(),
  route = useRoute(),
  router = useRouter();
const { currentTheme } = injectTheme();
const defaults = () => ({
  type: "all",
  start: "",
  end: "",
  linked: "all",
  person: "",
  album: "",
  memory: "",
  sort: "date",
});
const filters = toRef(store.browse, "filters"),
  draft = ref(defaults()),
  search = toRef(store.browse, "search");
const typeTabs = [
  { value: "all", label: "全部" },
  { value: "train", label: "火车票" },
  { value: "flight", label: "机票" },
];
const activeType = computed(() =>
  ["highspeed", "normal"].includes(filters.value.type)
    ? "train"
    : filters.value.type === "transport"
      ? "all"
      : filters.value.type,
);
const viewMode = useStorage<"timeline" | "grid">(
  "ticket-view-mode",
  "timeline",
);
const supportedTypes: SupportedTicketType[] = ["train", "flight"];
const showSearch = ref(Boolean(search.value)),
  moreOpen = ref(false),
  filterOpen = ref(false),
  selecting = ref(false),
  selected = ref<string[]>([]),
  visibleLimit = toRef(store.browse, "visibleLimit"),
  busy = ref(false);
const typeOpen = ref(false),
  trainOpen = ref(false),
  flightOpen = ref(false),
  saving = ref(false),
  editing = ref<WalletTicket | null>(null);
const detailOpen = ref(false),
  detailRef = ref<TicketRef | null>(null),
  associationOpen = ref(false),
  associationTickets = ref<TicketRef[]>([]);
const exportOpen = ref(false),
  exportOnly = ref<WalletTicket[]>([]),
  paperOpen = ref(false),
  paperTicket = ref<WalletTicket | null>(null),
  exportTicket = ref<WalletTicket | null>(null),
  paperStyle = ref<"red" | "blue">("blue"),
  exportProgress = ref(0),
  paperRef = ref<InstanceType<typeof TrainTicket> | null>(null);
const photoOpen = ref(false),
  photo = ref<AlbumImage | null>(null),
  inputFile = ref<HTMLInputElement | null>(null);
const contextKind = computed(() => (route.query.album_id ? "album" : "memory"));
const contextId = computed(() =>
  String(route.query.album_id || route.query.memory_id || ""),
);
const journey = computed(() => Boolean(route.query.start || route.query.end));
const sortLabels: Record<string, string> = {
  date: "最新优先",
  price: "票价从高到低",
  distance: "里程从长到短",
  duration: "时长从长到短",
};
const availableSortLabels = computed(() =>
  draft.value.type === "all"
    ? { date: sortLabels.date, price: sortLabels.price }
    : sortLabels,
);
watch(
  () => draft.value.type,
  (value) => {
    if (value === "all" && ["distance", "duration"].includes(draft.value.sort))
      draft.value.sort = "date";
  },
);
watch(
  () => filters.value.type,
  (value) => {
    if (
      value === "all" &&
      ["distance", "duration"].includes(filters.value.sort)
    ) {
      filters.value.sort = "date";
      ElMessage.info("已恢复按日期排序");
    }
  },
);
const passengers = computed(() => [
  ...new Set(store.items.map((item) => item.name).filter(Boolean)),
]);
const albumChoices = computed(() => [
  ...new Map(
    store.items
      .flatMap((item) => item.albums)
      .map((context) => [context.id, context]),
  ).values(),
]);
const memoryChoices = computed(() => [
  ...new Map(
    store.items
      .flatMap((item) => item.memories)
      .map((context) => [context.id, context]),
  ).values(),
]);
const filtered = computed(() =>
  store.items
    .filter((item) => {
      const f = filters.value,
        query = search.value.toLowerCase();
      if (
        query &&
        !`${item.title} ${item.code} ${item.name}`.toLowerCase().includes(query)
      )
        return false;
      if (
        contextId.value &&
        !(
          contextKind.value === "album"
            ? item.albums
            : [...item.memories, ...item.candidates]
        ).some((context) => context.id === contextId.value)
      )
        return false;
      const date = item.date_time?.slice(0, 10) || "";
      if ((f.start && date < f.start) || (f.end && date > f.end)) return false;
      if (
        route.query.start &&
        (!item.date_time ||
          new Date(item.date_time).getTime() <
            new Date(String(route.query.start)).getTime())
      )
        return false;
      if (
        route.query.end &&
        (!item.date_time ||
          new Date(item.date_time).getTime() >=
            new Date(String(route.query.end)).getTime())
      )
        return false;
      if (f.person && item.name !== f.person) return false;
      if (f.album && !item.albums.some((context) => context.id === f.album))
        return false;
      if (f.memory && !item.memories.some((context) => context.id === f.memory))
        return false;
      const linked = !!(item.albums.length || item.memories.length);
      if ((f.linked === "yes" && !linked) || (f.linked === "no" && linked))
        return false;
      if (["train", "flight"].includes(f.type) && item.type !== f.type)
        return false;
      if (
        ["highspeed", "normal"].includes(f.type) &&
        (item.type !== "train" ||
          /^[GDC]/i.test(item.code) !== (f.type === "highspeed"))
      )
        return false;
      return true;
    })
    .sort((a, b) =>
      filters.value.sort === "date"
        ? (b.date_time || "").localeCompare(a.date_time || "") ||
          a.key.localeCompare(b.key)
        : sortValue(b) - sortValue(a),
    ),
);
const selectedItems = computed(() =>
  filtered.value.filter((item) => selected.value.includes(item.key)),
);
const visibleGroups = computed(() => {
  const monthly =
    viewMode.value === "timeline" && filters.value.sort === "date";
  const totals = new Map<string, number>();
  const groups = new Map<
    string,
    { key: string; title: string; total: number; items: WalletTicket[] }
  >();
  for (const item of filtered.value) {
    const key = monthly ? item.date_time?.slice(0, 7) || "unknown" : "all";
    totals.set(key, (totals.get(key) || 0) + 1);
  }
  for (const item of filtered.value.slice(0, visibleLimit.value)) {
    const key = monthly ? item.date_time?.slice(0, 7) || "unknown" : "all";
    if (!groups.has(key))
      groups.set(key, {
        key,
        title:
          key === "all"
            ? `全部票据 · ${sortLabels[filters.value.sort]}`
            : key === "unknown"
              ? "日期待补充"
              : `${key.slice(0, 4)} 年 ${Number(key.slice(5))} 月`,
        total: totals.get(key) || 0,
        items: [],
      });
    groups.get(key)!.items.push(item);
  }
  return [...groups.values()];
});
const exportItems = computed(() =>
  exportOnly.value.length
    ? exportOnly.value
    : selected.value.length
      ? selectedItems.value
      : filtered.value,
);
watch(exportOpen, (value) => {
  if (!value) exportOnly.value = [];
});
function exportSingle(item: WalletTicket) {
  exportOnly.value = [item];
  exportOpen.value = true;
}
const chips = computed(() =>
  (Object.keys(defaults()) as Array<keyof ReturnType<typeof defaults>>)
    .filter(
      (key) =>
        filters.value[key] !== defaults()[key] &&
        !(
          key === "type" &&
          ["train", "flight", "transport"].includes(filters.value.type)
        ),
    )
    .map((key) => ({
      key,
      label:
        key === "type"
          ? (
              {
                transport: "交通",
                train: "火车票",
                flight: "机票",
                highspeed: "高铁/动车",
                normal: "普速",
              } as Record<string, string>
            )[filters.value[key]]
          : key === "linked"
            ? filters.value[key] === "yes"
              ? "已关联"
              : "未关联"
            : key === "album"
              ? albumChoices.value.find(
                  (context) => context.id === filters.value[key],
                )?.title || "相册"
              : key === "memory"
                ? memoryChoices.value.find(
                    (context) => context.id === filters.value[key],
                  )?.title || "回忆"
                : key === "sort"
                  ? sortLabels[filters.value[key]]
                  : filters.value[key],
    })),
);
const filterCount = computed(() => chips.value.length);
const trainInitial = computed(() =>
  editing.value
    ? {
        ...legacyTicket(editing.value),
        train_code: editing.value.code,
        dateTime: editing.value.date_time?.replace("T", " "),
        totalRunningTime: editing.value.duration,
      }
    : {},
);
const flightInitial = computed(() =>
  editing.value
    ? {
        id: editing.value.id,
        flight_code: editing.value.code,
        departure_city: editing.value.from,
        arrival_city: editing.value.to,
        date_time: editing.value.date_time,
        name: editing.value.name,
        price: editing.value.price,
        total_running_time: editing.value.duration,
        total_mileage: editing.value.distance,
        comments: editing.value.comments,
      }
    : {},
);
watch(
  [filters, search, contextId, () => route.query.start, () => route.query.end],
  () => {
    if (selected.value.length) ElMessage.info("条件已改变，已清空选择");
    selected.value = [];
    visibleLimit.value = 50;
  },
  { deep: true },
);
watch(selecting, (value) => ui.setSelectionActive(value));
watch(detailOpen, (value) => {
  if (!value && route.query.ticket_id) {
    const query = { ...route.query };
    delete query.ticket_id;
    delete query.ticket_type;
    void router.replace({ query });
  }
});
let routeTimer: ReturnType<typeof setTimeout>;
watch(
  () => route.fullPath,
  () => {
    clearTimeout(routeTimer);
    routeTimer = setTimeout(() => {
      if (route.path !== "/ticket") return;
      if (
        route.query.ticket_id &&
        ["train", "flight"].includes(String(route.query.ticket_type))
      ) {
        detailRef.value = {
          type: String(route.query.ticket_type) as SupportedTicketType,
          id: String(route.query.ticket_id),
        };
        detailOpen.value = true;
      }
      if (route.query.add === "true") {
        typeOpen.value = true;
        const query = { ...route.query };
        delete query.add;
        void router.replace({ query }).then(() => {
          typeOpen.value = true;
        });
      }
    }, 0);
  },
  { immediate: true },
);
onMounted(async () => {
  await store.fetch();
  await nextTick();
  const main = document.querySelector<HTMLElement>(".ts-main-scroll");
  if (main) main.scrollTop = store.scrollPositions.get(route.fullPath) || 0;
});
onBeforeRouteLeave(() => {
  const main = document.querySelector<HTMLElement>(".ts-main-scroll");
  if (main) store.scrollPositions.set(route.fullPath, main.scrollTop);
});
onActivated(async () => {
  ui.setSelectionActive(selecting.value);
  await store.fetch();
  await nextTick();
  const main = document.querySelector<HTMLElement>(".ts-main-scroll");
  if (main) main.scrollTop = store.scrollPositions.get(route.fullPath) || 0;
});
onDeactivated(() => ui.setSelectionActive(false));
onBeforeUnmount(() => {
  clearTimeout(routeTimer);
  ui.setSelectionActive(false);
});
function openDetail(item: TicketRef) {
  if (selecting.value) {
    toggle(ticketKey(item));
    return;
  }
  detailRef.value = item;
  detailOpen.value = true;
}
function associate(items: TicketRef[]) {
  associationTickets.value = items;
  associationOpen.value = true;
}
function beginSelection() {
  selecting.value = true;
  selected.value = [];
}
function toggle(key: string) {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((value) => value !== key)
    : [...selected.value, key];
}
function openFilters() {
  draft.value = { ...filters.value };
  filterOpen.value = true;
}
function applyFilters() {
  if (
    draft.value.start &&
    draft.value.end &&
    draft.value.start > draft.value.end
  ) {
    ElMessage.warning("结束日期不能早于开始日期");
    return;
  }
  filters.value = { ...draft.value };
  filterOpen.value = false;
}
function resetFilters() {
  filters.value = defaults();
  search.value = "";
}
function removeFilter(key: keyof ReturnType<typeof defaults>) {
  filters.value[key] = defaults()[key];
}
function clearContext() {
  const query = { ...route.query };
  delete query.album_id;
  delete query.memory_id;
  delete query.start;
  delete query.end;
  void router.replace({ query });
}
function sortValue(item: WalletTicket) {
  return filters.value.sort === "distance"
    ? ticketDistance(item)
    : filters.value.sort === "duration"
      ? ticketDuration(item)
      : Number(item.price ?? -1);
}
function ticketDistance(item: WalletTicket) {
  return item.distance || store.stats[item.key]?.distance_km || 0;
}
function ticketDuration(item: WalletTicket) {
  return item.duration || store.stats[item.key]?.duration_minutes || 0;
}
function startNew(type: SupportedTicketType) {
  typeOpen.value = false;
  editing.value = null;
  if (type === "train") trainOpen.value = true;
  else flightOpen.value = true;
}
function editTicket(item: WalletTicket) {
  editing.value = item;
  if (item.type === "train") trainOpen.value = true;
  else flightOpen.value = true;
}
function legacyTicket(item: WalletTicket) {
  return {
    id: item.id,
    type: item.type,
    from: item.from,
    to: item.to,
    trainCode: item.code,
    name: item.name,
    date: item.date_time?.slice(0, 10) || "",
    time: item.date_time?.slice(11, 16) || "",
    dateTime: item.date_time || "",
    price: item.price ?? 0,
    seatType: item.seat_type,
    carriage: item.carriage,
    seatNumber: item.seat_num,
    berthType: item.berth_type,
    discountType: item.discount_type,
    distance: item.distance,
    totalRunningTime: item.duration,
    duration: `${Math.floor(item.duration / 60)}小时${item.duration % 60}分钟`,
    comments: item.comments,
  };
}
async function saved(ref: TicketRef, isNew: boolean) {
  trainOpen.value = false;
  flightOpen.value = false;
  await store.changed();
  if (isNew && contextId.value && !journey.value) {
    try {
      await ticketWalletApi.link([ref], {
        kind: contextKind.value,
        id: contextId.value,
        title: "",
      });
      await store.changed();
    } catch {
      ElMessage.warning("票据已保存，关联未成功，请重试");
      associate([ref]);
    }
  }
  ElMessage.success("票据已保存");
}
async function saveTrain(data: TicketFormData) {
  if (saving.value) return;
  saving.value = true;
  try {
    const payload = {
      train_code: data.train_code,
      departure_station: data.from,
      arrival_station: data.to,
      date_time: data.dateTime,
      name: data.name,
      price: data.price,
      carriage: data.carriage,
      seat_num: data.seatNumber,
      berth_type: data.berthType,
      seat_type: data.seatType,
      discount_type: data.discountType,
      total_mileage: data.distance,
      total_running_time: data.totalRunningTime,
      comments: data.comments,
    };
    const isNew = !editing.value;
    const result = editing.value
      ? await ticketService.updateTicket(editing.value.id, payload)
      : (await ticketService.createTicket(payload)).data;
    await saved({ type: "train", id: String(result.id) }, isNew);
  } catch {
    ElMessage.error("保存失败，输入已保留");
  } finally {
    saving.value = false;
  }
}
async function saveFlight(data: FlightTicketFormData) {
  if (saving.value) return;
  saving.value = true;
  try {
    const isNew = !editing.value;
    const result = editing.value
      ? await ticketService.updateFlightTicket(editing.value.id, data)
      : await ticketService.createFlightTicket(data);
    await saved({ type: "flight", id: String(result.id) }, isNew);
  } catch {
    ElMessage.error("保存失败，输入已保留");
  } finally {
    saving.value = false;
  }
}
async function deleteTickets(items: WalletTicket[]) {
  if (busy.value || !items.length) return;
  try {
    await ElMessageBox.confirm(
      `删除 ${items.length} 张票据？将解除所有关联，原票照片、相册和回忆会保留。`,
      "删除票据",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  busy.value = true;
  const results = await Promise.allSettled(
    items.map((item) => ticketWalletApi.remove(item)),
  );
  const failed = items.filter(
    (_, index) => results[index]?.status === "rejected",
  );
  selected.value = failed.map((item) => item.key);
  if (
    items.some(
      (item) => detailRef.value && ticketKey(detailRef.value) === item.key,
    ) &&
    !failed.some((item) => item.key === ticketKey(detailRef.value!))
  )
    detailOpen.value = false;
  await store.changed();
  busy.value = false;
  if (failed.length)
    ElMessage.warning(
      `删除成功 ${items.length - failed.length} 张，失败 ${failed.length} 张，可重试`,
    );
  else ElMessage.success("删除成功");
}
function openPaper(item: WalletTicket) {
  paperTicket.value = item;
  paperOpen.value = true;
}
function openPhoto(id: string) {
  photo.value = {
    id,
    url: toServerUrl(`/api/medias/${id}/file`),
    thumbnail: thumbnailUrl(id),
    preview: thumbnailUrl(id, "medium"),
    srcset: "",
    timestamp: 0,
    albumIds: [],
    file_type: "image",
    filename: id,
  };
  photoOpen.value = true;
}
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function backendData(item: WalletTicket) {
  const base = {
    date_time: item.date_time,
    price: item.price,
    name: item.name,
    total_mileage: item.distance,
    total_running_time: item.duration,
    comments: item.comments,
    photo_id: item.photo_id,
  };
  return item.type === "train"
    ? {
        ...base,
        train_code: item.code,
        departure_station: item.from,
        arrival_station: item.to,
        carriage: item.carriage || "",
        seat_num: item.seat_num || "",
        seat_type: item.seat_type || "",
        berth_type: item.berth_type,
        discount_type: item.discount_type,
        stop_stations: item.stop_stations,
      }
    : {
        ...base,
        flight_code: item.code,
        departure_city: item.from,
        arrival_city: item.to,
      };
}
function exportData(format: "json" | "csv") {
  const items = exportItems.value;
  if (!items.length) return;
  const records = items.map((item) => ({
    id: item.id,
    type: item.type,
    ...backendData(item),
  }));
  let value: string;
  if (format === "json")
    value = JSON.stringify({ version: 1, items: records }, null, 2);
  else {
    const columns = [...new Set(records.flatMap((item) => Object.keys(item)))];
    const cell = (value: unknown) => {
      let text = String(value ?? "");
      if (/^[=+@-]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    value =
      "\uFEFF" +
      [
        columns.map(cell).join(","),
        ...records.map((item) =>
          columns
            .map((key) => cell((item as Record<string, unknown>)[key]))
            .join(","),
        ),
      ].join("\r\n");
  }
  download(
    new Blob([value], {
      type: format === "json" ? "application/json" : "text/csv;charset=utf-8",
    }),
    `票夹_${new Date().toISOString().slice(0, 10)}.${format}`,
  );
  exportOpen.value = false;
}
async function exportPng(items: WalletTicket[] = exportItems.value) {
  if (busy.value) return;
  const trains = items.filter((item) => item.type === "train");
  if (!trains.length) return;
  busy.value = true;
  exportProgress.value = 0;
  try {
    for (let index = 0; index < trains.length; index++) {
      exportTicket.value = trains[index]!;
      await nextTick();
      if (!paperRef.value) throw new Error("票面未加载");
      paperRef.value.exporting = true;
      await nextTick();
      const element = paperRef.value.wrapper;
      if (!element) throw new Error("票面未加载");
      const url = await toPng(element, {
        pixelRatio: 2,
        width: 856,
        height: 540,
        backgroundColor: "#fff",
      });
      const link = document.createElement("a");
      link.href = url;
      link.download = `火车票_${trains[index]!.code}_${trains[index]!.date_time?.slice(0, 10)}.png`;
      link.click();
      exportProgress.value = Math.round(((index + 1) / trains.length) * 100);
    }
    exportOpen.value = false;
    ElMessage.success(`已导出 ${trains.length} 张纪念票面`);
  } catch {
    ElMessage.error("图片导出失败，请重试");
  } finally {
    busy.value = false;
    exportTicket.value = null;
  }
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file) return;
  busy.value = true;
  try {
    const result = await ticketWalletApi.importFile(file);
    await store.changed();
    if (result.failed)
      ElMessage.warning(
        `导入成功 ${result.success} 张，失败 ${result.failed} 张`,
      );
    else ElMessage.success(`导入完成，共 ${result.success} 张`);
  } catch {
    ElMessage.error("导入失败，请检查文件格式");
  } finally {
    input.value = "";
    busy.value = false;
  }
}
</script>
<style>
.ticket-wallet .ts-glass-button {
  height: 44px;
}
.wallet-photo-viewer {
  z-index: 130 !important;
}
</style>
