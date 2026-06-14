<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">令牌管理</h1>
      <el-button type="primary" @click="showCreateDialog = true">
        <Plus class="w-4 h-4 mr-1" />新增令牌
      </el-button>
    </div>

    <!-- Usage Guide -->
    <div class="mb-6 bg-primary-50 dark:bg-gray-800/60 border border-primary-200 dark:border-gray-700 rounded-xl overflow-hidden">
      <div class="px-5 py-4 flex items-center justify-between cursor-pointer select-none" @click="guideExpanded = !guideExpanded">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-lg bg-primary-500/10 flex items-center justify-center">
            <Info class="w-4 h-4 text-primary-500" />
          </div>
          <span class="font-semibold text-gray-800 dark:text-white">令牌使用说明</span>
        </div>
        <ChevronDown class="w-4 h-4 text-gray-400 transition-transform duration-200" :class="{ 'rotate-180': guideExpanded }" />
      </div>
      <transition name="fade">
        <div v-show="guideExpanded" class="px-5 pb-5 pt-0">
          <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">令牌用于授权外部 AI 工具通过 API 访问你的相册数据，无需登录账号。</p>

          <div class="space-y-3">
            <!-- Step 1 -->
            <div class="flex gap-3">
              <div class="flex-shrink-0 w-6 h-6 rounded-full bg-primary-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">1</div>
              <div class="flex-1">
                <p class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">安装 CLI 工具</p>
                <div class="bg-gray-900 dark:bg-gray-950 rounded-lg px-3 py-2 font-mono text-xs text-green-400 overflow-x-auto leading-relaxed">
                  npm install -g trailsnap-cli<br>
                  trailsnap -v
                </div>
              </div>
            </div>
            <!-- Step 2 -->
            <div class="flex gap-3">
              <div class="flex-shrink-0 w-6 h-6 rounded-full bg-primary-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">2</div>
              <div class="flex-1">
                <p class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">配置服务地址和令牌</p>
                <div class="bg-gray-900 dark:bg-gray-950 rounded-lg px-3 py-2 font-mono text-xs text-green-400 overflow-x-auto">
                  trailsnap config set --url &lt;url&gt; --token <span class="text-amber-400">&lt;token&gt;</span>
                </div>
              </div>
            </div>
            <!-- Step 3 -->
            <div class="flex gap-3">
              <div class="flex-shrink-0 w-6 h-6 rounded-full bg-primary-500 text-white text-xs font-bold flex items-center justify-center mt-0.5">3</div>
              <div class="flex-1">
                <p class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">查询相册数据</p>
                <div class="bg-gray-900 dark:bg-gray-950 rounded-lg px-3 py-2 font-mono text-xs text-green-400 overflow-x-auto leading-relaxed">
                  trailsnap photos list --limit 10<br>
                  trailsnap albums list<br>
                  trailsnap locations timeline --level city
                </div>
              </div>
            </div>
          </div>

          <p class="text-xs text-gray-500 dark:text-gray-400 mt-4">
            将令牌配置到 Claude Code / OpenClaw 等 AI Agent 后，即可用自然语言查询相册。详见
            <a href="https://trailsnap.cn/docs/guide/agent" target="_blank" class="text-primary-500 hover:underline">Agent Skills 文档</a>。
          </p>
        </div>
      </transition>
    </div>

    <!-- Desktop View -->
    <div class="hidden md:block bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
      <el-table :data="tokens" style="width: 100%" v-loading="loading" class="tokens-table">
        <el-table-column prop="name" label="令牌名称" width="200" />
        <el-table-column label="令牌值" min-width="250">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <span class="font-mono text-gray-500 dark:text-gray-400">
                {{ maskToken(row.token) }}
              </span>
              <el-button link type="primary" @click="copyToken(row.token)">
                <Copy class="w-4 h-4" />
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="isExpired(row.expires_at) ? 'danger' : 'success'" size="small" round>
              {{ isExpired(row.expires_at) ? '已过期' : '有效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="180">
          <template #default="{ row }">
            <span class="text-sm text-gray-600 dark:text-gray-300">{{ formatDate(row.expires_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            <span class="text-sm text-gray-500 dark:text-gray-400">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确定要删除这个令牌吗？删除后该令牌将失效！" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" link size="small">
                  <Trash2 class="w-4 h-4" />
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Mobile View -->
    <div class="md:hidden space-y-3" v-loading="loading">
      <div v-if="tokens.length === 0 && !loading" class="text-center py-16">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
          <Key class="w-7 h-7 text-gray-400 dark:text-gray-500" />
        </div>
        <p class="text-gray-500 dark:text-gray-400 mb-4">暂无令牌</p>
        <el-button type="primary" size="small" @click="showCreateDialog = true">创建第一个令牌</el-button>
      </div>
      <div v-for="token in tokens" :key="token.id" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 space-y-3">
        <div class="flex justify-between items-start">
          <div class="font-semibold text-gray-800 dark:text-white">{{ token.name }}</div>
          <el-tag :type="isExpired(token.expires_at) ? 'danger' : 'success'" size="small" round>
            {{ isExpired(token.expires_at) ? '已过期' : '有效' }}
          </el-tag>
        </div>

        <div class="flex items-center gap-2 bg-gray-50 dark:bg-gray-900 p-2.5 rounded-lg">
          <span class="font-mono text-xs text-gray-600 dark:text-gray-300 break-all flex-1">
            {{ maskToken(token.token) }}
          </span>
          <el-button link type="primary" size="small" @click="copyToken(token.token)">
            <Copy class="w-4 h-4" />
          </el-button>
        </div>

        <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>创建：{{ formatDate(token.created_at) }}</span>
          <span>过期：{{ formatDate(token.expires_at) }}</span>
        </div>

        <div class="pt-2 border-t border-gray-100 dark:border-gray-700 flex justify-end">
          <el-popconfirm title="确定要删除这个令牌吗？删除后该令牌将失效！" @confirm="handleDelete(token.id)">
            <template #reference>
              <el-button type="danger" size="small" text>
                <Trash2 class="w-3.5 h-3.5 mr-1" />删除
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>

    <!-- Create Token Dialog -->
    <el-dialog v-model="showCreateDialog" title="新增令牌" width="420px" style="max-width: 90%" :close-on-click-modal="false">
      <el-form ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <el-form-item label="令牌名称" prop="name">
          <el-input v-model="formData.name" placeholder="例如：Claude Code、OpenClaw" />
        </el-form-item>
        <el-form-item label="过期时间" prop="expires_at">
          <el-date-picker
            v-model="formData.expires_at"
            type="datetime"
            placeholder="选择过期时间"
            :disabled-date="disabledDate"
            :shortcuts="shortcuts"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="验证密码" prop="password">
          <el-input v-model="formData.password" type="password" show-password placeholder="请输入当前用户密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { getTokens, createToken, deleteToken, type AgentToken } from '@/api/token'
import { Copy, Plus, Trash2, Info, ChevronDown, Key } from 'lucide-vue-next'

const tokens = ref<AgentToken[]>([])
const loading = ref(false)
const guideExpanded = ref(true)

const showCreateDialog = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()

const formData = reactive({
  name: '',
  expires_at: '',
  password: ''
})

const shortcuts = [
  {
    text: '一天后',
    value: () => {
      const date = new Date()
      date.setTime(date.getTime() + 3600 * 1000 * 24)
      return date
    },
  },
  {
    text: '一周后',
    value: () => {
      const date = new Date()
      date.setTime(date.getTime() + 3600 * 1000 * 24 * 7)
      return date
    },
  },
  {
    text: '一个月后',
    value: () => {
      const date = new Date()
      date.setMonth(date.getMonth() + 1)
      return date
    },
  },
  {
    text: '一年后',
    value: () => {
      const date = new Date()
      date.setFullYear(date.getFullYear() + 1)
      return date
    },
  },
]

const rules = reactive<FormRules>({
  name: [
    { required: true, message: '请输入令牌名称', trigger: 'blur' },
    { min: 2, max: 20, message: '长度在 2 到 20 个字符', trigger: 'blur' }
  ],
  expires_at: [
    { required: true, message: '请选择过期时间', trigger: 'change' }
  ],
  password: [
    { required: true, message: '请输入密码验证身份', trigger: 'blur' }
  ]
})

const fetchTokens = async () => {
  loading.value = true
  try {
    const res = await getTokens()
    tokens.value = res.data
  } catch (error: any) {
    ElMessage.error(error.message || '获取令牌列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (valid) {
      creating.value = true
      try {
        const payload = {
          ...formData,
          expires_at: new Date(formData.expires_at).toISOString()
        }
        await createToken(payload)
        ElMessage.success('令牌创建成功')
        showCreateDialog.value = false
        formRef.value?.resetFields()
        fetchTokens()
      } catch (error: any) {
        ElMessage.error(error.message || '创建令牌失败，可能是密码错误')
      } finally {
        creating.value = false
      }
    }
  })
}

const handleDelete = async (id: string) => {
  try {
    await deleteToken(id)
    ElMessage.success('令牌已删除')
    fetchTokens()
  } catch (error: any) {
    ElMessage.error(error.message || '删除令牌失败')
  }
}

const disabledDate = (time: Date) => {
  return time.getTime() < Date.now()
}

const maskToken = (token: string) => {
  if (!token) return ''
  if (token.length <= 10) return '*'.repeat(token.length)
  return token.substring(0, 4) + '...'.padEnd(10, '*') + '...' + token.substring(token.length - 4)
}

const copyToken = async (token: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(token)
    } else {
      const textArea = document.createElement('textarea')
      textArea.value = token
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()

      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)

      if (!successful) {
        throw new Error('Fallback copy command failed')
      }
    }
    ElMessage.success('令牌已复制到剪贴板')
  } catch (err) {
    console.error('Copy failed:', err)
    ElMessage.error('复制失败，请手动选择复制')
  }
}

const isExpired = (dateStr: string) => {
  return new Date(dateStr).getTime() < Date.now()
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

onMounted(() => {
  fetchTokens()
})
</script>
