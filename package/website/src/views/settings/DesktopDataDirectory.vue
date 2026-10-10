<template>
  <section class="space-y-6" :aria-busy="store.loading || store.saving">
    <header>
      <h2 class="text-xl font-semibold md:text-2xl">数据目录</h2>
      <p class="ts-muted mt-2 text-sm">选择数据库、缩略图、上传照片、AI 扩展包及模型的存放位置。</p>
    </header>
    <div v-if="!isTauriApp()" class="ts-surface p-5">请在行影集桌面客户端中修改数据目录。</div>
    <template v-else>
      <div v-if="store.error" role="alert" class="ts-surface space-y-3 p-5">
        <p class="text-[var(--ts-color-danger)]">{{ store.error }}</p>
        <button v-if="!store.directory" class="ts-button ts-button-secondary" :disabled="store.loading" @click="load">重试</button>
      </div>
      <p v-if="store.loading" role="status" class="ts-muted">正在读取数据目录…</p>
      <template v-if="store.directory">
        <div v-if="store.directory.migrationError" role="alert" class="ts-surface space-y-2 p-5">
          <p class="font-medium">上次迁移未完成，已继续使用原目录</p>
          <p class="ts-muted break-words text-sm">{{ store.directory.migrationError }}</p>
        </div>
        <div class="ts-surface space-y-5 p-5 md:p-6">
          <div>
            <h3 class="text-sm font-medium">当前目录</h3>
            <p class="ts-muted mt-2 break-all text-sm">{{ store.directory.root }}</p>
          </div>
          <div>
            <label for="desktop-data-directory" class="text-sm font-medium">新目录</label>
            <div class="mt-2 flex flex-col gap-3 sm:flex-row">
              <el-input id="desktop-data-directory" v-model="path" class="min-w-0 flex-1" placeholder="输入完整路径，或选择空文件夹" :disabled="busy" />
              <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="chooseDirectory">
                <FolderOpen class="h-4 w-4" />选择文件夹
              </button>
            </div>
            <p class="ts-muted mt-2 text-sm">请选择空文件夹并预留足够空间。外部图库中的原始照片仍保留在原位置。</p>
          </div>
          <p class="ts-muted text-sm">保存后重启生效。启动时会复制现有数据并修正文件路径；数据较多时需要等待，请勿中途关闭。原目录保留为备份，确认迁移成功后可自行清理。</p>
          <div class="flex flex-wrap gap-3">
            <button type="button" class="ts-button ts-button-primary" :disabled="busy || !path.trim()" @click="save">
              {{ store.saving ? '正在保存…' : '保存迁移设置' }}
            </button>
          </div>
        </div>
        <div v-if="store.directory.pendingRoot" class="ts-surface space-y-4 p-5" role="status">
          <div>
            <h3 class="font-medium">下次启动时迁移到</h3>
            <p class="ts-muted mt-2 break-all text-sm">{{ store.directory.pendingRoot }}</p>
          </div>
          <p class="ts-muted text-sm">重启会中断当前任务和下载，建议等待它们完成后再重启。</p>
          <div class="flex flex-wrap gap-3">
            <button type="button" class="ts-button ts-button-primary" :disabled="busy" @click="restart">立即重启并迁移</button>
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
import { computed, onMounted, ref } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isTauriApp } from '@/config/server'
import { useDesktopDataDirectoryStore } from '@/stores/desktopDataDirectory'

const store = useDesktopDataDirectoryStore()
const path = ref('')
const choosing = ref(false)
const restarting = ref(false)
const busy = computed(() => store.loading || store.saving || choosing.value || restarting.value)

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
  if (await store.save(path.value.trim())) ElMessage.success('已保存，下次启动时迁移数据')
}
async function cancel() {
  if (await store.save(null)) path.value = ''
}
async function restart() {
  try {
    await ElMessageBox.confirm('重启将中断正在运行的任务和下载，并开始迁移数据。是否继续？', '重启并迁移', {
      confirmButtonText: '重启并迁移', cancelButtonText: '稍后重启', type: 'warning',
    })
  } catch {
    return
  }
  restarting.value = true
  try {
    const { relaunch } = await import('@tauri-apps/plugin-process')
    await relaunch()
  } catch (cause) {
    store.error = String(cause)
    restarting.value = false
  }
}
onMounted(() => { if (isTauriApp()) void load() })
</script>
