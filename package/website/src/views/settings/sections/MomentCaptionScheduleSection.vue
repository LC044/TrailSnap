<template>
<SettingsSection v-model="activeNames" name="moment_caption_schedule" title="朋友圈文案定时生成设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="生成模式">
              <el-radio-group v-model="momentCaptionScheduleForm.mode">
                <el-radio value="off">关闭</el-radio>
                <el-radio value="interval">间隔循环</el-radio>
                <el-radio value="weekly">每周定时</el-radio>
              </el-radio-group>
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">到点自动为所有用户补齐"有照片但还没文案"的天。命中缓存的天会跳过，天然幂等。</div>
            </el-form-item>

            <el-form-item v-if="momentCaptionScheduleForm.mode === 'interval'" label="间隔时间 (分钟)">
              <el-select v-model="momentCaptionScheduleForm.interval" placeholder="选择间隔时间" class="w-full sm:w-auto" style="min-width: 120px;">
                <el-option label="30分钟" :value="30" />
                <el-option label="60分钟" :value="60" />
                <el-option label="120分钟" :value="120" />
                <el-option label="360分钟" :value="360" />
              </el-select>
            </el-form-item>

            <template v-if="momentCaptionScheduleForm.mode === 'weekly'">
              <el-form-item label="执行日期">
                <el-checkbox-group v-model="momentCaptionScheduleForm.weekdays">
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
                  v-model="momentCaptionScheduleForm.time"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                  placeholder="选择时间"
                />
                <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">建议凌晨 03:00 左右执行，与扫描任务错开。</div>
              </el-form-item>
            </template>

            <el-form-item v-if="momentCaptionScheduleForm.mode !== 'off'" label="每次生成间隔 (秒)">
              <el-input-number v-model="momentCaptionScheduleForm.per_caption_delay_sec" :min="0" :max="60" class="w-full sm:w-auto" />
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1 w-full">两次文案生成之间的间隔，保护 LLM 不被打爆（默认 2 秒）。</div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveMomentCaptionScheduleSettings">保存朋友圈文案设置</el-button>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-2">修改后需重启服务生效</span>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, momentCaptionScheduleForm, saveMomentCaptionScheduleSettings } = useBasicSettingsContext()
</script>
