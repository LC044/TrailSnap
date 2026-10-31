<template>
  <div class="ts-settings-page">
    <SettingsPageHeader title="个人资料" description="管理头像、昵称与账号信息" />

    <div class="ts-surface ts-settings-panel">
      <el-form label-position="top" :model="form" @submit.prevent="handleSave">
        <!-- Avatar Section -->
        <el-form-item label="头像">
          <div class="flex flex-wrap items-center gap-4">
            <el-avatar :size="80" :src="toServerUrl(form.avatar || defaultAvatar)" class="border-2 border-gray-200 dark:border-gray-700" />
            <div class="flex flex-col gap-2">
              <div class="ts-form-actions">
                <el-upload
                  :auto-upload="true"
                  :show-file-list="false"
                  accept="image/*"
                  :http-request="handleUploadAvatar"
                >
                  <el-button type="primary" plain :loading="uploading || savingAvatar" :disabled="saving || uploading || savingAvatar">本地上传</el-button>
                </el-upload>
                <el-button :disabled="saving || uploading || savingAvatar" @click="showGallerySelector = true">从图库选择</el-button>
              </div>
              <span class="text-xs text-gray-500 dark:text-gray-400">支持本地上传或从图库选择，确认后自动保存</span>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="用户名">
          <el-input v-model="form.username" disabled />
          <span class="text-xs text-gray-500 dark:text-gray-400 mt-1">用户名不可修改</span>
        </el-form-item>

        <el-form-item label="邮箱">
          <el-input v-model="form.email" disabled />
          <span class="text-xs text-gray-500 dark:text-gray-400 mt-1">邮箱暂不支持修改</span>
        </el-form-item>

        <el-form-item label="昵称">
          <el-input v-model="form.nickname" placeholder="请输入昵称" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving" :disabled="uploading || savingAvatar">保存修改</el-button>
        </el-form-item>
      </el-form>
    </div>

    <PhotoSelectorDialog
      v-model="showGallerySelector"
      title="选择头像"
      :store="selectionStore"
      single-select
      :busy="savingAvatar"
      @select="handleSelectFromGallery"
    />
  </div>
</template>

<script setup lang="ts">
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { userService } from '@/api/user'
import PhotoSelectorDialog from '@/components/PhotoSelectorDialog.vue'
import { useSelectionStore } from '@/stores/selectionStore'
import request from '@/utils/request'
import { toServerUrl } from '@/config/server'
import { thumbnailPath } from '@/utils/mediaUrl'

const userStore = useUserStore()
const selectionStore = useSelectionStore()
const defaultAvatar = new URL('../../assets/default-avatar.svg', import.meta.url).href

const form = reactive({
  username: '',
  email: '',
  nickname: '',
  avatar: ''
})

const saving = ref(false)
const uploading = ref(false)
const savingAvatar = ref(false)
const showGallerySelector = ref(false)

onMounted(async () => {
  if (!userStore.userInfo) {
    await userStore.getUserInfo()
  }
  if (userStore.userInfo) {
    form.username = userStore.userInfo.username || ''
    form.email = userStore.userInfo.email || ''
    form.nickname = userStore.userInfo.nickname || ''
    form.avatar = userStore.userInfo.avatar || ''
  }
})

const handleSave = async () => {
  if (saving.value || uploading.value || savingAvatar.value) return
  saving.value = true
  try {
    await userService.updateCurrentUser({
      nickname: form.nickname,
      avatar: form.avatar
    })
    await userStore.getUserInfo()
    ElMessage.success('个人资料已保存')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleUploadAvatar = async (options: any) => {
  const { file } = options
  if (saving.value || uploading.value || savingAvatar.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    // We upload it as a generic photo
    const res = await request.post('/api/medias', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    const photoId = res.data.id
    await persistAvatar(thumbnailPath(photoId, 'medium'))
  } catch (error) {
    ElMessage.error('头像上传失败')
  } finally {
    uploading.value = false
  }
}

// 只保存头像，避免一并提交还未确认的昵称草稿。
const persistAvatar = async (avatar: string) => {
  savingAvatar.value = true
  try {
    const updated = await userService.updateCurrentUser({ avatar })
    form.avatar = updated.avatar || avatar
    userStore.updateUserInfo(updated)
    ElMessage.success('头像已保存')
  } finally {
    savingAvatar.value = false
  }
}

const handleSelectFromGallery = async (ids: string[]) => {
  if (!ids.length || savingAvatar.value || saving.value || uploading.value) return
  try {
    await persistAvatar(thumbnailPath(ids[0], 'medium'))
    showGallerySelector.value = false
  } catch {
    ElMessage.error('头像保存失败，请重试')
  }
}
</script>
