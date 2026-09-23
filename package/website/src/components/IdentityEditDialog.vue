<template>
  <el-dialog
    :model-value="visible"
    title="编辑人物信息"
    :width="dialogWidth"
    :fullscreen="isMobile"
    top="5vh"
    class="identity-edit-dialog rounded-xl"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="封面">
        <div class="w-full">
          <div class="flex items-center justify-between gap-4 rounded-xl bg-gray-50 p-3 dark:bg-gray-800/70">
            <div class="flex min-w-0 items-center gap-3">
              <div class="relative h-16 w-16 shrink-0 overflow-hidden rounded-full border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800">
                <img
                  v-if="coverInfo"
                  :src="coverAvatarUrl"
                  class="absolute max-w-none"
                  :style="getFaceCropStyle(coverInfo)"
                  alt="当前人物封面"
                />
                <UserIcon v-else class="h-full w-full p-4 text-gray-400 dark:text-gray-500" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-100">当前封面</p>
                <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">从人物照片中选择更合适的一张</p>
              </div>
            </div>
            <el-button
              :disabled="coverLoaded && coverPhotos.length === 0"
              @click="toggleCoverPicker"
            >
              <span class="flex items-center gap-1.5">
                <CameraIcon class="h-4 w-4" />
                <span>{{ showCoverPicker ? '收起' : '选择照片' }}</span>
              </span>
            </el-button>
          </div>

          <div v-if="showCoverPicker" class="mt-3 rounded-xl border border-gray-200 p-3 dark:border-gray-700">
            <div class="mb-3 flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-medium text-gray-800 dark:text-gray-100">选择新封面</p>
                <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">图片将完整显示，人物相册中会自动聚焦人脸</p>
              </div>
              <span v-if="coverLoaded && coverPhotos.length" class="shrink-0 text-xs text-gray-400 dark:text-gray-500">
                {{ coverPhotos.length }} 张
              </span>
            </div>

            <div
              v-loading="coverLoading"
              class="cover-photo-grid grid min-h-24 max-h-[46vh] grid-cols-3 gap-2 overflow-y-auto pr-1 sm:grid-cols-4"
            >
              <button
                v-for="p in coverPhotos"
                :key="p.id"
                type="button"
                :data-photo-id="p.id"
                class="group relative aspect-[4/3] overflow-hidden rounded-lg border-2 bg-gray-100 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed dark:bg-gray-900"
                :class="p.id === selectedCoverId
                  ? 'border-primary-500 ring-2 ring-primary-500/20'
                  : 'border-transparent hover:border-gray-300 dark:hover:border-gray-600'"
                :disabled="settingCoverId !== null"
                :aria-pressed="p.id === selectedCoverId"
                :title="p.id === coverInfo?.photo_id ? '当前封面' : '选择这张照片'"
                @click="selectCover(p.id)"
              >
                <img :src="p.url" class="h-full w-full object-contain" loading="lazy" alt="封面候选照片" />
                <div
                  v-if="p.id === selectedCoverId"
                  class="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-primary-500 text-white shadow"
                >
                  <CheckIcon class="h-4 w-4" />
                </div>
                <span
                  v-if="p.id === coverInfo?.photo_id"
                  class="absolute bottom-1.5 left-1.5 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] text-white"
                >
                  当前
                </span>
              </button>
            </div>
            <p v-if="coverLoaded && coverPhotos.length === 0" class="py-5 text-center text-sm text-gray-500 dark:text-gray-400">
              该人物暂无照片，无法更换封面
            </p>
            <div v-if="coverPhotos.length" class="mt-3 flex justify-end">
              <el-button
                type="primary"
                :loading="settingCoverId !== null"
                :disabled="!hasCoverChanged"
                @click="applyCover"
              >
                使用此照片
              </el-button>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="姓名">
        <el-input v-model="form.identity_name" placeholder="输入姓名..." />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="输入描述..." />
      </el-form-item>
      <el-form-item label="标签">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="选择或输入标签"
          class="w-full"
        >
          <el-option v-for="tag in defaultTags" :key="tag" :label="tag" :value="tag" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="flex gap-2 justify-end">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { FaceIdentity } from '@/types/album'
import { faceApi } from '@/api/face'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'
import { getFaceCropStyle } from '@/utils/faceCrop'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { Camera as CameraIcon, Check as CheckIcon, User as UserIcon } from 'lucide-vue-next'

const props = defineProps<{
  visible: boolean
  identity: FaceIdentity | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', identity: FaceIdentity): void
  (e: 'cover-changed', identity: FaceIdentity): void
}>()

const { width } = useWindowSize()
const isMobile = computed(() => width.value < 640)
const dialogWidth = computed(() => isMobile.value ? '100%' : '560px')

const form = ref({
  identity_name: '',
  description: '',
  tags: [] as string[]
})
const saving = ref(false)

// 更换封面：候选来自该人物自己的照片（后端一定能从中找到对应人脸）
const currentIdentity = ref<FaceIdentity | null>(null)
const coverPhotos = ref<{ id: string, url: string }[]>([])
const coverLoaded = ref(false)
const coverLoading = ref(false)
const showCoverPicker = ref(false)
const settingCoverId = ref<string | null>(null)
const selectedCoverId = ref<string | null>(null)

const coverInfo = computed(() => currentIdentity.value?.cover_photo ?? props.identity?.cover_photo ?? null)
const coverAvatarUrl = computed(() => coverInfo.value ? thumbnailUrl(coverInfo.value.photo_id, 'medium') : '')
const hasCoverChanged = computed(() => (
  selectedCoverId.value !== null && selectedCoverId.value !== coverInfo.value?.photo_id
))

const defaultTags = ["自己", "朋友", "家人", "同事", "女朋友", "男朋友", "同学"]

const fillForm = (identity: FaceIdentity) => {
  form.value = {
    identity_name: identity.identity_name || '',
    description: identity.description || '',
    tags: identity.tags || []
  }
}

// 同一人物的对象刷新（更换封面后父组件回写新对象）不应覆盖未保存的表单输入，
// 因此按 id 判断是否切换了编辑对象（PeopleList 复用同一对话框编辑不同人物）
let lastFormIdentityId: string | null = null
watch(() => props.identity, (newVal) => {
  if (!newVal || newVal.id === lastFormIdentityId) return
  lastFormIdentityId = newVal.id
  fillForm(newVal)
}, { immediate: true })

// 每次打开都从当前 identity 重新填表，丢弃上次未保存的草稿
watch(() => props.visible, (v) => {
  if (v && props.identity) {
    lastFormIdentityId = props.identity.id
    fillForm(props.identity)
  }
})

// 切换编辑对象时重置封面候选；同一人物的封面刷新（id 不变）则保留最新封面
watch(() => props.identity?.id, () => {
  currentIdentity.value = null
  coverPhotos.value = []
  coverLoaded.value = false
  showCoverPicker.value = false
  selectedCoverId.value = null
})

const toggleCoverPicker = async () => {
  showCoverPicker.value = !showCoverPicker.value
  selectedCoverId.value = coverInfo.value?.photo_id ?? null
  if (showCoverPicker.value && !coverLoaded.value) {
    await loadCoverPhotos()
  }
}

const loadCoverPhotos = async () => {
  if (!props.identity) return
  coverLoading.value = true
  try {
    // 取最近 100 张供挑选
    const photos = await faceApi.getIdentityPhotos(props.identity.id, 1, 100)
    coverPhotos.value = photos.map(p => ({ id: p.id, url: thumbnailUrl(p.id, 'medium', p.owner_id) }))
  } catch (e) {
    console.error('Failed to fetch cover candidates', e)
    ElMessage.error('加载照片失败')
  } finally {
    coverLoading.value = false
    coverLoaded.value = true
  }
}

const selectCover = (photoId: string) => {
  if (!settingCoverId.value) selectedCoverId.value = photoId
}

const applyCover = async () => {
  if (!props.identity || !selectedCoverId.value || !hasCoverChanged.value || settingCoverId.value) return
  const photoId = selectedCoverId.value
  settingCoverId.value = photoId
  try {
    await faceApi.setCover(props.identity.id, photoId)
    ElMessage.success('封面已更新')
    // setCover 只返回状态；重新拉取人物信息以拿到最新 cover_photo（含人脸裁剪框）。
    // min_photos=0 绕过展示阈值，保证低照片数的人物也能刷到
    try {
      const identities = await faceApi.listIdentities(1, 1000, ['named', 'unnamed', 'hidden'], 0)
      const fresh = identities.find(i => i.id === props.identity!.id)
      if (fresh) {
        currentIdentity.value = fresh
        emit('cover-changed', fresh)
      }
    } catch (e) {
      console.error('Failed to refresh identity after cover change', e)
    }
    showCoverPicker.value = false
  } catch (e) {
    ElMessage.error('设置封面失败')
  } finally {
    settingCoverId.value = null
  }
}

const submit = async () => {
  if (!props.identity) return
  saving.value = true
  try {
    const updated = await faceApi.updateIdentity(props.identity.id, form.value)
    ElMessage.success('保存成功')
    emit('saved', updated)
    emit('update:visible', false)
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style>
.identity-edit-dialog {
  display: flex;
  max-height: 90vh;
  flex-direction: column;
  overflow: hidden;
}

.identity-edit-dialog .el-dialog__body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
}

.identity-edit-dialog.is-fullscreen {
  max-height: 100vh;
}
</style>
