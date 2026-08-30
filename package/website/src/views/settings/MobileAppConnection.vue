<template>
  <div class="mx-auto max-w-4xl space-y-6">
    <header class="space-y-2">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">连接手机 App</h1>
      <p class="text-sm leading-6 text-gray-600 dark:text-gray-300">
        在手机 TrailSnap App 中点击“扫描二维码”，即可使用与当前网页相同的服务地址。
      </p>
    </header>

    <section class="grid gap-6 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800 md:grid-cols-[minmax(0,1fr)_18rem] md:p-7">
      <div class="space-y-5">
        <label class="block">
          <span class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-200">手机可访问的 TrailSnap 地址</span>
          <input
            v-model.trim="address"
            type="text"
            inputmode="url"
            autocomplete="url"
            class="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-900 placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white dark:placeholder:text-gray-500"
            placeholder="http://192.168.1.10:8082"
          />
        </label>

        <button
          type="button"
          class="text-sm text-primary-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-primary-400"
          @click="address = currentOrigin"
        >
          使用当前网页地址：{{ currentOrigin }}
        </button>

        <p v-if="addressError" role="alert" class="text-sm text-red-600 dark:text-red-400">
          {{ addressError }}
        </p>
        <div v-else-if="isLoopbackAddress" class="rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          当前地址使用 localhost 或 127.0.0.1，手机无法访问。请改成这台电脑的局域网 IP 地址。
        </div>

        <ol class="space-y-3 text-sm leading-6 text-gray-600 dark:text-gray-300">
          <li><span class="mr-2 font-semibold text-primary-600 dark:text-primary-400">1.</span>让手机和电脑连接同一个路由器 Wi-Fi。</li>
          <li><span class="mr-2 font-semibold text-primary-600 dark:text-primary-400">2.</span>打开手机 TrailSnap App，进入“连接 TrailSnap”。</li>
          <li><span class="mr-2 font-semibold text-primary-600 dark:text-primary-400">3.</span>点击“扫描二维码”，扫描右侧二维码。</li>
          <li><span class="mr-2 font-semibold text-primary-600 dark:text-primary-400">4.</span>确认地址后点击“测试并保存”，然后登录。</li>
        </ol>

        <div class="rounded-xl bg-gray-50 p-4 text-xs leading-5 text-gray-500 dark:bg-gray-900 dark:text-gray-400">
          手机热点、访客 Wi-Fi、AP 隔离或服务器防火墙可能阻止手机访问电脑。连接前可先在手机浏览器中打开上面的地址进行确认。
        </div>
      </div>

      <div class="flex flex-col items-center justify-center rounded-2xl bg-gray-50 p-5 text-center dark:bg-gray-900">
        <template v-if="qrCode && !isLoopbackAddress">
          <img :src="qrCode" alt="TrailSnap 手机 App 连接二维码" class="h-52 w-52 rounded-xl bg-white p-2" />
          <p class="mt-3 max-w-full break-all text-xs text-gray-500 dark:text-gray-400">{{ normalizedAddress }}</p>
          <button
            type="button"
            class="mt-4 w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            @click="copyConnectionLink"
          >
            复制连接链接
          </button>
        </template>
        <div v-else class="py-12 text-sm leading-6 text-gray-500 dark:text-gray-400">
          输入手机可以访问的地址后，这里会生成二维码。
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'
import { normalizeServerUrl } from '@/config/server'
import { createConnectionDeepLink } from '@/config/serverConnection'

const currentOrigin = window.location.origin
const address = ref(currentOrigin)
const qrCode = ref('')

const normalizedAddress = computed(() => {
  try {
    return normalizeServerUrl(address.value)
  } catch {
    return ''
  }
})

const addressError = computed(() => {
  if (!address.value) return '请输入手机可以访问的 TrailSnap 地址'
  if (!normalizedAddress.value) return '请输入完整的 HTTP 或 HTTPS 地址，不要添加额外路径'
  return ''
})

const isLoopbackAddress = computed(() => {
  if (!normalizedAddress.value) return false
  const hostname = new URL(normalizedAddress.value).hostname
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
})

let qrGeneration = 0
watch(normalizedAddress, async value => {
  const generation = ++qrGeneration
  if (!value || isLoopbackAddress.value) {
    qrCode.value = ''
    return
  }
  try {
    const dataUrl = await QRCode.toDataURL(createConnectionDeepLink(value), {
      width: 360,
      margin: 1,
      errorCorrectionLevel: 'M',
    })
    if (generation === qrGeneration) qrCode.value = dataUrl
  } catch {
    if (generation === qrGeneration) qrCode.value = ''
  }
}, { immediate: true })

async function writeClipboard(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  if (!copied) throw new Error('copy failed')
}

async function copyConnectionLink() {
  if (!normalizedAddress.value || isLoopbackAddress.value) return
  try {
    await writeClipboard(createConnectionDeepLink(normalizedAddress.value))
    ElMessage.success('连接链接已复制，可发送到安装了 TrailSnap App 的手机')
  } catch {
    ElMessage.error('复制失败，请直接使用二维码连接')
  }
}
</script>
