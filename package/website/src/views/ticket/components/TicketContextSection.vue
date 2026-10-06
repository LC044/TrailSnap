<template>
  <section class="ts-surface p-4 md:p-6">
    <div class="flex items-center gap-2">
      <button
        class="ts-section-title min-h-11 flex-1 text-left"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        相关票据 · {{ confirmed.length }}</button
      ><RouterLink
        :to="{ path: '/ticket', query: { [`${kind}_id`]: contextId } }"
        class="min-h-11 flex items-center text-xs text-primary-600 dark:text-primary-400"
        >查看全部</RouterLink
      >
    </div>
    <div v-if="expanded">
      <p v-if="error" class="text-sm py-3 text-red-600 dark:text-red-400">
        票据加载失败 <button class="ts-button" @click="load">重试</button>
      </p>
      <p
        v-else-if="loading"
        class="text-sm py-3 text-gray-500 dark:text-gray-400"
      >
        加载中…
      </p>
      <div v-else class="grid gap-2.5 lg:grid-cols-2 xl:grid-cols-3">
        <WalletTicketCard
          v-for="item in confirmed.slice(0, 3)"
          :key="item.key"
          :ticket="item"
          preview
          @open="router.push(ticketLink(item))"
        />
      </div>
      <p
        v-if="!confirmed.length && !loading && !error"
        class="py-3 text-sm text-gray-500 dark:text-gray-400"
      >
        还没有关联票据
      </p>
      <div v-if="candidates.length" class="mt-4">
        <p class="text-sm text-gray-500 dark:text-gray-400">
          可能相关 · 时间相近，尚未确认
        </p>
        <RouterLink
          v-for="item in candidates.slice(0, 3)"
          :key="item.key"
          :to="ticketLink(item)"
          class="block min-h-11 py-3 text-sm text-primary-600 dark:text-primary-400"
          >{{ item.title }} · {{ item.code }}</RouterLink
        >
      </div>
      <div v-if="editable" class="flex flex-wrap gap-2 mt-3">
        <button
          class="ts-button ts-button-secondary"
          @click="
            selectOpen = true;
            store.fetch();
          "
        >
          关联已有票据</button
        ><RouterLink
          :to="{
            path: '/ticket',
            query: { [`${kind}_id`]: contextId, add: 'true' },
          }"
          class="ts-button ts-button-ghost"
          >新增票据</RouterLink
        >
      </div>
    </div>
  </section>
  <ResponsiveDialog
    history
    v-model="selectOpen"
    title="选择票据"
    mobile-mode="fullscreen"
    mobile-back
    :close-on-backdrop="false"
    :before-close="confirmExit"
  >
    <input
      v-model="search"
      class="ts-input w-full"
      type="search"
      aria-label="搜索票据"
      placeholder="搜索地点、车次或乘车人"
    />
    <p v-if="store.error" class="py-4">
      {{ store.error }}
      <button class="ts-button" @click="store.fetch()">重试</button>
    </p>
    <label
      v-for="item in available.slice(0, selectLimit)"
      :key="item.key"
      class="flex min-h-12 items-center gap-3 border-b border-gray-100 dark:border-gray-800 py-3"
      ><input
        v-model="selected"
        type="checkbox"
        :value="item.key"
        class="h-5 w-5 accent-[var(--theme-primary)]"
      /><span class="min-w-0 break-words text-sm"
        >{{ ticketLabel(item.type) }} · {{ item.title
        }}<span class="block text-xs text-gray-500 dark:text-gray-400"
          >{{ item.code }} · {{ item.date_time?.slice(0, 10) }}</span
        ></span
      ></label
    >
    <p
      v-if="!available.length && !store.loading"
      class="py-5 text-gray-500 dark:text-gray-400"
    >
      没有可选择的票据
    </p>
    <button
      v-if="available.length > selectLimit"
      class="ts-button mt-3"
      @click="selectLimit += 50"
    >
      加载更多
    </button>
    <template #footer
      ><button
        class="ts-button ts-button-primary w-full"
        :disabled="saving || !selected.length"
        @click="save"
      >
        {{ saving ? "保存中…" : `关联 ${selected.length} 张` }}
      </button></template
    >
  </ResponsiveDialog>
</template>
<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import {
  useRouter,
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  type RouteLocationNormalized,
} from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import WalletTicketCard from "./WalletTicketCard.vue";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import { ticketWalletApi } from "@/api/ticketWallet";
import {
  ticketLabel,
  ticketLink,
  type WalletTicket,
} from "@/types/ticketWallet";
const props = defineProps<{
  kind: "album" | "memory";
  contextId: string;
  editable?: boolean;
}>();
const emit = defineEmits<{ changed: [] }>();
const router = useRouter();
const store = useTicketWalletStore(),
  expanded = ref(true),
  loading = ref(false),
  error = ref(false),
  selectOpen = ref(false),
  saving = ref(false),
  search = ref(""),
  selected = ref<string[]>([]),
  selectLimit = ref(50),
  items = ref<WalletTicket[]>([]);
const confirmed = computed(() =>
  items.value.filter((item) =>
    (props.kind === "album" ? item.albums : item.memories).some(
      (context) => context.id === props.contextId,
    ),
  ),
);
const candidates = computed(() =>
  items.value.filter(
    (item) =>
      props.kind === "memory" &&
      item.candidates.some((context) => context.id === props.contextId),
  ),
);
const available = computed(() =>
  store.items.filter(
    (item) =>
      !confirmed.value.some((link) => link.key === item.key) &&
      `${item.title} ${item.code} ${item.name}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
);
let version = 0;
async function load() {
  const request = ++version;
  loading.value = true;
  error.value = false;
  try {
    const all: WalletTicket[] = [];
    let total = 0;
    do {
      const data = await ticketWalletApi.list({
        [`${props.kind}_id`]: props.contextId,
        skip: all.length,
        limit: 1000,
      });
      if (version !== request) return;
      all.push(...data.items);
      total = data.total;
      if (!data.items.length) break;
    } while (all.length < total);
    items.value = all;
  } catch {
    if (version === request) error.value = true;
  } finally {
    if (version === request) loading.value = false;
  }
}
async function confirmExit() {
  if (saving.value) return false;
  if (selected.value.length) {
    try {
      await ElMessageBox.confirm("放弃尚未保存的票据选择？", "放弃更改", {
        confirmButtonText: "放弃",
        cancelButtonText: "继续编辑",
      });
    } catch {
      return false;
    }
  }
  return true;
}
const guardNavigation = async (
  to: RouteLocationNormalized,
  from: RouteLocationNormalized,
) => {
  if (to.fullPath === from.fullPath) return true;
  if (!selectOpen.value) return true;
  const allowed = await confirmExit();
  if (allowed) selected.value = [];
  return allowed;
};
onBeforeRouteLeave(guardNavigation);
onBeforeRouteUpdate(guardNavigation);

onMounted(load);
watch(() => props.contextId, load);
watch(() => store.revision, load);
watch(selectOpen, (value) => {
  if (value) {
    selected.value = [];
    search.value = "";
    selectLimit.value = 50;
  }
});
async function save() {
  saving.value = true;
  try {
    await ticketWalletApi.link(
      store.items.filter((item) => selected.value.includes(item.key)),
      { id: props.contextId, kind: props.kind, title: "" },
    );
    selectOpen.value = false;
    await store.changed();
    await load();
    emit("changed");
    ElMessage.success("关联已保存");
  } catch {
    ElMessage.error("关联失败，选择已保留");
  } finally {
    saving.value = false;
  }
}
</script>
