<template>
  <div v-if="store.error" class="ts-surface p-4 text-sm">
    {{ store.error }}
    <button class="ts-button" @click="store.fetch()">重试</button>
  </div>
  <p
    v-else-if="store.loading && !store.items.length"
    class="text-sm text-gray-500 dark:text-gray-400"
  >
    正在加载票夹…
  </p>
  <template v-else-if="store.items.length">
    <HorizontalStrip label="票夹" strip-class="ticket-preview-strip" class="md:hidden">
      <RouterLink v-for="ticket in store.items.slice(0, 6)" :key="ticket.key" :to="ticketLink(ticket)" class="ticket-preview-cover" :aria-label="`${ticketLabel(ticket.type)} ${ticket.title} ${ticket.code}`">
        <TicketThumbnail :photo-id="ticket.photo_id" :type="ticket.type" class="ticket-preview-image" />
        <p class="mt-1 truncate text-xs font-semibold text-[var(--ts-color-text)]">{{ ticket.title }}</p>
        <p class="mt-0.5 truncate text-xs text-[var(--ts-color-text-secondary)]">{{ ticket.code || ticketLabel(ticket.type) }}</p>
      </RouterLink>
    </HorizontalStrip>
  <div class="hidden gap-2.5 md:grid md:grid-cols-2 xl:grid-cols-3">
    <WalletTicketCard
      v-for="ticket in store.items.slice(0, 6)"
      :key="ticket.key"
      :ticket="ticket"
      preview
      @open="router.push(ticketLink(ticket))"
    />
  </div>
  </template>
  <div v-else class="ts-surface p-4 flex flex-wrap items-center gap-3">
    <Ticket class="h-7 w-7 text-primary-500" />
    <p class="text-sm text-gray-500 dark:text-gray-400">
      留下一张票据，找回一段经历
    </p>
    <RouterLink
      to="/ticket?add=true"
      class="ts-button ts-button-ghost text-primary-600 dark:text-primary-400"
      >新增票据</RouterLink
    >
  </div>
</template>
<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import WalletTicketCard from "./WalletTicketCard.vue";
import TicketThumbnail from "./TicketThumbnail.vue";
import HorizontalStrip from "@/components/ui/HorizontalStrip.vue";
import { Ticket } from "lucide-vue-next";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import { ticketLink, ticketLabel } from "@/types/ticketWallet";
const router = useRouter();
const store = useTicketWalletStore();
onMounted(() => store.fetch());
</script>
<style scoped>
:deep(.ticket-preview-strip) { display: flex; gap: var(--album-cover-gap, 8px); overflow-x: auto; scroll-snap-type: x proximity; scrollbar-width: none; padding: 2px 2px 2px; }
:deep(.ticket-preview-strip)::-webkit-scrollbar { display: none; }
.ticket-preview-cover { flex: 0 0 calc((100% - (var(--album-cover-columns, 3) - 1) * var(--album-cover-gap, 8px)) / var(--album-cover-columns, 3)); min-width: 0; scroll-snap-align: start; }
.ticket-preview-image { width: 100%; height: auto; aspect-ratio: 1; border-radius: 12px; }
</style>
