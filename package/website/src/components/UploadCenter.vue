<template>
  <ResponsiveDialog v-if="upload.initialized" v-model="upload.visible" title="上传照片" max-width="42rem"
    description="收起后继续上传。原文件安全保存后，预览和照片信息会在后台整理。" keep-mounted>
    <MultiFileUpload @upload-complete="complete" @upload-state="updateState" />
  </ResponsiveDialog>
  <button v-if="upload.total && !upload.visible" type="button" @click="upload.open"
    class="fixed bottom-24 right-4 z-40 ts-glass-button gap-2 px-4 py-3 text-sm md:bottom-6"
    aria-label="打开上传队列">
    <UploadCloud class="h-4 w-4 text-primary-500" />
    <span>{{ upload.running ? `正在上传 ${upload.progress}%` : upload.failed ? `${upload.failed} 项上传失败` : '上传完成' }} · {{ upload.completed }}/{{ upload.total }}</span>
  </button>
</template>

<script setup lang="ts">
import { UploadCloud } from 'lucide-vue-next'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import MultiFileUpload from '@/components/MultiFileUpload.vue'
import { useUploadStore } from '@/stores/uploadCenterStore'
import { usePhotoStore, usePhotosPageStore } from '@/stores/photoStore'

const upload = useUploadStore()
const updateState = (state: { running: boolean; completed: number; total: number; failed: number; progress: number }) => Object.assign(upload, state)
const complete = () => {
  usePhotoStore().markDataStale('PROCESS_BASIC')
  usePhotosPageStore().markDataStale('PROCESS_BASIC')
}
</script>
