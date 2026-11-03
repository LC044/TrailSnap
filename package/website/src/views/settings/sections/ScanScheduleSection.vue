<template>
  <SettingsSection v-model="activeNames" name="scan_schedule" title="自动扫描照片文件夹">
    <div class="px-4 pb-4 md:px-6">
      <SettingsFormRow label="扫描模式" label-id="scan-mode-label">
        <el-radio-group v-model="scanScheduleForm.mode" aria-labelledby="scan-mode-label" class="flex flex-wrap gap-x-4">
          <el-radio value="off" class="!mr-0">关闭</el-radio>
          <el-radio value="interval" class="!mr-0">间隔循环</el-radio>
          <el-radio value="weekly" class="!mr-0">指定日期</el-radio>
        </el-radio-group>
      </SettingsFormRow>
      <SettingsFormRow v-if="scanScheduleForm.mode === 'interval'" label="扫描间隔" description="频繁扫描可能唤醒休眠中的硬盘。" label-id="scan-interval-label">
        <el-select v-model="scanScheduleForm.interval" aria-labelledby="scan-interval-label" class="!w-40">
          <el-option v-for="minutes in [5, 10, 15, 30, 60]" :key="minutes" :label="`${minutes} 分钟`" :value="minutes" />
        </el-select>
      </SettingsFormRow>
      <template v-if="scanScheduleForm.mode === 'weekly'">
        <SettingsFormRow label="执行日期" description="全选表示每天执行。" label-id="scan-days-label">
          <el-checkbox-group v-model="scanScheduleForm.weekdays" aria-labelledby="scan-days-label" class="flex flex-wrap gap-x-3">
            <el-checkbox v-for="(day, index) in ['周一', '周二', '周三', '周四', '周五', '周六', '周日']" :key="index" :value="index" class="!mr-0">{{ day }}</el-checkbox>
          </el-checkbox-group>
        </SettingsFormRow>
        <SettingsFormRow label="执行时间" description="按服务器时区执行，建议选择空闲时段。" label-id="scan-time-label">
          <UnifiedDatePicker v-model="scanScheduleForm.time" type="time" start="00:00" step="00:30" end="23:30" placeholder="选择时间" aria-labelledby="scan-time-label" />
        </SettingsFormRow>
      </template>
      <div class="flex justify-end border-t ts-divider mt-2 pt-3">
        <el-button type="primary" @click="saveScanScheduleSettings">保存扫描设置</el-button>
      </div>
    </div>
  </SettingsSection>
</template>
<script setup lang="ts">
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveScanScheduleSettings, scanScheduleForm } = useBasicSettingsContext()
</script>
