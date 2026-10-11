<template>
  <ResponsiveDialog
    history
    :model-value="visible"
    title="编辑人物信息"
    max-width="35rem"
    mobile-mode="fullscreen"
    mobile-back
    :before-close="() => !saving && !settingCoverId"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="封面">
        <div class="w-full">
          <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-gray-50 p-3 dark:bg-gray-800/70">
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
              :disabled="saving || !!settingCoverId"
              @click="openCoverPicker"
            >
              <span class="flex items-center gap-1.5">
                <CameraIcon class="h-4 w-4" />
                <span>从图库选择</span>
              </span>
            </el-button>
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
      <div class="flex gap-3">
        <button type="button" class="ts-button ts-button-secondary flex-1" :disabled="saving || !!settingCoverId" @click="$emit('update:visible', false)">取消</button>
        <button type="button" class="ts-button ts-button-primary flex-1" :disabled="saving || !!settingCoverId" @click="submit">{{ saving ? '保存中…' : '保存' }}</button>
      </div>
    </template>
  </ResponsiveDialog>
  <PhotoSelectorDialog
    v-model="showCoverPicker"
    title="选择人物封面"
    :store="coverStore"
    single-select
    :busy="!!settingCoverId"
    @select="applyCover"
  />
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import PhotoSelectorDialog from '@/components/PhotoSelectorDialog.vue'
import { useIdentityPhotoSelectionStore } from '@/stores/identityPhotoSelectionStore'
import type { InputInstance } from 'element-plus'
import type { FaceIdentity } from '@/types/album'
import { faceApi } from '@/api/face'
import { ElMessage } from 'element-plus'
import { getFaceCropStyle } from '@/utils/faceCrop'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { Camera as CameraIcon, User as UserIcon } from 'lucide-vue-next'

const props = defineProps<{
  visible: boolean
  identity: FaceIdentity | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', identity: FaceIdentity): void
  (e: 'cover-changed', identity: FaceIdentity): void
}>()


const form = ref({
  identity_name: '',
  description: '',
  tags: [] as string[]
})
const saving = ref(false)

// 弹窗打开后聚焦姓名输入框（桌面端快捷改名；移动端会唤起输入法，行为与
// 迁移 ResponsiveDialog 前的 @opened="focusNameInput" 保持一致）
const nameInputRef = ref<InputInstance | null>(null)


// 更换封面：候选来自该人物自己的照片（后端一定能从中找到对应人脸）
const currentIdentity = ref<FaceIdentity | null>(null)
const coverStore = useIdentityPhotoSelectionStore()
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
    currentIdentity.value = null
    lastFormIdentityId = props.identity.id
    fillForm(props.identity)
    // 弹层动画结束后再聚焦，避免与面板自身的 focus 抢时机
    void nextTick(() => setTimeout(() => nameInputRef.value?.focus(), 200))
  }
})

// 切换编辑对象时重置封面候选；同一人物的封面刷新（id 不变）则保留最新封面
watch(() => props.identity?.id, () => {
  currentIdentity.value = null
  showCoverPicker.value = false
})

const openCoverPicker = () => {
  if (!props.identity || saving.value || settingCoverId.value) return
  coverStore.setIdentity(props.identity.id)
  showCoverPicker.value = true
}

const applyCover = async (ids: string[]) => {
  if (!props.identity || !ids.length || settingCoverId.value) return
  const photoId = ids[0]
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
  if (!props.identity || saving.value || settingCoverId.value) return
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
