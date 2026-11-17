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
      <el-select :model-value="null" placeholder="插入日期、地点或编号" class="w-full" @update:model-value="insert">
        <el-option v-for="variable in [...variables, ...moreVariables]" :key="variable.value" :value="variable.value" :label="variable.label" />
      </el-select>
      <details class="mt-4">
        <summary class="cursor-pointer py-3 text-sm">更多设置</summary>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <el-form-item label="编号起点"><el-input-number v-model="config.start_index" :min="1" :max="1000000" /></el-form-item>
          <el-form-item label="排序"><el-select v-model="config.descending" class="w-full"><el-option label="从早到晚" :value="false" /><el-option label="从晚到早" :value="true" /></el-select></el-form-item>
        </div>
        <el-checkbox v-model="config.reset_index">每个文件夹重新编号</el-checkbox>
      <el-form-item label="信息缺失时" class="mt-5">
        <el-select v-model="config.missing" class="w-full max-w-md">
          <el-option label="跳过照片" value="skip" />
          <el-option label="地点和设备填“未知”" value="placeholder" />
          <el-option label="使用上传时间，其他填“未知”" value="upload" />
        </el-select>
      </el-form-item>
      </details>
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
  { name: '标准日期时间', template: 'IMG_{date}_{time}' },
  { name: '紧凑日期时间', template: 'IMG_{year}{month}{day}_{time}' },
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
  { label: '日期', value: 'date' }, { label: '时间', value: 'time' }, { label: '城市', value: 'city' },
  { label: '原名', value: 'original' }, { label: '三位序号', value: 'sequence3' }, { label: '四位序号', value: 'sequence4' },
]
const moreVariables = [
  { label: '年', value: 'year' }, { label: '月', value: 'month' }, { label: '日', value: 'day' },
  { label: '时', value: 'hour' }, { label: '分', value: 'minute' }, { label: '秒', value: 'second' },
  { label: '省份', value: 'province' }, { label: '区县', value: 'district' }, { label: '详细地址', value: 'location' },
  { label: '相机', value: 'camera' }, { label: '镜头', value: 'lens' }, { label: 'ISO', value: 'iso' },
  { label: '不补零序号', value: 'index' }, { label: '扩展名文字', value: 'extension' },
]
const templateError = computed(() => renameTemplateError(config.value.template))
const exampleName = computed(() => {
  const index = String(config.value.start_index)
  const values: Record<string, string> = { date: '2025-05-04', time: '143905', year: '2025', month: '05', day: '04', hour: '14', minute: '39', second: '05', city: '杭州市', province: '浙江省', district: '西湖区', location: '浙江省杭州市西湖区', original: 'IMG_001', index, sequence3: index.padStart(3, '0'), sequence4: index.padStart(4, '0'), camera: '相机', lens: '镜头', iso: '100', extension: 'jpg' }
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
