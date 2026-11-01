<template>
  <div class="ts-settings-page">
    <SettingsPageHeader v-if="!embedded" title="备份设置" description="设置手机图库的备份范围和服务器目录结构。" />

    <section v-if="!supported" class="ts-surface ts-settings-panel">
      <p class="font-medium text-gray-800 dark:text-white">当前平台暂不支持图库备份设置</p>
      <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">请在 Android 原生 APP 中配置本地相册范围。</p>
    </section>

    <template v-else>
      <p role="status" class="px-1 text-xs" :class="autoSaveNoticeClass">{{ autoSaveNotice }}</p>

      <section class="space-y-4 overflow-hidden rounded-2xl bg-white px-4 py-1 shadow-sm dark:bg-gray-800">
        <div v-for="(item, index) in switchOptions" :key="item.key" class="flex items-center justify-between gap-4" :class="index > 0 && 'border-t border-gray-100 pt-5 dark:border-gray-700'">
          <div>
            <p class="text-sm font-medium text-gray-700 dark:text-gray-200">{{ item.title }}</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ item.description }}</p>
          </div>
          <el-switch v-model="form[item.key]" />
        </div>
      </section>

      <section class="ts-surface ts-settings-panel">
        <h2 class="font-medium text-gray-800 dark:text-white">服务器保存路径</h2>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">填写服务器照片目录下的相对路径，例如“手机备份”。</p>
        <el-input v-model="form.folder" class="mt-4" placeholder="手机备份" maxlength="120" />
      </section>

      <section class="ts-surface ts-settings-panel">
        <h2 class="font-medium text-gray-800 dark:text-white">目的地整理方式</h2>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <button
            v-for="option in organizeOptions"
            :key="option.value"
            type="button"
            class="rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            :class="form.organizeMode === option.value ? 'border-primary-500 bg-primary-50 dark:bg-gray-700' : 'border-gray-200 hover:border-primary-500 dark:border-gray-700'"
            @click="form.organizeMode = option.value"
          >
            <p class="text-sm font-medium text-gray-800 dark:text-white">{{ option.label }}</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ option.description }}</p>
            <p class="mt-3 truncate font-mono text-xs text-primary-600">{{ option.example }}</p>
          </button>
        </div>
      </section>

      <section class="ts-surface ts-settings-panel">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="font-medium text-gray-800 dark:text-white">备份源</h2>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">选择整个图库，或只备份指定的本地相册文件夹。</p>
          </div>
          <button type="button" class="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700 hover:border-primary-500 hover:text-primary-600 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" :disabled="loadingFolders" @click="loadFolders">
            {{ loadingFolders ? '正在读取…' : '刷新相册' }}
          </button>
        </div>

        <div class="mt-4 flex gap-3">
          <button type="button" class="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" :class="sourceMode === 'all' && 'border-primary-500 bg-primary-50 text-primary-600 dark:bg-gray-700'" @click="sourceMode = 'all'">全部图库</button>
          <button type="button" class="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" :class="sourceMode === 'selected' && 'border-primary-500 bg-primary-50 text-primary-600 dark:bg-gray-700'" @click="selectSpecific">指定相册</button>
        </div>

        <div v-if="sourceMode === 'selected'" class="mt-4">
          <el-input v-model="folderSearch" clearable placeholder="搜索相册或目录" />
          <div class="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>已选择 {{ form.sourcePaths.length }} 个目录</span>
            <span v-if="filteredFolders.length > visibleFolders.length">仅显示前 {{ visibleFolders.length }} 项，请搜索缩小范围</span>
          </div>
          <div v-if="folders.length" class="mt-3 max-h-80 divide-y divide-gray-100 overflow-y-auto rounded-xl border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
            <label v-for="folder in visibleFolders" :key="folder.path" class="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-900">
              <el-checkbox v-model="form.sourcePaths" :value="folder.path" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm text-gray-700 dark:text-gray-200">{{ folder.name }}</span>
                <span class="block truncate text-xs text-gray-500 dark:text-gray-400">{{ folder.path }}</span>
              </span>
              <span class="shrink-0 text-xs text-gray-400 dark:text-gray-500">{{ folder.count }} 项</span>
            </label>
          </div>
          <p v-else class="mt-3 rounded-lg bg-gray-50 p-4 text-sm text-gray-500 dark:bg-gray-900 dark:text-gray-400">点击“刷新相册”并授权图库访问后选择目录。</p>
        </div>
      </section>

      <div class="pb-2">
        <button type="button" class="text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2" :disabled="running" @click="rescan">重置当前范围的增量记录</button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { galleryBackupNative, type GallerySourceFolder } from '@/native/galleryBackup'
import { useGalleryBackup, type BackupOrganizeMode, type GalleryBackupSettings } from '@/composables/useGalleryBackup'

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const AUTO_SAVE_DELAY_MS = 800

const backup = useGalleryBackup()
const { supported, settings, running } = backup
const form = reactive<GalleryBackupSettings>({ ...settings.value, sourcePaths: [...settings.value.sourcePaths] })
const sourceMode = ref<'all' | 'selected'>(form.sourcePaths.length ? 'selected' : 'all')
const folders = ref<GallerySourceFolder[]>([])
const folderSearch = ref('')
const loadingFolders = ref(false)
const saveState = ref<'idle' | 'pending' | 'saved'>('idle')
let saveTimer: number | undefined
let savedSignature = ''
const switchOptions: Array<{ key: 'enabled' | 'wifiOnly' | 'includeVideos'; title: string; description: string }> = [
  { key: 'enabled', title: '启用自动备份', description: '启动 APP、回到前台时自动检查新增或修改过的媒体。' },
  { key: 'wifiOnly', title: '仅在 Wi-Fi / 不计费网络上传', description: '避免自动备份消耗移动流量。' },
  { key: 'includeVideos', title: '同时备份视频', description: '视频文件较大，默认关闭。更改此项会使用对应范围的独立增量记录。' },
]

const organizeOptions: Array<{ value: BackupOrganizeMode; label: string; description: string; example: string }> = [
  { value: 'year_month', label: '按年月整理', description: '根据拍摄时间自动建立年、月目录。', example: '手机备份/2026/08' },
  { value: 'flat', label: '平展所有内容', description: '所有媒体都保存到同一个目录。', example: '手机备份' },
  { value: 'preserve', label: '保留手机原目录', description: '在服务器上复刻手机相册目录结构。', example: '手机备份/DCIM/Camera' },
]
const filteredFolders = computed(() => {
  const keyword = folderSearch.value.trim().toLocaleLowerCase()
  return keyword ? folders.value.filter(folder => `${folder.name} ${folder.path}`.toLocaleLowerCase().includes(keyword)) : folders.value
})
const visibleFolders = computed(() => filteredFolders.value.slice(0, 100))

// 自动保存以「与最近一次落盘快照的签名比对」判定变更，程序化回填（初始化、settings 外部更新）不会再次触发保存。
const candidateSettings = computed<GalleryBackupSettings>(() => ({
  ...form,
  sourcePaths: sourceMode.value === 'all' ? [] : [...form.sourcePaths],
}))
const signatureOf = (value: GalleryBackupSettings) => JSON.stringify([
  value.enabled, value.wifiOnly, value.includeVideos, value.folder.trim(), value.organizeMode, [...value.sourcePaths].sort(),
])
const folderValid = computed(() => form.folder.trim() !== '' && !form.folder.split(/[\\/]/).some(part => part === '..'))
const sourceValid = computed(() => sourceMode.value === 'all' || form.sourcePaths.length > 0)
const autoSaveNotice = computed(() => {
  if (saveState.value === 'saved') return '已自动保存'
  if (saveState.value === 'pending') return '正在保存…'
  if (!folderValid.value) return '未保存：请输入有效的服务器相对路径'
  if (!sourceValid.value) return '未保存：请至少选择一个备份源相册'
  return '更改会自动保存'
})
const autoSaveNoticeClass = computed(() => {
  if (saveState.value === 'saved') return 'text-green-600 dark:text-green-400'
  if (!folderValid.value || !sourceValid.value) return 'text-amber-600 dark:text-amber-400'
  return 'text-gray-400 dark:text-gray-500'
})

const flushPendingSave = () => {
  if (saveTimer === undefined) return
  window.clearTimeout(saveTimer)
  saveTimer = undefined
  void saveNow()
}
const saveNow = async () => {
  const candidate = candidateSettings.value
  if (!candidate.folder.trim() || candidate.folder.split(/[\\/]/).some(part => part === '..')) {
    saveState.value = 'idle'
    return
  }
  if (sourceMode.value === 'selected' && !candidate.sourcePaths.length) {
    saveState.value = 'idle'
    return
  }
  const scopeBefore = JSON.stringify([settings.value.enabled, settings.value.includeVideos, [...settings.value.sourcePaths].sort()])
  saveState.value = 'pending'
  try {
    await backup.saveSettings(candidate)
    savedSignature = signatureOf(candidate)
    saveState.value = 'saved'
    const scopeAfter = JSON.stringify([candidate.enabled, candidate.includeVideos, [...candidate.sourcePaths].sort()])
    if (candidate.enabled && scopeBefore !== scopeAfter) void backup.runBackup()
  } catch {
    saveState.value = 'idle'
    ElMessage.error('备份设置保存失败')
  }
}
const onVisibilityChange = () => { if (document.visibilityState === 'hidden') flushPendingSave() }

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  await backup.initialize()
  Object.assign(form, settings.value, { sourcePaths: [...settings.value.sourcePaths] })
  sourceMode.value = form.sourcePaths.length ? 'selected' : 'all'
  savedSignature = signatureOf(settings.value)
})
watch(settings, value => {
  Object.assign(form, value, { sourcePaths: [...value.sourcePaths] })
  sourceMode.value = form.sourcePaths.length ? 'selected' : 'all'
  savedSignature = signatureOf(value)
})
watch(candidateSettings, candidate => {
  if (signatureOf(candidate) === savedSignature) return
  saveState.value = 'pending'
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => { saveTimer = undefined; void saveNow() }, AUTO_SAVE_DELAY_MS)
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  flushPendingSave()
})

const loadFolders = async () => {
  loadingFolders.value = true
  try {
    const permission = await galleryBackupNative.requestGalleryPermission()
    if (!permission.granted) {
      if (permission.galleryGranted && !permission.originalGranted) {
        throw new Error('请允许“照片和视频中的位置”权限，以便读取包含 GPS 的原图')
      }
      throw new Error('请允许行影集访问照片和视频')
    }
    folders.value = (await galleryBackupNative.listSourceFolders({ includeVideos: form.includeVideos })).folders
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  } finally {
    loadingFolders.value = false
  }
}
const selectSpecific = () => {
  sourceMode.value = 'selected'
  if (!folders.value.length) void loadFolders()
}
const rescan = async () => {
  try {
    await ElMessageBox.confirm('下次备份会重新扫描当前来源范围，服务端已有文件仍会自动去重。', '重置增量记录', { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' })
    await backup.resetCursor()
    ElMessage.success('增量记录已重置')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}
</script>
