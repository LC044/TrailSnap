<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 px-5 py-[max(2rem,env(safe-area-inset-top))] flex items-center justify-center">
    <section class="w-full max-w-lg rounded-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 sm:p-8 shadow-lg">
      <div class="flex items-center gap-3 mb-2">
        <div class="w-11 h-11 rounded-xl bg-primary-500 text-white flex items-center justify-center">
          <Server class="w-6 h-6" />
        </div>
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">连接 TrailSnap</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400">配置你的自托管服务</p>
        </div>
      </div>

      <p class="mt-6 text-sm leading-6 text-gray-600 dark:text-gray-300">
        输入主后端地址，不需要添加 <code>/api</code>。Docker 默认示例为
        <code>http://192.168.1.10:8800</code>，请将 IP 替换为服务器在局域网中的地址。
      </p>

      <form class="mt-5 space-y-4" @submit.prevent="connectAndSave">
        <label class="block">
          <span class="block mb-2 text-sm font-medium text-gray-700 dark:text-gray-200">服务器地址</span>
          <input
            v-model.trim="address"
            type="text"
            inputmode="url"
            autocomplete="url"
            placeholder="http://192.168.1.10:8800"
            class="w-full rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-4 py-3 text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          />
        </label>

        <div class="rounded-lg bg-amber-50 dark:bg-amber-950/30 p-3 text-xs leading-5 text-amber-800 dark:text-amber-200">
          局域网可使用 HTTP；通过公网访问时建议配置 HTTPS，以保护账号、令牌和照片数据。
        </div>

        <p v-if="errorMessage" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ errorMessage }}</p>
        <p v-if="successMessage" class="text-sm text-green-600 dark:text-green-400">{{ successMessage }}</p>

        <button
          type="submit"
          :disabled="saving || !address"
          class="w-full rounded-xl bg-primary-600 hover:bg-primary-700 text-white py-3 font-medium transition disabled:opacity-50 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {{ saving ? '正在测试连接…' : '测试并保存' }}
        </button>

        <button
          v-if="hasExistingConfig"
          type="button"
          class="w-full rounded-xl border border-gray-300 dark:border-gray-600 py-3 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="goBack"
        >
          取消
        </button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Server } from 'lucide-vue-next'
import { getServerUrl, hasConfiguredServer, saveServerUrl, testServerConnection } from '@/config/server'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const address = ref(getServerUrl())
const saving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const hasExistingConfig = computed(() => hasConfiguredServer())

const connectAndSave = async () => {
  saving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const previous = getServerUrl()
    const normalized = await testServerConnection(address.value)
    await saveServerUrl(normalized)
    if (previous && previous !== normalized) userStore.resetState()
    successMessage.value = '连接成功，已保存服务器地址'
    window.setTimeout(() => {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/login'
      router.replace(redirect)
    }, 500)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

const goBack = () => {
  if (window.history.length > 1) router.back()
  else router.replace(userStore.token ? '/settings' : '/login')
}
</script>
