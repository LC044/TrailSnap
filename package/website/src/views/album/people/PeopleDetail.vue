<template>
  <UnifiedPhotoPage
    header-overlay
    :loading="loading"
    :photos="images"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    :allow-upload="false"
    delete-label="从人物中移除"
    :pending-remove-ids="pendingRemoveIds"
    confirm-remove
    @back="goBack"
    @confirm-delete="handleConfirmDelete"
    @set-cover="handleSetCover"
  >
    <template #hero>
      <div class="relative -mx-4 -mt-1 h-[90vw] min-h-[320px] max-h-[520px] overflow-hidden bg-gray-200 dark:bg-gray-800 sm:mx-0 sm:mt-0 sm:h-[420px] sm:rounded-b-3xl">
        <img
          v-if="coverPhotoId"
          :src="thumbnailUrl(coverPhotoId, 'medium')"
          :alt="`${identity?.identity_name || '人物'}的封面`"
          class="h-full w-full object-cover"
          :style="{ objectPosition: coverPosition }"
        />
        <div v-else class="flex h-full items-center justify-center bg-primary-50 text-primary-300 dark:bg-primary-900/30 dark:text-primary-700">
          <UserRoundIcon class="h-20 w-20" aria-hidden="true" />
        </div>
        <div class="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-black/55 to-transparent"></div>
      </div>
    </template>
    <template #header-left>
      <div class="flex min-w-0 items-center gap-2 px-1 text-white">
        <button type="button" class="rounded-full bg-black/35 p-2.5 backdrop-blur-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500" aria-label="返回人物相册" @click="goBack">
          <ArrowLeftIcon class="h-5 w-5" />
        </button>
        <span class="truncate rounded-full bg-black/25 px-3 py-1.5 text-sm font-semibold backdrop-blur-sm sm:text-base">{{ identity?.identity_name || '人物相册' }}</span>
      </div>
    </template>
    <template #intro>
      <section class="mb-5 bg-white px-1 pb-4 pt-5 dark:bg-gray-900 sm:rounded-2xl sm:px-6 sm:py-6">
        <div class="flex items-center gap-2 sm:gap-4">
          <PersonAvatar v-if="identity" :person="identity" class="!w-12 shrink-0 sm:!w-20" />
          <div v-else class="h-12 w-12 shrink-0 animate-pulse rounded-full bg-gray-200 dark:bg-gray-800 sm:h-20 sm:w-20"></div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <h1 class="truncate text-lg font-bold text-gray-900 dark:text-gray-100 sm:text-2xl">{{ identity?.identity_name || '人物相册' }}</h1>
              <button type="button" class="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200" title="编辑人物信息" aria-label="编辑人物信息" :disabled="!identity" @click="editDialogVisible = true">
                <PencilIcon class="h-4 w-4" />
              </button>
            </div>
            <p class="mt-1 truncate text-sm text-gray-500 dark:text-gray-400">{{ identity?.tags?.length ? `${identity.tags.join(' · ')} ｜ ` : '' }}{{ images.length }} 张照片</p>
          </div>
          <div class="ml-auto inline-flex shrink-0 rounded-xl bg-gray-100 p-1 dark:bg-gray-800" role="tablist" aria-label="人物详情视图">
            <button role="tab" :aria-selected="true" class="rounded-lg bg-white px-3 py-2 text-sm font-semibold text-primary-600 shadow-sm dark:bg-gray-700 dark:text-primary-300 sm:px-5">照片</button>
            <button role="tab" :aria-selected="false" class="rounded-lg px-3 py-2 text-sm text-gray-600 dark:text-gray-300 sm:px-5" @click="router.push(`/album/people/${identityId}/timeline`)">时光线</button>
          </div>
        </div>
      </section>
    </template>
    <template #header-actions>
      <el-dropdown trigger="click" placement="bottom-end" @command="handlePersonCommand">
        <button
          type="button"
          class="rounded-full border border-gray-200/50 bg-white/80 p-2 text-gray-700 shadow-sm backdrop-blur-md transition-all hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700/50 dark:bg-gray-900/80 dark:text-gray-200 dark:hover:bg-gray-900"
          title="人物操作"
          aria-label="人物操作"
          :disabled="!identity"
        >
          <MoreVerticalIcon class="h-5 w-5" />
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="timeline">
              <div class="flex items-center gap-2">
                <HistoryIcon class="h-4 w-4" />
                <span>AI 解读时光线</span>
              </div>
            </el-dropdown-item>
            <el-dropdown-item command="edit">
              <div class="flex items-center gap-2">
                <PencilIcon class="h-4 w-4" />
                <span>编辑人物信息</span>
              </div>
            </el-dropdown-item>
            <el-dropdown-item command="rescan">
              <div class="flex items-center gap-2">
                <RefreshCwIcon class="h-4 w-4" />
                <span>重新扫描人脸</span>
              </div>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>

    <template #batch-actions="{ selectedIds, clearSelection }">
      <el-dropdown-item
          v-if="selectedIds.size === 1"
          @click="handleSetCover(Array.from(selectedIds)); clearSelection()"
      >
          <div class="flex items-center gap-2">
            <ImageIcon class="w-4 h-4" />
            <span>设为封面</span>
          </div>
      </el-dropdown-item>
    </template>
  </UnifiedPhotoPage>

  <IdentityEditDialog
    v-model:visible="editDialogVisible"
    :identity="identity"
    @saved="(updated: FaceIdentity) => identity = updated"
    @cover-changed="(updated: FaceIdentity) => identity = updated"
  />

  <FaceRescanDialog
    v-model:visible="rescanDialogVisible"
    :identity="identity"
    @applied="handleRescanApplied"
  />
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { faceApi } from '@/api/face'
import type { FaceIdentity } from '@/types/album'

import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import PersonAvatar from '@/components/PersonAvatar.vue'
import IdentityEditDialog from '@/components/IdentityEditDialog.vue'
import FaceRescanDialog from '@/components/FaceRescanDialog.vue'
import { ArrowLeft as ArrowLeftIcon, History as HistoryIcon, ImageIcon, MoreVertical as MoreVerticalIcon, Pencil as PencilIcon, RefreshCw as RefreshCwIcon, UserRound as UserRoundIcon } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { usePhotoStore } from '@/stores/photoStore'
import { useUiStore } from '@/stores/uiStore'
import type { AlbumImage } from '@/types/album'
import { thumbnailUrl } from '@/utils/mediaUrl'

const photoStore = usePhotoStore()
const uiStore = useUiStore()

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album/people')
const identityId = route.params.id as string

// State
const identity = ref<FaceIdentity | null>(null)
const images = ref<AlbumImage[]>([])
const loading = ref(true)
const editDialogVisible = ref(false)
const rescanDialogVisible = ref(false)
const timeline = ref<any[]>([])
const pendingRemoveIds = ref(new Set<string>())
const coverPhotoId = computed(() => identity.value?.cover_photo?.photo_id || images.value[0]?.id || null)
const coverPosition = computed(() => {
  const rect = identity.value?.cover_photo?.face_rect
  if (!rect || rect.length !== 4) return 'center'
  const x = Math.min(85, Math.max(15, (rect[0] + rect[2]) * 50))
  const y = Math.min(80, Math.max(20, (rect[1] + rect[3]) * 50))
  return `${x}% ${y}%`
})

const fetchIdentity = async () => {
  try {
    const identities = await faceApi.listIdentities(1, 1000)
    identity.value = identities.find(i => i.id === identityId) || null
  } catch (e) {
    console.error('Failed to fetch identity info', e)
  }
}

const calculateTimelineStats = (photos: AlbumImage[]) => {
  const stats = new Map<string, { year: number, month: number, day: number, count: number }>()

  photos.forEach(photo => {
    const date = new Date(photo.timestamp)
    const year = date.getFullYear()
    const month = date.getMonth() + 1
    const day = date.getDate()
    const key = `${year}-${month}-${day}`

    if (!stats.has(key)) {
      stats.set(key, { year, month, day, count: 0 })
    }
    stats.get(key)!.count++
  })

  timeline.value = Array.from(stats.values()).sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year
    if (a.month !== b.month) return b.month - a.month
    return b.day - a.day
  })
}

const fetchAllPhotos = async () => {
  loading.value = true
  images.value = []

  try {
    let page = 1
    const limit = 500
    let hasNext = true

    while (hasNext) {
      const photos = await faceApi.getIdentityPhotos(identityId, page, limit)
      if (photos.length === 0) break

      const newImages = photos.map(photoStore.mapPhotoToImage)
      images.value.push(...newImages)

      if (photos.length < limit) hasNext = false
      page++
    }

    // Sort by time desc
    images.value.sort((a, b) => b.timestamp - a.timestamp)

    // Calculate timeline
    calculateTimelineStats(images.value)

  } catch (e) {
    console.error(e)
    ElMessage.error('加载照片失败')
  } finally {
    loading.value = false
  }
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    ids.forEach(id => pendingRemoveIds.value.add(id))

    await faceApi.removePhotos(identityId, ids)

    // Remove from local list
    images.value = images.value.filter(img => !ids.includes(img.id))
    calculateTimelineStats(images.value)
    ElMessage.success('移除成功')

    callback(true)

  } catch (e) {
    ElMessage.error('移除失败')
    callback(false)
  } finally {
    ids.forEach(id => pendingRemoveIds.value.delete(id))
  }
}

const handleSetCover = async (ids: string[]) => {
  if (!ids.length) return
  const photoId = ids[0]
  try {
    await faceApi.setCover(identityId, photoId)
    ElMessage.success('已设为封面')
    // Update local identity cover if needed
    fetchIdentity() // Refresh identity info
  } catch (e) {
    ElMessage.error('设置封面失败')
  }
}

const handleRescanApplied = async () => {
  await Promise.all([fetchIdentity(), fetchAllPhotos()])
}

const handlePersonCommand = (command: string) => {
  if (command === 'edit') {
    editDialogVisible.value = true
  } else if (command === 'rescan') {
    rescanDialogVisible.value = true
  } else if (command === 'timeline') {
    startPersonTimeline()
  }
}

const startPersonTimeline = () => {
  if (!identity.value) return
  uiStore.openAgentWithPrompt(
    `请加载 person-timeline Skill，为人物“${identity.value.identity_name}”生成只读时光机概览，identity_id=${identity.value.id}。先调用 get_person_timeline 展示跨年份分布和最多 5 个代表事件，再让我选择想深入查看的年份或经历；不要臆测人物关系，也不要修改人物或照片。`,
    true,
  )
}

onMounted(() => {
  fetchIdentity()
  fetchAllPhotos()
})
</script>

<style scoped>
/* Scoped styles */
</style>
