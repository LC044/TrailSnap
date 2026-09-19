<template>
  <el-dialog
    :model-value="visible"
    title="编辑人物信息"
    :width="dialogWidth"
    class="rounded-xl"
    @update:model-value="$emit('update:visible', $event)"
    @opened="focusNameInput"
  >
    <el-form label-position="top">
      <el-form-item label="封面">
        <div class="w-full">
          <div class="flex items-center gap-4">
            <div class="relative h-16 w-16 shrink-0 overflow-hidden rounded-full border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800">
              <img
                v-if="coverInfo"
                :src="coverAvatarUrl"
                class="absolute max-w-none"
                :style="getFaceCropStyle(coverInfo)"
                alt="人物封面"
              />
              <UserIcon v-else class="h-full w-full p-4 text-gray-400" />
            </div>
            <el-button
              :disabled="coverLoaded && coverPhotos.length === 0"
              @click="toggleCoverPicker"
            >
              <span class="flex items-center gap-1.5">
                <CameraIcon class="h-4 w-4" />
                <span>更换封面</span>
              </span>
            </el-button>
          </div>

          <div v-if="showCoverPicker" class="mt-3">
            <div
              v-loading="coverLoading"
              class="cover-photo-grid grid min-h-20 max-h-44 grid-cols-4 sm:grid-cols-5 gap-2 overflow-y-auto"
            >
              <button
                v-for="p in coverPhotos"
                :key="p.id"
                type="button"
                :data-photo-id="p.id"
                class="relative aspect-square overflow-hidden rounded-lg border-2 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed"
                :class="p.id === coverInfo?.photo_id
                  ? 'border-primary-500'
                  : 'border-transparent hover:border-gray-300 dark:hover:border-gray-600'"
                :disabled="settingCoverId !== null"
                :title="p.id === coverInfo?.photo_id ? '当前封面' : '设为封面'"
                @click="pickCover(p.id)"
              >
                <img :src="p.url" class="h-full w-full object-cover" loading="lazy" alt="封面候选" />
                <div
                  v-if="settingCoverId === p.id"
                  class="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-black/50"
                >
                  <Loader2Icon class="h-5 w-5 animate-spin text-primary-500" />
                </div>
              </button>
            </div>
            <p v-if="coverLoaded && coverPhotos.length === 0" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
              该人物暂无照片，无法更换封面
            </p>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="姓名">
        <el-input ref="nameInputRef" v-model="form.identity_name" placeholder="输入姓名..." />
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
import type { InputInstance } from 'element-plus'
import type { FaceIdentity } from '@/types/album'
import { faceApi } from '@/api/face'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'
import { getFaceCropStyle } from '@/utils/faceCrop'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { Camera as CameraIcon, Loader2 as Loader2Icon, User as UserIcon } from 'lucide-vue-next'

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
const dialogWidth = computed(() => width.value < 640 ? '90%' : '400px')

const form = ref({
  identity_name: '',
  description: '',
  tags: [] as string[]
})
const saving = ref(false)

// 弹窗动画结束后聚焦姓名输入框；此时仍在移动端点击的瞬时激活窗口内，
// focus() 会直接唤起输入法
const nameInputRef = ref<InputInstance | null>(null)
const focusNameInput = () => {
  nameInputRef.value?.focus()
}

// 更换封面：候选来自该人物自己的照片（后端一定能从中找到对应人脸）
const currentIdentity = ref<FaceIdentity | null>(null)
const coverPhotos = ref<{ id: string, url: string }[]>([])
const coverLoaded = ref(false)
const coverLoading = ref(false)
const showCoverPicker = ref(false)
const settingCoverId = ref<string | null>(null)

const coverInfo = computed(() => currentIdentity.value?.cover_photo ?? props.identity?.cover_photo ?? null)
const coverAvatarUrl = computed(() => coverInfo.value ? thumbnailUrl(coverInfo.value.photo_id, 'medium') : '')

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
})

const toggleCoverPicker = async () => {
  showCoverPicker.value = !showCoverPicker.value
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
    coverPhotos.value = photos.map(p => ({ id: p.id, url: thumbnailUrl(p.id, 'small', p.owner_id) }))
  } catch (e) {
    console.error('Failed to fetch cover candidates', e)
    ElMessage.error('加载照片失败')
  } finally {
    coverLoading.value = false
    coverLoaded.value = true
  }
}

const pickCover = async (photoId: string) => {
  if (!props.identity || settingCoverId.value) return
  if (photoId === coverInfo.value?.photo_id) {
    showCoverPicker.value = false
    return
  }
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
