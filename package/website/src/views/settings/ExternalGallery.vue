<template>
  <div class="p-4 md:p-6 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700">
    <h2 class="text-xl md:text-2xl font-semibold mb-4 border-b pb-2 dark:text-white">外部图库管理</h2>

    <el-tabs v-model="activeTab" class="demo-tabs">
      <el-tab-pane label="目录管理" name="directories">
        <!-- 管理员可切换目标用户 -->
        <div v-if="userStore.userInfo?.is_superuser" class="mb-4 p-4 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700">
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

        <!-- 候选发现区（仅管理员） -->
        <div v-if="isSuperuser" class="mb-6">
          <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 class="text-base font-medium dark:text-gray-200">照片目录接入</h3>
            <div class="flex gap-2">
              <el-button size="small" @click="showDockerGuide = true">查看 Docker 配置</el-button>
              <el-button size="small" type="primary" plain :loading="detecting" @click="loadCandidates">重新检测</el-button>
            </div>
          </div>

          <!-- 检测中 -->
          <div v-if="detecting" class="text-sm text-gray-500 dark:text-gray-400 py-4">正在检测已挂载的照片目录…</div>

          <!-- 未检测到挂载 -->
          <div v-else-if="!candidates.root_exists" class="p-6 text-center bg-gray-50 dark:bg-gray-900 rounded border border-dashed border-gray-300 dark:border-gray-600">
            <p class="text-gray-600 dark:text-gray-300 mb-1">还没有接入照片文件夹</p>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
              请先把电脑或 NAS 中的照片目录挂载到 TrailSnap 后端容器的
              <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">/app/Photos/&lt;图库名&gt;</code> 下。
            </p>
            <div class="flex justify-center gap-2 flex-wrap">
              <el-button type="primary" @click="showDockerGuide = true">查看 Docker 配置</el-button>
            </div>
          </div>

          <!-- 根存在但无候选 -->
          <div v-else-if="candidates.directories.length === 0" class="p-6 text-center bg-gray-50 dark:bg-gray-900 rounded border border-dashed border-gray-300 dark:border-gray-600">
            <p class="text-sm text-gray-500 dark:text-gray-400">
              在 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">{{ candidates.root }}</code> 下未检测到子目录。
            </p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">请按 Docker 配置示例挂载照片目录后重新检测，或使用下方手动添加。</p>
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
        <div class="mb-6">
          <h3 class="text-base font-medium mb-3 dark:text-gray-200">已接入图库</h3>
          <el-table :data="registeredDirs" style="width: 100%" border>
            <el-table-column label="目录路径" min-width="240">
              <template #default="{ row }">
                <div class="break-all text-sm">{{ row.path }}</div>
                <el-tag v-if="!isUnderRoot(row.path)" type="info" size="small" class="mt-1">自定义路径</el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isSuperuser" label="操作" width="200">
              <template #default="{ row }">
                <el-button size="small" @click="scanDir(row.path)">重新扫描</el-button>
                <el-button type="danger" size="small" @click="removeDir(row.path)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <p v-if="registeredDirs.length === 0" class="text-sm text-gray-400 dark:text-gray-500 mt-2">尚未接入任何图库。</p>
          <p v-if="!isSuperuser" class="text-xs text-gray-400 dark:text-gray-500 mt-2">仅管理员可管理图库，如需添加或移除请联系管理员。</p>
        </div>

        <!-- 手动添加（高级，仅管理员） -->
        <el-collapse v-if="isSuperuser" v-model="manualCollapse" class="mb-2">
          <el-collapse-item title="高级：手动输入容器内路径" name="manual">
            <p class="text-sm text-gray-500 mb-2 dark:text-gray-400">
              适用于非标准部署。请填写容器内绝对路径，如 <code class="px-1 bg-gray-200 dark:bg-gray-700 rounded">/app/Photos/family</code>。
            </p>
            <div class="flex flex-col sm:flex-row gap-2">
              <el-input v-model="manualPath" placeholder="/app/Photos/family" class="w-full sm:max-w-[400px]" />
              <el-button @click="validateManual" :loading="validating">校验</el-button>
              <el-button type="primary" @click="addManual" :loading="submitting" :disabled="!manualValid">添加并扫描</el-button>
            </div>
            <p v-if="manualMsg" class="text-xs mt-2" :class="manualValid ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'">
              {{ manualMsg }}
            </p>
          </el-collapse-item>
        </el-collapse>

        <p class="text-xs text-gray-400 dark:text-gray-500 mt-2">
          TrailSnap 不会主动移动或修改源文件，缩略图与索引存放在 TrailSnap 数据目录。
        </p>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { settingsApi } from '@/api/settings'
import { tasksApi } from '@/api/tasks'
import { userService, type User } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'

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

const submitting = ref(false)
const showDockerGuide = ref(false)

const filterConfig = reactive({
  enable: false,
  min_size_kb: 0,
  min_width: 0,
  min_height: 0,
  filename_patterns: [] as string[],
  exclude_folders: [] as string[]
})

const selectedPaths = computed(() => Array.from(selectedSet))

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
  if (isSuperuser.value) tasks.unshift(loadCandidates())
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
      ? (data.warnings?.includes('outside_root') ? '校验通过（该路径不在 /app/Photos 下，将作为自定义路径接入）' : '校验通过')
      : (data.msg || '校验未通过')
  } catch (e: any) {
    manualValid.value = false
    manualMsg.value = e?.data?.msg || '校验失败'
  } finally {
    validating.value = false
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
  if (userStore.userInfo?.is_superuser) {
    try {
      users.value = await userService.getUsers()
      if (userStore.userInfo.id) {
        selectedUserId.value = userStore.userInfo.id
      }
    } catch (e) {
      console.error(e)
    }
  }
  await reloadAll()
})
</script>
