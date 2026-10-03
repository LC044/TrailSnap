<template>
  <Teleport to="body">
    <section class="mobile-diary-reader" :class="{ dark: isDarkMode }" :style="themeStyle" aria-label="全屏日记阅读器">
      <header class="reader-header">
        <button aria-label="退出日记阅读" @click="router.push('/chapters')"><ArrowLeft :size="20" /></button>
        <span class="truncate font-serif">{{ chapter.title }}<small>{{ day?.day || '影像日记' }}</small></span>
        <button aria-label="显示或隐藏阅读工具" :aria-expanded="controls" @click="controls = !controls"><MoreHorizontal :size="22" /></button>
      </header>
      <div ref="paperHost" class="reader-paper" @pointerdown="pointerDown" @pointerup="pointerUp" @pointercancel="pointerCancel" @click.capture="paperClick">
        <div v-if="loading" class="reader-status" role="status">正在翻开日记…</div>
        <div v-else-if="!day" class="reader-status"><p>{{ error ? '日记暂时无法打开' : '这段时光还没有影像' }}</p><button @click="$emit('reload')">重新加载</button><button @click="directory = true">选择日期</button></div>
        <ChapterBook v-else class="immersive-book" single-page portrait :title="chapter.title" :page-key="day.day + ':' + leaf" :direction="direction" :duration="460" @busy="busy = $event">
          <section class="diary-page reader-leaf"><div class="reader-leaf-inner">
            <div class="reader-running"><span>{{ day.day.replaceAll('-', '.') }}</span><span>{{ current?.kind === 'photos' ? '影像' : current?.kind === 'text' ? '日记' : '人物与记忆' }}</span></div>
            <template v-if="current?.kind === 'photos'">
              <h2 class="reader-date">{{ day.day.slice(5).replace('-', ' / ') }}<small>{{ day.photo_count }} 张影像</small></h2>
              <div class="reader-photos" :class="{ 'two-photos': current.photos.length > 1 }">
                <button v-for="photo in current.photos" :key="photo.id" :aria-label="'查看照片 ' + photo.filename" @click="$emit('photo', photo.id)"><DiaryPhoto :id="photo.id" :alt="photo.filename" size="medium" contain /></button>
              </div>
              <p class="reader-note">每日精选 · {{ leaf + 1 }} / {{ photoLeaves }} 页</p>
            </template>
            <template v-else-if="current?.kind === 'text'">
              <h2 class="reader-title">{{ day.places[0] || '时光的一页' }}<small v-if="current.part > 0">续页</small></h2>
              <p class="reader-prose">{{ current.text }}</p>
              <p class="reader-note">{{ generationError || (generating ? 'AI 正在整理…' : source === 'manual' ? '你留下的文字' : caption ? 'AI 整理 · 已保存' : '在工具栏中写下这一天，或点击 AI 整理') }}</p>
            </template>
            <template v-else-if="current?.kind === 'clues'">
              <h2 class="reader-title">日记里的线索</h2>
              <div class="reader-clues">
                <template v-for="item in current.items" :key="item.key">
                  <RouterLink v-if="item.to" :to="item.to">{{ item.label }}<ArrowUpRight :size="16" /></RouterLink>
                  <p v-else>{{ item.label }}</p>
                </template>
              </div>
            </template>
            <span class="reader-folio">{{ leaf + 1 }} / {{ leaves.length }}</span>
          </div></section>
        </ChapterBook>
      </div>
      <footer class="reader-footer">
        <div class="reader-progress">
          <button aria-label="上一页" :disabled="busy || (index === 0 && leaf === 0)" @click="step(-1)"><ChevronLeft :size="20" /></button>
          <button aria-label="打开日记目录" @click="directory = true">{{ index + 1 }} / {{ total }} 天 · {{ leaf + 1 }} / {{ leaves.length || 1 }} 页</button>
          <button aria-label="下一页" :disabled="busy || (index + 1 >= total && leaf + 1 >= leaves.length)" @click="step(1)"><ChevronRight :size="20" /></button>
        </div>
        <nav v-show="controls" class="reader-tools" aria-label="阅读工具">
          <button @click="directory = true"><List :size="19" /><span>目录</span></button>
          <button :disabled="!day" @click="$emit('all')"><Images :size="19" /><span>全部影像</span></button>
          <button :disabled="!day || busy" @click="$emit('edit')"><Feather :size="19" /><span>写日记</span></button>
          <button :disabled="!day || generating || !canGenerate" @click="$emit('generate')"><Sparkles :size="19" /><span>{{ generating ? '整理中' : 'AI 整理' }}</span></button>
        </nav>
        <p v-show="!controls" class="reader-hint" @click="controls = true">轻触中间显示工具 · 左右轻扫翻页</p>
      </footer>
      <el-dialog v-model="directory" title="日记目录" width="min(94vw, 440px)" append-to-body>
        <div class="flex gap-3">
          <label class="text-sm">年份<select v-model="filterYear" class="mt-2 block min-h-11 rounded border border-gray-200 bg-white px-3 dark:border-gray-700 dark:bg-gray-800"><option value="">全部年份</option><option v-for="y in chapter.years" :key="y" :value="String(y)">{{ y }} 年</option></select></label>
          <label class="text-sm">月份<select v-model="filterMonth" class="mt-2 block min-h-11 rounded border border-gray-200 bg-white px-3 dark:border-gray-700 dark:bg-gray-800"><option value="">全部月份</option><option v-for="m in 12" :key="m" :value="String(m)">{{ m }} 月</option></select></label>
          <button class="mt-7 min-h-11 text-primary-600 dark:text-primary-400" @click="applyFilters">查看</button>
        </div>
        <div class="mt-4 max-h-[40dvh] overflow-y-auto"><button v-for="(entry, i) in days" :key="entry.day" class="flex min-h-12 w-full items-center justify-between border-b border-gray-200 text-left dark:border-gray-700" @click="chooseDay(i)"><span>{{ entry.day }}</span><span class="text-xs text-gray-500 dark:text-gray-400">{{ entry.photo_count }} 张影像</span></button><button v-if="days.length < total" class="min-h-12 text-primary-600 dark:text-primary-400" @click="$emit('more')">{{ loadingMore ? '加载中…' : '查看更多日期' }}</button></div>
        <div class="mt-4 flex flex-col border-t border-gray-200 pt-3 dark:border-gray-700">
          <button class="min-h-11 text-left text-primary-600 dark:text-primary-400" @click="$emit('book')">扉页与年度回顾 →</button>
          <RouterLink :to="`/chapters/${chapter.id}/edit`" class="flex min-h-11 items-center">编辑章节</RouterLink>
          <button class="min-h-11 text-left" @click="directory = false; $emit('manage')">章节管理</button>
        </div>
      </el-dialog>
    </section>
  </Teleport>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowUpRight, ChevronLeft, ChevronRight, Feather, Images, List, MoreHorizontal, Sparkles } from 'lucide-vue-next'
import { injectTheme } from '@/composables/useTheme'
import type { ChapterDay, ChapterDetail, ChapterPhoto } from '@/types/chapter'
import ChapterBook from './ChapterBook.vue'
import DiaryPhoto from './DiaryPhoto.vue'
const props = defineProps<{ chapter: ChapterDetail; day?: ChapterDay; days: ChapterDay[]; index: number; total: number; caption: string; source: string | null; generationError?: string; generating: boolean; canGenerate: boolean; loading: boolean; loadingMore: boolean; error: boolean; year: string; month: string }>()
const emit = defineEmits<{ move: [delta: number]; jump: [index: number]; filter: [year: string, month: string]; more: []; reload: []; photo: [id: string]; all: []; edit: []; generate: []; book: []; manage: [] }>()
const { isDarkMode, themeStyle } = injectTheme()
const router = useRouter()
const controls = ref(false), directory = ref(false), busy = ref(false), leaf = ref(0), direction = ref(1)
const filterYear = ref(props.year), filterMonth = ref(props.month)
const paperHost = ref<HTMLElement>(), paperWidth = ref(350), paperHeight = ref(650)
let observer: ResizeObserver | undefined, arrivingFrom = 1, activePointer: number | undefined, pointerX = 0, pointerY = 0, pointerTime = 0, suppressClickUntil = 0
let previousOverflow = ''
type Leaf = { kind: 'photos'; photos: ChapterPhoto[] } | { kind: 'text'; text: string; part: number } | { kind: 'clues'; items: { key: string; label: string; to?: string }[] }
const photosPerLeaf = computed(() => paperHeight.value < 500 ? 1 : 2)
const photoLeaves = computed(() => Math.ceil((props.day?.photos.length || 0) / photosPerLeaf.value))
const leaves = computed<Leaf[]>(() => {
  const day = props.day
  if (!day) return []
  const pages: Leaf[] = []
  for (let i = 0; i < day.photos.length; i += photosPerLeaf.value) pages.push({ kind: 'photos', photos: day.photos.slice(i, i + photosPerLeaf.value) })
  const context = document.createElement('canvas').getContext('2d')!
  const compact = window.innerHeight <= 600
  context.font = compact ? '16px serif' : '17px serif'
  const width = Math.max(180, paperWidth.value - 48)
  const maxLines = Math.max(1, Math.floor((paperHeight.value - (compact ? 180 : 220)) / (compact ? 28 : 32)))
  const lines: string[] = []; let line = ''
  const body = props.caption || (props.source === 'manual' ? '这一天，留给照片来讲述。你可以在阅读工具中修改日记文字。' : '这一天的影像已经收录。打开阅读工具，可以写下自己的日记，或点击 AI 整理文案。')
  const tokens = body.replaceAll('\r', '').match(/[A-Za-z0-9]+(?:[’'._-][A-Za-z0-9]+)*|[^\r]/gu) || []
  for (const token of tokens) {
    if (token === '\n') { lines.push(line); line = ''; continue }
    // Keep ordinary English words together; oversized URLs still wrap safely.
    const pieces = context.measureText(token).width > width ? Array.from(token) : [token]
    for (const piece of pieces) {
      if (context.measureText(line + piece).width > width && line) { lines.push(line); line = piece } else line += piece
    }
  }
  if (line) lines.push(line)
  for (let i = 0; i < lines.length; i += maxLines) pages.push({ kind: 'text', text: lines.slice(i, i + maxLines).join('\n'), part: i / maxLines })
  const clues = [...day.people.map(p => ({key:'person:'+p.id,label:p.name,to:'/album/people/'+p.id})), ...day.tags.map(t => ({key:'tag:'+t,label:'# '+t})), ...day.events.map(e => ({key:'event:'+e.id,label:e.title,to:'/memories/'+e.id}))]
  const perPage = Math.max(2, Math.floor((paperHeight.value - 140) / 56))
  for (let i = 0; i < clues.length; i += perPage) pages.push({kind:'clues',items:clues.slice(i,i+perPage)})
  return pages
})
const current = computed(() => leaves.value[Math.min(leaf.value, leaves.value.length - 1)])
watch(() => props.day?.day, () => { leaf.value = arrivingFrom < 0 ? Math.max(0, leaves.value.length - 1) : 0 }, { flush: 'pre' })
watch(() => leaves.value.length, length => { if (leaf.value >= length) leaf.value = Math.max(0, length - 1) })
async function step(delta: number) {
  if (busy.value || props.loadingMore || !props.day) return
  direction.value = delta; controls.value = false
  const target = leaf.value + delta
  if (target >= 0 && target < leaves.value.length) leaf.value = target
  else { arrivingFrom = delta; emit('move', delta) }
}
function pointerDown(event: PointerEvent) {
  if (event.isPrimary === false || (event.target as HTMLElement).closest('input,textarea,select')) return
  activePointer = event.pointerId; pointerX = event.clientX; pointerY = event.clientY; pointerTime = performance.now()
}
function pointerCancel() { activePointer = undefined }
function pointerUp(event: PointerEvent) {
  if (event.pointerId !== activePointer) return
  activePointer = undefined
  const dx = event.clientX - pointerX, dy = event.clientY - pointerY
  const fast = performance.now() - pointerTime < 280
  if (Math.abs(dx) >= (fast ? 18 : 30) && Math.abs(dx) > Math.abs(dy) * 1.15) {
    suppressClickUntil = performance.now() + 500; event.preventDefault(); void step(dx < 0 ? 1 : -1)
  }
}
function paperClick(event: MouseEvent) {
  if (performance.now() < suppressClickUntil) { event.preventDefault(); event.stopPropagation(); return }
  if ((event.target as HTMLElement).closest('button,a')) return
  const bounds = paperHost.value!.getBoundingClientRect(), fraction = (event.clientX - bounds.left) / bounds.width
  if (fraction < .22) void step(-1)
  else if (fraction > .78) void step(1)
  else controls.value = !controls.value
}
function chooseDay(index: number) { arrivingFrom = 1; direction.value = index >= props.index ? 1 : -1; directory.value = false; emit('jump', index) }
function applyFilters() { directory.value = false; arrivingFrom = 1; emit('filter', filterYear.value, filterMonth.value) }
onMounted(() => {
  previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'
  observer = new ResizeObserver(entries => { paperWidth.value = entries[0].contentRect.width; paperHeight.value = entries[0].contentRect.height })
  if (paperHost.value) observer.observe(paperHost.value)
})
onBeforeUnmount(() => { observer?.disconnect(); document.body.style.overflow = previousOverflow })
</script>
<style scoped>
.mobile-diary-reader { position:fixed; inset:0; z-index:80; height:100dvh; display:flex; flex-direction:column; overflow:hidden; background:#fffdf8; color:#44403c; padding-top:env(safe-area-inset-top); padding-bottom:env(safe-area-inset-bottom); }
.mobile-diary-reader.dark { background:#242526; color:#e7e5e4; }
.reader-header { flex-shrink:0; display:flex; align-items:center; justify-content:space-between; height:52px; padding:0 12px; font-size:14px; }
.reader-header button { display:grid; place-items:center; width:44px; height:44px; }
.reader-header span { text-align:center; max-width:70%; }
.reader-header small { font:10px sans-serif; display:block; color:#78716c; margin-top:2px; }
.reader-paper { flex:1; min-height:0; overflow:hidden; touch-action:pan-y; user-select:none; }
.reader-paper :deep(.immersive-book) { padding:0; height:100%; border:0; border-radius:0; background:transparent; box-shadow:none; }
.reader-paper :deep(.book-stage) { height:100%; overflow:hidden; }
.reader-paper :deep(.diary-spread) { border-radius:0; grid-template-columns:minmax(0,1fr); }
.reader-paper :deep(.book-stage::after) { display:none; }
.reader-paper :deep(.reader-leaf) { padding:0; height:100%; overflow:hidden; }
.reader-leaf-inner { padding:18px 24px 40px; height:100%; display:flex; flex-direction:column; overflow:hidden; }
.reader-running { display:flex; justify-content:space-between; font-size:10px; color:#78716c; padding-bottom:14px; border-bottom:1px solid #e7e2d8; flex-shrink:0; }
.reader-date { display:flex; align-items:baseline; justify-content:space-between; font:34px serif; margin:18px 0; flex-shrink:0; }
.reader-date small { font:11px sans-serif; color:#78716c; }
.reader-photos { flex:1; min-height:0; display:grid; gap:12px; grid-template-rows:minmax(0,1fr); }
.reader-photos.two-photos { grid-template-rows:repeat(2,minmax(0,1fr)); }
.reader-photos button { min-height:0; overflow:hidden; padding:6px; background:#fff; box-shadow:0 3px 12px rgb(45 36 20 / 8%); }
.reader-title { font:24px/1.5 serif; margin:20px 0; flex-shrink:0; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.reader-title small { margin-left:12px; font-size:12px; color:#78716c; }
.reader-prose { font:17px/32px serif; white-space:pre-wrap; overflow-wrap:anywhere; margin:0; flex-shrink:0; }
.reader-note { font-size:10px; color:#78716c; margin-top:auto; padding-top:14px; flex-shrink:0; }
.reader-folio { position:absolute; right:24px; bottom:14px; font:italic 11px serif; color:#78716c; }
.reader-clues { display:flex; flex-direction:column; gap:8px; }
.reader-clues a,.reader-clues p { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:48px; max-height:48px; overflow:hidden; font-size:14px; border-bottom:1px solid #e7e2d8; }
.reader-footer { flex-shrink:0; height:96px; padding:0 12px; }
.reader-progress { display:flex; justify-content:space-between; align-items:center; height:40px; font-size:11px; color:#78716c; }
.reader-progress button { min-height:40px; min-width:44px; display:grid; place-items:center; }
.reader-tools { display:grid; grid-template-columns:repeat(4,1fr); height:56px; border-top:1px solid #e7e2d8; }
.reader-tools button { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; font-size:10px; }
button:disabled { opacity:.35; }
.reader-hint { text-align:center; padding-top:14px; font-size:10px; color:#78716c; }
.reader-status { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:20px; font-size:14px; }
.reader-status button { min-height:44px; }
.dark .reader-title small,.dark .reader-header small,.dark .reader-running,.dark .reader-date small,.dark .reader-note,.dark .reader-folio,.dark .reader-progress,.dark .reader-hint { color:#a8a29e; }
.dark .reader-running,.dark .reader-tools,.dark .reader-clues a,.dark .reader-clues p { border-color:#44403c; }
.dark .reader-photos button { background:#343536; }
@media (max-height:600px) {
  .reader-header { height:44px; }
  .reader-footer { height:76px; }
  .reader-progress { height:32px; }
  .reader-progress button { min-height:32px; }
  .reader-tools { height:44px; }
  .reader-leaf-inner { padding:12px 24px 30px; }
  .reader-running { padding-bottom:8px; }
  .reader-date { font-size:26px; margin:10px 0; }
  .reader-title { font-size:20px; line-height:28px; margin:12px 0; }
  .reader-prose { font-size:16px; line-height:28px; }
}
</style>
