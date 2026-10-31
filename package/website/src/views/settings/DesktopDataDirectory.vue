<template>
  <section class="ts-settings-page" :aria-busy="working">
    <SettingsPageHeader title="照片与数据位置" description="查看保存位置、备份图库，或找回旧版本的照片。" />
    <p v-if="!isTauriApp()" class="ts-surface ts-settings-panel">请在行影集桌面客户端中管理本机照片位置。</p>
    <template v-else>
      <div v-if="store.error" role="alert" class="ts-surface space-y-3 ts-settings-panel">
        <p class="break-words text-[var(--ts-color-danger)]">{{ store.error }}</p>
        <div class="flex flex-wrap gap-3">
          <button v-if="store.waitingForTasks" class="ts-button ts-button-primary" :disabled="working" @click="store.waitAndRestart()">继续等待，结束后重启恢复</button>
          <button v-else-if="store.needsRestart" class="ts-button ts-button-primary" :disabled="working" @click="restartNow">重启并恢复使用</button>
          <button v-else-if="!store.directory" class="ts-button ts-button-secondary" :disabled="working" @click="load">重新读取</button>
          <button class="ts-button ts-button-secondary" @click="openData">打开行影集文件夹</button>
        </div>
      </div>
      <p v-if="store.loading" role="status" class="ts-muted">{{ store.inspecting ? '正在检查照片和文件，大图库需要多等一会儿…' : '正在读取保存位置…' }}</p>
      <template v-if="store.directory">
        <div class="ts-surface ts-settings-panel space-y-4">
          <h3 class="font-medium">行影集文件夹</h3>
          <p class="ts-muted break-all text-sm" data-testid="desktop-location">{{ locationRoot }}</p>
          <p class="ts-muted text-sm">{{ portable && !detachedData ? '程序、相册、照片记录和设置保存在这个文件夹中。' : portable ? '这里是行影集的程序文件夹。' : '这里保存相册、照片记录和设置。' }}引用其他文件夹中的原照片时，仍需保留那些文件夹。</p>
          <p v-if="detachedData" role="status" class="ts-muted text-sm">此实例配置了独立的资料保存位置。移动上方文件夹不会搬走那些资料，请保持原磁盘和保存位置可用。</p>
          <p v-if="store.discovery?.externalReferencesRetained" role="status" class="text-sm text-[var(--ts-color-danger)]">导入时保留了外部原照片的位置引用。请保留原照片和原磁盘；如需可独立恢复的备份，请备份当前图库并勾选同时复制原照片。</p>
          <button class="ts-button ts-button-secondary" :disabled="busy" @click="openData"><FolderOpen class="h-4 w-4" />打开文件夹</button>
          <details class="text-sm">
            <summary class="cursor-pointer font-medium">搬到其他磁盘</summary>
            <div class="ts-muted mt-3 space-y-3">
              <ol v-if="portable" class="list-decimal space-y-2 pl-5">
                <li>点击下方“安全退出行影集”，等待窗口关闭。</li>
                <li>将上方整个行影集文件夹移动到新位置，请保留里面的所有文件。</li>
                <li>从新位置打开 TrailSnap.exe，确认照片正常后更新桌面快捷方式。原入口找不到图库时，按提示选择搬迁后的整个行影集文件夹。</li>
              </ol>
              <p v-if="portable">引用其他位置的原照片时，仍需保留那些文件夹和磁盘。</p>
              <template v-else>
                <label for="migration-target" class="block">新的空文件夹</label>
                <el-input id="migration-target" v-model="migrationPath" :disabled="busy" placeholder="输入完整目录路径" />
                <button class="ts-button ts-button-secondary" :disabled="busy || !migrationPath.trim()" @click="saveMigration">保存搬迁位置</button>
              </template>
              <button class="ts-button ts-button-secondary" :disabled="busy" @click="store.safeExit()">安全退出行影集</button>
            </div>
          </details>
        </div>
        <div v-if="store.directory.pendingRoot" class="ts-surface space-y-3 ts-settings-panel">
          <h3 class="font-medium">等待搬迁</h3>
          <p class="ts-muted break-all text-sm">{{ store.directory.pendingRoot }}</p>
          <p class="ts-muted text-sm">重启前会等待上传和后台任务结束；原目录保留。未完成的手机上传可在重启后重试。</p>
          <div class="flex flex-wrap gap-3">
            <button class="ts-button ts-button-primary" :disabled="busy" @click="migrate">安全重启并搬迁</button>
            <button class="ts-button ts-button-secondary" :disabled="busy" @click="store.save(null)">取消搬迁</button>
          </div>
        </div>
        <div v-if="store.directory.migrationError" role="alert" class="ts-surface ts-settings-panel">
          <p>上次搬迁未完成，仍使用原位置。</p><p class="ts-muted mt-2 break-words text-sm">{{ store.directory.migrationError }}</p>
        </div>
        <template v-if="store.directory.portableSupported">
          <div v-if="operation" class="ts-surface space-y-3 ts-settings-panel" role="status">
            <h3 class="font-medium">{{ operation.phase === 'completed' ? (operation.activate ? '旧照片已导入以下位置' : '上次备份已完成') : '上次复制尚未完成' }}</h3>
            <p class="ts-muted break-all text-sm">副本位置：{{ operation.target }}</p>
            <p v-if="operation.phase === 'completed' && !operation.activate" class="ts-muted text-sm">{{ operation.copyExternal ? '已包含已登记的外部原照片。建议打开副本核对后再清理原位置。' : '未额外复制外部原照片，副本可能仍依赖原磁盘，请勿将它当作那些原照片的备份。' }}</p>
            <template v-if="operation.phase === 'completed' && operation.activate">
              <p class="ts-muted text-sm">当前是导入前保留的图库，日常快捷方式默认打开导入后的图库。</p>
              <button class="ts-button ts-button-secondary" :disabled="busy" @click="switchImported">返回导入后的图库</button>
            </template>
            <template v-if="operation.phase !== 'completed'">
              <p class="ts-muted text-sm">原图库仍保留。若已复制完成，可重新验证并继续；否则清理本次临时文件后重新选择。已保存的完整副本不会被删除。</p>
              <p v-if="operation.error" class="ts-muted break-words text-sm">{{ operation.error }}</p>
              <div v-if="!store.needsRestart && !store.waitingForTasks" class="flex flex-wrap gap-3">
                <button v-if="store.discovery?.canResume" class="ts-button ts-button-primary" :disabled="busy" @click="store.recover(true)">重新验证并继续</button>
                <button class="ts-button" :class="store.discovery?.canResume ? 'ts-button-secondary' : 'ts-button-primary'" :disabled="busy" @click="cleanInterrupted">清理临时文件并重新选择</button>
              </div>
            </template>
          </div>
          <div v-if="!unfinished" class="ts-surface space-y-5 ts-settings-panel">
            <div class="flex flex-wrap gap-3" role="group" aria-label="管理图库">
              <button class="ts-button" :class="!importing ? 'ts-button-primary' : 'ts-button-secondary'" :aria-pressed="showCopyForm && !importing" :disabled="busy" @click="selectMode('current')">备份当前图库</button>
              <button class="ts-button" :class="importing ? 'ts-button-primary' : 'ts-button-secondary'" :aria-pressed="showCopyForm && importing" :disabled="busy" @click="selectMode('legacy')">找回旧版本照片</button>
            </div>
            <p v-if="!showCopyForm" class="ts-muted text-sm">照片和设置会保存在上方位置。建议定期将图库备份到另一块磁盘。</p>
            <template v-if="showCopyForm">
              <p class="ts-muted text-sm">{{ importing ? '将旧图库复制到新位置，确认可用后开始使用。原数据保留。当前图库的照片、票夹和设置不会合并，可在导入后切换回来。' : '创建程序、照片记录和设置的副本，默认一并复制外部原照片。完成后继续使用当前图库，副本不会自动同步。' }}</p>
              <p v-if="importing && store.discovery?.currentPhotos" role="status" class="text-sm">当前图库已有 {{ store.discovery.currentPhotos }} 张照片。导入后将打开旧照片的副本，当前照片仍在原处，两边不会自动合并。</p>
              <p v-if="store.discoveryError" role="alert" class="ts-muted break-words text-sm">旧位置自动检查失败：{{ store.discoveryError }}。可以手动选择旧目录。</p>
              <p v-for="notice in (importing ? store.discovery?.notices : [])" :key="notice" class="ts-muted break-words text-sm">{{ notice }}</p>
              <div class="space-y-3">
                <p class="text-sm font-medium">1. {{ importing ? '要找回的旧图库' : '要备份的图库' }}</p>
                <template v-if="importing">
                  <p v-if="legacySource" class="ts-muted break-all text-sm">{{ legacySource }}</p>
                  <details :open="!store.discovery?.candidates.length" class="text-sm">
                    <summary class="cursor-pointer font-medium">{{ store.discovery?.candidates.length ? '选择其他旧图库' : '选择旧图库的位置' }}</summary>
                    <div class="mt-3 space-y-3">
                  <div v-if="store.discovery?.candidates.length" class="flex flex-wrap gap-2">
                    <button v-for="candidate in store.discovery.candidates" :key="candidate.path" class="ts-button ts-button-secondary max-w-full text-left" :disabled="busy" @click="legacySource = candidate.path"><span class="min-w-0 break-all">{{ candidate.path }}{{ candidate.photos === null ? '（需检查）' : `（${candidate.photos} 张）` }}</span></button>
                  </div>
                  <label for="legacy-library-source" class="block ts-muted">包含 data 文件夹的旧数据目录</label>
                  <div class="flex flex-col gap-3 sm:flex-row">
                    <el-input id="legacy-library-source" v-model="legacySource" :disabled="busy" placeholder="选择旧版本的数据文件夹" />
                    <button class="ts-button ts-button-secondary" :disabled="busy" @click="choose('source')">选择文件夹</button>
                  </div>
                  <details class="ts-muted text-sm"><summary class="cursor-pointer">不知道选哪个文件夹？</summary><p class="mt-2">先退出旧版本。选择包含 data 文件夹的那一级，不要进入 data。通常在 C:\Users\你的用户名\AppData\Local\TrailSnap；以前改过保存位置时，请选择改后的目录。</p></details>
                    </div>
                  </details>
                </template>
                <p v-else class="ts-muted text-sm">当前行影集文件夹</p>
                <button v-if="!store.preview && !store.inspecting" class="ts-button ts-button-secondary" :disabled="busy || (importing && !legacySource.trim())" @click="inspectSource">重新检查图库</button>
              </div>
              <template v-if="store.preview">
                <p role="status" class="text-sm">找到 {{ store.preview.counts.photos }} 张照片。已检查，尚未复制。</p>
                <details v-if="store.preview.externalRoots.length || store.preview.unregisteredPhotos" class="space-y-2 text-sm">
                  <summary class="cursor-pointer font-medium">备份范围：{{ copyExternal ? '包含其他位置的原照片' : '不复制其他位置的原照片' }}</summary>
                  <el-checkbox v-model="copyExternal" :disabled="busy">同时备份其他文件夹中的原照片</el-checkbox>
                  <p class="ts-muted text-sm">建议保留勾选。取消后仅复制图库数据和库内文件，外部原照片仍依赖原磁盘，不能用于恢复那些原照片。</p>
                  <details class="ts-muted text-sm"><summary class="cursor-pointer">查看这些文件夹</summary><ul class="mt-2 space-y-2"><li v-for="root in store.preview.externalRoots" :key="`${root.ownerId}:${root.path}`" class="break-all">{{ root.path }}{{ root.available ? '' : '（磁盘未连接）' }}</li></ul></details>
                </details>
                <p v-if="store.preview.unregisteredPhotos" class="ts-muted text-sm">{{ store.preview.unregisteredPhotos }} 张照片的位置尚未登记，只能保留原位置引用；如需完整备份，请先在旧版中添加对应的外部照片目录。</p>
                <p v-if="externalBlocked" role="alert" class="text-sm text-[var(--ts-color-danger)]">部分原照片位置不可用或尚未登记。请连接磁盘后重新检查；如需仅保留原位置，请展开“备份范围”调整。</p>
                <div class="space-y-3">
                  <label for="portable-instance-target" class="block text-sm font-medium">2. {{ importing ? '将找回的照片保存到哪里' : '备份保存到哪里' }}</label>
                  <div class="flex flex-col gap-3 sm:flex-row">
                    <el-input id="portable-instance-target" v-model="target" :disabled="busy" placeholder="例如 D:\行影集-照片（新的空文件夹）" />
                    <button class="ts-button ts-button-secondary" :disabled="busy" @click="choose('target')">选择空文件夹</button>
                  </div>
                  <p class="ts-muted text-sm">请选择新的空文件夹，不要选择当前安装目录、旧数据目录或它们内部的文件夹。</p>
                  <p v-if="store.checkingSpace" role="status" class="ts-muted text-sm">正在自动检查保存位置和可用空间…</p>
                  <button v-else-if="target.trim() && !store.space" class="ts-button ts-button-secondary" :disabled="busy || externalBlocked" @click="store.inspectSpace(target.trim(), copyExternal)">重新检查保存位置</button>
                  <p v-if="store.space" role="status" class="text-sm">需要约 {{ size(store.space.requiredBytes) }}（含程序、所选原照片与备份余量），可用 {{ size(store.space.freeBytes) }}。{{ store.space.enough ? '空间充足。' : '空间不足，请换一个磁盘。' }}</p>
                  <p v-else class="ts-muted text-sm">选择保存位置后会自动检查空间。</p>
                </div>
                <p role="status" class="text-sm" :class="copyExternal ? '' : 'text-[var(--ts-color-danger)]'">{{ copyExternal ? '将复制图库及已登记的原照片；完成后仍请核对照片再清理原位置。' : '此副本仍可能依赖原照片所在磁盘，请勿删除原照片。' }}</p>
                <button class="ts-button ts-button-primary" :disabled="busy || !store.space?.enough || externalBlocked || !!store.directory.pendingRoot || !!unfinished" @click="convert">{{ importing ? '导入并使用这些照片' : '开始备份' }}</button>
                <p v-if="importing" class="ts-muted text-sm">完成后原快捷方式也会打开导入后的图库；手机需要重新连接、登录。当前图库和旧图库均保留。</p>
              </template>
              </template>
          </div>
        </template>
        <div v-if="store.converting" class="ts-surface space-y-3 ts-settings-panel" role="status" aria-live="polite">
          <p class="font-medium">{{ progressLabel }}</p>
          <template v-if="store.progress?.total"><progress class="w-full accent-[var(--theme-primary)]" :value="store.progress.completed" :max="store.progress.total" /><p class="ts-muted text-sm">{{ store.progress.completed }} / {{ store.progress.total }} 个文件</p></template>
          <p class="ts-muted text-sm">请保持窗口打开，不要拔出磁盘。原图库仍保留。</p>
        </div>
        <details class="ts-surface ts-settings-panel text-sm">
          <summary class="cursor-pointer font-medium">高级信息</summary>
          <div class="ts-muted mt-3 space-y-3">
            <p v-if="portable">搬迁上方的行影集文件夹时，请保留其中全部内容。</p>
            <p v-else>当前图库保存在系统用户的数据目录。需要搬迁时，请使用上方“搬到其他磁盘”。</p>
            <template v-if="store.discovery?.previousEntry">
              <p class="break-all">导入前的图库：{{ store.discovery.previousEntry }}。其中的照片、票夹和设置均保留，未与当前图库合并。</p>
              <button class="ts-button ts-button-secondary" :disabled="busy" @click="openPrevious">切换到导入前的图库</button>
            </template>
            <p v-if="store.directory.previousRoot" class="break-all">上次搬迁保留的目录：{{ store.directory.previousRoot }}。核对照片、缩略图和模型后再清理。</p>
          </div>
        </details>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import SettingsPageHeader from '@/components/ui/SettingsPageHeader.vue'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { ElMessageBox } from 'element-plus'
import { isTauriApp } from '@/config/server'
import { useDesktopDataDirectoryStore } from '@/stores/desktopDataDirectory'
import { openDesktopDataDirectory, openDesktopInstanceDirectory, prepareDesktopMigration, restartDesktop, openPreviousDesktopLibrary, openLinkedDesktopLibrary } from '@/api/desktopDataDirectory'
const store = useDesktopDataDirectoryStore()
const sourceMode = ref<'legacy' | 'current'>('current')
const showCopyForm = ref(false)
const importing = computed(() => sourceMode.value === 'legacy')
const legacySource = ref('')
const target = ref('')
const copyExternal = ref(true)
const choosing = ref(false)
const restarting = ref(false)
const migrationPath = ref('')
const portable = computed(() => store.directory?.mode === 'portable')
const locationRoot = computed(() => portable.value ? store.directory?.instanceRoot : store.directory?.root)
const detachedData = computed(() => {
  if (!portable.value || !store.directory?.instanceRoot) return false
  const normalize = (value: string) => value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  const root = normalize(store.directory.instanceRoot)
  const data = normalize(store.directory.root)
  return data !== root && !data.startsWith(`${root}/`)
})
const working = computed(() => store.loading || store.saving || store.converting || store.checkingSpace || choosing.value || restarting.value)
const busy = computed(() => working.value || store.needsRestart || store.waitingForTasks)
const operation = computed(() => store.discovery?.operation)
const unfinished = computed(() => operation.value && operation.value.phase !== 'completed')
const externalBlocked = computed(() => copyExternal.value && (!!store.preview?.unregisteredPhotos || !!store.preview?.externalRoots.some(root => !root.available)))
const progressLabels: Record<string, string> = { waiting: '等待上传与后台任务结束…', checking: '正在检查磁盘空间…', copying: '正在复制并校验图库…', external: '正在复制其他位置的原照片…', database: '正在转换图库数据…', program: '正在准备程序…', verifying: '正在核对照片…', launching: '正在验证新图库能否正常打开…' }
const progressLabel = computed(() => progressLabels[store.progress?.stage || 'waiting'] || '正在处理…')
let previewTimer: ReturnType<typeof setTimeout> | undefined
let spaceTimer: ReturnType<typeof setTimeout> | undefined
function inspectSource() { return store.inspectPortable(importing.value ? legacySource.value.trim() : undefined) }
function selectMode(mode: 'legacy' | 'current') { sourceMode.value = mode; showCopyForm.value = true }
watch([legacySource, sourceMode, showCopyForm], () => {
  clearTimeout(previewTimer)
  store.clearPreview()
  if (showCopyForm.value && !unfinished.value && !store.needsRestart && !store.waitingForTasks && (!importing.value || legacySource.value.trim())) {
    previewTimer = setTimeout(() => { void inspectSource() }, 400)
  }
})
watch([target, copyExternal, () => store.preview], () => {
  clearTimeout(spaceTimer)
  store.clearSpace()
  if (store.preview && target.value.trim() && !externalBlocked.value && !store.needsRestart && !store.waitingForTasks) {
    spaceTimer = setTimeout(() => { void store.inspectSpace(target.value.trim(), copyExternal.value) }, 400)
  }
})
onBeforeUnmount(() => { clearTimeout(previewTimer); clearTimeout(spaceTimer); store.clearPreview() })
function size(bytes: number) { return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(2)} GB` : `${Math.ceil(bytes / 1024 ** 2)} MB` }
async function load() {
  await store.load()
  await store.loadDiscovery()
  migrationPath.value = store.directory?.pendingRoot || ''
  if (!legacySource.value) legacySource.value = store.discovery?.candidates[0]?.path || ''
  if (!store.discovery?.completed && !store.discovery?.dismissed && (store.discovery?.candidates.length || store.discovery?.notices.length)) selectMode('legacy')
}
async function choose(kind: 'source' | 'target') {
  choosing.value = true
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: kind === 'source' ? '选择旧版本的数据文件夹' : '选择新的空文件夹' })
    if (typeof selected === 'string') { if (kind === 'source') legacySource.value = selected; else target.value = selected }
  } catch (cause) { store.error = String(cause) }
  finally { choosing.value = false }
}
async function convert() {
  if (!store.preview || !store.space?.enough) return
  const detail = `来源：${store.preview.source}\n照片：${store.preview.counts.photos} 张\n保存到：${target.value.trim()}\n所需空间：约 ${size(store.space.requiredBytes)}\n原照片：${copyExternal.value ? '一并复制' : '保留原位置引用，仍需原磁盘'}\n\n${importing.value ? '将打开导入后的图库，原快捷方式以后也会打开它。当前图库保留，两边不会自动合并。' : '将创建独立备份，完成后重启并继续使用当前图库。副本不会自动同步。'}\n期间请勿关闭应用或拔盘。`
  try { await ElMessageBox.confirm(h('div', { class: 'whitespace-pre-line break-words' }, detail), importing.value ? '确认导入旧照片' : '确认备份图库', { confirmButtonText: '开始复制', cancelButtonText: '取消' }) }
  catch { return }
  await store.convert(target.value.trim(), copyExternal.value, importing.value ? legacySource.value.trim() : undefined, importing.value)
}
async function cleanInterrupted() {
  try { await ElMessageBox.confirm('只清理本次复制未发布的临时文件。已保存的完整副本和原图库都会保留；重新复制需另选空文件夹。', '清理未完成的复制', { confirmButtonText: '清理临时文件', cancelButtonText: '取消' }) }
  catch { return }
  await store.recover(false)
}
async function restartNow() { try { await restartDesktop() } catch (cause) { store.handleStoppedOperation(cause) } }
async function openData() { try { await (portable.value ? openDesktopInstanceDirectory() : openDesktopDataDirectory()) } catch (cause) { store.error = String(cause) } }
async function switchImported() {
  restarting.value = true
  try { await openLinkedDesktopLibrary() }
  catch (cause) { store.handleStoppedOperation(cause); restarting.value = false }
}
async function openPrevious() {
  try { await ElMessageBox.confirm('将安全退出当前图库，打开导入前的照片。以后原快捷方式仍默认打开导入后的图库，两边不会自动同步。', '切换图库', { confirmButtonText: '切换图库', cancelButtonText: '取消' }) }
  catch { return }
  restarting.value = true
  try { await openPreviousDesktopLibrary() }
  catch (cause) { store.handleStoppedOperation(cause); restarting.value = false }
}
async function saveMigration() { await store.save(migrationPath.value.trim()) }
async function migrate() {
  try { await ElMessageBox.confirm('等待上传和后台任务结束后重启并复制，原目录保留。', '搬迁图库', { confirmButtonText: '重启并搬迁', cancelButtonText: '取消' }) }
  catch { return }
  restarting.value = true
  try { await prepareDesktopMigration(); await restartDesktop() }
  catch (cause) { store.handleStoppedOperation(cause); restarting.value = false }
}
onMounted(() => { if (isTauriApp()) void load() })
</script>
