<template>
  <section class="space-y-5">
    <label for="rename-style" class="block text-sm font-medium">命名方式</label>
    <div>
      <el-select id="rename-style" :model-value="selectedStyle" class="w-full" @update:model-value="chooseStyle">
        <el-option v-for="preset in builtins" :key="preset.template" :label="preset.name" :value="preset.template" />
        <el-option label="自定义" value="custom" />
      </el-select>
    </div>
    <div class="rounded-xl bg-[var(--ts-color-surface-muted)] p-4">
      <p class="ts-muted text-xs">示例</p>
      <p class="mt-2 break-all text-sm">{{ templateError ? '请填写有效的命名规则' : exampleName }}</p>
    </div>
    <div v-if="selectedStyle === 'custom'">
    <el-form label-position="top">
      <el-form-item label="文件名格式">
        <el-input ref="input" v-model="config.template" maxlength="240" placeholder="IMG_{date}_{time}"
          @keyup="rememberCursor" @click="rememberCursor" @blur="rememberCursor" />
        <p v-if="templateError" role="alert" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ templateError }}</p>
      </el-form-item>
      <el-select :model-value="null" aria-label="插入命名变量" placeholder="插入命名变量" class="w-full" @update:model-value="insert">
        <el-option v-for="variable in variables" :key="variable.value" :value="variable.value" :label="variable.label" />
      </el-select>
      <p v-if="includesMetadata" class="ts-muted mt-2 text-xs">
        多个人物或类别用「+」连接。{{ config.missing === 'skip' ? '缺少模板所需信息的照片会跳过。' : '' }}
      </p>
    </el-form>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { renameTemplateError, type ToolConfig } from '@/api/toolboxWorkflows'
import type { InputInstance } from 'element-plus'
const config = defineModel<ToolConfig>({ required: true })
const builtins = [
  { name: '日期时间', template: 'IMG_{date}_{time}' },
  { name: '日期与城市', template: '{date}_{city}_{sequence3}' },
  { name: '原名加日期', template: '{date}_{original}' },
  { name: '旅行编号', template: '旅行_{year}_{sequence4}' },
]
const customStyle = ref(false)
const selectedStyle = computed(() => !customStyle.value && builtins.some(p => p.template === config.value.template) ? config.value.template : 'custom')
const chooseStyle = (value: string) => {
  customStyle.value = value === 'custom'
  if (!customStyle.value) config.value.template = value
  start = config.value.template.length; end = start
}
const variables = [
  { label: '日期', value: 'date' }, { label: '时间', value: 'time' },
  { label: '国家', value: 'country' }, { label: '省份', value: 'province' },
  { label: '城市', value: 'city' }, { label: '区县', value: 'district' },
  { label: '人物', value: 'person' }, { label: '类别', value: 'category' },
  { label: '原名', value: 'original' }, { label: '编号', value: 'sequence3' },
]
const includesMetadata = computed(() => /\{(country|province|city|district|person|category)\}/.test(config.value.template))
const templateError = computed(() => renameTemplateError(config.value.template))
const exampleName = computed(() => {
  const index = String(config.value.start_index)
  const values: Record<string, string> = { date: '2025-05-04', time: '143905', year: '2025', month: '05', day: '04', hour: '14', minute: '39', second: '05', country: '中国', city: '杭州市', province: '浙江省', district: '西湖区', person: '小林+小雨', category: '旅行+风景', location: '浙江省杭州市西湖区', original: 'IMG_001', index, sequence3: index.padStart(3, '0'), sequence4: index.padStart(4, '0'), camera: '相机', lens: '镜头', iso: '100', extension: 'jpg' }
  return config.value.template.replace(/\{([^{}]+)\}/g, (_, key: string) => values[key] ?? `{${key}}`) + '.jpg'
})
const input = ref<InputInstance>()
let start = config.value.template.length, end = start
const rememberCursor = () => { start = input.value?.input?.selectionStart ?? config.value.template.length; end = input.value?.input?.selectionEnd ?? start }
const insert = async (key: string) => {
  const text = `{${key}}`
  config.value.template = config.value.template.slice(0, start) + text + config.value.template.slice(end)
  start += text.length; end = start
  await nextTick()
  input.value?.focus()
  input.value?.input?.setSelectionRange(start, end)
}
</script>
