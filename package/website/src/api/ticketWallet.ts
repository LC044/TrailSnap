import request from "@/utils/request";
import type {
  TicketRef,
  TicketContext,
  WalletTicket,
} from "@/types/ticketWallet";
export const ticketWalletApi = {
  async list(
    params: {
      album_id?: string;
      memory_id?: string;
      start?: string;
      end?: string;
      skip?: number;
      limit?: number;
    } = {},
  ) {
    return (
      await request.get<{ items: WalletTicket[]; total: number }>(
        "/api/ticket-wallet",
        { params },
      )
    ).data;
  },
  async detail(ticket: TicketRef) {
    return (
      await request.get<WalletTicket>(
        `/api/ticket-wallet/${ticket.type}/${ticket.id}`,
      )
    ).data;
  },
  async transportStats(items: WalletTicket[]) {
    return (
      await request.post<
        Array<{ id: string; distance_km: number; duration_minutes: number }>
      >(
        "/api/railway/stats/batch",
        {
          items: items
            .filter((item) => item.type === "train")
            .map((item) => ({
              id: item.key,
              train_code: item.code,
              departure_station: item.from,
              arrival_station: item.to,
              date_time: item.date_time,
            })),
        },
        { silentError: true },
      )
    ).data;
  },
  async contexts(kind: "album" | "memory", q = "", skip = 0) {
    return (
      await request.get<{ items: TicketContext[]; total: number }>(
        "/api/ticket-wallet/contexts",
        { params: { kind, q, skip } },
      )
    ).data;
  },
  async link(tickets: TicketRef[], context: TicketContext, linked = true) {
    return (
      await request.post("/api/ticket-wallet/links", {
        tickets,
        context_kind: context.kind,
        context_id: context.id,
        linked,
      })
    ).data;
  },
  async importFile(file: File) {
    const payload = new FormData();
    payload.append("file", file);
    return (
      await request.post<{ success: number; failed: number }>(
        "/api/ticket-wallet/import",
        payload,
      )
    ).data;
  },
  async remove(ticket: TicketRef) {
    await request.delete(`/api/ticket-wallet/${ticket.type}/${ticket.id}`);
  },
};
