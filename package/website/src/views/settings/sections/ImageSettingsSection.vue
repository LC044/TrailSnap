<template>
<SettingsSection v-model="activeNames" name="image" title="图片生成质量 · 高级选项">
<div class="px-4 pb-4 md:px-6 md:pb-6">
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">当前账号 · 标准配置：缩略图 250px / 80，预览图 1440px / 85。提高质量会增加文件体积，不改变原始照片。仅影响之后生成的图片，已有图片需在后台任务中重新生成。</div>
          <div>
            <SettingsFormRow label="画质方案">
              <el-select :model-value="standard ? 'standard' : 'custom'" class="!w-full sm:!w-48" aria-label="画质方案" @change="applyPreset">
                <el-option label="标准（推荐）" value="standard" /><el-option label="自定义" value="custom" />
              </el-select>
            </SettingsFormRow>
            <details :open="customOpen || !standard" class="mb-4"><summary class="cursor-pointer ts-muted text-sm mb-3">自定义尺寸与质量</summary>
            <SettingsFormRow label="缩略图大小">
              <el-select v-model="imageForm.thumbnail_size" placeholder="选择缩略图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="250px" :value="250" />
                <el-option label="480px" :value="480" />
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
              </el-select>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 250px</span>
            </SettingsFormRow>

            <SettingsFormRow label="缩略图质量">
              <el-slider v-model="imageForm.thumbnail_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </SettingsFormRow>

            <SettingsFormRow label="预览图大小">
              <el-select v-model="imageForm.preview_size" placeholder="选择预览图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
                <el-option label="1440px" :value="1440" />
                <el-option label="2160px" :value="2160" />
              </el-select>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 1440px</span>
            </SettingsFormRow>

            <SettingsFormRow label="预览图质量">
              <el-slider v-model="imageForm.preview_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </SettingsFormRow>
            </details>
            <div class="flex flex-wrap items-center justify-end gap-3 border-t ts-divider pt-3 mt-2">
              <el-button type="primary" @click="saveImageSettings">保存图片配置</el-button>
            </div>
          </div>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, imageForm, saveImageSettings } = useBasicSettingsContext()
const customOpen = ref(false)
const standard = computed(() => imageForm.value.thumbnail_size === 250 && imageForm.value.thumbnail_quality === 80 && imageForm.value.preview_size === 1440 && imageForm.value.preview_quality === 85)
function applyPreset(value: string) {
  if (value === 'standard') Object.assign(imageForm.value, { thumbnail_size: 250, thumbnail_quality: 80, preview_size: 1440, preview_quality: 85 })
  else customOpen.value = true
}
</script>
