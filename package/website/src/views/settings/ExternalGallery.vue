<template>
  <div class="p-4 md:p-6 bg-white rounded-lg shadow-sm border border-gray-100 dark:bg-gray-800 dark:border-gray-700">
      <h2 class="text-xl md:text-2xl font-semibold mb-4 border-b pb-2 dark:text-white">外部图库管理</h2>
      
      <el-tabs v-model="activeTab" class="demo-tabs">
        <el-tab-pane label="目录管理" name="directories">
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

            <p class="text-sm text-gray-500 mb-4 dark:text-gray-400">
                添加外部文件夹路径，系统将扫描这些文件夹中的图片（只读模式）。
                <br>外部文件夹中的图片不会被移动或修改，生成的缩略图将存储在主目录中。
                <br><a href="https://trailsnap.cn/docs/guide/settings/directories.html" target="_blank" class="text-blue-500 hover:underline dark:text-blue-400">查看详细说明</a>
            </p>
            
            <div class="mb-4 flex flex-col sm:flex-row gap-2">
                <el-input v-model="newDir" placeholder="输入外部文件夹绝对路径" class="w-full sm:max-w-[400px]" />
                <el-button type="primary" @click="addDir" class="w-full sm:w-auto">添加目录</el-button>
            </div>

            <el-table :data="directories" style="width: 100%" border>
                <el-table-column prop="path" label="目录路径" />
                <el-table-column label="操作" width="180">
                <template #default="{ row }">
                    <el-button type="primary" size="small" @click="scanDir(row.path)">扫描</el-button>
                    <el-button type="danger" size="small" @click="removeDir(row.path)">移除</el-button>
                </template>
                </el-table-column>
            </el-table>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, watch } from 'vue'
import { settingsApi } from '@/api/settings'
import { tasksApi } from '@/api/tasks'
import { userService, type User } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'

const activeTab = ref('directories')
const directories = ref<{path: string}[]>([])
const newDir = ref('')
const userStore = useUserStore()
const users = ref<User[]>([])
const selectedUserId = ref('')

const filterConfig = reactive({
    enable: false,
    min_size_kb: 0,
    min_width: 0,
    min_height: 0,
    filename_patterns: [] as string[],
    exclude_folders: [] as string[]
})

const loadData = async () => {
    try {
        const uid = selectedUserId.value || undefined
        const res = await settingsApi.getDirectories(uid)
        directories.value = res.external.map((d: string) => ({ path: d }))
        
        // Filter settings are global, so we only load them once or when needed.
        // But for simplicity we load them here too.
        const settings = await settingsApi.getSettings()
        if (settings.filter) {
            Object.assign(filterConfig, settings.filter)
        }
    } catch (e) {
        console.error(e)
    }
}

watch(selectedUserId, () => {
    loadData()
})

const addDir = async () => {
    if (!newDir.value) return
    try {
        const uid = selectedUserId.value || undefined
        await settingsApi.addDirectory(newDir.value, uid)
        newDir.value = ''
        ElMessage.success('添加成功')
        await loadData()
    } catch {
        ElMessage.error('添加失败，请检查路径是否存在')
    }
}

const scanDir = async (path: string) => {
    try {
        // Scan task should probably take user_id if we want to associate scan with user?
        // But scan logic in backend:
        // TaskManager.add_task(db, TaskType.SCAN_FOLDER, {'scan_roots': external, 'user_id': str(target_user.id)})
        // Here we are calling tasksApi.createTask directly.
        // We should probably update scanDir to use selectedUserId if available?
        // But the scanDir takes a specific path.
        // The backend `add_directory` triggers a scan automatically for that user.
        // The manual "Scan" button in the table just triggers a scan for that path.
        // Does `tasksApi.createTask` support user_id?
        // Let's assume for now the manual scan is global or just scans the path.
        // If the path is in the system, it will be scanned.
        // The indexer might need to know the owner.
        // If we are admin triggering scan for another user's folder...
        // Let's leave it as is for now, or maybe check tasksApi.
        
        await tasksApi.createTask('SCAN_FOLDER', { scan_roots: [path], user_id: selectedUserId.value || undefined })
        ElMessage.success(`已创建扫描任务: ${path}`)
    } catch (e) {
        ElMessage.error('创建扫描任务失败')
    }
}

const removeDir = async (path: string) => {
    try {
        await ElMessageBox.confirm(`确定要移除目录 "${path}" 吗？该目录下的所有照片索引及其缩略图将被删除（源文件不会被删除）。`, '确认移除', {
            confirmButtonText: '移除',
            cancelButtonText: '取消',
            type: 'warning'
        })
        ElMessage.success('移除成功')
        directories.value = directories.value.filter(d => d.path !== path)
        const uid = selectedUserId.value || undefined
        await settingsApi.removeDirectory(path, uid)
        await loadData()
    } catch (e) {
        if (e !== 'cancel') ElMessage.error('移除失败')
    }
}

const addPattern = () => {
    filterConfig.filename_patterns.push('')
}

const removePattern = (index: number) => {
    filterConfig.filename_patterns.splice(index, 1)
    saveSettings()
}

const addExcludeFolder = () => {
    filterConfig.exclude_folders.push('')
}

const removeExcludeFolder = (index: number) => {
    filterConfig.exclude_folders.splice(index, 1)
    saveSettings()
}

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
    } catch (e) {
        ElMessage.error('保存设置失败')
    }
}

const applyFilter = async () => {
    try {
        await ElMessageBox.confirm('确定要对现有数据应用过滤规则吗？符合条件的文件将从数据库中移除（不会删除源文件）。这可能需要一些时间。', '确认操作', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
        })
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
            // Set default to current user
            if (userStore.userInfo.id) {
                selectedUserId.value = userStore.userInfo.id
            }
        } catch (e) {
            console.error(e)
        }
    }
    loadData()
})
</script>
