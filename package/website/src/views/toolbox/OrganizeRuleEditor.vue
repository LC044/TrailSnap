<template>
  <div class="space-y-5">
    <h2 class="ts-section-title">{{ config.kind === 'album' ? '相册命名' : '整理方式' }}</h2>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label="常用整理方案">
      <button v-for="preset in quickPresets" :key="preset.id" type="button" class="ts-button ts-button-secondary"
        :aria-pressed="currentPreset === preset.id" :class="{ 'preset-selected': currentPreset === preset.id }" @click="applyPreset(preset.id)"><Check v-if="currentPreset === preset.id" class="h-4 w-4 shrink-0" aria-hidden="true" />{{ preset.label }}</button>
    </div>
    <el-form label-position="top">
      <template v-if="config.kind === 'organize'">
        <el-form-item label="存放位置">
          <div class="flex w-full flex-wrap gap-2">
            <el-input v-model="config.target" readonly placeholder="选择已配置存储中的存放位置" class="min-w-0 flex-1" />
            <el-button @click="targetPicker = true">选择</el-button>
          </div>
        </el-form-item>
        <el-form-item label="处理方式">
          <el-radio-group v-model="config.action">
            <el-radio value="copy">复制</el-radio><el-radio value="move">移动</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-alert v-if="config.action === 'move'" title="移动会改变实际文件位置，外部软件依赖的原路径可能失效。执行前请检查真实预览。" type="warning" :closable="false" />
      </template>
      <el-form-item v-else label="相册名前缀"><el-input v-model="config.album_prefix" maxlength="40" placeholder="例如：旅行 · " class="max-w-md" /></el-form-item>
    </el-form>
    <DirectoryPickerDialog v-model:visible="targetPicker" v-model="config.target" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check } from 'lucide-vue-next'
import { type MediaScope, type ToolConfig, type OrganizeRule } from '@/api/toolboxWorkflows'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
defineProps<{ scope: MediaScope }>()
const config = defineModel<ToolConfig>({ required: true })
// Keep removed options consistent when restoring earlier configurations.
watch(() => [config.value.kind, config.value.layout, config.value.missing, config.value.multi_group], () => {
  if (!['organize', 'album'].includes(config.value.kind)) return
  if (config.value.kind === 'organize') config.value.layout = 'rebuild'
  config.value.missing = 'skip'
  config.value.multi_group = 'skip'
}, { immediate: true, flush: 'sync' })
const quickPresets = [{ id: 'month', label: '按年月' }, { id: 'city', label: '按城市' }, { id: 'year-city', label: '按年份和城市' }]
const presetRules = (id: string): OrganizeRule[] => id === 'month'
  ? [{ strategy: 'time', granularity: 'month', nested: true, groups: null }]
  : id === 'city' ? [{ strategy: 'location', granularity: 'city', nested: true, groups: null }]
  : [{ strategy: 'time', granularity: 'year', nested: true, groups: null }, { strategy: 'location', granularity: 'city', nested: true, groups: null }]
const currentPreset = computed(() => quickPresets.find(p => JSON.stringify(presetRules(p.id)) === JSON.stringify(config.value.rules))?.id)
const applyPreset = (id: string) => { config.value.rules = presetRules(id) }
const targetPicker = ref(false)
</script>

<style scoped>
.preset-selected {
  border-color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.12);
  color: var(--theme-primary);
}
.preset-selected:hover {
  background: rgba(var(--theme-rgb), 0.18);
}
</style>
