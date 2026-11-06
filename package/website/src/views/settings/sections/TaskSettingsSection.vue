<template>
  <SettingsSection v-model="activeNames" name="task" title="后台处理性能">
    <div class="px-4 pb-4 md:px-6">
      <slot />
      <SettingsFormRow inline label="处理模式" label-id="task-mode-label" :description="selectedMode?.description">
        <el-select v-model="taskForm.concurrency_level" aria-labelledby="task-mode-label" class="!w-36 sm:!w-48">
          <el-option v-for="mode in taskPerformanceModes" :key="mode.value" :label="mode.recommended ? `${mode.label}（推荐）` : mode.label" :value="mode.value" />
        </el-select>
      </SettingsFormRow>
      <details class="ts-muted text-xs leading-5 mt-1"><summary class="cursor-pointer">了解处理模式</summary><p class="mt-2">系统会根据 CPU、内存和任务响应自动调节；切换时先完成当前批次，不会中断任务。</p></details>
      <div v-if="taskApplyMessage" role="status" class="mt-2 rounded-lg bg-primary-500/10 px-3 py-2 text-sm text-primary-600 dark:text-primary-500">{{ taskApplyMessage }}</div>
      <div class="flex flex-wrap items-center justify-end gap-3 border-t ts-divider mt-2 pt-3">
        <el-button type="primary" :loading="savingTaskSettings" @click="saveTaskSettings">应用设置</el-button>
      </div>
    </div>
  </SettingsSection>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import SettingsFormRow from '@/components/ui/SettingsFormRow.vue'
import SettingsSection from '@/components/ui/SettingsSection.vue'
import { useBasicSettingsContext } from '@/composables/settings/useBasicSettings'
const { activeNames, saveTaskSettings, savingTaskSettings, taskApplyMessage, taskForm, taskPerformanceModes } = useBasicSettingsContext()
const selectedMode = computed(() => taskPerformanceModes.find(mode => mode.value === taskForm.value.concurrency_level))
</script>
