import { defineStore } from "pinia";
import { ref } from "vue";
import { ticketWalletApi } from "@/api/ticketWallet";
import type { WalletTicket } from "@/types/ticketWallet";

export const useTicketWalletStore = defineStore("ticket-wallet", () => {
  const items = ref<WalletTicket[]>([]);
  const loading = ref(false);
  const error = ref("");
  const revision = ref(0);
  const stats = ref<
    Record<string, { distance_km: number; duration_minutes: number }>
  >({});
  const browse = ref({
    filters: {
      type: "all",
      start: "",
      end: "",
      linked: "all",
      person: "",
      album: "",
      memory: "",
      sort: "date",
    },
    search: "",
    visibleLimit: 50,
  });
  const scrollPositions = new Map<string, number>();
  let pending: Promise<void> | null = null;
  let generation = 0;
  async function fetch() {
    if (pending) return pending;
    const current = ++generation;
    const request = (async () => {
      loading.value = true;
      error.value = "";
      try {
        const all: WalletTicket[] = [];
        let total = 0;
        do {
          const page = await ticketWalletApi.list({
            skip: all.length,
            limit: 1000,
          });
          if (current !== generation) return;
          all.push(...page.items);
          total = page.total;
          if (!page.items.length) break;
        } while (all.length < total);
        items.value = all;
        void loadStats(all, current);
      } catch {
        if (current === generation) error.value = "票据加载失败，请重试";
      } finally {
        if (current === generation) loading.value = false;
      }
    })();
    pending = request;
    try {
      await request;
    } finally {
      if (pending === request) pending = null;
    }
  }
  async function loadStats(all: WalletTicket[], current: number) {
    try {
      if (!all.some((item) => item.type === "train")) return;
      const data = await ticketWalletApi.transportStats(all);
      if (current === generation)
        stats.value = Object.fromEntries(data.map((item) => [item.id, item]));
    } catch {
      /* Optional enrichment must not block the wallet. */
    }
  }
  function reset() {
    generation++;
    pending = null;
    items.value = [];
    stats.value = {};
    loading.value = false;
    error.value = "";
    browse.value.filters = {
      type: "all",
      start: "",
      end: "",
      linked: "all",
      person: "",
      album: "",
      memory: "",
      sort: "date",
    };
    browse.value.search = "";
    browse.value.visibleLimit = 50;
    scrollPositions.clear();
  }
  async function changed() {
    revision.value++;
    if (pending) await pending;
    await fetch();
  }
  return {
    items,
    loading,
    error,
    revision,
    stats,
    browse,
    scrollPositions,
    fetch,
    changed,
    reset,
  };
});
