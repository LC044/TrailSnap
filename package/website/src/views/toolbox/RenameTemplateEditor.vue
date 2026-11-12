<template>
  <section class="space-y-5">
    <h2 class="ts-section-title">怎样命名？</h2>
    <div class="flex flex-wrap gap-2">
      <button v-for="preset in builtins" :key="preset.name" type="button" class="ts-button ts-button-secondary"
        :class="{ 'preset-selected': config.template === preset.template }" :aria-pressed="config.template === preset.template"
        @click="config.template = preset.template"><Check v-if="config.template === preset.template" class="h-4 w-4 shrink-0" aria-hidden="true" />{{ preset.name }}</button>
    </div>
    <div class="rounded-xl bg-[var(--ts-color-surface-muted)] p-4">
      <p class="ts-muted text-xs">命名示例 · 最终以真实预览为准</p>
      <p class="mt-2 break-all text-sm">{{ templateError ? '选择命名方式或展开自定义命名' : exampleName }}</p>
    </div>
    <details :open="!builtins.some(p => p.template === config.template)">
      <summary class="cursor-pointer py-3 text-sm font-semibold">自定义命名</summary>
    <el-form label-position="top">
      <el-form-item label="命名模板">
        <el-input ref="input" v-model="config.template" maxlength="240" placeholder="IMG_{date}_{time}"
          @keyup="rememberCursor" @click="rememberCursor" @blur="rememberCursor" />
        <p v-if="templateError" role="alert" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ templateError }}</p>
      </el-form-item>
      <div class="flex flex-wrap gap-2">
        <button v-for="variable in variables" :key="variable.value" type="button" class="ts-button ts-button-secondary"
          :aria-label="`在光标处插入${variable.label}`" @mousedown.prevent @click="insert(variable.value)">{{ variable.label }}</button>
      </div>
      <details class="mt-4">
        <summary class="cursor-pointer text-sm font-semibold">更多变量与编号设置</summary>
        <div class="mt-3 flex flex-wrap gap-2">
          <button v-for="variable in moreVariables" :key="variable.value" type="button" class="ts-button ts-button-secondary"
            @mousedown.prevent @click="insert(variable.value)">{{ variable.label }}</button>
        </div>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <el-form-item label="编号起点"><el-input-number v-model="config.start_index" :min="1" :max="1000000" /></el-form-item>
          <el-form-item label="排序"><el-select v-model="config.descending" class="w-full"><el-option label="拍摄时间从早到晚（默认）" :value="false" /><el-option label="拍摄时间从晚到早" :value="true" /></el-select></el-form-item>
        </div>
        <el-checkbox v-model="config.reset_index">每个文件夹重新编号</el-checkbox>
      </details>
      <el-form-item label="缺少命名信息" class="mt-5">
        <el-select v-model="config.missing" class="w-full max-w-md">
          <el-option label="跳过缺少日期、地点或设备的影像" value="skip" />
          <el-option label="地点或设备使用未知占位词；缺少时间仍跳过" value="placeholder" />
          <el-option label="缺少拍摄时间时使用上传时间，其他信息使用占位词" value="upload" />
        </el-select>
      </el-form-item>
    </el-form>
    </details>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Check } from 'lucide-vue-next'
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
let start = 0, end = 0
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

<style scoped>
.preset-selected { border-color: var(--theme-primary); background: rgba(var(--theme-rgb), .12); color: var(--theme-primary); }
.preset-selected:hover { background: rgba(var(--theme-rgb), .18); }
</style>
