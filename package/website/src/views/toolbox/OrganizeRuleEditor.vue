<template>
  <div class="space-y-5">
    <div>
      <h2 class="ts-section-title">{{ config.kind === 'album' ? '相册命名' : '整理方式' }}</h2>
      <p v-if="config.kind === 'organize'" class="ts-muted mt-2 text-sm">
        按拍摄时间、地点、人物或类别创建子文件夹，再把照片复制或移动到对应目录。
      </p>
    </div>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label="常用整理方案">
      <button v-for="preset in availablePresets" :key="preset.id" type="button" class="ts-button ts-button-secondary min-w-0 !whitespace-normal"
        :aria-label="preset.label" :aria-pressed="currentPreset === preset.id"
        :class="{ 'preset-selected': currentPreset === preset.id, '!min-h-14 !px-2': config.kind === 'organize' }" @click="applyPreset(preset.id)">
        <span class="flex min-w-0 max-w-full flex-col items-center gap-1 text-center">
          <span class="inline-flex max-w-full items-center gap-1">
            <Check v-if="currentPreset === preset.id" class="h-4 w-4 shrink-0" aria-hidden="true" />
            <span class="min-w-0 break-words">{{ preset.label }}</span>
          </span>
          <span v-if="config.kind === 'organize'" class="ts-muted max-w-full break-words text-xs">{{ preset.parts.join(' / ') }}</span>
        </span>
      </button>
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
        <div v-if="exampleTarget" class="mb-4 space-y-2 rounded-xl bg-[var(--ts-color-surface-muted)] p-4 text-sm">
          <p class="font-medium">归档路径示例</p>
          <p class="ts-muted">{{ selectedPreset?.sample || '以 2025 年 5 月 4 日在杭州市西湖区拍摄的照片为例。' }}</p>
          <p class="flex items-start gap-2"><FolderTree class="mt-0.5 h-4 w-4 shrink-0 text-primary-500" aria-hidden="true" />
            <code class="break-all">{{ exampleTarget }}</code>
          </p>
          <p class="ts-muted">{{ actionExplanation }}</p>
        </div>
        <el-alert v-if="config.action === 'move'" title="移动会改变实际文件位置，外部软件依赖的原路径可能失效。执行前请检查真实预览。" type="warning" :closable="false" />
      </template>
      <el-form-item v-else label="相册名前缀"><el-input v-model="config.album_prefix" maxlength="40" placeholder="例如：旅行 · " class="max-w-md" /></el-form-item>
    </el-form>
    <DirectoryPickerDialog v-model:visible="targetPicker" v-model="config.target" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, FolderTree } from 'lucide-vue-next'
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
type OrganizePreset = { id: string; label: string; parts: string[]; rules: OrganizeRule[]; sample?: string }
const quickPresets: OrganizePreset[] = [
  { id: 'month', label: '按年月', parts: ['2025', '05'], rules: [rule('time', 'month')] },
  { id: 'city', label: '按城市', parts: ['杭州市'], rules: [rule('location', 'city')] },
  { id: 'year-city', label: '按年份和城市', parts: ['2025', '杭州市'], rules: [rule('time', 'year'), rule('location', 'city')] },
]
const folderPresets: OrganizePreset[] = [
  ...quickPresets,
  { id: 'year', label: '按年份', parts: ['2025'], rules: [rule('time', 'year')] },
  { id: 'day', label: '按年月日', parts: ['2025', '05', '04'], rules: [rule('time', 'day')] },
  { id: 'country-province-city', label: '按国家、省份和城市', parts: ['中国', '浙江省', '杭州市'],
    rules: [rule('location', 'country_province_city')] },
  { id: 'city-district', label: '按城市和区县', parts: ['杭州市', '西湖区'], rules: [rule('location', 'city_district')] },
  { id: 'person', label: '按人物', parts: ['小林'], rules: [rule('person', 'month')],
    sample: '以只识别到一位已命名人物「小林」的照片为例。没有已命名人物或匹配多个人物的照片会跳过。' },
  { id: 'category', label: '按类别', parts: ['旅行'], rules: [rule('category', 'month')],
    sample: '以只有一个类别「旅行」的照片为例。没有类别或匹配多个类别的照片会跳过。' },
]
function rule(strategy: OrganizeRule['strategy'], granularity: string): OrganizeRule {
  return { strategy, granularity, nested: true, groups: null }
}
const availablePresets = computed(() => config.value.kind === 'organize' ? folderPresets : quickPresets)
const selectedPreset = computed(() => availablePresets.value.find(p => JSON.stringify(p.rules) === JSON.stringify(config.value.rules)))
const currentPreset = computed(() => selectedPreset.value?.id)
const exampleTarget = computed(() => {
  const preset = selectedPreset.value
  if (!preset) return ''
  const target = config.value.target || '目标文件夹'
  const separator = target.includes('\\') && !target.includes('/') ? '\\' : '/'
  return [target.replace(/[\\/]+$/, ''), ...preset.parts, 'IMG_0001.jpg'].join(separator)
})
const actionExplanation = computed(() => {
  if (config.value.action === 'copy') return '原文件保留在原目录，目标目录会有一份副本。'
  if (config.value.action === 'move') return '原文件会移到目标目录，文件路径会改变。'
  return '可选择复制并保留原文件，或移动原文件。'
})
const applyPreset = (id: string) => {
  const preset = availablePresets.value.find(item => item.id === id)
  if (preset) config.value.rules = preset.rules.map(item => ({ ...item }))
}
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
