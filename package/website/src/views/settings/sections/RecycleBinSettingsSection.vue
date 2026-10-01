<template>
<SettingsSection v-model="activeNames" name="recycle_bin" title="回收站设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="保留天数">
              <el-input-number v-model="recycleBinForm.retention_days" :min="1" :max="365" class="w-full sm:w-auto" />
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">照片在回收站中保留的天数，超过该天数将被永久删除。</div>
            </el-form-item>
            <el-form-item label="自动清理时间">
              <el-time-select
                v-model="recycleBinForm.cleanup_time"
                start="00:00"
                step="00:30"
                end="23:30"
                placeholder="选择时间"
              />
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">每天执行自动清理过期照片的时间。</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveRecycleBinSettings">保存回收站设置</el-button>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, recycleBinForm, saveRecycleBinSettings } = useBasicSettingsContext()
</script>
