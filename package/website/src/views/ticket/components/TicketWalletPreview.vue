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
  <div
    v-else-if="store.items.length"
    class="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3"
  >
    <WalletTicketCard
      v-for="ticket in store.items.slice(0, 6)"
      :key="ticket.key"
      :ticket="ticket"
      preview
      @open="router.push(ticketLink(ticket))"
    />
  </div>
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
import { Ticket } from "lucide-vue-next";
import { useTicketWalletStore } from "@/stores/ticketWalletStore";
import { ticketLink } from "@/types/ticketWallet";
const router = useRouter();
const store = useTicketWalletStore();
onMounted(() => store.fetch());
</script>
