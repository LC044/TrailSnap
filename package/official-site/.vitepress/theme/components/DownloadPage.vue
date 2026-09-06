<template>
  <main class="min-h-screen bg-gray-50 text-gray-900 dark:bg-[#141414] dark:text-gray-100">
    <section class="border-b border-gray-200 bg-white px-4 pb-16 pt-28 dark:border-gray-800 dark:bg-[#141414]">
      <div class="mx-auto max-w-6xl text-center">
        <span class="inline-flex rounded-full bg-blue-50 px-4 py-1.5 text-sm font-semibold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
          {{ copy.badge }}
        </span>
        <h1 class="mt-5 text-4xl font-bold tracking-tight sm:text-5xl">{{ copy.title }}</h1>
        <p class="mx-auto mt-5 max-w-2xl text-base leading-7 text-gray-600 dark:text-gray-400 sm:text-lg">
          {{ copy.description }}
        </p>
        <p v-if="releaseName" class="mt-3 text-sm text-gray-500 dark:text-gray-500">{{ copy.latest }}：{{ releaseName }}</p>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-4 py-14">
      <div class="grid gap-5 md:grid-cols-3">
        <article
          v-for="item in platforms"
          :key="item.key"
          class="relative flex flex-col rounded-2xl border bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg dark:bg-gray-900"
          :class="item.key === detectedPlatform ? 'border-blue-500 ring-2 ring-blue-500/15' : 'border-gray-200 dark:border-gray-800'"
        >
          <span v-if="item.key === detectedPlatform" class="absolute right-4 top-4 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
            {{ copy.recommended }}
          </span>
          <div class="text-4xl" aria-hidden="true">{{ item.icon }}</div>
          <h2 class="mt-5 text-xl font-bold">{{ item.name }}</h2>
          <p class="mt-2 min-h-12 text-sm leading-6 text-gray-600 dark:text-gray-400">{{ item.description }}</p>
          <div class="mt-5 flex flex-wrap gap-2">
            <span v-for="format in item.formats" :key="format" class="rounded-md bg-gray-100 px-2 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">{{ format }}</span>
          </div>
          <a
            :href="assetUrl(item.key)"
            @click="onDownload(item.key, $event)"
            class="mt-6 inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white no-underline transition hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900"
          >
            <span v-if="loadingPlatform === item.key" class="inline-flex items-center gap-2">
              <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
              {{ isEnglish ? 'Preparing…' : '准备中…' }}
            </span>
            <span v-else>{{ copy.download }} {{ item.name }}</span>
          </a>
        </article>
      </div>

      <div class="mt-5 rounded-xl border border-gray-200 bg-white px-5 py-4 text-sm text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
        {{ copy.assetHint }}
        <a :href="releaseUrl" class="font-semibold text-blue-600 dark:text-blue-400">{{ copy.allAssets }}</a>
      </div>
      <div v-if="apiUnavailable" class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-300">
        {{ isEnglish ? 'The latest release list could not be loaded (GitHub API is unreachable). The button now opens the GitHub Release page where you can pick the installer manually.' : '暂时无法获取最新安装包列表（GitHub API 无法访问）。点击下载按钮将跳转到 GitHub Release 页面，你可以在那里手动选择对应平台的安装包。' }}
      </div>
    </section>

    <section class="border-y border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900/40">
      <div class="mx-auto grid max-w-6xl gap-8 px-4 py-14 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <span class="text-sm font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">Docker</span>
          <h2 class="mt-2 text-3xl font-bold">{{ copy.dockerTitle }}</h2>
          <p class="mt-4 max-w-2xl leading-7 text-gray-600 dark:text-gray-400">{{ copy.dockerDescription }}</p>
          <div class="mt-6 flex flex-wrap gap-3">
            <a :href="docLink('/docs/guide/docker/')" class="rounded-xl bg-gray-900 px-5 py-3 font-semibold text-white no-underline transition hover:bg-gray-700 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200">{{ copy.dockerGuide }}</a>
            <a :href="docLink('/docs/guide/preflight')" class="rounded-xl border border-gray-300 px-5 py-3 font-semibold text-gray-700 no-underline transition hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800">{{ copy.preflight }}</a>
          </div>
        </div>
        <div class="rounded-2xl bg-gray-950 p-6 text-gray-100 shadow-xl">
          <div class="mb-4 flex gap-1.5"><span v-for="color in ['bg-red-400','bg-amber-400','bg-emerald-400']" :key="color" class="h-3 w-3 rounded-full" :class="color"></span></div>
          <code class="block whitespace-pre-wrap text-sm leading-7 text-emerald-300">{{ dockerCommand }}</code>
        </div>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-4 py-14">
      <div class="rounded-3xl bg-gradient-to-br from-blue-600 to-indigo-700 p-8 text-white shadow-xl sm:p-10">
        <div class="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <h2 class="text-2xl font-bold">{{ copy.aiTitle }}</h2>
            <p class="mt-3 max-w-3xl leading-7 text-blue-100">{{ copy.aiDescription }}</p>
          </div>
          <a :href="docLink('/docs/guide/desktop-ai-extension')" class="rounded-xl bg-white px-5 py-3 text-center font-semibold text-blue-700 no-underline transition hover:bg-blue-50">{{ copy.aiGuide }}</a>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useData } from 'vitepress'

type PlatformKey = 'windows' | 'macos' | 'linux'
type ReleaseAsset = { name: string; browser_download_url: string }

const { lang } = useData()
const releaseUrl = 'https://github.com/LC044/TrailSnap/releases/latest'
const assets = ref<ReleaseAsset[]>([])
const releaseName = ref('')
const detectedPlatform = ref<PlatformKey | ''>('')
const isEnglish = computed(() => lang.value.startsWith('en'))
const loadingPlatform = ref<PlatformKey | ''>('')
// 所有平台都尝试过且都拿不到直链时，提示用户走 Release 页手动下载
const apiUnavailable = ref(false)

const translations = {
  zh: {
    badge: '桌面安装包与自托管部署', title: '下载 TrailSnap', description: '桌面版适合个人电脑快速使用；Docker 版适合 NAS、家庭服务器和多设备访问。',
    latest: '最新版本', recommended: '适合当前设备', download: '下载', assetHint: '找不到匹配的安装包时，按钮会打开 GitHub Release 页面，你也可以直接查看', allAssets: '全部版本与文件',
    dockerTitle: '在 NAS 或服务器上部署', dockerDescription: '适合集中管理照片库，并通过局域网在手机和电脑上访问。', dockerGuide: '查看 Docker 部署指南', preflight: '部署前检查',
    aiTitle: 'AI 扩展按需安装', aiDescription: '桌面版的人脸识别、OCR、图片分类、语义检索和本地大模型能力由独立 AI 扩展提供。先安装基础客户端，再在设置中在线安装或离线导入与你的平台匹配的扩展包。', aiGuide: '查看 AI 扩展说明'
  },
  en: {
    badge: 'Desktop installers and self-hosting', title: 'Download TrailSnap', description: 'Use the desktop app for a quick personal setup, or Docker for a NAS, home server, and multi-device access. The desktop base app stays lightweight while AI features are installed on demand.',
    latest: 'Latest release', recommended: 'Recommended for this device', download: 'Download for', assetHint: 'If a matching installer cannot be detected, the button opens the latest GitHub Release. You can also browse', allAssets: 'all versions and assets',
    dockerTitle: 'Deploy on a NAS or server', dockerDescription: 'Docker Compose starts the frontend, backend, PostgreSQL, and AI service for a centrally managed photo library accessible across your LAN.', dockerGuide: 'Docker deployment guide', preflight: 'Preflight checklist',
    aiTitle: 'Install AI capabilities on demand', aiDescription: 'Face recognition, OCR, classification, semantic search, and local LLM features in the desktop app are delivered as a separate AI extension. Install the base app first, then download it in Settings or import the matching offline package.', aiGuide: 'AI extension guide'
  }
}
const copy = computed(() => isEnglish.value ? translations.en : translations.zh)

const platforms = computed(() => isEnglish.value ? [
  { key: 'windows' as const, name: 'Windows', icon: '▦', formats: ['.exe', 'x64'], description: 'Windows 10/11 64-bit installer.' },
  { key: 'macos' as const, name: 'macOS', icon: '●', formats: ['.dmg', 'Apple Silicon'], description: 'Installer for Apple Silicon Macs.' },
  { key: 'linux' as const, name: 'Linux', icon: '◆', formats: ['.AppImage', '.deb', 'x64'], description: 'Portable AppImage or Debian/Ubuntu package.' }
] : [
  { key: 'windows' as const, name: 'Windows', icon: '▦', formats: ['.exe', 'x64'], description: '适用于 Windows 10/11 的 64 位安装程序。' },
  { key: 'macos' as const, name: 'macOS', icon: '●', formats: ['.dmg', 'Apple 芯片'], description: '适用于 Apple Silicon（M 系列芯片）的安装镜像。' },
  { key: 'linux' as const, name: 'Linux', icon: '◆', formats: ['.AppImage', '.deb', 'x64'], description: '可选择便携 AppImage 或 Debian/Ubuntu 安装包。' }
])

const dockerCommand = computed(() => isEnglish.value
  ? 'curl -fsSL https://trailsnap.cn/install.sh | bash\n\n# Then open http://<server-ip>:3180'
  : 'curl -fsSL https://trailsnap.cn/install.sh | bash\n\n# 完成后访问 http://<服务器IP>:3180')

function docLink(path: string) {
  return isEnglish.value ? `/en${path}` : path
}

function matchesPlatform(name: string, platform: PlatformKey) {
  const lower = name.toLowerCase()
  // Tauri desktop bundles use the `TrailSnap_<version>_<arch>` naming
  // convention. Release assets also contain CLI executables, AI archives and
  // Android packages, so matching by file extension alone is unsafe.
  if (!lower.startsWith('trailsnap_')) return false
  if (lower.includes('cli') || lower.includes('-ai-') || lower.endsWith('.apk')) return false
  if (platform === 'windows') return lower.endsWith('-setup.exe')
  if (platform === 'macos') return lower.endsWith('.dmg')
  return lower.endsWith('.appimage') || lower.endsWith('.deb')
}

function assetUrl(platform: PlatformKey) {
  return assets.value.find(asset => matchesPlatform(asset.name, platform))?.browser_download_url || releaseUrl
}

// 尝试从 GitHub API 拉取最新 Release 的资产列表；失败返回 false
async function fetchAssets(): Promise<boolean> {
  try {
    const response = await fetch('https://api.github.com/repos/LC044/TrailSnap/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' }
    })
    if (!response.ok) return false
    const release = await response.json()
    releaseName.value = release.name || release.tag_name || ''
    assets.value = Array.isArray(release.assets) ? release.assets : []
    return assets.value.length > 0
  } catch {
    return false
  }
}

// 点击下载：优先用已加载的资产直链；若未加载则临时再拉一次，
// 仍失败才 fallback 到 Release 页，避免「API 拉取失败就跳中间页」的鲁棒性问题。
async function onDownload(platform: PlatformKey, event: MouseEvent) {
  if (assets.value.length === 0) {
    loadingPlatform.value = platform
    const ok = await fetchAssets()
    loadingPlatform.value = ''
    if (!ok) {
      apiUnavailable.value = true
      return // 让 <a> 的默认行为跳转到 releaseUrl（兜底）
    }
  }
  const url = assetUrl(platform)
  if (url !== releaseUrl) {
    event.preventDefault()
    window.location.href = url
  }
}

onMounted(async () => {
  const userAgent = navigator.userAgent.toLowerCase()
  detectedPlatform.value = userAgent.includes('windows') ? 'windows' : userAgent.includes('mac') ? 'macos' : userAgent.includes('linux') ? 'linux' : ''
  await fetchAssets()
  // 若首屏 API 失败，仍保留 releaseUrl 作为兜底，无需额外处理
})
</script>
