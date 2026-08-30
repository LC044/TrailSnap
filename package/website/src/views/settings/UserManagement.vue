<template>
  <div class="">
    <div class="mb-4 md:mb-6 flex justify-between items-center">
      <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">用户管理</h2>
      <div class="flex gap-2">
        <el-button type="primary" @click="showCreateDialog = true">添加用户</el-button>
        <el-button v-if="!isTauriApp()" type="danger" @click="handleLogout" class="hidden md:inline-flex">退出登录</el-button>
        <el-button v-if="!isTauriApp()" type="danger" size="small" @click="handleLogout" class="md:hidden">退出</el-button>
      </div>
    </div>

    <!-- Desktop View -->
    <div class="hidden md:block bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
      <el-table :data="users" style="width: 100%" v-loading="loading">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column label="角色">
          <template #default="{ row }">
            <el-tag :type="row.is_superuser ? 'danger' : 'info'">
              {{ row.is_superuser ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button type="primary" link @click="openResetPassword(row)">重置密码</el-button>
            <el-popconfirm
              v-if="currentUser?.id !== row.id"
              title="确定删除该用户吗？这将删除其所有相册和照片数据（保留原文件）。"
              @confirm="handleDelete(row)"
              width="250"
            >
              <template #reference>
                <el-button type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
            <span v-else class="text-gray-400 text-sm ml-2">当前用户</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Mobile View -->
    <div class="md:hidden space-y-4" v-loading="loading">
      <div v-if="users.length === 0 && !loading" class="text-center text-gray-500 py-8">
        暂无用户数据
      </div>
      <div v-for="user in users" :key="user.id" class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="flex justify-between items-start mb-3">
          <div>
            <div class="font-bold text-gray-800 dark:text-white text-lg">{{ user.username }}</div>
            <div class="text-sm text-gray-500 mt-1">{{ user.email }}</div>
          </div>
          <el-tag :type="user.is_superuser ? 'danger' : 'info'" size="small">
            {{ user.is_superuser ? '管理员' : '普通用户' }}
          </el-tag>
        </div>
        
        <div class="flex justify-between items-center pt-3 border-t dark:border-gray-700">
          <div class="flex items-center gap-2">
             <span class="text-sm text-gray-500">状态:</span>
             <el-tag :type="user.is_active ? 'success' : 'danger'" size="small">
              {{ user.is_active ? '正常' : '禁用' }}
             </el-tag>
          </div>
          
          <div class="flex gap-2">
            <el-button type="primary" size="small" plain @click="openResetPassword(user)">重置密码</el-button>
            <div v-if="currentUser?.id !== user.id">
              <el-popconfirm
                title="确定删除该用户吗？"
                @confirm="handleDelete(user)"
                width="200"
              >
                <template #reference>
                  <el-button type="danger" size="small" plain>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
            <span v-else class="text-gray-400 text-xs self-center">当前用户</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Create User Dialog -->
    <el-dialog v-model="showCreateDialog" title="添加用户" width="500px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="createForm.email" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="createForm.is_superuser" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" @click="handleCreateUser" :loading="createLoading">确定</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog v-model="showResetDialog" title="重置密码" width="400px">
      <el-form :model="resetForm" label-width="80px">
        <el-form-item label="新密码">
          <el-input v-model="resetForm.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showResetDialog = false">取消</el-button>
          <el-button type="primary" @click="handleResetPassword" :loading="resetLoading">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { userService, type User } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'
import { isTauriApp } from '@/config/server'

const userStore = useUserStore()
const router = useRouter()
const users = ref<User[]>([])
const loading = ref(false)

const currentUser = computed(() => userStore.userInfo)

const showCreateDialog = ref(false)
const createLoading = ref(false)
const createForm = reactive({
  username: '',
  email: '',
  password: '',
  is_superuser: false
})

const showResetDialog = ref(false)
const resetLoading = ref(false)
const resetForm = reactive({
  userId: '',
  password: ''
})

const fetchUsers = async () => {
  loading.value = true
  try {
    users.value = await userService.getUsers()
  } catch (error) {
    ElMessage.error('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreateUser = async () => {
  if (!createForm.username || !createForm.email || !createForm.password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  createLoading.value = true
  try {
    await userService.createUser(createForm)
    ElMessage.success('用户创建成功')
    showCreateDialog.value = false
    createForm.username = ''
    createForm.email = ''
    createForm.password = ''
    createForm.is_superuser = false
    await fetchUsers()
  } catch (error: any) {
    const msg = error.response?.data?.detail || '创建用户失败'
    ElMessage.error(msg)
  } finally {
    createLoading.value = false
  }
}

const openResetPassword = (user: User) => {
  resetForm.userId = user.id
  resetForm.password = ''
  showResetDialog.value = true
}

const handleResetPassword = async () => {
  if (!resetForm.password || resetForm.password.length < 6) {
    ElMessage.warning('密码至少需要6位')
    return
  }
  resetLoading.value = true
  try {
    await userService.resetPassword(resetForm.userId, { password: resetForm.password })
    ElMessage.success('密码重置成功')
    showResetDialog.value = false
  } catch (error: any) {
    const msg = error.response?.data?.detail || '重置密码失败'
    ElMessage.error(msg)
  } finally {
    resetLoading.value = false
  }
}

const handleLogout = async () => {
  await userStore.logout()
  router.push('/login')
}

const handleDelete = async (user: User) => {
  try {
    await userService.deleteUser(user.id)
    ElMessage.success('用户删除成功')
    await fetchUsers()
  } catch (error) {
    ElMessage.error('删除用户失败')
  }
}

onMounted(() => {
  fetchUsers()
  // Ensure we have current user info
  if (!userStore.userInfo) {
    userStore.getUserInfo()
  }
})
</script>
