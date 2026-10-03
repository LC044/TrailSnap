import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { dailyFrameApi } from '@/api/dailyFrame'
import { useUserStore } from '@/stores/user'
import { monthRange } from '@/utils/dailyFrame'
import type { DailyFrameSettings, DailyFrameCalendar } from '@/types/dailyFrame'

export const useDailyFrameStore = defineStore('daily-frame', () => {
  const settings = ref<DailyFrameSettings | null>(null)
  const calendar = ref<DailyFrameCalendar | null>(null)
  const yearCalendar = ref<DailyFrameCalendar | null>(null)
  const month = ref('')
  const view = ref<'month' | 'year' | 'works'>('month')
  const firstUse = ref(false)
  let calendarRequest = 0
  let yearRequest = 0
  let accountEpoch = 0
  let initialization: Promise<DailyFrameSettings> | null = null
  const user = useUserStore()
  watch(() => user.userInfo?.id, () => {
    accountEpoch++; calendarRequest++; yearRequest++
    settings.value = null; calendar.value = null; yearCalendar.value = null; month.value = ''; view.value = 'month'
    initialization = null
    firstUse.value = false
  })

  async function initialize(): Promise<DailyFrameSettings> {
    if (settings.value) return settings.value
    if (initialization) return initialization
    const epoch = accountEpoch
    initialization = (async (): Promise<DailyFrameSettings> => {
      let result = await dailyFrameApi.settings()
      if (epoch !== accountEpoch) return initialize()
      if (!result.initialized) {
        firstUse.value = true
        result = await dailyFrameApi.initialize(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
      }
      if (epoch === accountEpoch) {
        settings.value = result
        if (!month.value) month.value = result.today!.slice(0, 7)
      }
      else return initialize()
      return result
    })()
    try { return await initialization } finally { if (epoch === accountEpoch) initialization = null }
  }

  async function loadMonth(value = month.value) {
    const request = ++calendarRequest
    const result = await dailyFrameApi.calendar(...monthRange(value))
    if (request === calendarRequest) calendar.value = result
  }

  async function loadYear(year = Number(month.value.slice(0, 4))) {
    const request = ++yearRequest
    const result = await dailyFrameApi.calendar(`${year}-01-01`, `${year}-12-31`)
    if (request === yearRequest) yearCalendar.value = result
  }

  async function refresh() {
    const epoch = accountEpoch
    const result = await dailyFrameApi.settings()
    if (epoch !== accountEpoch) return
    settings.value = result
    await loadMonth()
    if (view.value === 'year') await loadYear()
  }

  return { settings, calendar, yearCalendar, month, view, firstUse, initialize, loadMonth, loadYear, refresh }
})
