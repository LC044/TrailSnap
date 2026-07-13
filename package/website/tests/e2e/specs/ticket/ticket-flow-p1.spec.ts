import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

import { ensureAuthSession, authHeaders } from '../../helpers/auth'
import { e2eEnv } from '../../../../playwright/e2e-env'
import type { BaseResponse } from '../../helpers/data-probe'

/**
 * P1 - 车票管理（/ticket）
 *
 * 覆盖 doc/e2e-test-checklist.md §2.9：车票列表、类型筛选、排序、
 * 新增火车票/机票（UI）、批量删除。
 *
 * 数据策略：车票模块自洽——不依赖照片扫描管线。每个用例通过后端 API
 * 自建带唯一标记（E2ETK + 时间戳）的车票，用例结束时清理，保证可重复运行
 * 且不污染用户真实数据。后端车票 API 返回 BaseResponse（code=200，注意非 0）。
 *
 * 鉴权说明：`request` fixture 直连后端（e2eEnv.apiBaseUrl，不经 vite 代理），
 * 路径不带 /api 前缀，需手动带 Bearer 头（storageState 只注入浏览器 localStorage）。
 *
 * store 持久化注意：ticketStore 用 useStorage 把 viewMode/filterType/sortType/
 * searchQuery 持久化到 localStorage。每个用例 beforeEach 通过 addInitScript 清理
 * 这些键，保证各用例从默认态出发（timeline 视图、all 筛选、date 排序、空搜索）。
 */

/** 本轮测试唯一标记，所有自建车票的车次/航班号都含此串，便于隔离与清理 */
const MARK = `E2ETK${Date.now().toString(36)}`
/** 直连后端基址 */
const API = e2eEnv.apiBaseUrl

// ---------- localStorage 持久化键（ticketStore） ----------
const TICKET_LS_KEYS = [
  'ticket-view-mode',
  'ticket-filter-type',
  'ticket-sort-type',
  'ticket-selected-passenger',
  'ticket-search-query',
  'ticket-stats-map',
]

// ---------- 类型 ----------
interface TrainTicketBackend {
  id: string
  train_code: string
  departure_station: string
  arrival_station: string
  date_time: string
  carriage: string
  seat_num: string
  price: number
  seat_type: string
  name: string
  type?: string
}
interface FlightTicketBackend {
  id: string
  flight_code: string
  departure_city: string
  arrival_city: string
  date_time: string
  price: number
  name: string
  type?: string
}

// ---------- API 辅助 ----------

async function createTrainViaApi(
  request: APIRequestContext,
  payload: Record<string, unknown>,
  token: string,
): Promise<TrainTicketBackend> {
  const res = await request.post(`${API}/train-ticket`, {
    data: payload,
    headers: authHeaders(token),
    timeout: 10_000,
  })
  expect(res.ok(), `createTrain ${payload.train_code} should succeed`).toBeTruthy()
  const body = (await res.json()) as BaseResponse<TrainTicketBackend>
  expect(body.code, `createTrain code should be 200, got ${body.code}`).toBe(200)
  return body.data
}

async function createFlightViaApi(
  request: APIRequestContext,
  payload: Record<string, unknown>,
  token: string,
): Promise<FlightTicketBackend> {
  const res = await request.post(`${API}/flight-ticket`, {
    data: payload,
    headers: authHeaders(token),
    timeout: 10_000,
  })
  expect(res.ok(), `createFlight ${payload.flight_code} should succeed`).toBeTruthy()
  const body = (await res.json()) as BaseResponse<FlightTicketBackend>
  expect(body.code, `createFlight code should be 200, got ${body.code}`).toBe(200)
  return body.data
}

async function deleteTrain(request: APIRequestContext, id: string, token: string): Promise<void> {
  await request
    .delete(`${API}/train-ticket/${id}`, { headers: authHeaders(token), timeout: 10_000 })
    .catch(() => undefined)
}

async function deleteFlight(request: APIRequestContext, id: string, token: string): Promise<void> {
  await request
    .delete(`${API}/flight-ticket/${id}`, { headers: authHeaders(token), timeout: 10_000 })
    .catch(() => undefined)
}

/** 删除所有车次/航班号含 marker 的车票（火车+飞机），用于用例清理 */
async function cleanupMarkerTickets(request: APIRequestContext, token: string): Promise<void> {
  // 火车票
  try {
    const tRes = await request.get(`${API}/train-ticket?skip=0&limit=10000`, {
      headers: authHeaders(token),
      timeout: 10_000,
    })
    if (tRes.ok()) {
      const tBody = (await tRes.json()) as BaseResponse<{ items: TrainTicketBackend[]; total: number }>
      const items = tBody.data?.items ?? []
      await Promise.all(
        items.filter((t) => (t.train_code ?? '').includes(MARK)).map((t) => deleteTrain(request, t.id, token)),
      )
    }
  } catch {
    /* ignore */
  }
  // 飞机票
  try {
    const fRes = await request.get(`${API}/flight-ticket?skip=0&limit=1000`, {
      headers: authHeaders(token),
      timeout: 10_000,
    })
    if (fRes.ok()) {
      const fBody = (await fRes.json()) as BaseResponse<{ items: FlightTicketBackend[]; total: number }>
      const items = fBody.data?.items ?? []
      await Promise.all(
        items.filter((t) => (t.flight_code ?? '').includes(MARK)).map((t) => deleteFlight(request, t.id, token)),
      )
    }
  } catch {
    /* ignore */
  }
}

// ---------- UI 辅助 ----------

/**
 * 带退避的 goto：dev 套件多 worker 并发时 Vite dev server 偶发 net::ERR_ABORTED，
 * 重试 2 次给 dev server 喘息。
 */
async function gotoRetry(page: Page, url: string, retries = 2): Promise<void> {
  for (let i = 0; ; i++) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded' })
      return
    } catch (e) {
      if (i >= retries) throw e
      await page.waitForTimeout(1_000)
    }
  }
}

/** 切换到卡片视图（grid），便于按车次号定位单张车票卡片 */
async function switchToGridView(page: Page): Promise<void> {
  const gridBtn = page.getByTitle('卡片视图')
  await expect(gridBtn).toBeVisible({ timeout: 10_000 })
  // 只有当前不是 grid 时才点（aria-pressed 不可靠，直接点击无副作用——重复点仍是 grid）
  await gridBtn.click()
}

/**
 * 车票卡片定位器：grid 视图下按车次/航班号文本匹配。
 * 限定到 <section> 主区域，避免命中左侧 TicketStatsSidebar 里的 grid。
 */
function cardByCode(page: Page, code: string) {
  return page.locator('section div.grid.grid-cols-1 > div', { hasText: code })
}

/** 读取 grid 视图第一张卡片的车次/航班号（.font-mono 元素） */
async function firstCardCode(page: Page): Promise<string> {
  const text = await page
    .locator('section div.grid.grid-cols-1 > div')
    .first()
    .locator('.font-mono')
    .first()
    .textContent({ timeout: 5_000 })
  return (text ?? '').trim()
}

/** 选择类型筛选（全部/飞机票/高铁动车/普速列车） */
async function selectFilter(page: Page, value: 'all' | 'flight' | 'highspeed' | 'normal'): Promise<void> {
  // 筛选下拉是页面上唯一含「全部车票」选项的 select
  const filterSelect = page.locator('select:has(option:has-text("全部车票"))').first()
  await expect(filterSelect).toBeVisible({ timeout: 10_000 })
  await filterSelect.selectOption(value)
}

/** 点击排序按钮（日期/里程/时长/票价） */
async function clickSort(page: Page, label: '日期' | '里程' | '时长' | '票价'): Promise<void> {
  const btn = page.getByRole('button', { name: label, exact: true })
  await expect(btn).toBeVisible({ timeout: 5_000 })
  await btn.click()
  // 排序为本地 computed，无网络请求；短暂等待 DOM 重排
  await page.waitForTimeout(300)
}

test.describe.serial('P1 - 车票管理 @ticket', () => {
  // serial 文件：任一用例偶发失败会级联跳过后续。dev 套件默认 retries=0，
  // 给 1 次重试吸收 Vite dev server 并发下的偶发 ERR_ABORTED。
  test.use({ retries: 1 })

  let authToken = ''

  test.beforeEach(async ({ page, request }, testInfo) => {
    authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return

    // 清理 ticketStore 持久化到 localStorage 的视图/筛选/排序/搜索状态，
    // 保证每个用例从默认态（timeline + all + date + 空搜索）出发。
    // addInitScript 在每次导航前执行，先于 SPA 读取 localStorage。
    await page.context().addInitScript((keys) => {
      try {
        keys.forEach((k) => window.localStorage.removeItem(k))
      } catch {
        /* ignore */
      }
    }, TICKET_LS_KEYS)

    // 兜底：清理上一轮残留的同标记车票，避免偶发失败遗留脏数据
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.1 车票列表加载 - 后端车票在卡片视图中可见', async ({ page, request }, testInfo) => {
    const code = `G_${MARK}_list`
    await createTrainViaApi(
      request,
      {
        train_code: code,
        departure_station: '北京南',
        arrival_station: '上海虹桥',
        date_time: '2025-06-15T10:00:00',
        carriage: '03',
        seat_num: '12F',
        price: 198.5,
        seat_type: '二等座',
        name: 'E2E测试人',
        total_running_time: 268,
        total_mileage: 1318,
      },
      authToken,
    )

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)
    await expect(cardByCode(page, code).first()).toBeVisible({ timeout: 15_000 })

    // 清理
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.2 类型筛选 - 飞机票/高铁/普速 正确收敛', async ({ page, request }, testInfo) => {
    // 高铁（G 开头 → 高铁/动车）、普速（K 开头 → 普速列车）、飞机票各一张
    const gCode = `G_${MARK}_flt` // 高铁
    const kCode = `K_${MARK}_flt` // 普速
    const fCode = `${MARK}FLT_flt` // 飞机票
    await createTrainViaApi(
      request,
      {
        train_code: gCode,
        departure_station: '北京南',
        arrival_station: '上海虹桥',
        date_time: '2025-06-15T10:00:00',
        carriage: '03',
        seat_num: '12F',
        price: 100,
        seat_type: '二等座',
        name: 'E2E测试人',
      },
      authToken,
    )
    await createTrainViaApi(
      request,
      {
        train_code: kCode,
        departure_station: '北京西',
        arrival_station: '广州',
        date_time: '2025-01-15T08:00:00',
        carriage: '10',
        seat_num: '05下',
        price: 500,
        seat_type: '硬卧',
        name: 'E2E测试人',
      },
      authToken,
    )
    await createFlightViaApi(
      request,
      {
        flight_code: fCode,
        departure_city: '北京首都',
        arrival_city: '上海虹桥',
        date_time: '2025-03-15T14:00:00',
        price: 300,
        name: 'E2E测试人',
        total_running_time: 150,
        total_mileage: 1200,
      },
      authToken,
    )

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)
    // 等三张自建车票就绪
    await expect(cardByCode(page, gCode).first()).toBeVisible({ timeout: 15_000 })

    // 1) 飞机票筛选：只显示飞机票
    await selectFilter(page, 'flight')
    await expect(cardByCode(page, fCode).first()).toBeVisible({ timeout: 5_000 })
    await expect(cardByCode(page, gCode)).toHaveCount(0)
    await expect(cardByCode(page, kCode)).toHaveCount(0)

    // 2) 高铁/动车筛选：只显示 G 开头
    await selectFilter(page, 'highspeed')
    await expect(cardByCode(page, gCode).first()).toBeVisible({ timeout: 5_000 })
    await expect(cardByCode(page, fCode)).toHaveCount(0)
    await expect(cardByCode(page, kCode)).toHaveCount(0)

    // 3) 普速列车筛选：只显示 K 开头
    await selectFilter(page, 'normal')
    await expect(cardByCode(page, kCode).first()).toBeVisible({ timeout: 5_000 })
    await expect(cardByCode(page, gCode)).toHaveCount(0)
    await expect(cardByCode(page, fCode)).toHaveCount(0)

    // 4) 全部车票：三张都回来
    await selectFilter(page, 'all')
    await expect(cardByCode(page, gCode).first()).toBeVisible({ timeout: 5_000 })
    await expect(cardByCode(page, kCode).first()).toBeVisible({ timeout: 5_000 })
    await expect(cardByCode(page, fCode).first()).toBeVisible({ timeout: 5_000 })

    // 清理
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.3 排序 - 按日期与按票价排序后首张卡片不同', async ({ page, request }, testInfo) => {
    // 两张火车票，日期与票价反向相关，便于区分两种排序的首张：
    //   A：日期最新(2025-06)、票价最低(100)
    //   B：日期最旧(2025-01)、票价最高(500)
    const codeA = `G_${MARK}_sA` // 日期最新 / 票价最低
    const codeB = `K_${MARK}_sB` // 日期最旧 / 票价最高
    await createTrainViaApi(
      request,
      {
        train_code: codeA,
        departure_station: '北京南',
        arrival_station: '上海虹桥',
        date_time: '2025-06-15T10:00:00',
        carriage: '03',
        seat_num: '12F',
        price: 100,
        seat_type: '二等座',
        name: 'E2E测试人',
      },
      authToken,
    )
    await createTrainViaApi(
      request,
      {
        train_code: codeB,
        departure_station: '北京西',
        arrival_station: '广州',
        date_time: '2025-01-15T08:00:00',
        carriage: '10',
        seat_num: '05下',
        price: 500,
        seat_type: '硬卧',
        name: 'E2E测试人',
      },
      authToken,
    )

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)

    // 用搜索框隔离出本标记车票，排除用户真实数据干扰
    const search = page.getByPlaceholder('搜索车次 / 地点 / 乘车人')
    await expect(search).toBeVisible({ timeout: 10_000 })
    await search.fill(MARK)
    // 搜索为本地过滤（filteredTickets 立即重算），等两张卡都出现
    await expect(cardByCode(page, codeA).first()).toBeVisible({ timeout: 10_000 })
    await expect(cardByCode(page, codeB).first()).toBeVisible({ timeout: 5_000 })

    // 按日期排序（倒序：最新在前）→ 首张应为 codeA（6 月）
    await clickSort(page, '日期')
    expect(await firstCardCode(page)).toBe(codeA)

    // 按票价排序（倒序：最高在前）→ 首张应为 codeB（500 元）
    await clickSort(page, '票价')
    expect(await firstCardCode(page)).toBe(codeB)

    // 清理
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.4 新增火车票 - UI 表单提交后列表出现', async ({ page, request }, testInfo) => {
    test.setTimeout(60_000)
    const code = `G_${MARK}_ui`

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)

    // 点击头部「新增」→ 弹出类型选择器 → 选「火车票」
    await page.locator('nav button', { hasText: '新增' }).first().click()
    const trainTypeBtn = page.locator('button', { hasText: '火车票' }).first()
    await expect(trainTypeBtn).toBeVisible({ timeout: 5_000 })
    await trainTypeBtn.click()

    // 等表单弹窗渲染（车次输入框出现）
    const codeInput = page.locator('input[placeholder="G101 / Z123"]')
    await expect(codeInput).toBeVisible({ timeout: 5_000 })
    await codeInput.fill(code)
    await page.locator('input[placeholder="如：北京南"]').fill('北京南')
    await page.locator('input[placeholder="如：上海虹桥"]').fill('上海虹桥')
    await page.locator('input[placeholder="如：张三"]').fill('E2E测试人')
    await page.locator('input[type="datetime-local"]').fill('2025-08-15T10:00')
    await page.locator('input[placeholder="如：03 / 8A"]').fill('03')
    await page.locator('input[placeholder="如：12A / 05下"]').fill('12F')
    await page.locator('input[placeholder="198.5"]').fill('199.5')

    // 保存
    const saveBtn = page.locator('div.fixed.z-50 button', { hasText: '保存' }).first()
    await expect(saveBtn).toBeVisible({ timeout: 5_000 })
    await saveBtn.click()

    // 成功提示
    await expect(
      page.locator('.el-message', { hasText: '新增成功' }).last(),
    ).toBeVisible({ timeout: 10_000 })

    // 列表中出现刚创建的车票（fetchTickets(true) 强制刷新后）
    await expect(cardByCode(page, code).first()).toBeVisible({ timeout: 15_000 })

    // 清理
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.5 新增机票 - UI 表单提交后列表出现', async ({ page, request }, testInfo) => {
    test.setTimeout(60_000)
    const code = `${MARK}FLT_ui`

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)

    await page.locator('nav button', { hasText: '新增' }).first().click()
    const flightTypeBtn = page.locator('button', { hasText: '飞机票' }).first()
    await expect(flightTypeBtn).toBeVisible({ timeout: 5_000 })
    await flightTypeBtn.click()

    const codeInput = page.locator('input[placeholder="如：MU2393"]')
    await expect(codeInput).toBeVisible({ timeout: 5_000 })
    await codeInput.fill(code)
    await page.locator('input[placeholder="如：北京首都"]').fill('北京首都')
    await page.locator('input[placeholder="如：上海虹桥"]').fill('上海虹桥')
    await page.locator('input[placeholder="如：张三"]').fill('E2E测试人')
    await page.locator('input[type="datetime-local"]').fill('2025-09-01T14:00')
    await page.locator('input[placeholder="1098"]').fill('1098')

    const saveBtn = page.locator('div.fixed.z-50 button', { hasText: '保存' }).first()
    await expect(saveBtn).toBeVisible({ timeout: 5_000 })
    await saveBtn.click()

    await expect(
      page.locator('.el-message', { hasText: '新增成功' }).last(),
    ).toBeVisible({ timeout: 10_000 })

    await expect(cardByCode(page, code).first()).toBeVisible({ timeout: 15_000 })

    // 清理
    await cleanupMarkerTickets(request, authToken)
  })

  // ----------------------------------------------------------------------

  test('2.9.6 批量删除 - 选中后删除并从列表消失', async ({ page, request }, testInfo) => {
    test.setTimeout(60_000)
    const code1 = `G_${MARK}_del1`
    const code2 = `K_${MARK}_del2`
    await createTrainViaApi(
      request,
      {
        train_code: code1,
        departure_station: '北京南',
        arrival_station: '上海虹桥',
        date_time: '2025-06-15T10:00:00',
        carriage: '03',
        seat_num: '12F',
        price: 100,
        seat_type: '二等座',
        name: 'E2E测试人',
      },
      authToken,
    )
    await createTrainViaApi(
      request,
      {
        train_code: code2,
        departure_station: '北京西',
        arrival_station: '广州',
        date_time: '2025-01-15T08:00:00',
        carriage: '10',
        seat_num: '05下',
        price: 500,
        seat_type: '硬卧',
        name: 'E2E测试人',
      },
      authToken,
    )

    await gotoRetry(page, '/ticket')
    await switchToGridView(page)

    // 搜索本标记，隔离出两张待删车票（避免误选用户真实车票）
    const search = page.getByPlaceholder('搜索车次 / 地点 / 乘车人')
    await expect(search).toBeVisible({ timeout: 10_000 })
    await search.fill(MARK)
    await expect(cardByCode(page, code1).first()).toBeVisible({ timeout: 15_000 })
    await expect(cardByCode(page, code2).first()).toBeVisible({ timeout: 5_000 })

    // 全选（仅选当前 filteredTickets = 两张本标记车票）
    const selectAll = page.locator('.el-checkbox', { hasText: '全选' }).first()
    await expect(selectAll).toBeVisible({ timeout: 5_000 })
    await selectAll.click()

    // 删除选中
    const batchDelBtn = page.locator('button', { hasText: '删除选中' }).first()
    await expect(batchDelBtn).toBeVisible({ timeout: 5_000 })
    await batchDelBtn.click()

    // ElMessageBox 确认（点 primary 按钮兼容中英文文案）
    const confirmBtn = page.locator('.el-message-box .el-button--primary').first()
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
    await confirmBtn.click()

    // 成功提示
    await expect(
      page.locator('.el-message', { hasText: '批量删除成功' }).last(),
    ).toBeVisible({ timeout: 10_000 })

    // 两张车票从列表消失
    await expect(cardByCode(page, code1)).toHaveCount(0, { timeout: 10_000 })
    await expect(cardByCode(page, code2)).toHaveCount(0)

    // 清理（已删除，兜底）
    await cleanupMarkerTickets(request, authToken)
  })
})
