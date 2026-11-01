<template>
  <SettingsSection v-model="activeNames" name="photo-viewing" title="照片查看">
    <div class="px-4 pb-4 md:px-6 md:pb-6 max-w-3xl">
      <div class="flex items-center justify-between gap-4">
        <label id="auto-view-original-label" for="auto-view-original" class="text-sm font-medium">自动查看原图</label>
        <el-switch id="auto-view-original" v-model="autoViewOriginal" aria-labelledby="auto-view-original-label" aria-describedby="auto-view-original-description" />
      </div>
      <p id="auto-view-original-description" class="ts-muted text-sm mt-2">
        打开大图时自动加载原图，适合局域网访问。关闭后优先加载预览图，仍可手动查看原图。设置自动保存，仅在当前设备生效。
      </p>
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
import { usePhotoViewingStore } from '@/stores/photoViewing'

const { activeNames } = useBasicSettingsContext()
const { autoViewOriginal } = storeToRefs(usePhotoViewingStore())
</script>
