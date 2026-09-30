<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-gray-900 md:px-8">
    <div class="mx-auto max-w-5xl">
      <button class="text-sm text-primary-600 dark:text-primary-400" @click="router.back()">← 返回章节</button>
      <h1 class="mt-5 font-serif text-3xl text-gray-900 dark:text-white">为这段时光，写下你的定义</h1>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">章节按拍摄日期收纳影像，文字由你决定。</p>
      <div class="mt-7 grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <form class="space-y-5 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 md:p-7" @submit.prevent="save">
          <label class="block text-sm text-gray-800 dark:text-gray-200">章节名称
            <input v-model.trim="form.title" maxlength="80" required class="mt-2 w-full rounded-lg border border-gray-300 bg-white p-3 dark:border-gray-600 dark:bg-gray-900" />
          </label>
          <label class="block text-sm text-gray-800 dark:text-gray-200">阶段简介
            <textarea v-model="form.summary" maxlength="1000" rows="4" class="mt-2 w-full rounded-lg border border-gray-300 bg-white p-3 dark:border-gray-600 dark:bg-gray-900" placeholder="写下这段日子对你的意义" />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="block text-sm text-gray-800 dark:text-gray-200">开始日期<input v-model="form.start_date" type="date" required class="mt-2 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2.5 dark:border-gray-600 dark:bg-gray-900" /></label>
            <label class="block text-sm text-gray-800 dark:text-gray-200">结束日期<input v-model="form.end_date" :disabled="ongoing" type="date" class="mt-2 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2.5 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900" /></label>
          </div>
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"><input v-model="ongoing" type="checkbox" />持续中</label>
          <button type="button" class="rounded-lg border border-primary-200 px-4 py-2 text-sm text-primary-600 dark:border-primary-800 dark:text-primary-400" :disabled="!validRange || previewing" @click="loadPreview">{{ previewing ? '正在计算' : '预览范围' }}</button>
          <div v-if="preview" class="rounded-xl bg-primary-50 p-4 text-sm text-gray-700 dark:bg-primary-900/20 dark:text-gray-300">
            新范围包含 {{ preview.photo_count }} 张影像<span v-if="preview.previous_photo_count !== undefined">；原范围 {{ preview.previous_photo_count }} 张</span>。原照片不会被修改。
          </div>
          <div v-if="preview?.preview_photo_ids.length">
            <p class="mb-3 text-sm text-gray-700 dark:text-gray-300">选择封面</p>
            <div class="grid grid-cols-4 gap-2 sm:grid-cols-6">
              <button v-for="id in preview.preview_photo_ids" :key="id" type="button" class="aspect-square overflow-hidden rounded-lg border-2" :class="form.cover_photo_id === id ? 'border-primary-500' : 'border-transparent'" :aria-label="`选择封面 ${id}`" @click="form.cover_photo_id = id">
                <img :src="thumbnailUrl(id, 'small')" alt="章节封面备选照片" class="h-full w-full object-cover" loading="lazy" />
              </button>
            </div>
          </div>
          <div class="flex justify-end gap-3 border-t border-gray-200 pt-5 dark:border-gray-700">
            <button type="button" class="rounded-lg border border-gray-300 px-4 py-2 dark:border-gray-600" @click="router.back()">取消</button>
            <button type="submit" class="rounded-lg bg-primary-500 px-5 py-2 text-white disabled:opacity-50" :disabled="saving || !validRange || !form.title.trim()">{{ saving ? '保存中' : chapter?.status === 'candidate' ? '保存建议' : '保存章节' }}</button>
          </div>
        </form>
        <aside class="h-fit rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
          <h2 class="mb-3 text-sm font-semibold text-gray-900 dark:text-white">目录封面预览</h2>
          <div class="relative aspect-[4/5] overflow-hidden rounded-xl bg-gray-200 dark:bg-gray-700">
            <img v-if="form.cover_photo_id" :src="thumbnailUrl(form.cover_photo_id, 'medium')" alt="目录封面预览" class="h-full w-full object-cover" />
            <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-5 pt-20 text-white"><p class="text-xs">{{ form.start_date }} — {{ ongoing ? '至今' : form.end_date }}</p><h2 class="mt-2 font-serif text-2xl">{{ form.title || '未命名章节' }}</h2></div>
          </div>
          <p class="mt-4 text-xs leading-6 text-gray-500 dark:text-gray-400">未选择封面时，系统会从这一阶段的有效照片中选取。照片仅按时间归属，不会据此推断你的身份或经历。</p>
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chapterApi } from '@/api/chapter'
import type { ChapterDetail } from '@/types/chapter'
import { thumbnailUrl } from '@/utils/mediaUrl'

const route = useRoute()
const router = useRouter()
const chapter = ref<ChapterDetail | null>(null)
const saving = ref(false)
const previewing = ref(false)
const preview = ref<{ photo_count: number; previous_photo_count?: number; preview_photo_ids: string[] } | null>(null)
const ongoing = ref(false)
const form = reactive({ title: '', summary: '', start_date: '', end_date: '', cover_photo_id: '' })
const validRange = computed(() => Boolean(form.start_date && (ongoing.value || !form.end_date || form.end_date >= form.start_date)))
watch(() => [form.start_date, form.end_date, ongoing.value], () => { preview.value = null })

async function loadPreview() {
  if (!validRange.value) return
  previewing.value = true
  try { preview.value = await chapterApi.preview(form.start_date, ongoing.value ? null : form.end_date || null, chapter.value?.id) }
  catch { ElMessage.error('预览范围失败') }
  finally { previewing.value = false }
}

async function save() {
  if (!validRange.value || !form.title.trim()) return
  saving.value = true
  try {
    const payload = { title: form.title.trim(), summary: form.summary, start_date: form.start_date,
      end_date: ongoing.value ? null : form.end_date || null, cover_photo_id: form.cover_photo_id || null }
    const result = chapter.value
      ? await chapterApi.update(chapter.value.id, { ...payload, version: chapter.value.version })
      : await chapterApi.create(payload)
    ElMessage.success(chapter.value?.status === 'candidate' ? '建议已保存，仍待确认' : '章节已保存')
    router.replace(`/chapters/${result.id}${chapter.value?.is_hidden ? '?manage=1' : ''}`)
  } catch { ElMessage.error('保存失败，请检查封面是否仍在章节时间范围内') }
  finally { saving.value = false }
}

onMounted(async () => {
  if (route.params.id) {
    try {
      chapter.value = await chapterApi.detail(String(route.params.id), true)
      form.title = chapter.value.title
      form.summary = chapter.value.summary || ''
      form.start_date = chapter.value.start_date
      form.end_date = chapter.value.end_date || ''
      form.cover_photo_id = chapter.value.cover_photo_id || ''
      ongoing.value = !chapter.value.end_date
      await loadPreview()
    } catch { ElMessage.error('加载章节失败'); router.replace('/chapters') }
  }
})
</script>
