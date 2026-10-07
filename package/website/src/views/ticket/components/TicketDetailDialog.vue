<template>
  <ResponsiveDialog
    history
    :model-value="modelValue"
    :title="`${ticketLabel(ticket?.type || reference?.type || '')}详情`"
    mobile-mode="fullscreen"
    mobile-back
    placement="right"
    max-width="36rem"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p
      v-if="loading"
      class="py-10 text-center text-gray-500 dark:text-gray-400"
    >
      加载中…
    </p>
    <div v-else-if="error" class="py-10 text-center">
      <p>{{ error }}</p>
      <button class="ts-button ts-button-secondary mt-4" @click="load">
        重试
      </button>
    </div>
    <template v-else-if="ticket">
      <div>
        <span class="text-xs text-primary-600 dark:text-primary-400"
          >{{ ticketLabel(ticket.type) }} · {{ ticket.code }}</span
        >
        <h3
          class="mt-2 break-words text-2xl font-semibold text-gray-900 dark:text-white"
        >
          {{ ticket.title }}
        </h3>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
          {{
            ticket.date_time
              ? new Date(ticket.date_time).toLocaleString("zh-CN")
              : "日期待补充"
          }}
        </p>
        <button
          v-if="ticket.photo_id"
          class="group mt-5 block w-full rounded-2xl text-left"
          aria-label="查看原票图片"
          @click="emit('photo', ticket.photo_id)"
        >
          <TicketThumbnail
            :photo-id="ticket.photo_id"
            :type="ticket.type"
            large
          />
          <span
            class="mt-2 flex min-h-11 items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400"
            ><Image class="h-4 w-4" />原票图片<ChevronRight
              class="ml-auto h-4 w-4"
          /></span>
        </button>
      </div>
      <section class="mt-6">
        <h3 class="ts-section-title text-gray-900 dark:text-white">相关经历</h3>
        <template v-for="kind in ['album', 'memory'] as const" :key="kind">
          <div
            v-if="(kind === 'album' ? ticket.albums : ticket.memories).length"
            class="mt-4"
          >
            <h4 class="mb-1 text-xs text-gray-500 dark:text-gray-400">
              {{ kind === "album" ? "相册" : "回忆" }}
            </h4>
            <div
              v-for="context in kind === 'album'
                ? ticket.albums
                : ticket.memories"
              :key="context.id"
              class="flex min-h-14 items-center gap-2 border-b border-gray-100 dark:border-gray-800"
            >
              <button
                class="flex min-h-14 min-w-0 flex-1 items-center gap-3 text-left"
                @click="navigate(context)"
              >
                <span
                  class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400"
                  ><component
                    :is="kind === 'album' ? Images : BookHeart"
                    class="h-5 w-5"
                /></span>
                <span
                  class="min-w-0 flex-1 break-words text-sm font-medium text-gray-900 dark:text-white"
                  >{{ context.title }}</span
                ><ChevronRight
                  class="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500"
                />
              </button>
              <button
                class="ts-icon-button ts-button-ghost shrink-0"
                :disabled="unlinking"
                :aria-label="`解除与${context.title}的关联`"
                @click="unlink(context)"
              >
                <Unlink class="h-4 w-4" />
              </button>
            </div>
          </div>
        </template>
        <p
          v-if="!ticket.albums.length && !ticket.memories.length"
          class="mt-3 rounded-2xl bg-gray-50 p-4 text-sm leading-relaxed text-gray-500 dark:bg-gray-800/50 dark:text-gray-400"
        >
          关联一个相册或一段回忆，把这张票和当时的照片放在一起。
        </p>
      </section>
      <section v-if="ticket.photos?.length" class="mt-6">
        <h3 class="ts-section-title text-gray-900 dark:text-white">相关照片</h3>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
          来自已关联相册和回忆
        </p>
        <div class="mt-3 grid grid-cols-3 gap-2">
          <button
            v-for="photo in ticket.photos"
            :key="photo.id"
            :aria-label="`查看${photo.filename}`"
            @click="emit('photo', photo.id)"
          >
            <img
              :src="thumbnailUrl(photo.id, 'small')"
              :alt="photo.filename"
              loading="lazy"
              class="aspect-square w-full rounded-xl object-cover"
            />
          </button>
        </div>
      </section>
      <section v-if="ticket.candidates.length" class="mt-6">
        <h3 class="ts-section-title text-gray-900 dark:text-white">可能相关</h3>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
          时间相近的回忆，确认后才会加入相关经历。
        </p>
        <div
          v-for="candidate in ticket.candidates"
          :key="candidate.id"
          class="mt-3 rounded-2xl bg-gray-50 p-4 dark:bg-gray-800/50"
        >
          <p class="break-words text-sm font-medium">{{ candidate.title }}</p>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ candidate.reason }}
          </p>
          <div class="mt-2 flex gap-2">
            <button
              class="ts-button ts-button-secondary"
              :disabled="unlinking"
              @click="confirm(candidate)"
            >
              确认关联</button
            ><button
              class="ts-button ts-button-ghost"
              :disabled="unlinking"
              @click="unlink(candidate)"
            >
              排除
            </button>
          </div>
        </div>
      </section>
      <details class="group mt-7 border-t border-gray-100 dark:border-gray-800">
        <summary
          class="flex min-h-14 cursor-pointer list-none items-center justify-between text-sm font-medium text-gray-900 dark:text-white"
        >
          票据资料<ChevronDown
            class="h-4 w-4 text-gray-400 transition-transform group-open:rotate-180 dark:text-gray-500"
          />
        </summary>
        <dl
          class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-3 pb-4 text-sm"
        >
          <dt class="text-gray-500 dark:text-gray-400">
            {{ ticket.type === "train" ? "乘车人" : "乘机人" }}
          </dt>
          <dd class="break-words">{{ ticket.name || "未填写" }}</dd>
          <dt class="text-gray-500 dark:text-gray-400">票价</dt>
          <dd class="break-words">
            {{ ticket.price === null ? "未填写" : `${ticket.price} 元` }}
          </dd>
          <template v-if="ticket.type === 'train'"
            ><dt class="text-gray-500 dark:text-gray-400">座位</dt>
            <dd class="break-words">
              {{
                [
                  ticket.seat_type,
                  ticket.carriage && `${ticket.carriage}车`,
                  ticket.seat_num,
                ]
                  .filter(Boolean)
                  .join(" · ") || "未填写"
              }}
            </dd></template
          >
          <dt class="text-gray-500 dark:text-gray-400">里程</dt>
          <dd class="break-words">
            {{ ticket.distance ? `${ticket.distance} km` : "未填写" }}
          </dd>
          <dt class="text-gray-500 dark:text-gray-400">时长</dt>
          <dd class="break-words">
            {{ ticket.duration ? `${ticket.duration} 分钟` : "未填写" }}
          </dd>
          <template v-if="ticket.comments"
            ><dt class="text-gray-500 dark:text-gray-400">备注</dt>
            <dd class="whitespace-pre-wrap break-words">
              {{ ticket.comments }}
            </dd></template
          >
        </dl>
      </details>
    </template>
    <template v-if="ticket" #footer>
      <div class="flex items-center gap-3">
        <button
          class="ts-button ts-button-primary flex-1"
          @click="associate = true"
        >
          <Link class="h-4 w-4" />关联相册或回忆
        </button>
        <div class="relative">
          <button
            class="ts-icon-button ts-button-secondary"
            aria-label="更多票据操作"
            :aria-expanded="actions"
            @click="actions = !actions"
          >
            <MoreHorizontal class="h-5 w-5" />
          </button>
          <AdaptiveMenu
            v-model="actions"
            title="票据操作"
            mobile-presentation="popover"
            glass
          >
            <button
              class="ts-action-row"
              @click="
                actions = false;
                emit('edit', ticket);
              "
            >
              <Pencil />编辑票据
            </button>
            <button
              class="ts-action-row"
              @click="
                actions = false;
                emit('export', ticket);
              "
            >
              <Download />导出票据
            </button>
            <button
              v-if="ticketKinds[ticket.type]?.paper"
              class="ts-action-row"
              @click="
                actions = false;
                emit('paper', ticket);
              "
            >
              <Ticket />纪念票面
            </button>
            <button
              class="ts-action-row text-red-600 dark:text-red-400"
              @click="
                actions = false;
                emit('delete', ticket);
              "
            >
              <Trash2 />删除票据
            </button>
          </AdaptiveMenu>
        </div>
      </div>
    </template>
  </ResponsiveDialog>
  <TicketAssociationDialog
    v-model="associate"
    :tickets="reference ? [reference] : []"
    :existing="ticket || undefined"
    @saved="load"
  />
</template>
<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Image,
  Link,
  Unlink,
  Pencil,
  Trash2,
  Images,
  BookHeart,
  ChevronRight,
  ChevronDown,
  MoreHorizontal,
  Download,
  Ticket,
} from "lucide-vue-next";
import AdaptiveMenu from "@/components/ui/AdaptiveMenu.vue";
import TicketThumbnail from "./TicketThumbnail.vue";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import TicketAssociationDialog from "./TicketAssociationDialog.vue";
import { ticketWalletApi } from "@/api/ticketWallet";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import {
  ticketLabel,
  ticketKinds,
  contextLink,
  type TicketRef,
  type TicketContext,
  type WalletTicket,
} from "@/types/ticketWallet";
import { thumbnailUrl } from "@/utils/mediaUrl";
const props = defineProps<{
  modelValue: boolean;
  reference: TicketRef | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [boolean];
  edit: [WalletTicket];
  paper: [WalletTicket];
  photo: [string];
  delete: [WalletTicket];
  export: [WalletTicket];
}>();
const router = useRouter(),
  store = useTicketWalletStore();
const ticket = ref<WalletTicket | null>(null),
  loading = ref(false),
  error = ref(""),
  associate = ref(false),
  actions = ref(false),
  unlinking = ref(false);
let version = 0;
async function load() {
  if (!props.reference || !props.modelValue) return;
  const request = ++version;
  loading.value = true;
  error.value = "";
  ticket.value = null;
  try {
    const data = await ticketWalletApi.detail(props.reference);
    if (request === version) ticket.value = data;
  } catch {
    if (request === version) error.value = "票据不存在、已删除或加载失败";
  } finally {
    if (request === version) loading.value = false;
  }
}
watch(
  [
    () => props.modelValue,
    () => props.reference?.type,
    () => props.reference?.id,
  ],
  () => {
    if (props.modelValue) void load();
    else {
      version++;
      associate.value = false;
      actions.value = false;
      ticket.value = null;
    }
  },
);
watch(
  () => store.revision,
  () => {
    if (props.modelValue) void load();
  },
);
function navigate(context: TicketContext) {
  void router.push(contextLink(context));
}
async function unlink(context: TicketContext) {
  if (!props.reference) return;
  try {
    await ElMessageBox.confirm(
      context.reason
        ? "排除这项候选？以后不会自动重新加入此回忆。"
        : "解除关联？票据和相关经历均会保留。",
      "解除关联",
      { confirmButtonText: "解除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  unlinking.value = true;
  try {
    await ticketWalletApi.link([props.reference], context, false);
    await store.changed();
    await load();
  } catch {
    ElMessage.error("解除失败，请重试");
  } finally {
    unlinking.value = false;
  }
}
async function confirm(context: TicketContext) {
  if (!props.reference) return;
  unlinking.value = true;
  try {
    await ticketWalletApi.link([props.reference], context);
    await store.changed();
    await load();
  } catch {
    ElMessage.error("关联失败");
  } finally {
    unlinking.value = false;
  }
}
</script>
