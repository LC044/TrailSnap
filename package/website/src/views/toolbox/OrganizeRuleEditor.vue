<template>
  <div class="space-y-5">
    <h2 class="ts-section-title">怎样整理？</h2>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="常用整理方案">
      <button v-for="preset in quickPresets" :key="preset.id" type="button" class="ts-button ts-button-secondary"
        :aria-pressed="currentPreset === preset.id" :class="{ 'preset-selected': currentPreset === preset.id }" @click="applyPreset(preset.id)"><Check v-if="currentPreset === preset.id" class="h-4 w-4 shrink-0" aria-hidden="true" />{{ preset.label }}</button>
      <button type="button" class="ts-button ts-button-secondary" :aria-expanded="customRules" @click="customRules = !customRules">自定义</button>
    </div>
    <p class="ts-muted text-sm">{{ ruleSummary }}<span v-if="currentPreset"> · 示例：{{ currentPreset === 'month' ? '2026/11' : currentPreset === 'city' ? '杭州市' : '2026/杭州市' }}</span></p>
    <div v-if="customRules || !currentPreset" class="space-y-4">
      <el-button :disabled="config.rules.length >= 3" @click="addRule"><Plus class="mr-1 h-4 w-4" />增加一级</el-button>
    <div v-for="(rule, index) in config.rules" :key="index" class="ts-divider space-y-3 rounded-2xl border p-4">
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold">第 {{ index + 1 }} 级</span>
        <button v-if="config.rules.length > 1" type="button" class="ts-icon-button" :aria-label="`删除第 ${index + 1} 级`" @click="config.rules.splice(index, 1)"><X class="h-4 w-4" /></button>
      </div>
      <el-form label-position="top">
        <el-form-item label="按什么归类">
          <el-select :model-value="rule.strategy" class="w-full max-w-md" @update:model-value="changeStrategy(index, $event)">
            <el-option label="日期" value="time" /><el-option label="地点" value="location" />
            <el-option label="人物" value="person" /><el-option label="智能分类" value="category" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="['time', 'location'].includes(rule.strategy)" label="细分到">
          <el-select v-model="rule.granularity" class="w-full max-w-md">
            <template v-if="rule.strategy === 'time'"><el-option label="年份" value="year" /><el-option label="年月" value="month" /><el-option label="年月日" value="day" /></template>
            <template v-else><el-option v-for="option in locationOptions" :key="option.value" :label="option.label" :value="option.value" /></template>
          </el-select>
        </el-form-item>
        <el-checkbox v-if="['time', 'location'].includes(rule.strategy)" v-model="rule.nested">使用嵌套层级（如 2026/05 或 省/市）</el-checkbox>
        <div v-if="rule.strategy !== 'time'" class="mt-3 space-y-2">
          <el-checkbox :model-value="rule.groups === null" @update:model-value="rule.groups = $event ? null : []; $event || loadOptions(index)">使用范围内全部分组</el-checkbox>
          <el-select v-if="rule.groups !== null" v-model="rule.groups" multiple filterable :loading="loading[index]"
            placeholder="至少明确选择一个分组" class="w-full" @visible-change="value => value && loadOptions(index)">
            <el-option v-for="option in options[index] || []" :key="option.id" :label="`${option.name} · ${option.count} 项`" :value="option.id" />
          </el-select>
          <p v-if="errors[index]" class="text-sm text-red-600 dark:text-red-400" role="alert">{{ errors[index] }} <el-button link @click="loadOptions(index)">重试</el-button></p>
        </div>
      </el-form>
    </div>
    </div>
    <el-form label-position="top">
      <template v-if="config.kind === 'organize'">
        <el-form-item label="目标目录">
          <div class="flex w-full flex-wrap gap-2">
            <el-input v-model="config.target" readonly placeholder="选择已配置存储中的目标目录" class="min-w-0 flex-1" />
            <el-button @click="targetPicker = true">选择目录</el-button>
          </div>
        </el-form-item>
        <el-form-item label="原文件如何处理（请明确选择）">
          <el-radio-group v-model="config.action">
            <el-radio value="copy">复制，保留原文件</el-radio><el-radio value="move">移动，改变原文件位置</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-alert v-if="config.action === 'move'" title="移动会改变实际文件位置，外部软件依赖的原路径可能失效。执行前请检查真实预览。" type="warning" :closable="false" />
      </template>
      <el-form-item v-else label="相册名前缀（可选）"><el-input v-model="config.album_prefix" maxlength="40" placeholder="例如：旅行 · " class="max-w-md" /></el-form-item>
      <details class="mt-4">
        <summary class="cursor-pointer py-3 text-sm">高级设置 · {{ advancedSummary }}</summary>
        <el-form-item v-if="config.kind === 'organize'" label="怎样生成目录">
          <el-select v-model="config.layout" class="w-full">
            <el-option label="重新归档：仅按新规则生成目录" value="rebuild" />
            <el-option label="保留原文件夹层级，再继续细分" value="preserve" :disabled="scope.source !== 'folders' || scope.folders.length !== 1" />
          </el-select>
          <p class="ts-muted mt-2 text-xs">{{ config.layout === 'preserve' ? '保留相对于所选源文件夹的月/日等目录，再追加新分组。目标选源文件夹即可在原位置细分。' : '原有月份/日期目录不会自动保留在新结构中。' }}</p>
        </el-form-item>
      <el-form-item class="mt-4" label="缺少归档信息">
        <el-select v-model="config.missing" class="w-full max-w-md"><el-option label="跳过并在预览中说明" value="skip" /><el-option label="归入未知信息分组" value="placeholder" /><el-option label="缺少拍摄时间时使用上传时间，其他缺失跳过" value="upload" /></el-select>
      </el-form-item>
      <el-form-item label="同一影像匹配多人或多类别">
        <el-select v-model="config.multi_group" class="w-full max-w-md">
          <el-option label="跳过有歧义的影像" value="skip" /><el-option label="按名称稳定排序，归入第一个匹配分组" value="first" />
          <el-option label="每个匹配分组各生成一份" value="all" :disabled="config.kind === 'organize' && config.action !== 'copy'" />
        </el-select>
      </el-form-item>
      </details>
    </el-form>
    <DirectoryPickerDialog v-model:visible="targetPicker" v-model="config.target" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Plus, X } from 'lucide-vue-next'
import { workflowApi, type MediaScope, type ToolConfig, type OrganizeRule } from '@/api/toolboxWorkflows'
import DirectoryPickerDialog from '@/components/DirectoryPickerDialog.vue'
const props = defineProps<{ scope: MediaScope }>()
const config = defineModel<ToolConfig>({ required: true })
const customRules = ref(false)
const quickPresets = [{ id: 'month', label: '按年月' }, { id: 'city', label: '按城市' }, { id: 'year-city', label: '按年份和城市' }]
const presetRules = (id: string): OrganizeRule[] => id === 'month'
  ? [{ strategy: 'time', granularity: 'month', nested: true, groups: null }]
  : id === 'city' ? [{ strategy: 'location', granularity: 'city', nested: true, groups: null }]
  : [{ strategy: 'time', granularity: 'year', nested: true, groups: null }, { strategy: 'location', granularity: 'city', nested: true, groups: null }]
const currentPreset = computed(() => quickPresets.find(p => JSON.stringify(presetRules(p.id)) === JSON.stringify(config.value.rules))?.id)
const ruleSummary = computed(() => config.value.rules.map(r => `${({ time: '日期', location: '地点', person: '人物', category: '分类' })[r.strategy]} · ${({ year: '年份', month: '年月', day: '年月日', city: '城市', province: '省份', district: '区县', province_city: '省 / 市', city_district: '市 / 区县', province_city_district: '省 / 市 / 区县' } as Record<string, string>)[r.granularity] || '分组'}${r.groups !== null ? '（指定分组）' : ''}${!r.nested ? '（平铺）' : ''}`).join(' → '))
const advancedSummary = computed(() => [config.value.layout === 'preserve' ? '保留原层级' : '按新规则生成目录',
  config.value.missing === 'skip' ? '缺失信息跳过' : config.value.missing === 'upload' ? '使用上传时间' : '归入未知分组',
  config.value.multi_group === 'skip' ? '' : config.value.multi_group === 'all' ? '多分组各生成一份' : '采用首个分组'].filter(Boolean).join(' · '))
const applyPreset = (id: string) => { config.value.rules = presetRules(id); customRules.value = false; revision++; options.value = {}; errors.value = {} }
const locationOptions = [
  { label: '省份', value: 'province' }, { label: '城市', value: 'city' }, { label: '区县', value: 'district' },
  { label: '省 / 市', value: 'province_city' }, { label: '市 / 区县', value: 'city_district' }, { label: '省 / 市 / 区县', value: 'province_city_district' },
]
const targetPicker = ref(false)
const options = ref<Record<number, { id: string; name: string; count: number }[]>>({})
const loading = ref<Record<number, boolean>>({})
const errors = ref<Record<number, string>>({})
let revision = 0
watch(() => props.scope, () => { revision++; options.value = {}; errors.value = {} }, { deep: true })
const addRule = () => config.value.rules.push({ strategy: 'location', granularity: 'city', nested: true, groups: null })
const changeStrategy = (index: number, strategy: OrganizeRule['strategy']) => {
  config.value.rules[index] = { strategy, granularity: strategy === 'time' ? 'year' : 'city', nested: true, groups: null }
  options.value[index] = []
}
const loadOptions = async (index: number) => {
  const version = revision
  const rule = config.value.rules[index]
  const key = JSON.stringify(rule)
  loading.value[index] = true
  errors.value[index] = ''
  try {
    const rows = await workflowApi.options(props.scope, { ...rule, groups: null })
    if (version === revision && key === JSON.stringify(config.value.rules[index])) options.value[index] = rows
  } catch { errors.value[index] = '范围内分组加载失败' }
  finally { loading.value[index] = false }
}
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
