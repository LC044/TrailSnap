<template>
  <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800 md:p-6">
    <div class="mb-5">
      <h2 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">外部图库</h2>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">接入已有照片文件夹，TrailSnap 会为照片建立索引，不会移动或修改源文件。</p>
    </div>

    <el-tabs v-model="activeTab" class="demo-tabs">
      <el-tab-pane label="目录管理" name="directories">
        <!-- 管理员可切换目标用户 -->
        <div v-if="userStore.userInfo?.is_superuser && !desktopMode" class="mb-4 p-4 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700">
          <span class="text-sm font-medium mr-2 dark:text-gray-300">管理用户目录:</span>
          <el-select v-model="selectedUserId" placeholder="选择用户" class="w-64">
            <el-option
              v-for="user in users"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </div>

        <!-- 桌面端以系统目录选择器作为主入口 -->
        <section
          v-if="isSuperuser && desktopMode"
          class="mb-6 overflow-hidden rounded-xl border p-5 md:p-6"
          style="border-color: rgba(var(--theme-rgb), 0.2); background-color: rgba(var(--theme-rgb), 0.05)"
        >
          <div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex min-w-0 items-start gap-4">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-500 text-white shadow-primary-500/20">
                <FolderPlus class="h-5 w-5" />
              </div>
              <div>
                <h3 class="font-semibold text-gray-900 dark:text-white">添加本机照片文件夹</h3>
                <p class="mt-1 text-sm leading-6 text-gray-500 dark:text-gray-400">选择电脑上的照片目录，添加后会立即在后台扫描。以后新增的照片可通过“重新扫描”同步。</p>
              </div>
            </div>
            <button
              type="button"
              class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-primary-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              @click="chooseFolder"
            >
              <FolderOpen class="h-4 w-4" />
              选择照片文件夹
            </button>
          </div>

          <div v-if="manualPath" class="mt-5 rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800">
            <div class="flex flex-col gap-3 md:flex-row md:items-center">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <HardDrive class="h-3.5 w-3.5" /> 已选择
                </div>
                <p class="mt-1 truncate text-sm font-medium text-gray-900 dark:text-gray-100" :title="manualPath">{{ manualPath }}</p>
                <p v-if="manualMsg" class="mt-1 text-xs" :class="manualValid ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'">{{ manualMsg }}</p>
              </div>
              <div class="flex shrink-0 gap-2">
                <el-button class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" @click="chooseFolder">重新选择</el-button>
                <el-button class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" type="primary" :loading="submitting || validating" :disabled="!manualValid" @click="addManual">添加并扫描</el-button>
              </div>
            </div>
          </div>

          <details class="mt-4 text-sm">
            <summary class="cursor-pointer select-none text-gray-500 hover:text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400">无法选择？手动输入目录路径</summary>
            <div class="mt-3 flex flex-col gap-2 sm:flex-row">
              <el-input ref="manualInputRef" v-model="manualPath" placeholder="例如 D:/Photos/family" @input="resetManualValidation" />
              <el-button class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" :loading="validating" @click="validateManual">校验路径</el-button>
            </div>
          </details>
        </section>

        <!-- 服务端部署以挂载目录自动发现作为主入口 -->
        <div v-if="isSuperuser && !desktopMode" class="mb-6">
          <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 class="font-medium text-gray-900 dark:text-gray-200">添加照片目录</h3>
              <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">自动发现服务端已挂载的照片文件夹，也可以手动指定路径。</p>
            </div>
            <div class="flex gap-2">
              <el-button size="small" @click="showDockerGuide = true">Docker 挂载说明</el-button>
              <el-button size="small" type="primary" plain :loading="detecting" @click="loadCandidates">重新检测</el-button>
            </div>
          </div>

          <!-- 检测中 -->
          <div v-if="detecting" class="text-sm text-gray-500 dark:text-gray-400 py-4">正在检测已挂载的照片目录…</div>

          <!-- 未检测到挂载 -->
          <div v-else-if="!candidates.root_exists" class="p-6 text-center bg-gray-50 dark:bg-gray-900 rounded border border-dashed border-gray-300 dark:border-gray-600">
            <p class="text-gray-600 dark:text-gray-300 mb-1">尚未接入照片文件夹</p>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
              TrailSnap 默认在
              <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">{{ candidates.root }}</code>
              下自动发现照片图库，当前该目录不存在。可直接手动添加本机任意照片文件夹路径；若使用 Docker 部署，也可按挂载示例把照片目录挂到该路径下。
            </p>
            <div class="flex justify-center gap-2 flex-wrap">
              <el-button type="primary" @click="focusManual">手动指定路径</el-button>
              <el-button @click="showDockerGuide = true">查看 Docker 配置</el-button>
            </div>
          </div>

          <!-- 根存在但无候选 -->
          <div v-else-if="candidates.directories.length === 0" class="p-6 text-center bg-gray-50 dark:bg-gray-900 rounded border border-dashed border-gray-300 dark:border-gray-600">
            <p class="text-sm text-gray-500 dark:text-gray-400">
              在 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">{{ candidates.root }}</code> 下未检测到子目录。
            </p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">可将照片目录放入该路径后重新检测，或使用下方手动添加任意路径。</p>
          </div>

          <!-- 候选列表 -->
          <div v-else>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-2">
              检测到 {{ candidates.directories.length }} 个目录，已默认勾选可读取且未接入的项。
            </p>
            <div class="border border-gray-200 dark:border-gray-700 rounded divide-y divide-gray-100 dark:divide-gray-700">
              <div
                v-for="c in candidates.directories"
                :key="c.path"
                class="flex items-start gap-3 px-3 py-2.5"
                :class="{'bg-gray-50 dark:bg-gray-900/50': selectedSet.has(c.path)}"
              >
                <el-checkbox
                  :model-value="selectedSet.has(c.path)"
                  :disabled="c.registered || !c.readable || !!c.conflict_path"
                  @change="(val: boolean) => toggleSelect(c.path, val)"
                >
                  <span class="font-medium dark:text-gray-200">{{ c.name }}</span>
                </el-checkbox>
                <div class="flex-1 min-w-0">
                  <div class="text-xs text-gray-500 dark:text-gray-400 break-all">{{ c.path }}</div>
                  <div class="text-xs mt-0.5 flex flex-wrap gap-2">
                    <el-tag v-if="c.registered" type="success" size="small">已接入</el-tag>
                    <el-tag v-else-if="!c.exists" type="info" size="small">不存在</el-tag>
                    <el-tag v-else-if="!c.readable" type="danger" size="small">无法读取</el-tag>
                    <el-tag v-else type="primary" size="small">可读取</el-tag>
                    <el-tag v-if="c.read_only === true" type="warning" size="small">只读</el-tag>
                    <span v-if="c.conflict_path" class="text-red-500 dark:text-red-400">
                      与已接入的 {{ c.conflict_path }} 存在层级冲突
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-3 flex-wrap">
              <el-button
                type="primary"
                :loading="submitting"
                :disabled="selectedPaths.length === 0"
                @click="batchAdd"
              >
                添加选中的 {{ selectedPaths.length }} 个图库并扫描
              </el-button>
              <span class="text-xs text-gray-400 dark:text-gray-500">添加后会自动在后台扫描，无需再手动点扫描</span>
            </div>
          </div>
        </div>

        <!-- 已接入图库 -->
        <section class="mb-6">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="font-medium text-gray-900 dark:text-gray-200">已添加的文件夹</h3>
            <span v-if="registeredDirs.length" class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">{{ registeredDirs.length }} 个</span>
          </div>
          <div v-if="registeredDirs.length" class="grid gap-3">
            <article v-for="row in registeredDirs" :key="row.path" class="flex flex-col gap-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700 sm:flex-row sm:items-center">
              <div class="flex min-w-0 flex-1 items-center gap-3">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-primary-500 dark:bg-gray-700">
                  <FolderOpen class="h-5 w-5" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <p class="truncate text-sm font-medium text-gray-900 dark:text-gray-100" :title="row.path">{{ directoryName(row.path) }}</p>
                    <el-tag v-if="!desktopMode && !isUnderRoot(row.path)" type="info" size="small">自定义</el-tag>
                  </div>
                  <p class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400" :title="row.path">{{ row.path }}</p>
                </div>
              </div>
              <div v-if="isSuperuser" class="flex shrink-0 gap-2 pl-[52px] sm:pl-0">
                <el-button class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" size="small" @click="scanDir(row.path)"><RefreshCw class="mr-1 h-3.5 w-3.5" />重新扫描</el-button>
                <el-button class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" type="danger" plain size="small" @click="removeDir(row.path)">移除</el-button>
              </div>
            </article>
          </div>
          <div v-else class="rounded-xl border border-dashed border-gray-300 px-5 py-9 text-center dark:border-gray-600">
            <FolderOpen class="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p class="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">还没有添加照片文件夹</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">添加后，照片会陆续出现在图库中。</p>
            <el-button v-if="isSuperuser && desktopMode" class="mt-4 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" type="primary" @click="chooseFolder">选择照片文件夹</el-button>
          </div>
          <p v-if="!isSuperuser" class="text-xs text-gray-400 dark:text-gray-500 mt-2">仅管理员可管理图库，如需添加或移除请联系管理员。</p>
        </section>

        <!-- 服务端部署的自定义路径入口 -->
        <el-collapse v-if="isSuperuser && !desktopMode" v-model="manualCollapse" class="mb-2">
          <el-collapse-item title="高级：手动输入路径" name="manual">
            <p class="text-sm text-gray-500 mb-2 dark:text-gray-400">
              填写照片文件夹的绝对路径。本机部署如 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">D:/Photos/family</code>，Docker 部署如 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">/app/Photos/family</code>。
            </p>
            <div class="flex flex-col sm:flex-row gap-2">
              <el-input ref="manualInputRef" v-model="manualPath" placeholder="D:/Photos/family 或 /app/Photos/family" class="w-full sm:max-w-[400px]" />
              <el-button
                class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                @click="chooseFolder"
              >选择文件夹</el-button>
              <el-button @click="validateManual" :loading="validating">校验</el-button>
              <el-button type="primary" @click="addManual" :loading="submitting" :disabled="!manualValid">添加并扫描</el-button>
            </div>
            <p v-if="manualMsg" class="text-xs mt-2" :class="manualValid ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'">
              {{ manualMsg }}
            </p>
          </el-collapse-item>
        </el-collapse>

        <div class="mt-4 flex items-start gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-xs text-gray-500 dark:bg-gray-900 dark:text-gray-400">
          <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
          <span>源文件保持原位，移除文件夹时只会清理 TrailSnap 中的索引和缩略图。</span>
        </div>
      </el-tab-pane>

      <el-tab-pane label="图片文件过滤" name="filter">
        <p class="text-sm text-gray-500 mb-4 dark:text-gray-400">
          配置扫描和索引时的过滤规则。符合过滤条件的文件将不会被添加到数据库。
          <br>点击“应用过滤”将从数据库中移除符合当前规则的现有文件（不会删除源文件）。
        </p>

        <el-form label-position="top" class="max-w-lg">
          <el-form-item label="启用过滤">
            <el-switch v-model="filterConfig.enable" @change="saveSettings" />
          </el-form-item>

          <div v-if="filterConfig.enable">
            <el-form-item label="最小文件大小 (KB)">
              <el-input-number v-model="filterConfig.min_size_kb" :min="0" @change="saveSettings" />
              <div class="text-xs text-gray-400 mt-1 dark:text-gray-500">小于此大小的文件将被过滤</div>
            </el-form-item>

            <el-form-item label="最小图片宽度 (像素)">
              <el-input-number v-model="filterConfig.min_width" :min="0" @change="saveSettings" />
              <div class="text-xs text-gray-400 mt-1 dark:text-gray-500">宽度小于此值将被过滤</div>
            </el-form-item>

            <el-form-item label="最小图片高度 (像素)">
              <el-input-number v-model="filterConfig.min_height" :min="0" @change="saveSettings" />
              <div class="text-xs text-gray-400 mt-1 dark:text-gray-500">高度小于此值将被过滤</div>
            </el-form-item>

            <el-form-item label="文件名过滤规则 (Regex)">
              <div v-for="(pattern, index) in filterConfig.filename_patterns" :key="index" class="flex gap-2 mb-2">
                <el-input v-model="filterConfig.filename_patterns[index]" placeholder="例如: ^tmp_.*" @change="saveSettings" />
                <el-button type="danger" :icon="Delete" circle @click="removePattern(index)" />
              </div>
              <el-button type="primary" plain size="small" @click="addPattern">添加规则</el-button>
              <div class="text-xs text-gray-400 mt-1 dark:text-gray-500">符合任一正则表达式的文件名将被过滤</div>
            </el-form-item>
          </div>

          <!-- 文件夹过滤独立于“启用过滤”开关，始终生效，用于跳过 NAS 等系统索引目录 -->
          <el-divider content-position="left" class="!my-6">文件夹过滤</el-divider>
          <el-form-item label="排除文件夹 (Regex)">
            <p class="text-sm text-gray-500 mb-2 dark:text-gray-400">
              扫描时将跳过名称匹配以下规则的文件夹（及其子目录），避免重复统计 NAS 索引目录（如 @eaDir、#recycle）。
              <br>该规则始终生效，无需开启“启用过滤”。点击“应用过滤到现有数据”可清理已索引的相关照片。
            </p>
            <div v-for="(folder, index) in filterConfig.exclude_folders" :key="'f-'+index" class="flex gap-2 mb-2">
              <el-input v-model="filterConfig.exclude_folders[index]" placeholder="例如: @eaDir" @change="saveSettings" />
              <el-button type="danger" :icon="Delete" circle @click="removeExcludeFolder(index)" />
            </div>
            <div class="flex gap-2">
              <el-button type="primary" plain size="small" @click="addExcludeFolder">添加文件夹</el-button>
              <el-button plain size="small" @click="fillCommonFolders">填入常用 NAS 目录</el-button>
            </div>
            <div class="text-xs text-gray-400 mt-1 dark:text-gray-500">按文件夹名匹配（正则），如 @eaDir、#recycle、.@__thumb</div>
          </el-form-item>

          <div class="mt-6">
            <el-button type="danger" @click="applyFilter">应用过滤到现有数据</el-button>
          </div>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <!-- Docker 配置弹窗 -->
    <el-dialog v-model="showDockerGuide" title="Docker 挂载配置" width="640px">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-3">
        把宿主机照片目录挂载到容器的 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">/app/Photos/&lt;图库名&gt;</code> 下，TrailSnap 会自动发现这些一级子目录。
      </p>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-1">Windows（Docker Desktop）：</p>
      <pre class="text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded overflow-x-auto mb-3 dark:text-gray-300">services:
  server:
    volumes:
      - ./data:/app/data
      - "D:/家庭照片:/app/Photos/家庭照片"
      - "E:/旅行照片:/app/Photos/travel"</pre>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-1">Linux / NAS：</p>
      <pre class="text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded overflow-x-auto mb-3 dark:text-gray-300">services:
  server:
    volumes:
      - ./data:/app/data
      - /volume1/family:/app/Photos/family
      - /volume2/travel:/app/Photos/travel</pre>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        冒号左侧是宿主机照片位置，右侧是容器内路径。修改后需重建容器再回到本页重新检测。
      </p>
      <template #footer>
        <el-button type="primary" @click="showDockerGuide = false">知道了</el-button>
      </template>
    </el-dialog>
    <ExternalGalleryPickerDialog v-model:visible="showServerPicker" @select="useSelectedFolder" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { settingsApi } from '@/api/settings'
import { tasksApi } from '@/api/tasks'
import { userService, type User } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { FolderPlus, FolderOpen, HardDrive, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import ExternalGalleryPickerDialog from '@/components/ExternalGalleryPickerDialog.vue'
import { isTauriApp } from '@/config/server'

interface Candidate {
  name: string
  path: string
  exists: boolean
  readable: boolean
  read_only: boolean | null
  registered: boolean
  conflict_path: string | null
}

const activeTab = ref('directories')
const userStore = useUserStore()
const users = ref<User[]>([])
const selectedUserId = ref('')
const isSuperuser = computed(() => !!userStore.userInfo?.is_superuser)
const desktopMode = isTauriApp()

// 候选发现
const detecting = ref(false)
const candidates = ref<{ root: string; root_exists: boolean; directories: Candidate[] }>({
  root: '/app/Photos', root_exists: false, directories: []
})
const selectedSet = reactive<Set<string>>(new Set())

// 已接入
const registeredDirs = ref<{ path: string }[]>([])

// 手动添加
const manualCollapse = ref<string[]>([])
const manualPath = ref('')
const manualValid = ref(false)
const manualMsg = ref('')
const validating = ref(false)
const manualInputRef = ref<any>(null)

const submitting = ref(false)
const showDockerGuide = ref(false)
const showServerPicker = ref(false)

const filterConfig = reactive({
  enable: false,
  min_size_kb: 0,
  min_width: 0,
  min_height: 0,
  filename_patterns: [] as string[],
  exclude_folders: [] as string[]
})

const selectedPaths = computed(() => Array.from(selectedSet))

const directoryName = (path: string) => path.replace(/[\\/]+$/, '').split(/[\\/]/).filter(Boolean).pop() || path

const resetManualValidation = () => {
  manualValid.value = false
  manualMsg.value = ''
}

const isUnderRoot = (path: string) => {
  const root = candidates.value.root
  if (!root) return false
  const r = root.replace(/\/+$/, '')
  return path === r || path.startsWith(r + '/')
}

const toggleSelect = (path: string, val: boolean) => {
  if (val) selectedSet.add(path)
  else selectedSet.delete(path)
}

const uid = () => selectedUserId.value || undefined

const loadCandidates = async () => {
  detecting.value = true
  try {
    const data = await settingsApi.getDirectoryCandidates(uid())
    candidates.value = {
      root: data.root,
      root_exists: data.root_exists,
      directories: data.directories || []
    }
    // 默认勾选可读取、未接入、无冲突的项
    selectedSet.clear()
    for (const c of candidates.value.directories) {
      if (c.readable && !c.registered && !c.conflict_path) {
        selectedSet.add(c.path)
      }
    }
  } catch (e) {
    console.error(e)
  } finally {
    detecting.value = false
  }
}

const loadRegistered = async () => {
  try {
    const res = await settingsApi.getDirectories(uid())
    registeredDirs.value = (res.external || []).map((d: string) => ({ path: d }))
  } catch (e) {
    console.error(e)
  }
}

const loadFilter = async () => {
  try {
    const settings = await settingsApi.getSettings()
    if (settings.filter) {
      Object.assign(filterConfig, settings.filter)
    }
  } catch (e) {
    console.error(e)
  }
}

const reloadAll = async () => {
  // 候选发现仅管理员需要（普通用户无管理权限，不展示候选区）
  const tasks: Promise<unknown>[] = [loadRegistered(), loadFilter()]
  if (isSuperuser.value && !desktopMode) tasks.unshift(loadCandidates())
  await Promise.all(tasks)
}

watch(selectedUserId, () => {
  manualValid.value = false
  manualMsg.value = ''
  manualPath.value = ''
  reloadAll()
})

const batchAdd = async () => {
  if (selectedPaths.value.length === 0) return
  submitting.value = true
  try {
    const data = await settingsApi.batchAddDirectories(selectedPaths.value, uid())
    const added = data.added?.length || 0
    const skipped = data.skipped?.length || 0
    if (added > 0) {
      ElMessage.success(`已添加 ${added} 个图库${skipped ? `（跳过 ${skipped} 个已接入）` : ''}，正在后台扫描`)
    } else if (skipped > 0) {
      ElMessage.info(`${skipped} 个图库已接入，无需重复添加`)
    }
    await reloadAll()
  } catch (e: any) {
    // 批量校验失败时后端返回 {code:400, data:{errors}}，request 拦截器已弹错误提示
    const errors = e?.data?.errors || e?.errors
    if (errors?.length) {
      ElMessageBox.alert(
        errors.map((x: { path: string; msg: string }) => `${x.path}\n${x.msg}`).join('\n\n'),
        '部分目录未能添加',
        { type: 'warning' }
      )
    }
    // 即便扫描任务未启动（配置已写入），也刷新列表让已添加的图库可见
    await reloadAll()
  } finally {
    submitting.value = false
  }
}

const focusManual = () => {
  manualCollapse.value = ['manual']
  nextTick(() => {
    manualInputRef.value?.focus?.()
  })
}

const validateManual = async () => {
  if (!manualPath.value.trim()) {
    manualValid.value = false
    manualMsg.value = '请输入路径'
    return
  }
  validating.value = true
  try {
    const data = await settingsApi.validateDirectory(manualPath.value.trim(), uid())
    manualValid.value = data.valid
    manualMsg.value = data.valid
      ? (desktopMode
          ? '校验通过，可以添加此文件夹'
          : (data.warnings?.includes('outside_root') ? '校验通过（该路径不在 /app/Photos 下，将作为自定义路径接入）' : '校验通过'))
      : (data.msg || '校验未通过')
  } catch (e: any) {
    manualValid.value = false
    manualMsg.value = e?.data?.msg || '校验失败'
  } finally {
    validating.value = false
  }
}

const useSelectedFolder = async (path: string) => {
  manualPath.value = path
  manualValid.value = false
  manualMsg.value = '正在检查文件夹…'
  await validateManual()
}

const chooseFolder = async () => {
  if (!isTauriApp()) {
    showServerPicker.value = true
    return
  }
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择照片文件夹' })
    if (typeof selected === 'string') await useSelectedFolder(selected)
  } catch {
    ElMessage.error('无法打开系统文件夹选择器')
  }
}

const addManual = async () => {
  if (!manualValid.value || !manualPath.value.trim()) return
  submitting.value = true
  try {
    await settingsApi.addDirectory(manualPath.value.trim(), uid())
    ElMessage.success('已添加并开始扫描')
    manualPath.value = ''
    manualValid.value = false
    manualMsg.value = ''
    await reloadAll()
  } catch {
    ElMessage.error('添加失败，请检查路径')
  } finally {
    submitting.value = false
  }
}

const scanDir = async (path: string) => {
  try {
    await tasksApi.createTask('SCAN_FOLDER', { scan_roots: [path], user_id: uid() })
    ElMessage.success(`已创建扫描任务: ${path}`)
  } catch {
    ElMessage.error('创建扫描任务失败')
  }
}

const removeDir = async (path: string) => {
  try {
    await ElMessageBox.confirm(
      `确定要移除目录 "${path}" 吗？该目录下的所有照片索引及其缩略图将被删除（源文件不会被删除）。`,
      '确认移除',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return // 用户取消
  }
  // 先调用后端，成功后再刷新列表，避免提前提示成功
  try {
    await settingsApi.removeDirectory(path, uid())
    ElMessage.success('移除成功')
    await reloadAll()
  } catch {
    ElMessage.error('移除失败，该目录可能正在被使用')
  }
}

const addPattern = () => { filterConfig.filename_patterns.push('') }
const removePattern = (index: number) => { filterConfig.filename_patterns.splice(index, 1); saveSettings() }
const addExcludeFolder = () => { filterConfig.exclude_folders.push('') }
const removeExcludeFolder = (index: number) => { filterConfig.exclude_folders.splice(index, 1); saveSettings() }

const fillCommonFolders = () => {
  const common = ['@eaDir', '#recycle', '@Recycle', '.@__thumb', 'SYNOFILE_THUMB']
  const existing = new Set(filterConfig.exclude_folders.map(f => f.trim()))
  let added = false
  for (const f of common) {
    if (!existing.has(f)) {
      filterConfig.exclude_folders.push(f)
      added = true
    }
  }
  if (added) {
    saveSettings()
    ElMessage.success('已填入常用 NAS 目录')
  } else {
    ElMessage.info('常用目录已存在')
  }
}

const saveSettings = async () => {
  try {
    await settingsApi.updateSettings({ filter: filterConfig })
    ElMessage.success('设置已保存')
  } catch {
    ElMessage.error('保存设置失败')
  }
}

const applyFilter = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要对现有数据应用过滤规则吗？符合条件的文件将从数据库中移除（不会删除源文件）。这可能需要一些时间。',
      '确认操作',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await settingsApi.applyFilter()
    ElMessage.success('已触发过滤操作，请稍候查看结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

onMounted(async () => {
  // 刷新页面后 store.userInfo 为 null（仅在 login / Profile / UserManagement 时拉取）。
  // 主动补拉一次，保证 is_superuser 判断与管理员 UI 在直进 /settings 时也生效；
  // 失败则降级为非管理员只读视图。
  if (userStore.token && !userStore.userInfo) {
    try { await userStore.getUserInfo() } catch { /* ignore */ }
  }
  if (isSuperuser.value) {
    try {
      users.value = await userService.getUsers()
      if (userStore.userInfo?.id) {
        selectedUserId.value = userStore.userInfo.id
      }
    } catch (e) {
      console.error(e)
    }
  }
  await reloadAll()
})
</script>
