export type SupportedTicketType = "train" | "flight";
export type TicketType =
  SupportedTicketType | "attraction" | "concert" | "movie";
export interface TicketRef {
  type: SupportedTicketType;
  id: string;
}
export interface TicketContext {
  id: string;
  title: string;
  kind: "album" | "memory";
  reason?: string;
}
export interface TicketSummary {
  id: string;
  type: TicketType | (string & {});
  title: string;
  occurredAt: string | null;
  endsAt?: string | null;
  timePrecision: "datetime" | "date" | "range" | "unknown";
  location?: string | null;
  amount?: number | null;
  currency?: string;
  photoId?: string | null;
  comments?: string;
  fields: Record<string, string | number | null>;
}
export interface WalletTicket extends TicketRef {
  key: string;
  title: string;
  code: string;
  from: string;
  to: string;
  date_time: string | null;
  price: number | null;
  name: string;
  photo_id: string | null;
  distance: number;
  duration: number;
  comments: string;
  seat_type?: string;
  carriage?: string;
  seat_num?: string;
  berth_type?: string;
  discount_type?: string;
  stop_stations?: string;
  albums: TicketContext[];
  memories: TicketContext[];
  candidates: TicketContext[];
  photos?: Array<{ id: string; filename: string }>;
}
// Category, form, and rendering capabilities are independent of transport fields.
export const ticketKinds: Record<
  TicketType,
  {
    label: string;
    category: string;
    supported: boolean;
    transport: boolean;
    paper: boolean;
  }
> = {
  train: {
    label: "火车票",
    category: "交通",
    supported: true,
    transport: true,
    paper: true,
  },
  flight: {
    label: "机票",
    category: "交通",
    supported: true,
    transport: true,
    paper: false,
  },
  attraction: {
    label: "景区门票",
    category: "游览",
    supported: false,
    transport: false,
    paper: false,
  },
  concert: {
    label: "演唱会票",
    category: "演出",
    supported: false,
    transport: false,
    paper: false,
  },
  movie: {
    label: "电影票",
    category: "电影",
    supported: false,
    transport: false,
    paper: false,
  },
};
export const ticketKey = (ticket: TicketRef) => `${ticket.type}:${ticket.id}`;
export const ticketLabel = (type: string) =>
  ticketKinds[type as TicketType]?.label || "票据";
export const ticketLink = (ticket: TicketRef) => ({
  path: "/ticket",
  query: { ticket_type: ticket.type, ticket_id: ticket.id },
});
export const contextLink = (context: TicketContext) =>
  context.kind === "album" ? `/album/${context.id}` : `/memories/${context.id}`;
