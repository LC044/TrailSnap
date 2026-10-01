<template>
<SettingsSection v-model="activeNames" name="scan_schedule" title="定时扫描设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="扫描模式">
              <el-radio-group v-model="scanScheduleForm.mode">
                <el-radio value="off">关闭</el-radio>
                <el-radio value="interval">间隔循环</el-radio>
                <el-radio value="weekly">每周定时</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="scanScheduleForm.mode === 'interval'" label="间隔时间 (分钟)">
              <el-select v-model="scanScheduleForm.interval" placeholder="选择间隔时间" class="w-full sm:w-auto" style="min-width: 120px;">
                <el-option label="5分钟" :value="5" />
                <el-option label="10分钟" :value="10" />
                <el-option label="15分钟" :value="15" />
                <el-option label="30分钟" :value="30" />
                <el-option label="60分钟" :value="60" />
              </el-select>
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">适合频繁上传，机械硬盘唤醒较频繁</div>
            </el-form-item>

            <template v-if="scanScheduleForm.mode === 'weekly'">
              <el-form-item label="执行日期">
                <el-checkbox-group v-model="scanScheduleForm.weekdays">
                  <el-checkbox :value="0">周一</el-checkbox>
                  <el-checkbox :value="1">周二</el-checkbox>
                  <el-checkbox :value="2">周三</el-checkbox>
                  <el-checkbox :value="3">周四</el-checkbox>
                  <el-checkbox :value="4">周五</el-checkbox>
                  <el-checkbox :value="5">周六</el-checkbox>
                  <el-checkbox :value="6">周日</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="执行时间">
                <el-time-select
                  v-model="scanScheduleForm.time"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                  placeholder="选择时间"
                />
                <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">NAS推荐凌晨02:00~04:00执行，全选等价每天执行</div>
              </el-form-item>
            </template>

            <el-form-item>
              <el-button type="primary" @click="saveScanScheduleSettings">保存扫描设置</el-button>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveScanScheduleSettings, scanScheduleForm } = useBasicSettingsContext()
</script>
