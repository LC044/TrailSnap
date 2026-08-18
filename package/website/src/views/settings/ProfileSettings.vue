<template>
  <div>
    <div class="mb-4 md:mb-6 flex justify-between items-center">
      <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">个人资料</h2>
    </div>

    <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 max-w-2xl">
      <el-form label-position="top" :model="form" @submit.prevent="handleSave">
        <!-- Avatar Section -->
        <el-form-item label="头像">
          <div class="flex items-center gap-6">
            <el-avatar :size="80" :src="toServerUrl(form.avatar || defaultAvatar)" class="border-2 border-gray-200 dark:border-gray-700" />
            <div class="flex flex-col gap-2">
              <div class="flex gap-2">
                <el-upload
                  :auto-upload="true"
                  :show-file-list="false"
                  accept="image/*"
                  :http-request="handleUploadAvatar"
                >
                  <el-button type="primary" plain :loading="uploading">本地上传</el-button>
                </el-upload>
                <el-button @click="showGallerySelector = true">从图库选择</el-button>
              </div>
              <span class="text-xs text-gray-500">支持本地上传或从已上传的照片中选择</span>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="用户名">
          <el-input v-model="form.username" disabled />
          <span class="text-xs text-gray-500 mt-1">用户名不可修改</span>
        </el-form-item>

        <el-form-item label="邮箱">
          <el-input v-model="form.email" disabled />
          <span class="text-xs text-gray-500 mt-1">邮箱暂不支持修改</span>
        </el-form-item>

        <el-form-item label="昵称">
          <el-input v-model="form.nickname" placeholder="请输入昵称" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存修改</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Photo Selector Dialog -->
    <el-dialog v-model="showGallerySelector" title="选择头像" width="80%" top="5vh" class="gallery-selector-dialog">
      <div class="h-[60vh] -mx-4 -mt-4 -mb-4">
        <PhotoSelector v-if="showGallerySelector" :is-selector="true" title="选择头像照片" @select="handleSelectFromGallery" @cancel="showGallerySelector = false" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { userService } from '@/api/user'
import PhotoSelector from '@/components/PhotoSelector.vue'
import request from '@/utils/request'
import { toServerUrl } from '@/config/server'

const userStore = useUserStore()
const defaultAvatar = 'https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png'

const form = reactive({
  username: '',
  email: '',
  nickname: '',
  avatar: ''
})

const saving = ref(false)
const uploading = ref(false)
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
    form.avatar = `/api/medias/${photoId}/thumbnail?size=medium`
    ElMessage.success('头像上传成功')
  } catch (error) {
    ElMessage.error('头像上传失败')
  } finally {
    uploading.value = false
  }
}

const handleSelectFromGallery = (ids: string[]) => {
  if (ids.length > 0) {
    const photoId = ids[0]
    form.avatar = `/api/medias/${photoId}/thumbnail?size=medium`
    showGallerySelector.value = false
    ElMessage.success('已选择头像')
  }
}
</script>

<style>
.gallery-selector-dialog .el-dialog__body {
  padding: 0;
  overflow: hidden;
}
</style>
