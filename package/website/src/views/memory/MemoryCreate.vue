<template>
  <div class="min-h-full bg-gray-50 px-4 py-5 dark:bg-gray-900 md:px-7 md:py-7">
    <div class="mx-auto max-w-6xl">
      <header class="flex flex-wrap items-center gap-3">
        <button class="rounded-full p-2 text-gray-600 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" aria-label="返回" @click="router.back()"><ArrowLeft class="h-5 w-5" /></button>
        <div class="min-w-0 flex-1"><h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建记忆</h1><p class="text-sm text-gray-500 dark:text-gray-400">选择属于同一段经历的照片</p></div>
        <button class="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" @click="openAgentCreate"><Bot class="mr-1.5 inline h-4 w-4" />和 AI 对话创建</button>
      </header>

      <div class="mt-5 rounded-2xl border border-primary-200 bg-primary-50 p-4 dark:border-primary-900 dark:bg-primary-900/20">
        <p class="text-sm text-primary-800 dark:text-primary-200">你可以直接告诉 AI：“把去年国庆在西安拍的照片整理成一段记忆”。AI 会继续询问线索、展示候选照片，并在你确认后创建。</p>
      </div>

      <div class="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section class="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 md:p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div><h2 class="font-semibold text-gray-900 dark:text-white">最近的照片</h2><p class="text-xs text-gray-500 dark:text-gray-400">已选择 {{ selectedIds.length }} 张</p></div>
            <el-input v-model="search" clearable placeholder="搜索文件名" class="sm:!w-60" />
          </div>
          <div v-if="loading" class="flex min-h-[360px] items-center justify-center"><LoaderCircle class="h-7 w-7 animate-spin text-primary-500" /></div>
          <div v-else class="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-6">
            <button
              v-for="photo in filteredPhotos"
              :key="photo.id"
              class="group relative aspect-square overflow-hidden rounded-lg bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-900"
              :aria-label="photo.filename || '照片'"
              @click="toggle(photo.id)"
            >
              <img :src="thumbnailUrl(photo.id, 'small')" :alt="photo.filename || '照片'" class="h-full w-full object-cover transition group-hover:scale-105" loading="lazy" />
              <span class="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white bg-black/25">
                <Check v-if="selectedIds.includes(photo.id)" class="h-3.5 w-3.5 text-white" />
              </span>
              <span v-if="selectedIds.includes(photo.id)" class="absolute inset-0 border-4 border-primary-500"></span>
            </button>
          </div>
        </section>

        <aside class="h-fit rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800 lg:sticky lg:top-5">
          <h2 class="font-semibold text-gray-900 dark:text-white">记忆信息</h2>
          <el-form label-position="top" class="mt-4">
            <el-form-item label="标题" required><el-input v-model="title" maxlength="255" placeholder="例如：秋日杭州三日行" /></el-form-item>
            <el-form-item label="故事"><el-input v-model="story" type="textarea" :rows="4" placeholder="写下一些想记住的细节" /></el-form-item>
            <el-form-item label="地点"><el-input v-model="places" placeholder="多个地点用顿号分隔" /></el-form-item>
            <el-form-item label="封面">
              <el-select v-model="coverId" class="w-full" placeholder="默认使用第一张照片">
                <el-option v-for="photo in selectedPhotos" :key="photo.id" :label="photo.filename || photo.id" :value="photo.id" />
              </el-select>
            </el-form-item>
          </el-form>
          <button
            class="w-full rounded-lg bg-primary-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :disabled="!canSubmit || saving"
            @click="submit"
          >{{ saving ? '正在创建' : '创建记忆' }}</button>
          <p class="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">手动创建的记忆会直接视为已确认。照片仍保留在原相册和文件夹中。</p>
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Bot, Check, LoaderCircle } from 'lucide-vue-next'
import { albumService } from '@/api/album'
import { memoryApi } from '@/api/memory'
import type { Photo } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { useUiStore } from '@/stores/uiStore'

const router = useRouter()
const uiStore = useUiStore()
const photos = ref<Photo[]>([])
const selectedIds = ref<string[]>([])
const loading = ref(true)
const saving = ref(false)
const search = ref('')
const title = ref('')
const story = ref('')
const places = ref('')
const coverId = ref('')

const filteredPhotos = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return keyword ? photos.value.filter(photo => (photo.filename || '').toLowerCase().includes(keyword)) : photos.value
})
const selectedPhotos = computed(() => photos.value.filter(photo => selectedIds.value.includes(photo.id)))
const canSubmit = computed(() => title.value.trim() && selectedIds.value.length > 0)

function openAgentCreate() {
  uiStore.openAgentWithPrompt('我想创建一段记忆。请先问我大概时间、地点、人物或画面线索，然后搜索并展示候选照片。请在我明确确认标题、照片和地点后再创建正式记忆。', false)
}

function toggle(id: string) {
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id]
  if (!coverId.value && selectedIds.value.length) coverId.value = selectedIds.value[0]
  if (coverId.value && !selectedIds.value.includes(coverId.value)) coverId.value = selectedIds.value[0] || ''
}

async function submit() {
  if (!canSubmit.value) return
  saving.value = true
  try {
    const memory = await memoryApi.create({
      title: title.value.trim(), story: story.value || undefined,
      photo_ids: selectedIds.value, cover_photo_id: coverId.value || undefined,
      place_names: places.value.split(/[、,，]/).map(item => item.trim()).filter(Boolean),
      origin: 'manual',
    })
    ElMessage.success('记忆已创建')
    router.replace(`/memories/${memory.id}`)
  } catch { ElMessage.error('创建记忆失败') }
  finally { saving.value = false }
}

onMounted(async () => {
  try { photos.value = await albumService.getAllPhotos(0, 200) }
  catch { ElMessage.error('加载照片失败') }
  finally { loading.value = false }
})
</script>
