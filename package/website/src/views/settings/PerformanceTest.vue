<template>
  <div class="h-full flex flex-col gap-6">
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-2 gap-4 sm:gap-0">
        <h2 class="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white">性能测试</h2>
        <div class="text-sm text-gray-500 dark:text-gray-400">
            用于测试添加外部图库目录后，端到端各项处理任务的耗时与速率。
        </div>
    </div>

    <!-- 控制面板 -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
      <div class="flex flex-col sm:flex-row gap-4 items-center">
         <el-input 
            v-model="testPath" 
            placeholder="输入测试用的外部文件夹绝对路径 (例如: /Photos/Test)" 
            class="flex-1"
            :disabled="isTesting"
            clearable
         />
         <el-button type="primary" @click="startTest" :loading="isTesting" class="w-full sm:w-auto">
             {{ isTesting ? '测试运行中...' : '开始测试' }}
         </el-button>
         <el-button type="danger" @click="stopTest(true)" :disabled="!isTesting" class="w-full sm:w-auto">
             停止监控
         </el-button>
      </div>

      <!-- 总体统计 -->
      <div v-if="testStartTime" class="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
         <div class="bg-gray-50 dark:bg-gray-700/50 p-4 rounded-lg border border-gray-100 dark:border-gray-600">
            <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">测试开始时间</div>
            <div class="font-medium text-gray-800 dark:text-gray-200">{{ new Date(testStartTime).toLocaleTimeString() }}</div>
         </div>
         <div class="bg-gray-50 dark:bg-gray-700/50 p-4 rounded-lg border border-gray-100 dark:border-gray-600">
            <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">端到端总耗时</div>
            <div class="text-2xl font-bold text-blue-600 dark:text-blue-400">{{ (totalElapsed / 1000).toFixed(1) }} <span class="text-sm font-normal">s</span></div>
         </div>
         <div class="bg-gray-50 dark:bg-gray-700/50 p-4 rounded-lg border border-gray-100 dark:border-gray-600">
            <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">当前状态</div>
            <div class="mt-1">
                <el-tag :type="isTesting ? 'primary' : 'success'" size="large" effect="dark">
                    {{ isTesting ? '测试进行中' : '测试已完成' }}
                </el-tag>
            </div>
         </div>
      </div>
    </div>

    <!-- 任务明细表格 -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 flex-1 overflow-hidden flex flex-col">
        <h3 class="text-lg font-medium mb-4 text-gray-800 dark:text-white">各任务处理详情</h3>
        <el-table 
            :data="statsList" 
            style="width: 100%" 
            border 
            stripe 
            height="100%"
            class="flex-1"
        >
            <el-table-column prop="task_name" label="任务类别" min-width="150" />
            
            <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                    <el-tag 
                        :type="row.statusText === '已完成' ? 'success' : (row.statusText === '进行中' ? 'primary' : 'info')" 
                        size="small"
                    >
                        {{ row.statusText }}
                    </el-tag>
                </template>
            </el-table-column>

            <el-table-column label="耗时 (s)" width="120" align="right">
                <template #default="{ row }">
                    <span class="font-mono">{{ row.elapsed ? (row.elapsed / 1000).toFixed(1) : '0.0' }}</span>
                </template>
            </el-table-column>

            <el-table-column label="进度 (已完成 / 待处理)" min-width="180" align="center">
                <template #default="{ row }">
                    <div class="flex items-center justify-center gap-2 font-mono">
                        <span class="text-green-600 dark:text-green-400 font-medium">{{ row.completed }}</span>
                        <span class="text-gray-400">/</span>
                        <span class="text-blue-600 dark:text-blue-400 font-medium">{{ row.pending }}</span>
                    </div>
                </template>
            </el-table-column>

            <el-table-column label="平均速度" width="140" align="right">
                <template #default="{ row }">
                    <span class="font-mono">{{ row.avgSpeed.toFixed(2) }}</span> <span class="text-xs text-gray-500">项/s</span>
                </template>
            </el-table-column>

            <el-table-column label="实时速度" width="140" align="right">
                <template #default="{ row }">
                    <span class="font-mono" :class="{'text-orange-500': row.currentSpeed > 0}">{{ row.currentSpeed.toFixed(2) }}</span> <span class="text-xs text-gray-500">项/s</span>
                </template>
            </el-table-column>
        </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, computed } from 'vue'
import { tasksApi } from '@/api/tasks'
import { settingsApi } from '@/api/settings'
import { ElMessage, ElMessageBox } from 'element-plus'

const testPath = ref('')
const isTesting = ref(false)
const testStartTime = ref<number | null>(null)
const totalElapsed = ref(0)
let pollTimer: number | null = null
// 完成「稳定期」：所有任务 pending 归零后，持续观察一段时间再判定测试结束，
// 避免扫描刚结束、下游任务尚未创建的空窗期被误判为完成。
let finishedSince: number | null = null
const FINISH_GRACE_MS = 5000
const hasSaved = ref(false)

interface TaskStat {
    category: string
    task_name: string
    startTime: number | null
    endTime: number | null
    elapsed: number
    // 任务总个数：取该分类「待处理」数量在测试期间出现过的最大值。
    // 因为后端任务一旦完成即从数据库删除，completed 恒为 0，
    // 只能通过 pending 的峰值反推本批次创建的任务总数。
    totalItems: number
    completed: number   // = totalItems - pending，仅用于展示
    pending: number
    lastPending: number
    avgSpeed: number
    currentSpeed: number
    hasStarted: boolean
    isFinished: boolean
    statusText: string
}

const statsMap = ref<Record<string, TaskStat>>({})
// 保证按照特定顺序或原有顺序显示
const statsList = computed(() => {
    return Object.values(statsMap.value)
})

const startTest = async () => {
    if (!testPath.value) {
        ElMessage.warning('请输入测试用的外部文件夹绝对路径')
        return
    }
    
    try {
        await ElMessageBox.confirm(
            `此操作将添加目录 "${testPath.value}" 并开始扫描。如果目录中照片较多，测试将持续较长时间。是否继续？`,
            '确认测试',
            {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning'
            }
        )
    } catch {
        return
    }

    // 初始化或重置状态
    isTesting.value = true
    testStartTime.value = Date.now()
    totalElapsed.value = 0
    statsMap.value = {}
    finishedSince = null
    hasSaved.value = false
    
    try {
        // 1. 获取初始状态，记录各任务当前待处理数（作为峰值基线）
        const initialStatus = await tasksApi.getGroupedStatus()
        initialStatus.forEach((cat: any) => {
            const pending = cat.pending || 0
            statsMap.value[cat.category] = {
                category: cat.category,
                task_name: cat.task_name,
                startTime: null,
                endTime: null,
                elapsed: 0,
                totalItems: pending,
                completed: 0,
                pending,
                lastPending: pending,
                avgSpeed: 0,
                currentSpeed: 0,
                hasStarted: false,
                isFinished: false,
                statusText: '等待中'
            }
        })
        
        // 2. 调用添加目录 API 触发后端扫描
        await settingsApi.addDirectory(testPath.value)
        ElMessage.success('目录添加成功，开始监控任务...')
        
        // 3. 开启 1 秒轮询
        pollTimer = window.setInterval(pollStatus, 1000)
    } catch (e) {
        ElMessage.error('启动测试失败，请检查路径是否存在或后端服务状态')
        isTesting.value = false
    }
}

const stopTest = (saveResult = false) => {
    isTesting.value = false
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
    if (saveResult) {
        saveResults()
    }
}

const saveResults = () => {
    if (hasSaved.value) return
    if (!testStartTime.value) return
    hasSaved.value = true

    const startDate = new Date(testStartTime.value)
    const pad = (n: number) => n.toString().padStart(2, '0')
    const ts = `${startDate.getFullYear()}-${pad(startDate.getMonth() + 1)}-${pad(startDate.getDate())}_${pad(startDate.getHours())}-${pad(startDate.getMinutes())}-${pad(startDate.getSeconds())}`

    const results = {
        testStartTime: startDate.toLocaleString(),
        totalElapsedSeconds: Number((totalElapsed.value / 1000).toFixed(1)),
        tasks: Object.values(statsMap.value).map(s => ({
            task_name: s.task_name,
            category: s.category,
            status: s.statusText,
            elapsedSeconds: Number((s.elapsed / 1000).toFixed(1)),
            completed: s.completed,
            pending: s.pending,
            avgSpeed: Number(s.avgSpeed.toFixed(2)),
            currentSpeed: Number(s.currentSpeed.toFixed(2)),
        }))
    }

    try {
        const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `性能测试_${ts}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        ElMessage.success('测试结果已自动保存')
    } catch (e) {
        console.error('保存测试结果失败', e)
        ElMessage.error('保存测试结果失败')
    }
}

const pollStatus = async () => {
    if (!isTesting.value) return
    const now = Date.now()
    totalElapsed.value = now - testStartTime.value!
    
    try {
        const currentStatus = await tasksApi.getGroupedStatus()
        let allFinished = true
        let hasAnyStarted = false
        
        currentStatus.forEach((cat: any) => {
            let stat = statsMap.value[cat.category]
            if (!stat) {
                // 如果后端新增了未记录的分类
                const pending = cat.pending || 0
                stat = {
                    category: cat.category,
                    task_name: cat.task_name,
                    startTime: null,
                    endTime: null,
                    elapsed: 0,
                    totalItems: pending,
                    completed: 0,
                    pending,
                    lastPending: pending,
                    avgSpeed: 0,
                    currentSpeed: 0,
                    hasStarted: false,
                    isFinished: false,
                    statusText: '等待中'
                }
                statsMap.value[cat.category] = stat
            }

            const prevPending = stat.pending
            const currentPending = cat.pending || 0

            // 更新待处理数与峰值（任务总个数）
            stat.pending = currentPending
            if (currentPending > stat.totalItems) {
                stat.totalItems = currentPending
            }

            // 判断是否开始：出现过待处理任务即视为已启动
            if (!stat.hasStarted && stat.totalItems > 0) {
                stat.hasStarted = true
                stat.startTime = now
                stat.statusText = '进行中'
            }

            if (stat.hasStarted) {
                hasAnyStarted = true

                // 已完成数 = 峰值 - 当前待处理（任务完成后即从库中删除，故用 pending 下降量推算）
                const completedSoFar = Math.max(0, stat.totalItems - currentPending)
                // 过去 1 秒完成数 = 上一秒 pending - 当前 pending（1 秒轮询一次，即为 项/s）
                const deltaCompleted = Math.max(0, prevPending - currentPending)
                stat.completed = completedSoFar
                stat.currentSpeed = deltaCompleted
                stat.lastPending = currentPending

                if (currentPending > 0) {
                    // 任务仍在进行中
                    stat.isFinished = false
                    stat.endTime = null
                    stat.statusText = '进行中'
                    stat.elapsed = now - stat.startTime!
                    allFinished = false
                } else if (!stat.isFinished) {
                    // 刚刚完成
                    stat.isFinished = true
                    stat.endTime = now
                    stat.elapsed = stat.endTime - stat.startTime!
                    stat.statusText = '已完成'
                } else {
                    // 保持已完成状态
                }

                // 更新平均速度
                if (stat.elapsed > 0) {
                    stat.avgSpeed = completedSoFar / (stat.elapsed / 1000)
                }
            }
        })
        
        // 整体完成判断：
        // 必须至少有一个任务开始过，且所有分类的 pending 都归零。
        // 由于扫描（SCAN_FOLDER）不在 grouped-status 返回的分类中，无法直接依赖其状态，
        // 这里采用「稳定期」策略：所有 pending 归零后持续观察 FINISH_GRACE_MS，
        // 期间若无新任务出现则判定整个测试结束，避免扫描刚结束、下游任务尚未创建的空窗期误判。
        if (hasAnyStarted && allFinished) {
            if (finishedSince === null) finishedSince = now
            if (now - finishedSince >= FINISH_GRACE_MS) {
                stopTest(true)
                ElMessage.success('测试完成，所有任务已结束')
            }
        } else {
            finishedSince = null
        }
        
    } catch (e) {
        console.error('获取任务状态失败', e)
    }
}

onUnmounted(() => {
    stopTest()
})
</script>
