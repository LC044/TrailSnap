<template>
<SettingsSection v-model="activeNames" name="task" title="任务设置">
<div class="px-6 pb-6">
          <el-form label-position="top" class="max-w-3xl">
            <el-form-item label="后台处理性能">
              <div class="grid w-full gap-2 sm:grid-cols-2">
                <button
                  v-for="mode in taskPerformanceModes"
                  :key="mode.value"
                  type="button"
                  class="rounded-lg border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
                  :class="taskForm.concurrency_level === mode.value
                    ? 'border-primary-500 bg-primary-500/5'
                    : 'border-gray-200 bg-white hover:border-primary-500/50 dark:border-gray-700 dark:bg-gray-900'"
                  @click="taskForm.concurrency_level = mode.value"
                >
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-gray-800 dark:text-gray-100">{{ mode.label }}</span>
                    <span v-if="mode.recommended" class="rounded-full bg-primary-500 px-2 py-0.5 text-xs text-white">推荐</span>
                  </div>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ mode.description }}</p>
                </button>
              </div>
              <div class="mt-2 w-full text-sm text-gray-500 dark:text-gray-400">
                系统会继续根据 CPU、内存和任务响应自动调节；切换时会先完成当前批次，不会直接中断任务。
              </div>
              <div v-if="taskApplyMessage" class="mt-2 w-full rounded-lg bg-primary-500/10 px-3 py-2 text-sm text-primary-600 dark:text-primary-500">
                {{ taskApplyMessage }}
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingTaskSettings" @click="saveTaskSettings">应用设置</el-button>
            </el-form-item>
          </el-form>
        </div>
</SettingsSection>
</template>
<script setup lang="ts">
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveTaskSettings, savingTaskSettings, taskApplyMessage, taskForm, taskPerformanceModes } = useBasicSettingsContext()
</script>
