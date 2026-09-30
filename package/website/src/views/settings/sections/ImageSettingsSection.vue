<template>
<SettingsSection v-model="activeNames" name="image" title="图片设置">
<div class="px-6 pb-6">
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">修改图片配置后将在下次新增照片时生效，如果要修改已有图片质量请在任务管理中执行缩略图生成任务</div>
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="缩略图大小">
              <el-select v-model="imageForm.thumbnail_size" placeholder="选择缩略图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="250px" :value="250" />
                <el-option label="480px" :value="480" />
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
              </el-select>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 250px</span>
            </el-form-item>

            <el-form-item label="缩略图质量">
              <el-slider v-model="imageForm.thumbnail_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </el-form-item>

            <el-form-item label="预览图大小">
              <el-select v-model="imageForm.preview_size" placeholder="选择预览图大小" class="w-full sm:w-auto min-w-[120px]">
                <el-option label="720px" :value="720" />
                <el-option label="1080px" :value="1080" />
                <el-option label="1440px" :value="1440" />
                <el-option label="2160px" :value="2160" />
              </el-select>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-0 sm:ml-2 block sm:inline mt-1 sm:mt-0">默认 1440px</span>
            </el-form-item>

            <el-form-item label="预览图质量">
              <el-slider v-model="imageForm.preview_quality" :min="1" :max="100" show-input class="w-full sm:w-64" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveImageSettings">保存图片配置</el-button>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, imageForm, saveImageSettings } = useBasicSettingsContext()
</script>
