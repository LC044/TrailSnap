<template>
  <SettingsSection v-model="activeNames" name="recycle_bin" title="回收站设置">
    <div class="px-4 pb-4 md:px-6">
      <SettingsFormRow label="保留天数" control-id="recycle-retention" description="保留期内可恢复，过期后自动永久删除。">
        <el-input-number id="recycle-retention" v-model="recycleBinForm.retention_days" :min="1" :max="365" class="!w-36" />
        <span class="ts-muted text-sm">天</span>
      </SettingsFormRow>
      <details class="py-2">
        <summary class="cursor-pointer ts-muted text-sm">高级选项 · 自动清理时间</summary>
        <SettingsFormRow label="自动清理时间" label-id="recycle-time-label" description="每天检查并清理超过保留期限的照片。">
          <UnifiedDatePicker v-model="recycleBinForm.cleanup_time" type="time" start="00:00" step="00:30" end="23:30" placeholder="选择时间" aria-labelledby="recycle-time-label" />
        </SettingsFormRow>
      </details>
      <div class="flex flex-wrap items-center justify-end gap-3 border-t ts-divider mt-2 pt-3">
        <el-button type="primary" @click="saveRecycleBinSettings">保存回收站设置</el-button>
      </div>
    </div>
  </SettingsSection>
</template>
<script setup lang="ts">
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, recycleBinForm, saveRecycleBinSettings } = useBasicSettingsContext()
</script>
