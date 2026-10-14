<template>
  <section class="space-y-6" :aria-busy="store.loading || store.saving">
    <header>
      <h2 class="text-xl font-semibold md:text-2xl">数据目录</h2>
      <p class="ts-muted mt-2 text-sm">管理图库位置、复制独立实例，并在拔出移动硬盘前安全退出。</p>
    </header>
    <div v-if="!isTauriApp()" class="ts-surface p-5">请在行影集桌面客户端中修改数据目录。</div>
    <template v-else>
      <div v-if="store.error" role="alert" class="ts-surface space-y-3 p-5">
        <p class="text-[var(--ts-color-danger)]">{{ store.error }}</p>
        <button v-if="!store.directory" class="ts-button ts-button-secondary" :disabled="store.loading" @click="load">重试</button>
        <template v-else>
          <button class="ts-button ts-button-secondary" @click="restartAfterError">重启当前实例</button>
          <button class="ts-button ts-button-secondary" @click="openCurrentDirectory">打开数据与日志目录</button>
        </template>
      </div>
      <p v-if="store.loading" role="status" class="ts-muted">正在读取数据目录…</p>
      <template v-if="store.directory">
        <div class="ts-surface space-y-3 p-5 md:p-6">
          <h3 class="font-medium">{{ portable ? '独立本地实例' : '本地数据目录' }}</h3>
          <template v-if="portable">
            <p class="ts-muted break-all text-sm">{{ store.directory.instanceRoot }}</p>
            <p class="ts-muted text-sm">安装包与 ZIP 使用相同目录规则：入口旁的 instance.json 保存配置，数据默认位于当前文件夹的 userdata。安全退出后可整体移动，外部图库需要另行携带。</p>
            <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="openInstance">打开实例文件夹</button>
          </template>
          <p v-else class="ts-muted text-sm">当前配置位于程序目录。可将程序和数据复制为一个独立实例，原图库保持可用。</p>
          <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="store.safeExit()">{{ store.converting ? '正在等待上传和任务结束…' : '安全退出' }}</button>
        </div>
        <div v-if="store.directory.migrationError" role="alert" class="ts-surface space-y-2 p-5">
          <p class="font-medium">上次迁移未完成，已继续使用原目录</p>
          <p class="ts-muted break-words text-sm">{{ store.directory.migrationError }}</p>
        </div>
        <div class="ts-surface space-y-5 p-5 md:p-6">
          <div>
            <h3 class="text-sm font-medium">当前目录</h3>
            <p class="ts-muted mt-2 break-all text-sm">{{ store.directory.root }}</p>
            <button type="button" class="ts-button ts-button-secondary mt-3" :disabled="busy" @click="openCurrentDirectory">
              <FolderOpen class="h-4 w-4" />打开数据目录
            </button>
          </div>
          <div v-if="!portable">
            <label for="desktop-data-directory" class="text-sm font-medium">新目录</label>
            <div class="mt-2 flex flex-col gap-3 sm:flex-row">
              <el-input id="desktop-data-directory" v-model="path" class="min-w-0 flex-1" placeholder="输入完整路径，或选择空文件夹" :disabled="busy" />
              <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="chooseDirectory">
                <FolderOpen class="h-4 w-4" />选择文件夹
              </button>
            </div>
            <p class="ts-muted mt-2 text-sm">请选择空文件夹并预留足够空间。外部图库中的原始照片仍保留在原位置。</p>
          </div>
          <p v-if="!portable" class="ts-muted text-sm">保存后使用“安全重启并迁移”生效。启动时会复制现有数据并修正文件路径；数据较多时需要等待，请勿中途关闭。原目录保留为备份，确认迁移成功后可自行清理。</p>
          <div v-if="!portable" class="flex flex-wrap gap-3">
            <button type="button" class="ts-button ts-button-primary" :disabled="busy || !path.trim()" @click="save">
              {{ store.saving ? '正在保存…' : '保存迁移设置' }}
            </button>
          </div>
        </div>
        <div v-if="store.directory.portableSupported" class="ts-surface space-y-4 p-5 md:p-6">
          <h3 class="font-medium">复制图库或导入旧版本数据</h3>
          <p class="ts-muted text-sm">升级后需要旧图库时，请先完全退出旧版本，再选择包含 data/trailsnap.sqlite 的旧数据目录。程序只读取你明确选择的目录，原图库保持可用。</p>
          <label for="legacy-library-source" class="block text-sm font-medium">旧数据目录（留空则复制当前图库）</label>
          <div class="flex flex-col gap-3 sm:flex-row">
            <el-input id="legacy-library-source" v-model="legacySource" :disabled="busy" placeholder="选择旧数据目录" />
            <button class="ts-button ts-button-secondary" :disabled="busy" @click="chooseLegacySource">选择旧目录</button>
          </div>
          <p class="ts-muted text-sm">选择一个新的空文件夹。操作会等待后台任务结束，复制并校验数据，再从新实例启动；大图库需要较长时间。</p>
          <p v-if="portable" class="ts-muted text-sm">复制后原实例仍可继续使用。两个实例有独立身份和数据库，之后新增的照片不会自动同步。</p>
          <p class="ts-muted text-sm">复制会为新实例生成独立认证密钥；手机需重新登录。未复制的外部图库仍依赖原磁盘。</p>
          <button type="button" class="ts-button ts-button-secondary" :disabled="busy || !!store.directory.pendingRoot" @click="store.inspectPortable(legacySource.trim())">检查图库与外部引用</button>
          <template v-if="store.preview">
            <p class="ts-muted text-sm">{{ store.preview.counts.photos }} 张照片，当前目录约 {{ (store.preview.bytes / 1024 ** 3).toFixed(2) }} GB；需要额外预留程序、外部照片和数据库备份空间。</p>
            <p v-if="store.preview.unregisteredPhotos" role="status" class="ts-muted text-sm">{{ store.preview.unregisteredPhotos }} 张照片没有登记存储根。它们会保留原路径；创建完整便携副本前需补充外部图库目录。</p>
            <ul v-if="store.preview.externalRoots.length" class="ts-muted space-y-2 text-sm">
              <li v-for="root in store.preview.externalRoots" :key="`${root.ownerId}:${root.path}`" class="break-all">{{ root.path }}{{ root.available ? '' : '（磁盘不可用）' }}</li>
            </ul>
            <el-checkbox v-model="copyExternal" :disabled="busy">同时复制外部图库中的照片</el-checkbox>
            <label for="portable-instance-target" class="block text-sm font-medium">便携实例文件夹</label>
            <div class="flex flex-col gap-3 sm:flex-row">
              <el-input id="portable-instance-target" v-model="portableTarget" placeholder="选择移动硬盘中的空文件夹" :disabled="busy" />
              <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="choosePortableTarget">选择文件夹</button>
            </div>
            <button type="button" class="ts-button ts-button-primary" :disabled="busy || !portableTarget.trim() || !!store.directory.pendingRoot" @click="convertPortable">{{ store.converting ? '正在安全复制，请勿关闭或拔盘…' : portable ? '复制并打开独立实例' : '转换并打开便携实例' }}</button>
          </template>
        </div>
        <div v-if="store.directory.pendingRoot" class="ts-surface space-y-4 p-5" role="status">
          <div>
            <h3 class="font-medium">待迁移目录</h3>
            <p class="ts-muted mt-2 break-all text-sm">{{ store.directory.pendingRoot }}</p>
          </div>
          <p class="ts-muted text-sm">安全重启会停止接收新请求，等待已接收的上传、当前后台任务和下载完成，再迁移数据。尚未执行的任务将在重启后继续。等待期间请勿强制关闭应用。</p>
          <p class="ts-muted text-sm">未完成的分块上传可能提示失败；已保存的分块会随数据迁移，请在重启后重试上传或手机备份。</p>
          <div class="flex flex-wrap gap-3">
            <button type="button" class="ts-button ts-button-primary" :disabled="busy" @click="restart">{{ restarting ? '正在等待上传、任务和下载结束…' : '安全重启并迁移' }}</button>
            <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="cancel">取消迁移</button>
          </div>
        </div>
        <div v-if="store.directory.previousRoot" class="ts-surface space-y-2 p-5">
          <h3 class="text-sm font-medium">上次迁移保留的备份目录</h3>
          <p class="ts-muted break-all text-sm">{{ store.directory.previousRoot }}</p>
          <p class="ts-muted text-sm">确认照片、缩略图和模型正常后，可删除此备份以释放空间。</p>
        </div>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isTauriApp } from '@/config/server'
import { useDesktopDataDirectoryStore } from '@/stores/desktopDataDirectory'
import { openDesktopDataDirectory, openDesktopInstanceDirectory, prepareDesktopMigration, restartDesktop } from '@/api/desktopDataDirectory'

const store = useDesktopDataDirectoryStore()
const path = ref('')
const choosing = ref(false)
const restarting = ref(false)
const portableTarget = ref('')
const legacySource = ref('')
watch(legacySource, () => { store.preview = null })
const copyExternal = ref(false)
const portable = computed(() => store.directory?.mode === 'portable')
const busy = computed(() => store.loading || store.saving || store.converting || choosing.value || restarting.value)

async function openInstance() {
  try { await openDesktopInstanceDirectory() } catch (cause) { store.error = String(cause) }
}
async function restartAfterError() {
  try { await restartDesktop() } catch (cause) { store.error = String(cause) }
}
async function chooseLegacySource() {
  choosing.value = true
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择包含 data/trailsnap.sqlite 的旧数据目录' })
    if (typeof selected === 'string') legacySource.value = selected
  } catch (cause) { store.error = String(cause) }
  finally { choosing.value = false }
}
async function choosePortableTarget() {
  choosing.value = true
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择空文件夹存放便携实例' })
    if (typeof selected === 'string') portableTarget.value = selected
  } catch (cause) { store.error = String(cause) }
  finally { choosing.value = false }
}
async function convertPortable() {
  try {
    await ElMessageBox.confirm(portable.value ? '将安全停止当前实例，复制并校验图库后打开新实例。原实例保留并可独立继续使用，之后新增照片不会自动同步。期间不要关闭应用或拔盘。' : '将复制并校验图库，转换成功后打开新实例。请等待上传和后台任务结束，期间不要关闭应用或拔盘。原目录保留，可重新打开原客户端；之后新增照片不会自动同步。', portable.value ? '复制为独立实例' : '转换为便携实例', { confirmButtonText: '开始复制', cancelButtonText: '取消' })
  } catch { return }
  await store.convert(portableTarget.value.trim(), copyExternal.value, legacySource.value.trim())
}

async function load() {
  await store.load()
  path.value = store.directory?.pendingRoot || ''
}
async function chooseDirectory() {
  choosing.value = true
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择空文件夹作为数据目录' })
    if (typeof selected === 'string') path.value = selected
  } catch (cause) {
    store.error = String(cause)
  } finally {
    choosing.value = false
  }
}
async function save() {
  if (await store.save(path.value.trim())) ElMessage.success('已保存，请使用安全重启并迁移')
}
async function openCurrentDirectory() {
  try { await openDesktopDataDirectory() }
  catch (cause) { ElMessage.error(String(cause)) }
}
async function cancel() {
  if (await store.save(null)) path.value = ''
}
async function restart() {
  try {
    await ElMessageBox.confirm('将停止接收新请求，等待已接收的上传、当前任务和下载完成后重启。未执行的任务在迁移后继续，请勿强制关闭应用。', '安全重启并迁移', {
      confirmButtonText: '重启并迁移', cancelButtonText: '稍后重启', type: 'warning',
    })
  } catch {
    return
  }
  restarting.value = true
  try {
    await prepareDesktopMigration()
    await restartDesktop()
  } catch (cause) {
    store.error = String(cause)
    restarting.value = false
  }
}
onMounted(() => { if (isTauriApp()) void load() })
</script>
