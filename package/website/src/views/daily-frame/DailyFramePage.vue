<template>
  <div class="df-page space-y-5">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div><h1 class="text-2xl font-bold tracking-tight">一日一帧</h1><p class="mt-1 text-sm text-gray-500 dark:text-gray-400">每天留下一个代表瞬间</p></div>
      <RouterLink :to="filmRoute" class="df-primary"><Film class="h-4 w-4" />制作影片</RouterLink>
    </header>
    <p v-if="error" role="alert" class="rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{{ error }} <button type="button" class="underline" @click="boot">重试</button></p>
    <p v-if="loading && !store.calendar" role="status" class="py-20 text-center text-gray-500 dark:text-gray-400">正在打开你的日历…</p>
    <template v-if="store.settings && store.month">
      <div v-if="store.firstUse" class="df-panel border-primary-200 dark:border-primary-900">
        <h2 class="font-semibold">用已有照片开始，也可以慢慢记录</h2>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">一天挑一个瞬间，每个瞬间一秒。空缺日期会自然跳过。</p>
        <div class="mt-3 flex flex-wrap gap-2"><button class="df-primary" type="button" @click="startToday">从今天开始</button><button class="df-button" type="button" @click="store.firstUse = false; monthInput?.focus()">挑选过去的月份</button></div>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex gap-1 rounded-xl bg-gray-100 p-1 dark:bg-gray-800">
          <button v-for="tab in tabs" :key="tab.value" class="rounded-lg px-4 py-2 text-sm" :class="store.view === tab.value ? 'bg-white text-primary-600 shadow-sm dark:bg-gray-700 dark:text-primary-300' : 'text-gray-500 dark:text-gray-400'" type="button" :aria-pressed="store.view === tab.value" @click="changeView(tab.value)">{{ tab.label }}</button>
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">日历时区：{{ store.settings.timezone }} <button v-if="!store.settings.locked" type="button" class="text-primary-600 dark:text-primary-400" @click="changeTimezone">修改</button></p>
      </div>
      <WorkList v-if="store.view === 'works'" />
      <template v-else>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <button class="df-button !px-2" type="button" aria-label="上一月或上一年" @click="move(-1)"><ChevronLeft class="h-5 w-5" /></button>
            <input ref="monthInput" :value="store.month" type="month" min="1900-01" max="2200-12" class="df-input !w-auto" aria-label="选择年份月份" @change="setMonth(($event.target as HTMLInputElement).value)" />
            <button class="df-button !px-2" type="button" aria-label="下一月或下一年" @click="move(1)"><ChevronRight class="h-5 w-5" /></button>
            <button class="df-button hidden sm:inline-flex" type="button" @click="setMonth(store.settings.today!.slice(0, 7))">回到本月</button>
          </div>
          <button v-if="store.view === 'month'" type="button" class="df-button" :disabled="!canFill || loading" @click="fillVisible = true">填充本月</button>
          <RouterLink v-else :to="`/daily-frame/create?year=${year}`" class="df-button">制作这一年</RouterLink>
        </div>
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ store.view === 'month' ? '本月' : '这一年' }}已留下 {{ selectedCount }} 个瞬间<span v-if="store.view === 'month'"> · {{ pendingCount }} 天有素材待选</span></p>
        <section v-if="store.view === 'month'" class="df-panel" @touchstart.passive="touchStart" @touchend.passive="touchEnd">
          <div class="mb-3 grid grid-cols-7 text-center text-xs text-gray-500 dark:text-gray-400"><span v-for="weekday in weekdays" :key="weekday">{{ weekday }}</span></div>
          <div class="grid grid-cols-7 gap-1.5 sm:gap-3">
            <div v-for="n in padding" :key="`pad-${n}`" aria-hidden="true" />
            <button v-for="day in store.calendar?.days || []" :key="day.day" type="button" class="df-cell" :class="{ 'ring-2 ring-primary-500': day.day === store.settings.today, 'opacity-35': day.future }" :disabled="day.future" :aria-label="dayLabel(day)" :title="dayLabel(day)" @click="openDay(day.day)">
              <img v-if="day.frame?.available && !day.frame.removed && day.frame.photo_id" :src="thumbnailUrl(day.frame.photo_id)" alt="" loading="lazy" class="absolute inset-0 h-full w-full object-cover" />
              <span class="absolute left-1 top-1 rounded px-1 text-xs sm:left-2 sm:top-2 sm:text-sm" :class="day.frame?.available && !day.frame.removed ? 'bg-black/55 text-white' : 'text-gray-700 dark:text-gray-200'">{{ Number(day.day.slice(-2)) }}</span>
              <span v-if="day.frame && !day.frame.removed" class="absolute bottom-1 right-1 rounded bg-black/55 px-1 text-xs text-white">{{ !day.frame.available ? '需更换' : day.frame.mode === 'motion' ? '▶' : '✓' }}</span>
              <span v-else-if="!day.future" class="absolute inset-x-0 bottom-2 text-center text-[10px] text-gray-400 dark:text-gray-500 sm:text-xs">{{ day.candidate_count ? '选一帧' : '无素材' }}</span>
              <span v-if="day.frame?.caption && day.frame.available" class="absolute right-1 top-1 rounded bg-black/55 px-1 text-xs text-white" aria-label="有一句话">···</span>
            </button>
          </div>
        </section>
        <section v-else class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <button v-for="number in 12" :key="number" type="button" class="df-panel !p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" @click="openMonth(number)">
            <h2 class="mb-2 text-sm font-semibold">{{ number }} 月</h2>
            <div class="grid grid-cols-7 gap-0.5"><span v-for="n in monthPadding(`${year}-${String(number).padStart(2, '0')}`)" :key="`p-${n}`" />
              <span v-for="day in yearDays(number)" :key="day.day" class="relative aspect-square overflow-hidden rounded-sm bg-gray-100 dark:bg-gray-800" :title="dayLabel(day)">
                <img v-if="day.frame?.available && !day.frame.removed && day.frame.photo_id" :src="thumbnailUrl(day.frame.photo_id)" alt="" loading="lazy" class="h-full w-full object-cover" />
                <span v-else class="absolute inset-0 flex items-center justify-center text-[8px] text-gray-400 dark:text-gray-500">{{ Number(day.day.slice(-2)) }}</span>
              </span>
            </div>
          </button>
        </section>
      </template>
    </template>
    <FrameEditor v-if="selectedDay" v-model="editorVisible" :day="selectedDay" :preferred-photo="preferredPhoto" @saved="store.refresh" />
    <FillDialog v-model="fillVisible" :month="store.month" @saved="store.refresh" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { ChevronLeft, ChevronRight, Film } from 'lucide-vue-next'
import { useDailyFrameStore } from '@/stores/dailyFrameStore'
import { dailyFrameApi, dailyFrameError } from '@/api/dailyFrame'
import { monthPadding, shiftMonth } from '@/utils/dailyFrame'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { DailyFrameDay } from '@/types/dailyFrame'
import FrameEditor from './FrameEditor.vue'
import FillDialog from './FillDialog.vue'
import WorkList from './WorkList.vue'
import './daily-frame.css'

const store = useDailyFrameStore(), route = useRoute(), router = useRouter()
const selectedDay = ref(''), editorVisible = ref(false), fillVisible = ref(false), preferredPhoto = ref('')
const loading = ref(false), error = ref(''), monthInput = ref<HTMLInputElement | null>(null)
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const tabs = [{ value: 'month' as const, label: '月历' }, { value: 'year' as const, label: '年度' }, { value: 'works' as const, label: '我的作品' }]
const year = computed(() => Number(store.month.slice(0, 4)))
const padding = computed(() => store.month ? monthPadding(store.month) : 0)
const visibleDays = computed(() => store.view === 'year' ? store.yearCalendar?.days || [] : store.calendar?.days || [])
const selectedCount = computed(() => visibleDays.value.filter(day => day.frame?.available && !day.frame.removed).length)
const pendingCount = computed(() => visibleDays.value.filter(day => !day.future && day.candidate_count && (!day.frame || day.frame.removed)).length)
const canFill = computed(() => pendingCount.value > 0)
const filmRoute = computed(() => `/daily-frame/create?month=${store.month}`)
function dayLabel(day: DailyFrameDay) { return `${day.day}，${day.future ? '这一天还没到' : day.frame && !day.frame.removed ? day.frame.available ? `已选${day.frame.mode === 'motion' ? '动态片段' : '照片'}` : '素材失效，需更换' : day.candidate_count ? `${day.candidate_count} 个素材，待选` : '无素材'}` }
function yearDays(number: number) { const prefix = `${year.value}-${String(number).padStart(2, '0')}`; return (store.yearCalendar?.days || []).filter(day => day.day.startsWith(prefix)) }
async function reload() {
  loading.value = true; error.value = ''
  try { if (store.view === 'year') await store.loadYear(); else await store.loadMonth() }
  catch (err) { error.value = dailyFrameError(err) } finally { loading.value = false }
}
async function setMonth(value: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value) || value < '1900-01' || value > '2200-12') return
  store.month = value; await reload()
}
function move(delta: number) { void setMonth(shiftMonth(store.month, delta * (store.view === 'year' ? 12 : 1))) }
function openMonth(number: number) { store.view = 'month'; void setMonth(`${year.value}-${String(number).padStart(2, '0')}`) }
async function changeView(value: 'month' | 'year' | 'works') { store.view = value; if (value !== 'works') await reload() }
function openDay(day: string) { selectedDay.value = day; preferredPhoto.value = ''; editorVisible.value = true }
function startToday() { store.firstUse = false; openDay(store.settings!.today!) }
async function changeTimezone() {
  try {
    const result = await ElMessageBox.prompt('已有选帧后会固定时区，跨设备保持相同日期。', '日历时区', { inputValue: store.settings!.timezone || 'UTC', inputPlaceholder: 'Asia/Shanghai' })
    store.settings = await dailyFrameApi.initialize(result.value); await reload()
  } catch (err) { if (err !== 'cancel' && err !== 'close') error.value = dailyFrameError(err) }
}
let touchX = 0, touchY = 0
function touchStart(event: TouchEvent) { touchX = event.changedTouches[0].clientX; touchY = event.changedTouches[0].clientY }
function touchEnd(event: TouchEvent) { const x = event.changedTouches[0].clientX - touchX, y = event.changedTouches[0].clientY - touchY; if (Math.abs(x) > 75 && Math.abs(y) < 50) move(x < 0 ? 1 : -1) }
async function boot() {
  error.value = ''; loading.value = true
  try {
    await store.initialize()
    const requested = typeof route.query.month === 'string' ? route.query.month : typeof route.query.day === 'string' ? route.query.day.slice(0, 7) : ''
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(requested)) store.month = requested
    await reload()
    const photo = typeof route.query.photo === 'string' ? route.query.photo : ''
    const day = typeof route.query.day === 'string' ? route.query.day : ''
    if (photo) {
      const asset = await dailyFrameApi.asset(photo)
      if (!asset.day) throw new Error('照片没有拍摄日期')
      await setMonth(asset.day.slice(0, 7)); selectedDay.value = asset.day; preferredPhoto.value = photo; editorVisible.value = true
    } else if (/^\d{4}-\d{2}-\d{2}$/.test(day) && day <= store.settings!.today!) openDay(day)
    if (photo || day) void router.replace({ path: '/daily-frame', query: { month: store.month } })
  } catch (err) { error.value = dailyFrameError(err) } finally { loading.value = false }
}
onMounted(() => void boot())
</script>
