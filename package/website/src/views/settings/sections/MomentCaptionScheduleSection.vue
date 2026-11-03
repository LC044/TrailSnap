<template>
<SettingsSection v-model="activeNames" name="moment_caption_schedule" title="自动生成文案">
<div class="px-4 pb-4 md:px-6 md:pb-6">
          <div>
            <SettingsFormRow label="生成模式" description="为所有成员补全行影集内的朋友圈文案，已有文案会跳过。请先在「大模型与文案」配置可用模型；第三方服务可能产生调用费用。">
              <el-radio-group class="flex flex-wrap gap-x-3" v-model="momentCaptionScheduleForm.mode">
                <el-radio class="!mr-0" value="off">关闭</el-radio>
                <el-radio class="!mr-0" value="interval">间隔循环</el-radio>
                <el-radio class="!mr-0" value="weekly">指定日期</el-radio>
              </el-radio-group>

            </SettingsFormRow>

            <SettingsFormRow v-if="momentCaptionScheduleForm.mode === 'interval'" label="间隔时间 (分钟)">
              <el-select v-model="momentCaptionScheduleForm.interval" placeholder="选择间隔时间" class="w-full sm:w-auto" style="min-width: 120px;">
                <el-option label="30分钟" :value="30" />
                <el-option label="60分钟" :value="60" />
                <el-option label="120分钟" :value="120" />
                <el-option label="360分钟" :value="360" />
              </el-select>
            </SettingsFormRow>

            <template v-if="momentCaptionScheduleForm.mode === 'weekly'">
              <SettingsFormRow label="执行日期">
                <el-checkbox-group class="flex flex-wrap gap-x-3" v-model="momentCaptionScheduleForm.weekdays">
                  <el-checkbox class="!mr-0" :value="0">周一</el-checkbox>
                  <el-checkbox class="!mr-0" :value="1">周二</el-checkbox>
                  <el-checkbox class="!mr-0" :value="2">周三</el-checkbox>
                  <el-checkbox class="!mr-0" :value="3">周四</el-checkbox>
                  <el-checkbox class="!mr-0" :value="4">周五</el-checkbox>
                  <el-checkbox class="!mr-0" :value="5">周六</el-checkbox>
                  <el-checkbox class="!mr-0" :value="6">周日</el-checkbox>
                </el-checkbox-group>
              </SettingsFormRow>
              <SettingsFormRow label="执行时间" description="建议凌晨 03:00 左右执行，与扫描任务错开。">
                <UnifiedDatePicker type="time"
                  v-model="momentCaptionScheduleForm.time"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                  placeholder="选择时间"
                />

              </SettingsFormRow>
            </template>

            <SettingsFormRow v-if="momentCaptionScheduleForm.mode !== 'off'" label="每次生成间隔 (秒)" description="控制连续请求的间隔，减少触发模型服务限流。默认 2 秒。">
              <el-input-number v-model="momentCaptionScheduleForm.per_caption_delay_sec" :min="0" :max="60" class="w-full sm:w-auto" />

            </SettingsFormRow>

            <div class="flex flex-wrap items-center justify-end gap-3 border-t ts-divider pt-3 mt-2">
              <el-button type="primary" @click="saveMomentCaptionScheduleSettings">保存朋友圈文案设置</el-button>
              <span class="text-sm text-gray-500 dark:text-gray-400 ml-2">修改后需重启服务生效</span>
            </div>
          </div>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, momentCaptionScheduleForm, saveMomentCaptionScheduleSettings } = useBasicSettingsContext()
</script>
