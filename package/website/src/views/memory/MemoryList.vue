<template>
  <div class="memory-collection" :class="{ 'memory-collection--review': isReview }">
    <header ref="masthead" class="memory-masthead" tabindex="-1">
      <div v-if="isReview" class="memory-review-heading">
        <BackButton to="/memories" label="返回记忆" />
        <h1 class="journal-page-title">整理记忆</h1>
      </div>
      <h1 v-else class="journal-page-title">记忆</h1>
      <div v-if="!isReview" class="memory-command-bar" aria-label="记忆操作">
        <RouterLink to="/memories/new" class="memory-command memory-command--add" aria-label="新建记忆"><Plus /><span>新建记忆</span></RouterLink>
        <div class="relative">
          <button type="button" class="memory-command" aria-label="更多记忆操作" :aria-expanded="showActions" aria-haspopup="menu" @click="showActions = !showActions">
            <MoreHorizontal aria-hidden="true" />
          </button>
          <AdaptiveMenu v-model="showActions" title="记忆操作" mobile-presentation="popover" glass>
            <button v-if="canSelect" type="button" class="ts-action-row" @click="showActions = false; toggleSelectMode()"><ListChecks />{{ selectMode ? '取消选择' : '批量合并' }}</button>
            <button class="ts-action-row" @click="showActions = false; createWithAgent()"><Bot />和 AI 创建</button>
            <RouterLink to="/daily-frame" class="ts-action-row" @click="showActions = false"><Film />一日一帧</RouterLink>
            <RouterLink to="/explore/relations" class="ts-action-row" @click="showActions = false"><Network />关联探索</RouterLink>
          </AdaptiveMenu>
        </div>
      </div>
    </header>

    <ChapterShelf v-if="!isReview" class="memory-chapters" />

    <section ref="memoryResults" class="memory-results" aria-label="记忆列表" :aria-busy="store.loading">
      <div v-if="isReview" class="memory-filters">
        <nav aria-label="记忆状态">
          <RouterLink v-for="tab in reviewTabs" :key="tab.status" :to="{ name: 'MemoryList', query: { status: tab.status } }" :aria-current="viewStatus === tab.status ? 'page' : undefined">
            {{ tab.label }}<span>{{ store.counts[tab.status] }}</span>
          </RouterLink>
        </nav>
        <div v-if="viewStatus === 'candidate'" class="memory-command-bar">
          <button type="button" class="memory-command memory-discover" :aria-label="store.discovering ? '正在发现记忆' : '发现记忆'" :disabled="store.discovering" @click="runDiscovery">
            <RefreshCw :class="{ 'motion-safe:animate-spin': store.discovering }" aria-hidden="true" /><span>{{ store.discovering ? '正在发现…' : '发现记忆' }}</span>
          </button>
          <button v-if="canSelect" type="button" class="memory-command memory-batch" :aria-label="selectMode ? '取消选择' : '批量合并'" :aria-pressed="selectMode" @click="toggleSelectMode">
            <ListChecks aria-hidden="true" /><span>{{ selectMode ? '取消选择' : '批量合并' }}</span>
          </button>
        </div>
      </div>
      <div v-else class="memory-section-heading">
        <h2>我的记忆 <span>{{ store.counts.confirmed }}</span></h2>
        <RouterLink :to="{ name: 'MemoryList', query: { status: 'candidate' } }" class="memory-review-link">
          <ListFilter aria-hidden="true" />整理记忆<ChevronRight aria-hidden="true" />
        </RouterLink>
      </div>

      <div v-if="selectMode" class="memory-selection">
        <span aria-live="polite">已选 {{ selectedIds.length }} 段记忆</span>
        <div class="memory-command-bar">
          <button v-if="!isReview" type="button" class="ts-button ts-button-ghost" @click="toggleSelectMode">取消选择</button>
          <button type="button" class="ts-button ts-button-secondary" :disabled="selectedIds.length < 2" @click="openMerge">合并</button>
        </div>
      </div>
      <div v-if="store.loading" :class="recordsClass" role="status" aria-label="正在加载记忆">
        <div v-for="index in 3" :key="index" class="memory-record-skeleton"></div>
      </div>
      <div v-else-if="store.listError" class="memory-empty" role="status">
        <h2>记忆暂时无法加载</h2>
        <button type="button" class="ts-button ts-button-secondary" @click="requestPage()">重试</button>
      </div>
      <template v-else-if="store.items.length">
        <div :class="recordsClass">
          <MemoryCard
            v-for="memory in store.items"
            :key="memory.id"
            :memory="memory"
            :selectable="selectMode"
            :selected="selectedIds.includes(memory.id)"
            :busy="pendingIds.has(memory.id)"
            @confirm="confirmMemory"
            @ignore="ignoreMemory"
            @restore="restoreMemory"
            @toggle-select="toggleSelect"
          />
        </div>
        <div v-if="store.total > store.pageSize" class="memory-pagination">
          <p>{{ (store.page - 1) * store.pageSize + 1 }}–{{ Math.min(store.page * store.pageSize, store.total) }} / {{ store.total }} 段</p>
          <el-pagination :current-page="store.page" :page-size="store.pageSize" :total="store.total" :pager-count="5" layout="prev, pager, next" @current-change="changePage" />
        </div>
      </template>
      <div v-else class="memory-empty">
        <BookHeart aria-hidden="true" />
        <h2>{{ emptyTitle }}</h2>
        <p>{{ emptyDescription }}</p>
        <button v-if="store.activeStatus === 'candidate'" type="button" class="ts-button ts-button-secondary" :disabled="store.discovering" @click="runDiscovery">{{ store.discovering ? '正在发现记忆…' : '开始发现' }}</button>
        <RouterLink v-else-if="store.activeStatus === 'confirmed'" to="/memories/new" class="ts-button ts-button-secondary">从照片创建</RouterLink>
      </div>
    </section>

    <el-dialog v-model="mergeVisible" title="合并记忆" width="min(92vw, 520px)">
      <p class="text-sm text-gray-500 dark:text-gray-400">合并后会生成一段新记忆，原记忆会保留为历史来源。</p>
      <el-form label-position="top" class="mt-4">
        <el-form-item label="新标题"><el-input v-model="mergeTitle" maxlength="255" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" :loading="merging" @click="mergeSelected">确认合并</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { BookHeart, Bot, ChevronRight, Film, ListChecks, ListFilter, MoreHorizontal, Network, Plus, RefreshCw } from 'lucide-vue-next'
import BackButton from '@/components/ui/BackButton.vue'
import MemoryCard from '@/components/memory/MemoryCard.vue'
import ChapterShelf from '@/components/chapter/ChapterShelf.vue'
import { memoryApi } from '@/api/memory'
import { useMemoryStore } from '@/stores/memoryStore'
import { useUiStore } from '@/stores/uiStore'
import type { MemoryItem, MemoryStatus } from '@/types/memory'

const store = useMemoryStore()
const showActions = ref(false)
const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const selectMode = ref(false)
const selectedIds = ref<string[]>([])
const pendingIds = ref(new Set<string>())
const mergeVisible = ref(false)
const mergeTitle = ref('')
const merging = ref(false)
const masthead = ref<HTMLElement | null>(null)
const memoryResults = ref<HTMLElement | null>(null)
const viewStatus = computed<MemoryStatus>(() => {
  const status = route.query.status
  return status === 'candidate' || status === 'ignored' ? status : 'confirmed'
})
const isReview = computed(() => viewStatus.value !== 'confirmed')
const canSelect = computed(() => viewStatus.value !== 'ignored' && store.items.length > 0 && !store.loading && !store.listError)
const recordsClass = computed(() => ({
  'memory-records': true,
  'memory-records--gallery': !isReview.value,
}))

const reviewTabs = [
  { status: 'candidate' as const, label: '待确认' },
  { status: 'ignored' as const, label: '已忽略' },
]

const emptyTitle = computed(() => ({
  candidate: '暂时没有新的候选记忆',
  confirmed: '还没有保存记忆',
  ignored: '没有已忽略的候选',
}[store.activeStatus] || '暂无内容'))
const emptyDescription = computed(() => store.activeStatus === 'candidate'
  ? '系统会根据照片的时间、地点和人物线索寻找经历，你也可以手动创建。'
  : store.activeStatus === 'confirmed' ? '把一次旅行、一场聚会或普通的一天保存下来。' : '被忽略的候选会保留在这里，随时可以恢复。')

watch(() => route.name === 'MemoryList' ? viewStatus.value : null, async (status, previous) => {
  if (!status) return
  selectedIds.value = []
  selectMode.value = false
  const loading = requestPage(status, 1)
  if (previous && (status === 'confirmed' || previous === 'confirmed')) {
    await nextTick()
    masthead.value?.focus({ preventScroll: true })
    masthead.value?.scrollIntoView({ block: 'start', behavior: 'instant' })
  }
  await loading
}, { immediate: true })
function toggleSelectMode() {
  selectMode.value = !selectMode.value
  selectedIds.value = []
}
async function requestPage(status = store.activeStatus, page = store.page) {
  try { await store.fetchList(status, page) }
  catch { /* The list renders its retry action. */ }
}
async function changePage(page: number) {
  selectedIds.value = []
  const loading = requestPage(store.activeStatus, page)
  await nextTick()
  memoryResults.value?.scrollIntoView({ block: 'start', behavior: 'instant' })
  await loading
}
function createWithAgent() {
  uiStore.openAgentWithPrompt('我想创建一段相册记忆。请先问我这段经历的大概时间、地点、人物或画面线索，再搜索照片并展示候选。在我明确确认标题、照片和地点后，创建正式记忆。', false)
}
function toggleSelect(id: string) {
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id]
}
async function runDiscovery() {
  try {
    const created = await store.discover()
    ElMessage.success(created ? `发现 ${created} 段候选记忆` : '没有发现新的候选记忆')
  } catch (error) { ElMessage.error('发现记忆失败，请稍后重试') }
}
function confirmMemory(memory: MemoryItem) {
  return updateMemory(memory.id, 'confirm', '已保存为我的记忆')
}
function ignoreMemory(memory: MemoryItem) {
  return updateMemory(memory.id, 'ignore', '已忽略这段候选记忆')
}
function restoreMemory(memory: MemoryItem) {
  return updateMemory(memory.id, 'restore', '已恢复为待确认')
}
async function updateMemory(id: string, action: 'confirm' | 'ignore' | 'restore', message: string) {
  if (pendingIds.value.has(id)) return
  pendingIds.value.add(id)
  try {
    await store[action](id)
    ElMessage.success(message)
  } catch {
    ElMessage.error('更新记忆失败，请重试')
  } finally {
    pendingIds.value.delete(id)
  }
}
function openMerge() {
  const selected = store.items.filter(item => selectedIds.value.includes(item.id))
  mergeTitle.value = selected.map(item => item.title).join(' · ').slice(0, 255)
  mergeVisible.value = true
}
async function mergeSelected() {
  if (selectedIds.value.length < 2 || !mergeTitle.value.trim()) return
  merging.value = true
  try {
    const merged = await memoryApi.merge({ memory_ids: selectedIds.value, title: mergeTitle.value.trim() })
    mergeVisible.value = false
    ElMessage.success('记忆已合并')
    router.push(`/memories/${merged.id}`)
  } finally { merging.value = false }
}

onMounted(() => {
  void store.fetchCounts().catch(() => {})
})
</script>

<style scoped>
.memory-collection { width: 100%; max-width: 1360px; min-height: 100%; margin-inline: auto; padding: 24px var(--ts-page-gutter) 36px; }
.memory-masthead { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 19px; }
.memory-review-heading, .memory-command-bar { display: flex; align-items: center; gap: 8px; }
.memory-review-heading { gap: 12px; }
.memory-command { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-width: 44px; min-height: 44px; padding-inline: 11px; border: 1px solid var(--ts-glass-border); border-radius: 10px; background: var(--ts-glass-sheen), var(--ts-glass-control); box-shadow: var(--ts-glass-rim); color: var(--ts-color-text); white-space: nowrap; font-size: 13px; font-weight: 600; }
.memory-command svg { width: 17px; height: 17px; }
.memory-command:hover { background-color: var(--ts-color-surface-muted); }
.memory-command:disabled { opacity: .6; }
.memory-command--add { background-color: var(--ts-journal-action); border-color: transparent; color: white; }
.memory-command--add:hover { background-color: var(--ts-journal-action-hover); }
.memory-command:focus-visible, .memory-filters nav a:focus-visible, .memory-review-link:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 2px; }

.memory-chapters { margin-bottom: clamp(20px, 3vw, 36px); }
.memory-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.memory-section-heading h2 { display: flex; align-items: baseline; gap: 8px; font: 700 23px/1.25 var(--ts-journal-serif); }
.memory-section-heading h2 span { color: var(--ts-color-text-secondary); font: 500 13px/1 var(--ts-font-sans); font-variant-numeric: tabular-nums; }
.memory-review-link { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding-inline: 8px; border-radius: 8px; color: var(--ts-color-text-secondary); font-size: 13px; white-space: nowrap; }
.memory-review-link:hover { color: var(--ts-color-text); background: var(--ts-color-surface-muted); }
.memory-review-link svg { width: 15px; height: 15px; }

.memory-filters { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 12px; padding-block: 5px; border-bottom: 1px solid var(--ts-color-divider); background: var(--ts-color-page); }
.memory-filters nav { display: flex; align-items: center; gap: 4px; min-width: 0; }
.memory-filters nav a { position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-height: 44px; padding: 0 10px; border-radius: 8px; color: var(--ts-color-text-secondary); font-size: 13px; white-space: nowrap; }
.memory-filters nav a:hover, .memory-batch[aria-pressed='true'] { background: var(--ts-color-surface-muted); }
.memory-filters nav a[aria-current='page'] { color: var(--ts-journal-accent-text); font-weight: 700; }
.memory-filters nav a[aria-current='page']::after { position: absolute; inset: auto 10px -6px; height: 2px; border-radius: 2px; background: var(--ts-journal-focus); content: ''; }
.memory-filters nav a span { border-radius: 5px; padding-inline: 5px; background: var(--ts-color-surface-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.memory-filters nav a[aria-current='page'] span { background: var(--ts-journal-active); }
.memory-batch, .memory-discover { flex-shrink: 0; }
.memory-selection { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 12px; padding: 6px 10px 6px 14px; border-radius: 10px; background: var(--ts-journal-active); font-size: 13px; }
.memory-collection--review > :is(.memory-results, .memory-masthead) { max-width: 1020px; margin-inline: auto; }
.memory-records { display: grid; gap: 8px; }
.memory-records--gallery { grid-template-columns: repeat(auto-fill, minmax(min(100%, 255px), 1fr)); gap: 14px; }
.memory-record-skeleton { min-height: 94px; border-radius: 14px; background: var(--ts-color-surface-muted); }
.memory-records--gallery .memory-record-skeleton { min-height: 240px; }
.memory-pagination { display: grid; justify-items: center; gap: 8px; padding-top: 22px; font-size: 12px; color: var(--ts-color-text-secondary); }
.memory-empty { display: grid; justify-items: center; gap: 12px; padding: clamp(32px, 5vw, 64px) 16px; border: 1px dashed var(--ts-color-border); border-radius: 14px; text-align: center; }
.memory-empty > svg { color: var(--ts-journal-focus); width: 29px; height: 29px; }
.memory-empty h2 { font: 700 21px/1.2 var(--ts-journal-serif); }
.memory-empty p { color: var(--ts-color-text-secondary); font-size: 13px; }
@media (max-width: 639px) {
  .memory-collection { padding-top: 14px; }
  .memory-masthead { margin-bottom: 13px; }
  .memory-section-heading h2 { font-size: 21px; }
  .memory-filters nav { gap: 3px; }
  .memory-filters nav a { padding-inline: 6px; }
  .memory-filters nav a[aria-current='page']::after { inset-inline: 6px; }
  .memory-filters nav a span { padding-inline: 3px; }
  .memory-batch span, .memory-discover span { display: none; }
}
</style>
