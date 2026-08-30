<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 px-5 py-[max(2rem,env(safe-area-inset-top))] flex items-center justify-center">
    <section class="w-full max-w-lg rounded-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 sm:p-8 shadow-lg">
      <div class="flex items-center gap-3 mb-2">
        <div class="w-11 h-11 rounded-xl bg-primary-500 text-white flex items-center justify-center">
          <Server class="w-6 h-6" />
        </div>
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">连接 TrailSnap</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400">网页和 App 使用同一个地址</p>
        </div>
      </div>

      <p class="mt-6 text-sm leading-6 text-gray-600 dark:text-gray-300">
        输入 TrailSnap 访问地址，不需要添加 <code>/api</code>。它与浏览器中打开的地址完全相同，
        例如 <code>http://192.168.1.10:8082</code>。
      </p>

      <form class="mt-5 space-y-4" @submit.prevent="connectAndSave">
        <label class="block">
          <span class="block mb-2 text-sm font-medium text-gray-700 dark:text-gray-200">服务器地址</span>
          <input
            v-model.trim="address"
            type="text"
            inputmode="url"
            autocomplete="url"
            placeholder="http://192.168.1.10:8082"
            class="w-full rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-4 py-3 text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <button
            type="button"
            :disabled="scanning"
            class="rounded-xl border border-gray-300 dark:border-gray-600 py-3 px-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="scanQrCode"
          >
            <QrCode class="inline-block w-4 h-4 mr-1.5 -mt-0.5" />
            {{ scanning ? '正在扫码…' : '扫描二维码' }}
          </button>
          <button
            type="button"
            :disabled="discovering"
            class="rounded-xl border border-gray-300 dark:border-gray-600 py-3 px-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="discoverServers"
          >
            <Radar class="inline-block w-4 h-4 mr-1.5 -mt-0.5" />
            {{ discovering ? '正在发现…' : '发现附近服务' }}
          </button>
        </div>

        <div v-if="discoveredServers.length" class="space-y-2">
          <p class="text-xs font-medium text-gray-600 dark:text-gray-300">发现的 TrailSnap</p>
          <button
            v-for="server in discoveredServers"
            :key="server"
            type="button"
            class="w-full flex items-center justify-between rounded-xl bg-gray-50 dark:bg-gray-900 px-3 py-2.5 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            @click="address = server"
          >
            <span class="truncate">{{ server }}</span>
            <span class="ml-3 text-primary-600 dark:text-primary-400">选择</span>
          </button>
        </div>

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

      <div v-if="shareQrCode" class="mt-7 border-t border-gray-200 dark:border-gray-700 pt-6 text-center">
        <p class="text-sm font-medium text-gray-700 dark:text-gray-200">在另一台设备上连接</p>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">使用 TrailSnap App 扫描此二维码</p>
        <img :src="shareQrCode" alt="TrailSnap 连接二维码" class="mx-auto mt-3 w-40 h-40 rounded-xl bg-white p-2" />
        <button
          type="button"
          class="mt-2 text-sm text-primary-600 dark:text-primary-400 hover:underline focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="copyConnectionLink"
        >
          复制连接链接
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { QrCode, Radar, Server } from 'lucide-vue-next'
import { getServerUrl, hasConfiguredServer, isMobileApp, saveServerUrl, testServerConnection } from '@/config/server'
import {
  createConnectionDeepLink,
  discoverTrailSnapServers,
  scanConnectionQrCode,
} from '@/config/serverConnection'
import { useUserStore } from '@/stores/user'
import QRCode from 'qrcode'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const address = ref(getServerUrl())
const saving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const scanning = ref(false)
const discovering = ref(false)
const discoveredServers = ref<string[]>([])
const shareQrCode = ref('')
const hasExistingConfig = computed(() => hasConfiguredServer())

const updateShareQrCode = async () => {
  try {
    const value = address.value || (isMobileApp() ? '' : window.location.origin)
    if (!value) {
      shareQrCode.value = ''
      return
    }
    shareQrCode.value = await QRCode.toDataURL(createConnectionDeepLink(value), {
      width: 320,
      margin: 1,
      errorCorrectionLevel: 'M',
    })
  } catch {
    shareQrCode.value = ''
  }
}

onMounted(() => {
  if (typeof route.query.url === 'string') address.value = route.query.url
  void updateShareQrCode()
})
watch(address, () => void updateShareQrCode())

const scanQrCode = async () => {
  scanning.value = true
  errorMessage.value = ''
  try {
    address.value = await scanConnectionQrCode()
    successMessage.value = '已识别连接地址，请测试并保存'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法识别二维码'
  } finally {
    scanning.value = false
  }
}

const discoverServers = async () => {
  discovering.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    discoveredServers.value = await discoverTrailSnapServers()
    if (discoveredServers.value.length === 1) address.value = discoveredServers.value[0]
    successMessage.value = discoveredServers.value.length
      ? `发现 ${discoveredServers.value.length} 个可用服务`
      : '暂未发现服务，请确认设备连接同一局域网或使用二维码'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '局域网发现失败'
  } finally {
    discovering.value = false
  }
}

const copyConnectionLink = async () => {
  try {
    const value = address.value || (isMobileApp() ? '' : window.location.origin)
    if (!value) throw new Error('missing server URL')
    await navigator.clipboard.writeText(createConnectionDeepLink(value))
    successMessage.value = '连接链接已复制'
  } catch {
    errorMessage.value = '复制失败，请使用二维码连接'
  }
}

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

const goBack = useAppBack(() => router.replace(userStore.token ? '/settings' : '/login'))
</script>
