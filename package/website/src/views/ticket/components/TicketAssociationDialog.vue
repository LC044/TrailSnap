<template>
  <ResponsiveDialog history
    :model-value="modelValue"
    title="关联经历"
    mobile-mode="fullscreen"
    mobile-back
    max-width="40rem"
    :close-on-backdrop="false"
    :before-close="confirmExit"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="flex gap-2 mb-4">
      <button
        v-for="value in ['album', 'memory'] as const"
        :key="value"
        class="ts-button"
        :class="kind === value ? 'ts-button-primary' : 'ts-button-secondary'"
        @click="kind = value"
      >
        {{ value === "album" ? "相册" : "回忆" }}
      </button>
    </div>
    <input
      v-model="search"
      class="ts-input w-full"
      type="search"
      aria-label="搜索关联对象"
      placeholder="搜索名称"
    />
    <p class="my-3 text-xs text-gray-500 dark:text-gray-400">
      仅显示可编辑的普通相册或已确认回忆。已关联对象再次选择不会重复添加。
    </p>
    <p v-if="error" class="py-4 text-sm text-red-600 dark:text-red-400">
      {{ error }} <button class="ts-button" @click="load()">重试</button>
    </p>
    <p v-if="loading" class="py-4 text-gray-500 dark:text-gray-400">加载中…</p>
    <label
      v-for="item in choices"
      :key="item.id"
      class="flex min-h-12 items-center gap-3 border-b border-gray-100 dark:border-gray-800 py-3"
    >
      <input
        v-model="chosen"
        :value="item"
        type="checkbox"
        class="h-5 w-5 accent-[var(--theme-primary)]"
      /><span class="min-w-0 break-words">{{ item.title }}</span
      ><span
        v-if="isLinked(item)"
        class="ml-auto shrink-0 text-xs text-gray-500 dark:text-gray-400"
        >已关联</span
      >
    </label>
    <p
      v-if="!loading && !error && !choices.length"
      class="py-8 text-center text-gray-500 dark:text-gray-400"
    >
      没有可关联的{{ kind === "album" ? "相册" : "回忆" }}
    </p>
    <button
      v-if="choices.length < total"
      class="ts-button ts-button-secondary mt-3"
      :disabled="loading"
      @click="load(true)"
    >
      加载更多
    </button>
    <template #footer
      ><div class="flex justify-end gap-3">
        <button
          class="ts-button ts-button-secondary"
          :disabled="saving"
          @click="close(false)"
        >
          取消</button
        ><button
          class="ts-button ts-button-primary"
          :disabled="!chosen.length || saving"
          @click="save"
        >
          {{ saving ? "保存中…" : `关联 ${chosen.length} 项` }}
        </button>
      </div></template
    >
  </ResponsiveDialog>
</template>
<script setup lang="ts">
import { ref, watch } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, type RouteLocationNormalized } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import { ticketWalletApi } from "@/api/ticketWallet";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import type {
  TicketRef,
  TicketContext,
  WalletTicket,
} from "@/types/ticketWallet";
const props = defineProps<{
  modelValue: boolean;
  tickets: TicketRef[];
  existing?: WalletTicket;
}>();
const emit = defineEmits<{ "update:modelValue": [boolean]; saved: [] }>();
const store = useTicketWalletStore();
const kind = ref<"album" | "memory">("album"),
  search = ref(""),
  chosen = ref<TicketContext[]>([]);
const choices = ref<TicketContext[]>([]),
  total = ref(0),
  loading = ref(false),
  saving = ref(false),
  error = ref("");
let requestVersion = 0,
  timer: ReturnType<typeof setTimeout>;
const isLinked = (item: TicketContext) =>
  (item.kind === "album"
    ? props.existing?.albums
    : props.existing?.memories
  )?.some((link) => link.id === item.id);
async function load(more = false) {
  const version = ++requestVersion;
  loading.value = true;
  error.value = "";
  try {
    const data = await ticketWalletApi.contexts(
      kind.value,
      search.value,
      more ? choices.value.length : 0,
    );
    if (version === requestVersion) {
      choices.value = more ? [...choices.value, ...data.items] : data.items;
      total.value = data.total;
    }
  } catch {
    if (version === requestVersion) error.value = "加载失败";
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}
watch([kind, search], () => {
  clearTimeout(timer);
  choices.value = [];
  timer = setTimeout(() => {
    if (props.modelValue) void load();
  }, 250);
});
watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      chosen.value = [];
      search.value = "";
      void load();
    } else {
      requestVersion++;
      clearTimeout(timer);
    }
  },
);
async function close(value: boolean) {
  if (await confirmExit()) emit("update:modelValue", value);
}
async function confirmExit() {
  if (saving.value) return false;
  if (chosen.value.length) {
    try {
      await ElMessageBox.confirm("放弃尚未保存的关联选择？", "放弃更改", {
        confirmButtonText: "放弃",
        cancelButtonText: "继续编辑",
      });
    } catch {
      return false;
    }
  }
  return true;
}
const guardNavigation = async (to: RouteLocationNormalized, from: RouteLocationNormalized) => {
  if (to.fullPath === from.fullPath) return true;
  if (!props.modelValue) return true;
  const allowed = await confirmExit();
  if (allowed) chosen.value = [];
  return allowed;
};
onBeforeRouteLeave(guardNavigation);
onBeforeRouteUpdate(guardNavigation);
async function save() {
  saving.value = true;
  let done = 0;
  try {
    for (const context of chosen.value) {
      await ticketWalletApi.link(props.tickets, context);
      done++;
    }
    await store.changed();
    chosen.value = [];
    emit("saved");
    emit("update:modelValue", false);
    ElMessage.success("关联已保存");
  } catch {
    if (done) {
      chosen.value = chosen.value.slice(done);
      await store.changed();
      emit("saved");
    }
    ElMessage.error(
      done ? `已关联 ${done} 项，其余保存失败，可重试` : "关联失败，选择已保留",
    );
  } finally {
    saving.value = false;
  }
}
</script>
