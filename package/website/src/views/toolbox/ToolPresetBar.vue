<template>
  <section class="space-y-3">
    <details :open="!!chosen || !!loadError">
      <summary class="cursor-pointer py-3 text-sm">使用已有方案（可选）<span v-if="currentPreset"> · {{ currentPreset.name }}</span><span v-else-if="chosen === 'recent'"> · 上次使用</span></summary>
    <div class="flex flex-wrap items-center gap-2">
      <el-select v-model="chosen" clearable placeholder="选择保存的模板或整理方案" class="w-full sm:max-w-sm" @change="applyPreset">
        <el-option v-for="preset in visiblePresets" :key="preset.id" :value="preset.id"
          :label="preset.name + (store.preferences.default_rename_id === preset.id ? ' · 默认' : '')" />
        <el-option v-if="config.kind === 'rename' && recent" value="recent" label="上次使用的有效模板" />
      </el-select>
      <div class="relative">
        <button type="button" class="ts-icon-button" aria-label="模板管理" :aria-expanded="menu" @click="menu = !menu"><MoreHorizontal class="h-5 w-5" /></button>
        <AdaptiveMenu v-model="menu" title="模板管理" close-on-action>
          <button v-if="currentPreset && config.kind === 'rename'" type="button" class="ts-action-row" @click="setDefault"><Star class="h-[18px] w-[18px]" />设为默认</button>
          <button v-if="currentPreset" type="button" class="ts-action-row" @click="renameDialog"><Pencil class="h-[18px] w-[18px]" />重命名模板</button>
          <button type="button" class="ts-action-row" @click="exportPresets"><Download class="h-[18px] w-[18px]" />导出我的模板</button>
          <button type="button" class="ts-action-row" @click="importInput?.click()"><Upload class="h-[18px] w-[18px]" />导入模板</button>
          <button v-if="currentPreset" type="button" class="ts-action-row danger" @click="removePreset"><Trash2 class="h-[18px] w-[18px]" />删除所选模板</button>
        </AdaptiveMenu>
      </div>
      <input ref="importInput" type="file" accept="application/json,.json" class="hidden" @change="importPresets" />
    </div>
    <p v-if="loadError" class="text-sm text-red-600 dark:text-red-400" role="alert">{{ loadError }} <el-button link @click="load">重新载入</el-button></p>

    </details>
    <slot />
    <div class="ts-divider flex flex-wrap items-center justify-end gap-2 border-t pt-4">
      <el-button :disabled="store.busy || !!loadError" @click="openSave">保存为{{ config.kind === 'rename' ? '模板' : '方案' }}</el-button>
      <slot name="actions" />
    </div>
    <ResponsiveDialog v-model="saveDialog" :title="renameOnly ? '重命名模板' : '保存常用方案'">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="presetName" maxlength="30" show-word-limit placeholder="例如：旅行照片" /></el-form-item>
        <el-checkbox v-if="config.kind === 'rename' && !renameOnly" v-model="makeDefault">设为默认命名模板</el-checkbox>
      </el-form>
      <template #footer><div class="flex justify-end gap-2"><el-button @click="saveDialog = false">取消</el-button><el-button type="primary" :loading="store.busy" :disabled="!presetName.trim() || !!loadError" @click="saveNew">保存</el-button></div></template>
    </ResponsiveDialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { MoreHorizontal, Star, Pencil, Download, Upload, Trash2 } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue'
import { useToolboxStore } from '@/stores/toolbox'
import type { ToolConfig, ToolPreset } from '@/api/toolboxWorkflows'

const config = defineModel<ToolConfig>({ required: true })
const emit = defineEmits<{ ready: []; 'apply-default': [config: ToolConfig] }>()
const store = useToolboxStore()
const chosen = ref('')
const menu = ref(false)
const saveDialog = ref(false)
const presetName = ref('')
const renameOnly = ref(false)
const makeDefault = ref(false)
const loadError = ref('')
const visiblePresets = computed(() => store.preferences.presets.filter(p => p.config.kind === config.value.kind))
const currentPreset = computed(() => visiblePresets.value.find(p => p.id === chosen.value))
const recent = computed(() => store.preferences.recent.find(p => p.kind === 'rename'))
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const openSave = () => {
  renameOnly.value = false; makeDefault.value = false
  presetName.value = ''; saveDialog.value = true
}
const load = async () => {
  try {
    await store.load()
    loadError.value = ''
    if (config.value.kind === 'rename') {
      const preset = store.preferences.presets.find(p => p.id === store.preferences.default_rename_id)
      const initial = preset?.config || recent.value
      if (initial) { emit('apply-default', clone(initial)); chosen.value = preset?.id || 'recent' }
    }
    emit('ready')
  } catch { loadError.value = '模板加载失败，请重试后再保存，避免覆盖已有设置' }
}
onMounted(load)
const applyPreset = (id: string) => {
  const value = id === 'recent' ? recent.value : visiblePresets.value.find(p => p.id === id)?.config
  if (value) config.value = clone(value)
}
const persist = async (operation: () => Promise<unknown>) => {
  try { await operation(); ElMessage.success('模板已保存'); saveDialog.value = false; return true }
  catch { loadError.value = '保存失败或版本已变化，请重新载入后重试'; return false }
}
const saveNew = async () => {
  const value = clone(store.preferences)
  const name = presetName.value.trim()
  if (value.presets.some(p => p.name === name && p.id !== (renameOnly.value ? chosen.value : ''))) {
    ElMessage.warning('已有同名模板，请使用其他名称'); return
  }
  let savedId = chosen.value
  if (renameOnly.value && currentPreset.value) {
    value.presets = value.presets.map(p => p.id === chosen.value ? { ...p, name } : p)
  } else {
    const id = crypto.randomUUID()
    value.presets.push({ id, name, config: clone(config.value) })
    if (value.presets.length > 20) { ElMessage.warning('最多保存 20 套，请先删除不用的模板'); return }
    if (makeDefault.value) value.default_rename_id = id
    savedId = id
  }
  if (await persist(() => store.save(value))) { chosen.value = savedId; renameOnly.value = false }
}
const renameDialog = () => { presetName.value = currentPreset.value?.name || ''; renameOnly.value = true; saveDialog.value = true }
const setDefault = () => persist(() => store.save({ ...clone(store.preferences), default_rename_id: chosen.value }))
const removePreset = async () => {
  try { await ElMessageBox.confirm('删除保存的模板？当前编辑内容仍会保留。', '删除模板', { type: 'warning' }) }
  catch { return }
  const value = clone(store.preferences)
  value.presets = value.presets.filter(p => p.id !== chosen.value)
  if (value.default_rename_id === chosen.value) value.default_rename_id = null
  await persist(() => store.save(value))
  chosen.value = ''
}
const exportPresets = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify({ schema: 1, presets: store.preferences.presets }, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'trailsnap-toolbox-templates.json'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const importInput = ref<HTMLInputElement>()
const importPresets = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    if (file.size > 100000) throw new Error()
    const parsed = JSON.parse(await file.text()) as { schema: number; presets: ToolPreset[] }
    if (parsed.schema !== 1 || !Array.isArray(parsed.presets)) throw new Error()
    const value = clone(store.preferences)
    for (const preset of parsed.presets) {
      if (!preset.name || !preset.config || value.presets.some(p => p.name === preset.name)) throw new Error()
      value.presets.push({ id: crypto.randomUUID(), name: preset.name, config: preset.config })
    }
    if (value.presets.length > 20) throw new Error()
    await store.save(value)
    ElMessage.success('模板已导入')
  } catch { ElMessage.error('导入失败：请检查格式、重名和 20 套数量限制') }
  finally { input.value = '' }
}
</script>
