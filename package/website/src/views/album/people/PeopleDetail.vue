<template>
  <UnifiedPhotoPage
    :title="identity?.identity_name || ''"
    :subtitle="`${images.length} 张`"
    :loading="loading"
    :loading-title="!identity"
    :photos="images"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    :allow-upload="false"
    delete-label="从人物中移除"
    :pending-remove-ids="pendingRemoveIds"
    confirm-remove
    @back="router.back()"
    @confirm-delete="handleConfirmDelete"
    @set-cover="handleSetCover"
  >
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
  />

  <FaceRescanDialog
    v-model:visible="rescanDialogVisible"
    :identity="identity"
    @applied="handleRescanApplied"
  />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { faceApi } from '@/api/face'
import type { FaceIdentity } from '@/types/album'

import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import IdentityEditDialog from '@/components/IdentityEditDialog.vue'
import FaceRescanDialog from '@/components/FaceRescanDialog.vue'
import { ImageIcon, MoreVertical as MoreVerticalIcon, Pencil as PencilIcon, RefreshCw as RefreshCwIcon } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'

const photoStore = usePhotoStore()

const route = useRoute()
const router = useRouter()
const identityId = route.params.id as string

// State
const identity = ref<FaceIdentity | null>(null)
const images = ref<AlbumImage[]>([])
const loading = ref(true)
const editDialogVisible = ref(false)
const rescanDialogVisible = ref(false)
const timeline = ref<any[]>([])
const pendingRemoveIds = ref(new Set<string>())

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
  }
}

onMounted(() => {
  fetchIdentity()
  fetchAllPhotos()
})
</script>

<style scoped>
/* Scoped styles */
</style>
