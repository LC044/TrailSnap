<template>
  <article
    class="wallet-ticket-card relative min-w-0 rounded-2xl bg-[var(--ts-color-surface)] p-3 sm:p-4"
    :class="selected && 'ring-2 ring-primary-500'"
  >
    <div class="flex items-start gap-2 sm:gap-3">
      <button
        v-if="selecting"
        class="ts-icon-button shrink-0 self-center"
        :aria-label="`选择${ticket.title}`"
        :aria-pressed="selected"
        @click="emit('select')"
      >
        <Check
          v-if="selected"
          class="h-5 w-5 text-primary-600 dark:text-primary-400"
        /><Circle v-else class="h-5 w-5" />
      </button>
      <button
        class="flex min-w-0 flex-1 items-center gap-3 rounded-xl text-left focus-visible:ring-2 focus-visible:ring-primary-500"
        :aria-label="`${ticketLabel(ticket.type)} ${ticket.title} ${ticket.code} · ${displayTime}`"
        @click="emit('open')"
      >
        <TicketThumbnail :photo-id="ticket.photo_id" :type="ticket.type" />
        <span class="min-w-0 flex-1">
          <span class="block text-[11px] text-gray-500 dark:text-gray-400">{{
            ticketLabel(ticket.type)
          }}</span>
          <span
            class="ts-card-title mt-1 block line-clamp-2 break-words text-gray-900 dark:text-white"
            >{{ ticket.title }}</span
          >
          <span
            class="mt-1 block break-words text-xs leading-relaxed text-gray-500 dark:text-gray-400"
            >{{ ticket.code }} · {{ displayTime }}</span
          >
        </span>
      </button>
      <div v-if="!selecting && !preview" class="relative -mr-1 shrink-0">
        <button
          class="ts-icon-button ts-button-ghost"
          :aria-label="`${ticket.title}的更多操作`"
          :aria-expanded="menu"
          @click="menu = !menu"
        >
          <MoreHorizontal class="h-4 w-4" />
        </button>
        <AdaptiveMenu
          v-model="menu"
          title="票据操作"
          mobile-presentation="popover"
          glass
        >
          <button
            class="ts-action-row"
            @click="
              menu = false;
              emit('open');
            "
          >
            <Eye />查看详情
          </button>
          <button
            class="ts-action-row"
            @click="
              menu = false;
              emit('associate');
            "
          >
            <Link />关联相册或回忆
          </button>
          <button
            class="ts-action-row"
            @click="
              menu = false;
              emit('edit');
            "
          >
            <Pencil />编辑
          </button>
          <button
            class="ts-action-row text-red-600 dark:text-red-400"
            @click="
              menu = false;
              emit('delete');
            "
          >
            <Trash2 />删除票据
          </button>
        </AdaptiveMenu>
      </div>
    </div>
    <div
      v-if="!selecting && !preview && contexts.length"
      class="mt-1 flex min-w-0 items-center gap-1 pl-[68px] sm:pl-[76px]"
    >
      <RouterLink
        :to="contextLink(contexts[0]!)"
        class="flex min-h-11 min-w-0 flex-1 items-center gap-1.5 text-xs text-primary-600 dark:text-primary-400"
      >
        <component
          :is="contexts[0]!.kind === 'album' ? Images : BookHeart"
          class="h-3.5 w-3.5 shrink-0"
        />
        <span class="truncate">{{ contexts[0]!.title }}</span
        ><ChevronRight class="h-3.5 w-3.5 shrink-0" />
      </RouterLink>
      <button
        v-if="contexts.length > 1"
        class="min-h-11 shrink-0 px-1 text-xs text-gray-500 dark:text-gray-400"
        @click="emit('open')"
      >
        +{{ contexts.length - 1 }}
      </button>
    </div>
  </article>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import {
  Check,
  Circle,
  MoreHorizontal,
  Eye,
  Link,
  Pencil,
  Trash2,
  Images,
  BookHeart,
  ChevronRight,
} from "lucide-vue-next";
import AdaptiveMenu from "@/components/ui/AdaptiveMenu.vue";
import TicketThumbnail from "./TicketThumbnail.vue";
import {
  contextLink,
  ticketLabel,
  type WalletTicket,
} from "@/types/ticketWallet";
const props = defineProps<{
  ticket: WalletTicket;
  selecting?: boolean;
  selected?: boolean;
  preview?: boolean;
}>();
const emit = defineEmits<{
  open: [];
  select: [];
  associate: [];
  edit: [];
  delete: [];
}>();
const menu = ref(false);
const contexts = computed(() => [
  ...props.ticket.albums,
  ...props.ticket.memories,
]);
const displayTime = computed(() =>
  props.ticket.date_time
    ? new Date(props.ticket.date_time).toLocaleString("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "日期待补充",
);
</script>
<style scoped>
.wallet-ticket-card {
  box-shadow: 0 2px 10px rgb(0 0 0 / 3%);
  transition: box-shadow 180ms ease;
}
.wallet-ticket-card:focus-within {
  box-shadow: 0 3px 14px rgb(0 0 0 / 6%);
}
</style>
