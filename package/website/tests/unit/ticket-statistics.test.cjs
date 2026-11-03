const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const filename = path.resolve(__dirname, "../../src/utils/ticketStatistics.ts");
const source = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const loaded = { exports: {} };
vm.runInThisContext(`(function(exports){${source}\n})`, { filename })(
  loaded.exports,
);
const {
  aggregateTicketStatistics: aggregate,
  ticketDate,
  normalizeTicketCity,
  formatTravelDuration,
} = loaded.exports;

test("站点城市映射读取完整分页目录，并兼容统一响应解包", async () => {
  const filename = path.resolve(__dirname, "../../src/api/ticketStatistics.ts");
  const source = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const api = {};
  const pages = [];
  const request = {
    get: async (url, { params }) => {
      pages.push(params.page);
      return {
        data: {
          total: 3,
          list:
            params.page === 1
              ? [
                  { station_name: "甲站", city: "甲市" },
                  { station_name: "乙站", city: "乙市" },
                ]
              : [{ station_name: "丙站", city: "丙市" }],
        },
      };
    },
  };
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(
    () => ({ default: request }),
    api,
  );
  const cities = await api.ticketStatisticsApi.stationCities();
  assert.deepEqual(pages, [1, 2]);
  assert.equal(cities.size, 3);
  assert.equal(cities.get("丙站"), "丙市");
});
function ticket(id, fields = {}) {
  return {
    id,
    key: `train:${id}`,
    type: "train",
    code: "G123",
    from: "北京南",
    to: "上海虹桥",
    date_time: "2025-01-06 09:30:00",
    name: "甲",
    price: 100.1,
    distance: 1318,
    duration: 300,
    carriage: "05",
    seat_num: "12A",
    seat_type: "二等座",
    albums: [],
    memories: [],
    candidates: [],
    ...fields,
  };
}

test("同行票据合并行程里程时长，金额按票据计算，重复导入不重复计费", () => {
  const data = aggregate(
    [
      ticket("a"),
      ticket("b", { name: "乙", seat_num: "12B", price: 50.2 }),
      ticket("copy"),
      ticket("a"),
    ],
    {},
    {},
    new Map(),
  );
  assert.equal(data.count, 1);
  assert.equal(data.ticketCount, 2);
  assert.equal(data.distance, 1318);
  assert.equal(data.duration, 300);
  assert.equal(data.amount, 150.3);
  assert.equal(data.months[0].modes.highspeed.amount, 150.3);
  assert.equal(data.cityCount, 2);
  assert.equal(data.seats[0].count, 2);
});

test("复合类型标识隔离，补全值优先且零值不覆盖已有数据", () => {
  const data = aggregate(
    [
      ticket("same"),
      ticket("same", { key: "flight:same", type: "flight", code: "MU123" }),
    ],
    {},
    {
      "train:same": { distance_km: 1400, duration_minutes: 0 },
      "flight:same": { distance_km: 1200, duration_minutes: 120 },
    },
  );
  assert.equal(data.count, 2);
  assert.equal(data.distance, 2600);
  assert.equal(data.duration, 420);
  assert.deepEqual(
    data.modes.map((mode) => mode.count),
    [1, 0, 1],
  );
});

test("跨年年月序列补齐空月，不混合不同年份的一月", () => {
  const data = aggregate([
    ticket("a"),
    ticket("b", { date_time: "2026-01-06T09:30:00" }),
  ]);
  assert.equal(data.months.length, 13);
  assert.equal(data.months[0].month, "2025-01");
  assert.equal(data.months.at(-1).month, "2026-01");
  assert.equal(data.months[0].modes.highspeed.count, 1);
  assert.equal(data.months[1].modes.highspeed.count, 0);
  assert.equal(data.months.at(-1).modes.highspeed.count, 1);
  assert.equal(aggregate([], { year: 2025 }).months.length, 12);
});

test("时间、乘车人和交通方式联合筛选，不按当前时刻排除未来日期", () => {
  const tickets = [
    ticket("a"),
    ticket("b", { name: "乙", date_time: "2025-01-07 10:00:00" }),
    ticket("c", { code: "K123", date_time: "2025-02-01 09:00:00" }),
    ticket("future", { date_time: "2075-07-04 13:00:00" }),
  ];
  assert.equal(
    aggregate(
      tickets,
      {
        year: 2025,
        passenger: "乙",
        transport: "highspeed",
        start: "2025-01-07",
        end: "2025-01-07",
      },
      {},
      new Map(),
    ).count,
    1,
  );
  assert.equal(aggregate(tickets, { transport: "normal" }).count, 1);
  assert.equal(aggregate(tickets).count, 4);
  assert.equal(aggregate(tickets, { year: 2075 }).count, 1);
  assert.equal(
    aggregate(tickets, { start: "2025-01-01", end: "2025-12-31" }).count,
    3,
  );
  assert.equal(aggregate(tickets, { passenger: "不存在" }).count, 0);
});

test("往返合并不影响行程总数，站点按城市归一但同城不同站保留路线", () => {
  const rows = [
    ticket("a"),
    ticket("b", {
      from: "上海虹桥",
      to: "北京南",
      date_time: "2025-01-07 09:00:00",
    }),
  ];
  const merged = aggregate(rows);
  assert.equal(merged.routes.length, 1);
  assert.equal(merged.routes[0].count, 2);
  const directional = aggregate(rows, {}, {}, new Map(), false);
  assert.equal(directional.routes.length, 2);
  assert.equal(directional.count, 2);
  const local = aggregate([ticket("c", { from: "上海南", to: "金山卫" })]);
  assert.equal(local.cityCount, 1);
  assert.equal(local.routes[0].from === local.routes[0].to, false);
  assert.equal(
    normalizeTicketCity("民权北", new Map([["民权北", "商丘市"]])),
    "商丘",
  );
  assert.equal(normalizeTicketCity("济南"), "济南");
  assert.equal(
    normalizeTicketCity("西安北", new Map([["西安北", "西安北"]])),
    "西安",
  );
});

test("时段星期一致，ISO与空格时间同日去重，席别归一和纪录基于同一筛选", () => {
  const data = aggregate([
    ticket("a", {
      code: "K123",
      date_time: "2025-01-06T03:00:00",
      seat_type: "新空调硬座",
      distance: 200,
      duration: 600,
    }),
    ticket("b", { date_time: "2025-01-06 09:30:00", distance: 1400 }),
  ]);
  assert.equal(data.days, 1);
  assert.equal(data.heatmap[0][0], 1);
  assert.equal(data.heatmap[1][0], 1);
  assert.ok(data.seats.some((row) => row.name === "硬座"));
  assert.equal(data.longestDistance.ticket.id, "b");
  assert.equal(data.longestDuration.ticket.id, "a");
  assert.equal(formatTravelDuration(1122), "18小时42分");
});

test("无效日期、相同起终点、缺失金额及非有限数字不会污染统计", () => {
  const data = aggregate([
    ticket("bad-date", { date_time: "2025-02-30 09:00:00" }),
    ticket("same-station", { to: "北京南" }),
    ticket("nan", { price: NaN, distance: Infinity, duration: -5 }),
  ]);
  assert.equal(ticketDate("2025-02-30"), null);
  assert.equal(ticketDate("2025-01-06 25:00:00"), null);
  assert.equal(data.count, 1);
  assert.equal(data.amount, 0);
  assert.equal(data.distance, 0);
  assert.equal(data.duration, 0);
  assert.equal(data.longestDistance, null);
  assert.equal(aggregate([]).routes.length, 0);
  assert.equal(
    aggregate([])
      .heatmap.flat()
      .reduce((a, b) => a + b, 0),
    0,
  );
});

const mapFilename = path.resolve(__dirname, "../../src/utils/ticketMap.ts");
const mapSource = ts.transpileModule(fs.readFileSync(mapFilename, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const mapTools = {};
vm.runInThisContext(`(function(exports){${mapSource}\n})`, {
  filename: mapFilename,
})(mapTools);

test("地图路线与城市选择复用聚合口径，同行金额保留且往返可区分", () => {
  const rows = [
    ticket("a"),
    ticket("b", { name: "乙", seat_num: "12B", price: 50.2 }),
    ticket("c", {
      from: "上海虹桥",
      to: "北京南",
      date_time: "2025-01-07 10:00:00",
    }),
    ticket("d", {
      from: "成都东",
      to: "广州南",
      date_time: "2025-02-01 12:00:00",
    }),
  ];
  const summary = aggregate(rows);
  const city = mapTools.mapSelectionDetail(summary, {
    type: "city",
    name: "北京",
  });
  assert.equal(city.count, 2);
  assert.equal(city.tickets.length, 3);
  assert.equal(city.amount, 250.4);
  assert.equal(city.distance, 2636);
  const route = { type: "route", from: "北京", to: "上海", directional: false };
  assert.equal(mapTools.mapSelectionDetail(summary, route).count, 2);
  assert.equal(
    mapTools.mapSelectionDetail(summary, { ...route, directional: true }).count,
    1,
  );
  assert.equal(
    mapTools.mapSelectionDetail(summary, { type: "city", name: "不存在" })
      .count,
    0,
  );
  assert.equal(
    mapTools.sameMapSelection(route, { ...route, from: "上海", to: "北京" }),
    true,
  );
  assert.equal(
    mapTools.sameMapSelection(
      { ...route, directional: true },
      { ...route, from: "上海", to: "北京", directional: true },
    ),
    false,
  );
  assert.equal(mapTools.sameMapSelection(null, route), false);
});
test("地图同城路线保留站点身份，范围适配处理空坐标与单城市", () => {
  const summary = aggregate([ticket("a", { from: "上海南", to: "金山卫" })]);
  assert.equal(
    mapTools.mapSelectionDetail(summary, {
      type: "route",
      from: "上海南",
      to: "金山卫",
      directional: false,
    }).count,
    1,
  );
  assert.deepEqual(mapTools.fitMapViewport([]), mapTools.nationalViewport());
  assert.deepEqual(
    mapTools.fitMapViewport([[NaN, 30]]),
    mapTools.nationalViewport(),
  );
  const city = mapTools.fitMapViewport([[121, 31]]);
  assert.deepEqual(city.center, [121, 31]);
  assert.ok(city.zoom <= 6 && city.zoom > 1);
  const region = mapTools.fitMapViewport([
    [90, 20],
    [120, 40],
  ]);
  assert.deepEqual(region.center, [105, 30]);
  assert.ok(region.zoom >= 1 && region.zoom <= 6);
  assert.deepEqual(
    mapTools.featureCenter({
      properties: { center: [121, 31] },
      geometry: { type: "Polygon", coordinates: [] },
    }),
    [121, 31],
  );
  assert.equal(
    mapTools.featureCenter({
      properties: {},
      geometry: { type: "Point", coordinates: [121, 31] },
    }),
    null,
  );
});

test("动态箭头保留实际方向，同行不重复计数且不伪造返程", () => {
  const rows = [
    ticket("a"),
    ticket("b", { name: "乙", seat_num: "12B" }),
    ticket("c", {
      from: "上海虹桥",
      to: "北京南",
      date_time: "2025-01-07 10:00:00",
    }),
    ticket("d", {
      from: "成都东",
      to: "广州南",
      date_time: "2025-02-01 12:00:00",
    }),
  ];
  const flows = mapTools.directionalMapRoutes(aggregate(rows));
  assert.equal(flows.length, 3);
  assert.equal(
    flows.find((row) => row.from === "北京" && row.to === "上海").count,
    1,
  );
  assert.equal(
    flows.find((row) => row.from === "上海" && row.to === "北京").count,
    1,
  );
  assert.equal(
    flows.find((row) => row.from === "广州" && row.to === "成都"),
    undefined,
  );
  assert.deepEqual(mapTools.directionalMapRoutes(aggregate([])), []);
});
