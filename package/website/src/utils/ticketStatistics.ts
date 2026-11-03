import type { WalletTicket } from "@/types/ticketWallet";

export const transportKinds = [
  { key: "highspeed", label: "高铁动车" },
  { key: "normal", label: "普速列车" },
  { key: "flight", label: "飞机" },
] as const;
export type TransportKind = (typeof transportKinds)[number]["key"];
export type TrendMetric = "count" | "distance" | "amount";
export interface StatisticsFilter {
  year?: number | null;
  start?: string;
  end?: string;
  passenger?: string;
  transport?: string;
}
export interface TransportStats {
  distance_km: number;
  duration_minutes: number;
}
export interface CityCount {
  name: string;
  count: number;
}
export interface RouteCount {
  from: string;
  to: string;
  count: number;
}

// Only established city aliases are used when the station catalogue is unavailable.
const cityAliases: Record<string, string> = {
  北京南: "北京",
  北京北: "北京",
  北京西: "北京",
  北京朝阳: "北京",
  北京大兴: "北京",
  上海虹桥: "上海",
  上海南: "上海",
  上海西: "上海",
  金山卫: "上海",
  天津南: "天津",
  天津西: "天津",
  广州南: "广州",
  广州北: "广州",
  深圳北: "深圳",
  成都东: "成都",
  重庆北: "重庆",
  重庆西: "重庆",
  重庆东: "重庆",
  杭州东: "杭州",
  杭州西: "杭州",
  西安北: "西安",
  南京南: "南京",
  长沙南: "长沙",
  兰州西: "兰州",
  郑州东: "郑州",
  郑州西: "郑州",
  民权北: "民权",
  济南西: "济南",
  合肥南: "合肥",
  南宁东: "南宁",
  昆明南: "昆明",
  贵阳北: "贵阳",
  哈尔滨西: "哈尔滨",
  哈尔滨东: "哈尔滨",
};
export function normalizeTicketCity(
  value: string,
  stations: ReadonlyMap<string, string> = new Map(),
) {
  const name = String(value || "").trim();
  const city = stations.get(name) || cityAliases[name] || name;
  return (cityAliases[city] || city).replace(/市$/, "");
}
export function positiveNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}
export function ticketDate(value: string | null) {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(
      value || "",
    );
  if (!match) return null;
  const [, y, m, day, h = "00", min = "00", sec = "00"] = match;
  const date = new Date(+y, +m - 1, +day, +h, +min, +sec);
  if (
    date.getFullYear() !== +y ||
    date.getMonth() !== +m - 1 ||
    date.getDate() !== +day ||
    date.getHours() !== +h ||
    date.getMinutes() !== +min ||
    date.getSeconds() !== +sec
  )
    return null;
  return {
    date,
    day: `${y}-${m}-${day}`,
    month: `${y}-${m}`,
    year: +y,
    time: `${y}-${m}-${day} ${h}:${min}:${sec}`,
  };
}

export type TicketStatistics = ReturnType<typeof aggregateTicketStatistics>;
export function transportKind(ticket: WalletTicket): TransportKind {
  return ticket.type === "flight"
    ? "flight"
    : /^[GDC]/i.test(ticket.code.trim())
      ? "highspeed"
      : "normal";
}
export function formatTravelDuration(minutes: number) {
  const value = Math.round(positiveNumber(minutes));
  if (!value) return "—";
  const hours = Math.floor(value / 60),
    rest = value % 60;
  return `${hours ? `${hours}小时` : ""}${rest ? `${rest}分` : ""}`;
}
function ranked(map: Map<string, number>): CityCount[] {
  return Array.from(map, ([name, count]) => ({ name, count })).sort(
    (a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh-CN"),
  );
}
function seatName(value?: string) {
  const name = (value || "").trim().replace(/^新空调/, "");
  if (!name || name === "等座") return "其他";
  if (/硬卧/.test(name)) return "硬卧";
  if (/软卧/.test(name)) return "软卧";
  return name;
}

export function aggregateTicketStatistics(
  items: WalletTicket[],
  filter: StatisticsFilter = {},
  enrichment: Record<string, TransportStats> = {},
  stations: ReadonlyMap<string, string> = new Map(),
  mergeReturns = true,
) {
  const seenIds = new Set<string>(),
    seenTickets = new Set<string>();
  const tickets = items.flatMap((ticket) => {
    const parsed = ticketDate(ticket.date_time);
    if (
      !parsed ||
      !ticket.from?.trim() ||
      !ticket.to?.trim() ||
      ticket.from.trim() === ticket.to.trim()
    )
      return [];
    if (filter.year && parsed.year !== filter.year) return [];
    if (
      (filter.start && parsed.day < filter.start) ||
      (filter.end && parsed.day > filter.end)
    )
      return [];
    if (filter.passenger && ticket.name !== filter.passenger) return [];
    const kind = transportKind(ticket);
    if (
      filter.transport &&
      filter.transport !== "all" &&
      filter.transport !== kind
    )
      return [];
    const id = `${ticket.type}:${ticket.id}`;
    const journeyKey = JSON.stringify([
      ticket.type,
      ticket.code.trim().toUpperCase(),
      ticket.from.trim(),
      ticket.to.trim(),
      parsed.time,
    ]);
    const fingerprint = ticket.name?.trim()
      ? JSON.stringify([
          journeyKey,
          ticket.name.trim(),
          ticket.carriage || "",
          ticket.seat_num || "",
        ])
      : id;
    if (seenIds.has(id) || seenTickets.has(fingerprint)) return [];
    seenIds.add(id);
    seenTickets.add(fingerprint);
    const stat = enrichment[ticket.key];
    return [
      {
        ticket,
        parsed,
        kind,
        journeyKey,
        from: normalizeTicketCity(ticket.from, stations),
        to: normalizeTicketCity(ticket.to, stations),
        distance:
          positiveNumber(stat?.distance_km) || positiveNumber(ticket.distance),
        duration:
          positiveNumber(stat?.duration_minutes) ||
          positiveNumber(ticket.duration),
        cents: Math.round(positiveNumber(ticket.price) * 100),
      },
    ];
  });
  type Entry = (typeof tickets)[number];
  const grouped = new Map<string, Entry & { cents: number }>();
  for (const entry of tickets) {
    const existing = grouped.get(entry.journeyKey);
    if (!existing) grouped.set(entry.journeyKey, { ...entry });
    else {
      existing.distance = Math.max(existing.distance, entry.distance);
      existing.duration = Math.max(existing.duration, entry.duration);
      existing.cents += entry.cents;
    }
  }
  const journeys = [...grouped.values()].sort((a, b) =>
    a.parsed.time.localeCompare(b.parsed.time),
  );
  const months = new Map<
    string,
    Record<TransportKind, { count: number; distance: number; amount: number }>
  >();
  const emptyMonth = () =>
    Object.fromEntries(
      transportKinds.map(({ key }) => [
        key,
        { count: 0, distance: 0, amount: 0 },
      ]),
    ) as Record<
      TransportKind,
      { count: number; distance: number; amount: number }
    >;
  // Fill missing months, without merging different years into the same 12 buckets.
  const startMonth = filter.year
    ? `${filter.year}-01`
    : filter.start?.slice(0, 7) || journeys[0]?.parsed.month;
  const endMonth = filter.year
    ? `${filter.year}-12`
    : filter.end?.slice(0, 7) || journeys.at(-1)?.parsed.month;
  if (startMonth && endMonth) {
    const [sy, sm] = startMonth.split("-").map(Number),
      [ey, em] = endMonth.split("-").map(Number);
    const first = sy * 12 + sm - 1,
      last = ey * 12 + em - 1;
    // Very sparse ranges remain bounded (e.g. incorrectly recognised ticket years).
    if (last - first <= 600)
      for (let index = first; index <= last; index++) {
        months.set(
          `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`,
          emptyMonth(),
        );
      }
  }
  const cities = new Map<string, number>(),
    arrivals = new Map<string, number>(),
    routes = new Map<string, RouteCount>();
  const codes = new Map<string, number>(),
    seats = new Map<string, number>();
  const heatmap = Array.from({ length: 4 }, () => Array(7).fill(0) as number[]);
  const modes = transportKinds.map(({ key, label }) => ({
    key,
    label,
    count: 0,
    distance: 0,
    amount: 0,
  }));
  let distance = 0,
    duration = 0;
  for (const entry of journeys) {
    const { from, to, kind, parsed } = entry;
    distance += entry.distance;
    duration += entry.duration;
    const mode = modes.find((mode) => mode.key === kind)!;
    mode.count++;
    mode.distance += entry.distance;
    mode.amount += entry.cents / 100;
    if (!months.has(parsed.month)) months.set(parsed.month, emptyMonth());
    const month = months.get(parsed.month)![kind];
    month.count++;
    month.distance += entry.distance;
    month.amount += entry.cents / 100;
    for (const city of new Set([from, to]))
      cities.set(city, (cities.get(city) || 0) + 1);
    arrivals.set(to, (arrivals.get(to) || 0) + 1);
    let ends = from === to ? [entry.ticket.from, entry.ticket.to] : [from, to];
    if (mergeReturns)
      ends = [...ends].sort((a, b) => a.localeCompare(b, "zh-CN"));
    const routeKey = JSON.stringify(ends);
    const route = routes.get(routeKey) || {
      from: ends[0],
      to: ends[1],
      count: 0,
    };
    route.count++;
    routes.set(routeKey, route);
    if (entry.ticket.code.trim())
      codes.set(
        entry.ticket.code.trim().toUpperCase(),
        (codes.get(entry.ticket.code.trim().toUpperCase()) || 0) + 1,
      );
    const hour = parsed.date.getHours(),
      slot = hour < 6 ? 0 : hour < 12 ? 1 : hour < 18 ? 2 : 3;
    heatmap[slot][(parsed.date.getDay() + 6) % 7]++;
  }
  for (const { ticket } of tickets)
    if (ticket.type === "train") {
      const seat = seatName(ticket.seat_type);
      seats.set(seat, (seats.get(seat) || 0) + 1);
    }
  const longest = (field: "distance" | "duration") =>
    journeys.reduce<Entry | null>(
      (best, row) => (row[field] > (best?.[field] || 0) ? row : best),
      null,
    );
  return {
    entries: tickets,
    journeys,
    mergeReturns,
    count: journeys.length,
    ticketCount: tickets.length,
    distance: Math.round(distance),
    duration,
    amount: tickets.reduce((sum, row) => sum + row.cents, 0) / 100,
    cityCount: cities.size,
    days: new Set(journeys.map((row) => row.parsed.day)).size,
    months: [...months]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, modes]) => ({ month, modes })),
    modes,
    cities: ranked(cities),
    arrivals: ranked(arrivals),
    routes: [...routes.values()].sort(
      (a, b) => b.count - a.count || a.from.localeCompare(b.from, "zh-CN"),
    ),
    seats: ranked(seats),
    heatmap,
    codes: ranked(codes),
    longestDistance: longest("distance"),
    longestDuration: longest("duration"),
  };
}
