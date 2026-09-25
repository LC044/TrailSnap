<template>
  <main class="mx-auto max-w-6xl px-4 py-5 text-gray-900 dark:text-gray-100 sm:px-6">
    <div class="mb-5 flex items-center justify-between gap-3">
      <button class="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800" @click="router.push('/album/people')">← 人物相册</button>
      <div class="flex gap-2">
        <button v-if="!withId && data" class="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700" @click="startAi">AI 解读时光线</button>
        <button v-if="!withId && currentIdentity" class="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700" @click="showEdit = true">编辑人物标签</button>
        <button class="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700" @click="showHidden = true">隐藏管理</button>
      </div>
    </div>
    <div class="mb-6 flex items-center gap-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-gray-800">
      <div class="flex -space-x-3">
        <div v-for="person in data?.people || []" :key="person.id" class="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border-2 border-white bg-primary-100 font-bold text-primary-700 dark:border-gray-800 dark:bg-primary-900/50 dark:text-primary-300">
          <img v-if="person.avatar_url" :src="toServerUrl(person.avatar_url)" :alt="person.name" class="h-full w-full object-cover" />
          <span v-else>{{ person.name.slice(0, 1) }}</span>
        </div>
      </div>
      <div class="min-w-0 flex-1">
        <h1 class="truncate text-xl font-bold">{{ data?.people.map(p => p.name).join('与') || '人物时光线' }}</h1>
        <p v-if="data" class="text-sm text-gray-500 dark:text-gray-400">{{ data.year_count }} 个有照片的年份 · {{ data.photo_count }} 张{{ withId ? '同框' : '' }}照片</p>
        <p v-if="peopleTags" class="text-xs text-primary-600 dark:text-primary-400">{{ peopleTags }}</p>
      </div>
    </div>

    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div role="tablist" aria-label="人物详情视图" class="inline-flex rounded-xl bg-gray-100 p-1 dark:bg-gray-800">
        <button role="tab" :aria-selected="false" class="rounded-lg px-5 py-2 text-sm text-gray-600 dark:text-gray-300" @click="router.push(`/album/people/${personId}`)">照片</button>
        <button role="tab" :aria-selected="true" class="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-primary-600 shadow-sm dark:bg-gray-700 dark:text-primary-300">时光线</button>
      </div>
      <div class="flex items-center gap-2">
        <el-select v-model="selectedWithId" filterable clearable placeholder="选择另一人物" class="!w-48" @change="changePerson">
          <el-option v-for="person in choices" :key="person.id" :label="person.identity_name || '未命名人物'" :value="person.id" />
        </el-select>
      </div>
    </div>

    <div v-if="!loading && data?.photo_count" class="mb-6 flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-300">
      <button v-if="data.first_photo" class="rounded-full bg-gray-100 px-3 py-1.5 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700" @click="openKeyPhoto(data.first_photo)">相册里最早：{{ data.first_photo.photo_time.slice(0, 10) }}</button>
      <button v-if="data.latest_photo" class="rounded-full bg-gray-100 px-3 py-1.5 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700" @click="openKeyPhoto(data.latest_photo)">最近拍摄：{{ data.latest_photo.photo_time.slice(0, 10) }}</button>
      <span v-if="data.peak_month" class="rounded-full bg-gray-100 px-3 py-1.5 dark:bg-gray-800">合影较多：{{ data.peak_month.month }}（{{ data.peak_month.count }} 张）</span>
    </div>
    <div v-if="loading" class="space-y-4" aria-live="polite">
      <div v-for="n in 3" :key="n" class="h-36 animate-pulse rounded-2xl bg-gray-100 dark:bg-gray-800" />
    </div>
    <div v-else-if="error" class="rounded-2xl bg-red-50 p-6 text-red-700 dark:bg-red-900/20 dark:text-red-300">
      {{ error }} <button class="ml-3 underline" @click="load">重试</button>
    </div>
    <div v-else-if="!data?.years.length" class="rounded-2xl bg-white p-10 text-center dark:bg-gray-800">
      <p class="font-medium">{{ withId ? '暂未找到两人同框的照片' : '暂无可按年份展示的照片' }}</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">仅有拍摄时间的照片会进入时光线；可返回照片页查看全部内容。</p>
    </div>
    <div v-else class="grid gap-6 md:grid-cols-[110px_minmax(0,1fr)]">
      <nav aria-label="年份" class="flex gap-2 overflow-x-auto md:sticky md:top-20 md:block md:self-start">
        <a v-for="item in data.years" :key="item.year" :href="`#year-${item.year}`" class="mb-2 block shrink-0 rounded-lg px-3 py-2 text-sm text-primary-700 hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-900/30">{{ item.year }}</a>
      </nav>
      <div class="space-y-5">
        <p class="text-xs text-gray-500 dark:text-gray-400">照片只证明人物在画面中；已确认记忆会单独标注。</p>
        <section v-for="item in data.years" :id="`year-${item.year}`" :key="item.year" class="scroll-mt-24 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <div class="flex items-center justify-between gap-3">
            <div><h2 class="text-xl font-bold">{{ item.year }}</h2><p class="text-sm text-gray-500 dark:text-gray-400">{{ item.photo_count }} 张{{ withId ? '同框' : '' }}照片</p></div>
            <button class="rounded-lg px-3 py-2 text-sm text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-900/30" @click="toggleYear(item.year)">{{ openYear === item.year ? '收起' : '查看这一年' }}</button>
          </div>
          <div class="mt-3 flex items-center justify-between gap-2">
            <p class="text-sm text-gray-600 dark:text-gray-300">{{ item.representative_event.start_at.slice(0, 10) }}{{ item.representative_event.start_at.slice(0, 10) === item.representative_event.end_at.slice(0, 10) ? '' : `—${item.representative_event.end_at.slice(0, 10)}` }} · {{ item.representative_event.photo_count }} 张照片整理的片段</p>
            <button class="shrink-0 text-xs text-gray-500 underline dark:text-gray-400" @click="previewHide(item.representative_event.start_at.slice(0, 10), item.representative_event.end_at.slice(0, 10))">隐藏片段</button>
          </div>
          <div class="mt-4 grid grid-cols-3 gap-2">
            <button v-for="photo in item.representative_photos" :key="photo.id" class="aspect-[4/3] overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-900" :aria-label="`查看 ${item.year} 年照片`" @click="openRepresentative(photo.id)">
              <img :src="toServerUrl(photo.thumbnail_url)" alt="年度代表照片" class="h-full w-full object-cover" loading="lazy" />
            </button>
          </div>
          <div v-if="item.memories.length" class="mt-4 space-y-2">
            <router-link v-for="memory in item.memories" :key="memory.id" :to="`/memories/${memory.id}`" class="block rounded-lg bg-primary-50 px-3 py-2 text-sm text-primary-700 hover:underline dark:bg-primary-900/30 dark:text-primary-300">{{ memory.kind === 'travel' ? (withId ? '共同旅行' : '旅行记忆') : memory.kind === 'holiday' ? '节日记忆' : '已确认记忆' }} · {{ memory.title }}</router-link>
          </div>
          <div v-if="openYear === item.year" class="mt-5 border-t border-gray-200 pt-5 dark:border-gray-700">
            <p v-if="yearLoading" class="text-sm text-gray-500 dark:text-gray-400">正在加载照片…</p>
            <template v-else-if="yearData">
              <div v-if="yearData.memories.length" class="mb-5 space-y-2">
                <router-link v-for="memory in yearData.memories" :key="memory.id" :to="`/memories/${memory.id}`" class="block rounded-lg bg-primary-50 px-3 py-2 text-sm text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">{{ memory.kind === 'travel' ? (withId ? '共同旅行' : '旅行记忆') : memory.kind === 'holiday' ? '节日记忆' : '已确认记忆' }} · {{ memory.title }}</router-link>
              </div>
              <div v-for="group in dayGroups" :key="group.day" class="mb-5">
                <div class="mb-2 flex items-center justify-between gap-2">
                  <h3 class="text-sm font-semibold">{{ group.day }} · {{ group.photos.length }} 张</h3>
                  <button class="text-xs text-gray-500 underline dark:text-gray-400" @click="previewHide(group.day, group.day)">从故事隐藏这一天</button>
                </div>
                <div class="grid grid-cols-3 gap-2 sm:grid-cols-5">
                  <button v-for="photo in group.photos" :key="photo.id" class="aspect-square overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-900" :aria-label="photo.filename || '打开照片'" @click="openPhoto(photo.id)">
                    <img :src="toServerUrl(photo.thumbnail_url)" :alt="photo.filename || '照片'" class="h-full w-full object-cover" loading="lazy" />
                  </button>
                </div>
              </div>
              <button v-if="yearData.next_skip !== null" class="w-full rounded-lg border border-gray-200 py-2 text-sm dark:border-gray-700" :disabled="yearLoading" @click="loadMore">加载更多</button>
            </template>
          </div>
        </section>
      </div>
    </div>

    <el-dialog v-model="showHidePreview" title="确认隐藏片段" width="min(92vw, 560px)">
      <p class="text-sm text-gray-600 dark:text-gray-300">当前{{ withId ? '双人' : '单人' }}时光线中，{{ hidePreview?.photo_count || 0 }} 张照片会从故事展示中隐藏。原照片与记忆仍保留。</p>
      <div class="mt-4 grid max-h-64 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-5">
        <img v-for="photo in hidePreview?.photos || []" :key="photo.id" :src="toServerUrl(photo.thumbnail_url)" :alt="photo.filename || '受影响照片'" class="aspect-square w-full rounded-lg object-cover" />
      </div>
      <p v-if="(hidePreview?.photo_count || 0) > 20" class="mt-2 text-xs text-gray-500 dark:text-gray-400">仅预览前 20 张，范围内其余照片也会隐藏。</p>
      <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">已保存的历史作品不会自动改写。</p>
      <template #footer><el-button @click="showHidePreview = false">取消</el-button><el-button type="primary" :disabled="!hidePreview?.photo_count" @click="confirmHide">确认隐藏</el-button></template>
    </el-dialog>

    <IdentityEditDialog v-model:visible="showEdit" :identity="currentIdentity" @saved="onIdentitySaved" @cover-changed="onIdentitySaved" />

    <el-drawer v-model="showHidden" title="隐藏管理" :size="drawerSize">
      <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">隐藏仅影响当前{{ withId ? '双人' : '单人' }}时光线和故事；原照片仍在相册中。</p>
      <p v-if="!hiddenRules.length" class="text-sm text-gray-500 dark:text-gray-400">暂无隐藏片段</p>
      <div v-for="rule in hiddenRules" :key="rule.id" class="mb-3 flex items-center justify-between rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700">
        <span>{{ rule.start_at.slice(0, 10) }} 至 {{ hiddenEndLabel(rule.end_at) }} · {{ rule.photo_count }} 张</span>
        <button class="text-primary-600 dark:text-primary-400" @click="restore(rule.id)">恢复</button>
      </div>
    </el-drawer>
    <PhotoLightbox v-if="lightboxIndex >= 0" :visible="true" :image="lightboxImages[lightboxIndex] || null" :images="lightboxImages" :current-index="lightboxIndex" :has-prev="lightboxIndex > 0" :has-next="lightboxIndex < lightboxImages.length - 1" @close="lightboxIndex = -1" @prev="lightboxIndex = Math.max(0, lightboxIndex - 1)" @next="lightboxIndex = Math.min(lightboxImages.length - 1, lightboxIndex + 1)" @select="lightboxIndex = $event" />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { faceApi } from '@/api/face'
import { personTimelineApi } from '@/api/personTimeline'
import type { PersonTimeline, TimelineHiddenRule, TimelinePhoto, TimelineYearDetail } from '@/api/personTimeline'
import type { FaceIdentity, AlbumImage } from '@/types/album'
import { toServerUrl } from '@/config/server'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import IdentityEditDialog from '@/components/IdentityEditDialog.vue'
import { useUiStore } from '@/stores/uiStore'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const personId = computed(() => String(route.params.id))
const withId = computed(() => typeof route.query.with === 'string' ? route.query.with : undefined)
const selectedWithId = ref(withId.value || '')
const data = ref<PersonTimeline | null>(null)
const choices = ref<FaceIdentity[]>([])
const currentIdentity = ref<FaceIdentity | null>(null)
const loading = ref(true)
const error = ref('')
const openYear = ref<number | null>(null)
const yearData = ref<TimelineYearDetail | null>(null)
const yearLoading = ref(false)
const showEdit = ref(false)
const showHidden = ref(false)
const showHidePreview = ref(false)
const hidePreview = ref<{ photo_count: number; photos?: TimelinePhoto[] } | null>(null)
const hideRange = ref({ start: '', end: '' })
const hiddenRules = ref<TimelineHiddenRule[]>([])
const lightboxIndex = ref(-1)
const lightboxPhotos = ref<TimelinePhoto[]>([])
const drawerSize = computed(() => window.innerWidth < 640 ? '90%' : '420px')
const peopleTags = computed(() => (data.value?.people || [])
  .filter(person => person.tags?.length)
  .map(person => withId.value ? `${person.name}：${person.tags.join('、')}` : person.tags.join('、'))
  .join(' · '))
const dayGroups = computed(() => {
  const groups = new Map<string, TimelinePhoto[]>()
  for (const photo of yearData.value?.photos || []) {
    const day = photo.photo_time.slice(0, 10)
    groups.set(day, [...(groups.get(day) || []), photo])
  }
  return Array.from(groups, ([day, photos]) => ({ day, photos }))
})
const lightboxImages = computed<AlbumImage[]>(() => lightboxPhotos.value.map(photo => ({
  id: photo.id, url: toServerUrl(`/api/medias/${photo.id}/file`), thumbnail: toServerUrl(photo.thumbnail_url),
  preview: toServerUrl(photo.thumbnail_url), srcset: '', timestamp: new Date(photo.photo_time).getTime(),
  albumIds: [], filename: photo.filename || '照片', file_type: 'image',
})))

async function load() {
  loading.value = true
  error.value = ''
  openYear.value = null
  yearData.value = null
  try {
    const [timeline, rules] = await Promise.all([
      personTimelineApi.get(personId.value, withId.value), personTimelineApi.hidden(personId.value, withId.value),
    ])
    data.value = timeline
    hiddenRules.value = rules
  } catch (e) {
    console.error(e)
    error.value = '加载时光线失败，请稍后重试'
  } finally { loading.value = false }
}
async function loadChoices() {
  try {
    const identities = await faceApi.listIdentities(1, 1000)
    currentIdentity.value = identities.find(person => person.id === personId.value) || null
    choices.value = identities.filter(person => person.id !== personId.value && !person.is_hidden)
  } catch { choices.value = []; currentIdentity.value = null }
}
function changePerson(value: string) { router.push({ path: `/album/people/${personId.value}/timeline`, query: value ? { with: value } : {} }) }
function startAi() {
  const name = data.value?.people[0]?.name || '此人'
  const tags = data.value?.people[0]?.tags || []
  const label = tags.length ? `人物编辑中保存的标签为“${tags.join('、')}”，可用于称谓，不要推断其他关系。` : '不要推断人物关系。'
  uiStore.openAgentWithPrompt(`请加载 person-timeline Skill，为人物“${name}”生成只读时光线概览，identity_id=${personId.value}。${label}仅使用未隐藏的照片和已确认的记忆，先展示跨年份分布及最多 5 个代表事件；不要修改人物或照片。`, true)
}
async function toggleYear(year: number) {
  if (openYear.value === year) { openYear.value = null; return }
  openYear.value = year
  yearData.value = null
  yearLoading.value = true
  try { yearData.value = await personTimelineApi.year(personId.value, year, withId.value) }
  catch { ElMessage.error('加载年度照片失败') }
  finally { yearLoading.value = false }
}
async function loadMore() {
  if (!yearData.value || yearData.value.next_skip === null) return
  yearLoading.value = true
  try {
    const next = await personTimelineApi.year(personId.value, yearData.value.year, withId.value, yearData.value.next_skip)
    yearData.value = { ...next, photos: [...yearData.value.photos, ...next.photos],
      memories: Array.from(new Map([...yearData.value.memories, ...next.memories].map(memory => [memory.id, memory])).values()) }
  } catch { ElMessage.error('加载更多照片失败') }
  finally { yearLoading.value = false }
}
function openPhoto(id: string) { lightboxPhotos.value = yearData.value?.photos || []; lightboxIndex.value = lightboxPhotos.value.findIndex(photo => photo.id === id) }
function openRepresentative(id: string) {
  const photo = data.value?.years.flatMap(item => item.representative_photos).find(item => item.id === id)
  if (!photo) return
  lightboxPhotos.value = [photo]
  lightboxIndex.value = 0
}
function openKeyPhoto(photo: { id: string; photo_time: string }) {
  lightboxPhotos.value = [{ ...photo, thumbnail_url: `/api/medias/${photo.id}/thumbnail`, filename: '照片' }]
  lightboxIndex.value = 0
}
function hiddenEndLabel(endAt: string) {
  const end = new Date(endAt)
  end.setDate(end.getDate() - 1)
  return `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`
}
function onIdentitySaved(updated: FaceIdentity) {
  currentIdentity.value = updated
  load()
}
async function previewHide(startDay: string, endDay: string) {
  const start = `${startDay}T00:00:00`
  const endDate = new Date(`${endDay}T00:00:00`)
  endDate.setDate(endDate.getDate() + 1)
  const end = `${endDate.getFullYear()}-${String(endDate.getMonth() + 1).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}T00:00:00`
  try {
    hidePreview.value = await personTimelineApi.hide(personId.value, start, end, withId.value, true)
    hideRange.value = { start, end }
    showHidePreview.value = true
  } catch { ElMessage.error('预览隐藏范围失败') }
}
async function confirmHide() {
  try {
    await personTimelineApi.hide(personId.value, hideRange.value.start, hideRange.value.end, withId.value)
    showHidePreview.value = false
    ElMessage.success('已隐藏，可在隐藏管理中恢复')
    await load()
  } catch { ElMessage.error('隐藏失败') }
}
async function restore(ruleId: string) {
  try { await personTimelineApi.restore(personId.value, ruleId, withId.value); ElMessage.success('已恢复'); await load() }
  catch { ElMessage.error('恢复失败') }
}
watch([personId, withId], () => { selectedWithId.value = withId.value || ''; load(); loadChoices() })
onMounted(() => { load(); loadChoices() })
</script>
