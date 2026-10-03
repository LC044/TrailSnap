<template>
  <el-dialog :model-value="visible" :title="year === null ? '写在扉页上的话' : `写下 ${year} 年的日记`" width="min(94vw, 860px)" top="6vh" :close-on-click-modal="false" @update:model-value="close">
    <p class="mb-5 text-sm leading-6 text-gray-500 dark:text-gray-400">写下自己的记忆，也可以让 AI 根据这一段时间的照片和已确认记忆起草。</p>
    <div class="grid max-h-[62vh] gap-6 overflow-y-auto pr-1 md:grid-cols-2">
      <div class="space-y-4">
        <label v-if="year !== null" class="block text-sm text-gray-700 dark:text-gray-200">这一页的标题<input v-model="title" maxlength="80" placeholder="给这一年起个名字" class="mt-2 w-full rounded-lg border border-gray-300 bg-white p-3 dark:border-gray-600 dark:bg-gray-900" /></label>
        <label class="block text-sm text-gray-700 dark:text-gray-200">{{ year === null ? '章节简介' : '日记正文' }}<textarea v-model="body" maxlength="1000" rows="9" placeholder="从一张照片、一段经历开始写……" class="mt-2 w-full resize-y rounded-lg border border-gray-300 bg-white p-3 leading-7 dark:border-gray-600 dark:bg-gray-900" /></label>
        <p class="text-right text-xs text-gray-500 dark:text-gray-400">{{ body.length }} / 1000</p>
      </div>
      <div class="rounded-xl bg-primary-50 p-4 dark:bg-primary-900/20">
        <h3 class="flex items-center gap-2 font-medium text-gray-900 dark:text-white"><Sparkles :size="17" class="text-primary-600 dark:text-primary-400" />AI 帮我起草</h3>
        <label class="mt-3 block text-xs leading-5 text-gray-600 dark:text-gray-300">补充想写的经历（选填）<textarea v-model="notes" maxlength="1000" rows="2" placeholder="例如：这一年开始学摄影，想多写写旅行。" class="mt-2 w-full rounded-lg border border-primary-200 bg-white p-3 text-sm dark:border-primary-800 dark:bg-gray-900" /></label>
        <button class="mt-3 flex min-h-11 items-center gap-2 rounded-lg bg-primary-500 px-4 py-2 text-sm text-white disabled:opacity-50" :disabled="busy || chapter.is_hidden" @click="store.generate(chapter.id, year, chapter.version, notes)"><Sparkles :size="15" />{{ busy ? '正在起草，可以关闭此窗口…' : draft ? '重新起草' : '生成草稿' }}</button>
        <p v-if="chapter.is_hidden" class="mt-3 text-xs text-gray-500 dark:text-gray-400">隐藏的章节支持手写；恢复显示后可使用 AI。</p>
        <div v-if="store.errors[draftKey]" class="mt-3 text-sm text-red-600 dark:text-red-400" role="alert">{{ store.errors[draftKey] }}<RouterLink v-if="store.errors[draftKey].includes('配置')" to="/settings" class="mt-2 block text-primary-600 dark:text-primary-400">前往配置 AI →</RouterLink></div>
        <div v-if="draft" class="mt-4 border-t border-primary-200 pt-4 dark:border-primary-800">
          <p class="text-xs font-medium text-primary-700 dark:text-primary-300">AI 草稿 · 尚未保存</p>
          <h4 v-if="draft.title && year !== null" class="mt-2 font-serif text-lg text-gray-900 dark:text-white">{{ draft.title }}</h4>
          <p class="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap text-sm leading-7 text-gray-700 dark:text-gray-200">{{ draft.body }}</p>
          <div v-if="draft.source_photo_ids?.length" class="mt-3 flex gap-2"><img v-for="id in draft.source_photo_ids.slice(0, 4)" :key="id" :src="thumbnailUrl(id)" alt="起草所依据的照片" class="h-12 w-12 rounded object-cover" /></div>
          <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">参考 {{ draft.source_photo_ids?.length || 0 }} 张代表影像、{{ draft.source_memory_ids?.length || 0 }} 段记忆，请核对后采用。</p>
          <p v-if="draft.version !== chapter.version" class="mt-2 text-xs text-red-600 dark:text-red-400">章节已变化，请重新起草。</p>
          <button class="mt-3 min-h-11 rounded-lg border border-primary-300 px-4 py-2 text-sm text-primary-700 disabled:opacity-50 dark:border-primary-700 dark:text-primary-300" :disabled="draft.version !== chapter.version || busy" @click="acceptDraft">采用这段文字</button>
        </div>
      </div>
    </div>
    <template #footer><div class="flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-gray-500 dark:text-gray-400">{{ source === 'ai' ? '已采用 AI 草稿，可继续修改。' : '保存后会出现在日记本中。' }}</p><div class="flex gap-2"><button class="min-h-11 rounded-lg border border-gray-300 px-4 py-2 dark:border-gray-600" @click="close(false)">取消</button><button class="min-h-11 rounded-lg bg-primary-500 px-5 py-2 text-white disabled:opacity-50" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存到日记本' }}</button></div></div></template>
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { Sparkles } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import { useChapterDiaryStore } from '@/stores/chapterDiaryStore'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { ChapterDetail, ChapterDiaryEntry } from '@/types/chapter'

const props = defineProps<{ visible: boolean; chapter: ChapterDetail; year: number | null }>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()
const store = useChapterDiaryStore()
const title = ref(''), body = ref(''), notes = ref('')
const source = ref<'user' | 'ai'>('user')
const saving = ref(false)
let original = ''
let accepted: ChapterDiaryEntry | null = null
let loadedVersion = 0
const draftKey = computed(() => store.key(props.chapter.id, props.year))
const draft = computed(() => store.drafts[draftKey.value])
const busy = computed(() => store.generating[draftKey.value])
watch(() => [props.visible, props.chapter.id, props.year], () => {
  if (!props.visible) return
  const entry = props.year === null ? null : props.chapter.diary_entries?.[String(props.year)]
  title.value = entry?.title || ''
  body.value = props.year === null ? props.chapter.summary || '' : entry?.body || ''
  source.value = entry?.source || (props.year === null ? props.chapter.summary_source : null) || 'user'
  accepted = entry || null
  notes.value = ''
  loadedVersion = props.chapter.version
  original = JSON.stringify([title.value, body.value])
}, { immediate: true })
function acceptDraft() {
  if (!draft.value || draft.value.version !== props.chapter.version) return
  title.value = draft.value.title
  body.value = draft.value.body
  source.value = 'ai'
  accepted = draft.value
}
async function close(value: boolean) {
  if (value || saving.value) return
  if (JSON.stringify([title.value, body.value]) !== original) {
    try { await ElMessageBox.confirm('这页文字还没有保存，离开后会丢失修改。', '离开日记编辑', { confirmButtonText: '放弃修改', cancelButtonText: '继续写' }) }
    catch { return }
  }
  emit('update:visible', false)
}
onBeforeRouteLeave(async () => {
  if (!props.visible || JSON.stringify([title.value, body.value]) === original) return true
  try { await ElMessageBox.confirm('这页文字还没有保存，离开后会丢失修改。', '离开日记编辑', { confirmButtonText: '放弃修改', cancelButtonText: '继续写' }); return true }
  catch { return false }
})
async function save() {
  saving.value = true
  try {
    const entries = { ...props.chapter.diary_entries }
    if (props.year !== null) {
      if (!title.value.trim() && !body.value.trim()) delete entries[String(props.year)]
      else entries[String(props.year)] = { ...accepted, title: title.value.trim(), body: body.value.trim(), source: source.value }
    }
    await chapterApi.update(props.chapter.id, {
      title: props.chapter.title, start_date: props.chapter.start_date, end_date: props.chapter.end_date,
      cover_photo_id: props.chapter.cover_photo_id, summary: props.year === null ? body.value.trim() : props.chapter.summary,
      summary_source: props.year === null ? source.value : props.chapter.summary_source,
      diary_entries: entries, version: loadedVersion,
    })
    delete store.drafts[draftKey.value]
    original = JSON.stringify([title.value, body.value])
    emit('update:visible', false)
    emit('saved')
    ElMessage.success('这一页已保存')
  } catch { /* The API interceptor displays the server's conflict or validation message. */ }
  finally { saving.value = false }
}
</script>
