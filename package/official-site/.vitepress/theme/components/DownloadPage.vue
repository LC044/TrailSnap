<template>
  <main class="download-page">
    <header class="download-heading">
      <h1>{{ copy.title }}</h1>
      <p>{{ copy.description }}</p>
      <div role="tablist" :aria-label="copy.badge" class="install-tabs">
        <button v-for="mode in installModes" :id="`${mode.key}-tab`" :key="mode.key" type="button" role="tab"
          :aria-selected="activeMode === mode.key" :aria-controls="mode.key" :tabindex="activeMode === mode.key ? 0 : -1"
          @click="activeMode = mode.key" @keydown="onTabKeydown">{{ mode.label }}</button>
      </div>
    </header>

    <div class="download-content">
      <section v-show="activeMode === 'desktop'" id="desktop" role="tabpanel" aria-labelledby="desktop-tab" tabindex="0">
        <article class="download-card featured-card">
          <span v-if="featuredPlatform.key === detectedPlatform" class="device-badge">{{ copy.recommended }}</span>
          <div class="platform-heading">
            <span class="platform-icon"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path :d="featuredPlatform.icon" /></svg></span>
            <div><h2>{{ copy.download }} {{ featuredPlatform.name }} {{ copy.edition }}</h2><p>{{ copy.desktopTitle }}</p></div>
          </div>
          <div class="format-tags"><span v-for="format in featuredPlatform.formats" :key="format">{{ format }}</span></div>
          <a ref="featuredDownload" :href="assetUrl(featuredPlatform.key, featuredKind)" class="primary-action" :aria-busy="loadingPlatform === featuredLoadingKey" @click="onDownload(featuredPlatform.key, $event, featuredKind)">
            <Download :size="19" aria-hidden="true" />{{ loadingPlatform === featuredLoadingKey ? copy.preparing : `${copy.download} ${featuredPlatform.name} ${featuredPlatform.key === 'linux' ? 'AppImage' : copy.installer}` }}
          </a>
          <p v-if="featuredAccels.length" class="accel-options">
            <span>{{ copy.accelHint }}</span>
            <a v-for="(url, index) in featuredAccels" :key="index" :href="url" target="_blank" rel="noopener noreferrer">{{ copy.accelLines[index] }} <ArrowUpRight :size="14" aria-hidden="true" /></a>
          </p>
          <div v-if="featuredPlatform.key === 'windows'" class="portable-download">
            <a :href="assetUrl('windows', 'portable')" :aria-busy="loadingPlatform === 'windows-portable'" @click="onDownload('windows', $event, 'portable')">{{ loadingPlatform === 'windows-portable' ? copy.preparing : copy.downloadZip }}</a>
            <a v-if="portableAccel" :href="portableAccel" target="_blank" rel="noopener noreferrer">{{ copy.accelInline }}</a>
            <p>{{ copy.portableHint }}</p>
          </div>
          <div v-if="featuredPlatform.key === 'linux'" class="portable-download">
            <a :href="assetUrl('linux', 'deb')" :aria-busy="loadingPlatform === 'linux-deb'" @click="onDownload('linux', $event, 'deb')">{{ loadingPlatform === 'linux-deb' ? copy.preparing : `${copy.download} .deb` }}</a>
            <a v-if="debAccel" :href="debAccel" target="_blank" rel="noopener noreferrer">{{ copy.accelInline }}</a>
            <p>Debian / Ubuntu · x64</p>
          </div>
          <p class="mirror-download">{{ copy.mirrorHint }} <a :href="mirrorUrl" target="_blank" rel="noopener noreferrer">{{ copy.mirrorLink }} <ArrowUpRight :size="14" aria-hidden="true" /></a></p>
          <div class="release-row"><span>{{ releaseName ? `${copy.latest}: ${releaseName}` : copy.releaseHint }}</span><a :href="docLink('/docs/guide/changelog')">{{ copy.changelog }} <ArrowUpRight :size="14" aria-hidden="true" /></a></div>
        </article>

        <div class="other-platforms">
          <article v-for="item in otherPlatforms" :key="item.key" class="download-card secondary-card">
            <span class="platform-icon small"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path :d="item.icon" /></svg></span>
            <div class="min-w-0"><h3>{{ item.name }}</h3><p>{{ item.description }}</p><button type="button" class="text-action" @click="selectPlatform(item.key)">{{ copy.chooseInstaller }} <ArrowRight :size="14" aria-hidden="true" /></button></div>
          </article>
        </div>
        <p class="all-assets"><a :href="releaseUrl">{{ copy.allAssets }} <ArrowUpRight :size="14" aria-hidden="true" /></a></p>
        <p v-if="apiUnavailable" role="status" class="api-warning">{{ copy.apiUnavailable }}</p>
        <InstallPrompt :title="copy.desktopPromptTitle" :description="copy.desktopPromptDescription" :prompt="desktopPrompt" :copy-label="copy.copyPrompt" :copied-label="copy.promptCopied" :error-label="copy.copyFailed" :show-label="copy.showPrompt" :hide-label="copy.hidePrompt" />
        <details class="extension-help"><summary>{{ copy.aiTitle }}</summary><p>{{ copy.aiDescription }}</p><a :href="docLink('/docs/guide/desktop-ai-extension')">{{ copy.aiGuide }} ↗</a></details>
      </section>

      <section v-show="activeMode === 'nas'" id="nas" role="tabpanel" aria-labelledby="nas-tab" tabindex="0">
        <article class="download-card nas-card">
          <div class="platform-heading"><span class="platform-icon"><Server :size="34" aria-hidden="true" /></span><div><h2>{{ copy.nasTitle }}</h2><p>{{ copy.nasDescription }}</p></div></div>
          <div class="format-tags"><span>{{ copy.nasLabel }}</span><span>{{ copy.dockerLabel }}</span></div>
          <ol class="deployment-steps"><li v-for="(step, index) in copy.nasSteps" :key="step.title"><span class="step-number">{{ index + 1 }}</span><div><h3>{{ step.title }}</h3><p>{{ step.description }}</p></div></li></ol>
          <a :href="docLink('/docs/guide/docker/')" class="primary-action">{{ copy.dockerGuide }} <ArrowUpRight :size="18" aria-hidden="true" /></a>
          <p class="preflight-link"><a :href="docLink('/docs/guide/preflight')">{{ copy.preflight }} <ArrowUpRight :size="14" aria-hidden="true" /></a></p>
        </article>
        <InstallPrompt class="nas-prompt" :title="copy.nasPromptTitle" :description="copy.nasPromptDescription" :prompt="nasPrompt" :copy-label="copy.copyPrompt" :copied-label="copy.promptCopied" :error-label="copy.copyFailed" :show-label="copy.showPrompt" :hide-label="copy.hidePrompt" />
      </section>
    </div>
  </main>
  <ContactFooter />
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useData } from 'vitepress'
import InstallPrompt from './InstallPrompt.vue'
import ContactFooter from './ContactFooter.vue'
import { ArrowRight, ArrowUpRight, Download, Server } from 'lucide-vue-next'

type PlatformKey = 'windows' | 'macos' | 'linux'
type InstallMode = 'nas' | 'desktop'
type DownloadKind = 'installer' | 'portable' | 'appimage' | 'deb'
type ReleaseAsset = { name: string; browser_download_url: string }

const { lang } = useData()
const isEnglish = computed(() => lang.value.startsWith('en'))
const releaseUrl = 'https://github.com/LC044/TrailSnap/releases/latest'
const mirrorUrl = 'https://ug.link/dxp4800plus-72ab-9a51/filemgr/share-download/?id=35a6dea0517d482aa40526429a453e29'
const assets = ref<ReleaseAsset[]>([])
const releaseName = ref('')
const detectedPlatform = ref<PlatformKey | ''>('')
const loadingPlatform = ref<string>('')
const apiUnavailable = ref(false)
const activeMode = ref<InstallMode>('desktop')
const selectedPlatform = ref<PlatformKey | ''>('')
const featuredDownload = ref<HTMLAnchorElement | null>(null)

async function selectPlatform(platform: PlatformKey) {
  selectedPlatform.value = platform
  await nextTick()
  featuredDownload.value?.focus({ preventScroll: true })
}

const translations = {
  zh: {
    edition: '版', installer: '安装包', chooseInstaller: '选择安装包', dockerLabel: 'Docker 部署', releaseHint: '版本与文件以最新发布为准', changelog: '更新日志', showPrompt: '查看提示词', hidePrompt: '收起提示词', footer: '照片与回忆，始终属于你。',
    badge: '选择适合你的使用方式', title: '开始使用 TrailSnap',
    description: '选择照片存放的设备，开启你的私人照片库。',
    nasEntry: 'NAS / 服务器', desktopEntry: '桌面版', latest: '最新版本',
    nasLabel: 'NAS / 家庭服务器', nasTitle: '把 NAS 变成家庭照片库',
    nasDescription: '照片集中存储，同一局域网内的手机、平板和电脑都能通过浏览器访问。',
    nasSteps: [{ title: '准备设备与照片路径', description: '确认 NAS 型号、Docker 支持和存储位置。' }, { title: '按指南完成部署', description: '配置照片目录，启动 TrailSnap 服务。' }, { title: '打开你的照片库', description: '通过浏览器访问，开始整理与浏览。' }],
    dockerGuide: '查看 Docker 部署指南', preflight: '查看设备与环境要求',
    nasPromptTitle: '让 AI 帮你部署',
    nasPromptDescription: '告诉 AI 设备型号和照片路径，获取分步部署指导。',
    desktopLabel: '方式二 · 个人电脑', desktopTitle: '在自己的电脑上，整理照片与回忆',
    desktopDescription: '适合照片主要存放在电脑上的用户。选择对应系统的安装包，下载并安装；遇到不熟悉的步骤，也可以用下面的提示词请 AI 帮忙。',
    installerTitle: '下载安装包', recommended: '适合当前设备', download: '下载', preparing: '准备中…',
    downloadZip: '下载 ZIP 便携版', portableHint: '完整便携包，解压后运行 TrailSnap.exe，无需安装。',
    accelHint: '国内下载慢？', accelLines: ['加速线路一', '加速线路二'], accelInline: '国内加速',
    mirrorHint: '仍无法下载？', mirrorLink: '从国内备用地址下载',
    assetHint: '没有找到合适的安装包？查看', allAssets: '全部版本与文件',
    apiUnavailable: '暂时无法获取最新安装包。下载按钮将打开 GitHub 版本页面，你可以在那里选择对应系统的安装包。',
    desktopPromptTitle: '让 AI 帮你安装',
    desktopPromptDescription: '复制专用提示词，跟着 AI 完成安装与初始设置。',
    copyPrompt: '复制提示词', promptCopied: '已复制，粘贴给 AI 助手', copyFailed: '复制失败，请展开提示词后选中文字手动复制。',
    aiTitle: '装好后，再按需开启 AI 功能',
    aiDescription: '安装包已包含 AI 运行环境，随应用统一更新。人脸识别、文字识别和语义搜索所需模型按需下载。',
    aiGuide: '了解内置 AI 与模型准备'
  },
  en: {
    edition: '', installer: 'installer', chooseInstaller: 'Choose installer', dockerLabel: 'Docker deployment', releaseHint: 'See the latest release for available files', changelog: 'Changelog', showPrompt: 'View prompt', hidePrompt: 'Hide prompt', footer: 'Your photos and memories, always yours.',
    badge: 'Choose how you want to use it', title: 'Get started with TrailSnap',
    description: 'Choose where your photos live. Start your own photo library.',
    nasEntry: 'NAS deployment', desktopEntry: 'Desktop app', latest: 'Latest release',
    nasLabel: 'NAS / home server', nasTitle: 'Turn your NAS into a family photo library',
    nasDescription: 'For photos stored on a NAS or home server. Keep your library in one place and access it from phones, tablets, and computers on the same local network.',
    nasSteps: [{ title: 'Prepare your device and photo path', description: 'Check your NAS model, Docker support, and storage.' }, { title: 'Follow the deployment guide', description: 'Configure the photo folder and start TrailSnap.' }, { title: 'Open your photo library', description: 'Visit in your browser to start organizing and browsing.' }],
    dockerGuide: 'Read the Docker deployment guide', preflight: 'Device and setup requirements',
    nasPromptTitle: 'Let AI guide your NAS setup',
    nasPromptDescription: 'Tell AI your device model and photo path for step-by-step guidance.',
    desktopLabel: 'Option two · Personal computer', desktopTitle: 'Manage photos on your own computer',
    desktopDescription: 'For photos stored on your computer. Download the installer for your operating system. For help with installation, use the AI prompt below.',
    installerTitle: 'Download an installer', recommended: 'For this device', download: 'Download for', preparing: 'Preparing...',
    downloadZip: 'Download portable ZIP', portableHint: 'Full portable package. Extract it and run TrailSnap.exe without installing.',
    accelHint: 'Slow download?', accelLines: ['Fast link 1', 'Fast link 2'], accelInline: 'China mirror',
    mirrorHint: 'Still not working?', mirrorLink: 'Get them from an alternate mirror',
    assetHint: 'Need a different installer? Browse', allAssets: 'all versions and assets',
    apiUnavailable: 'The latest installers could not be loaded. Download buttons open the GitHub release page so you can choose an installer manually.',
    desktopPromptTitle: 'Need help installing? Ask AI',
    desktopPromptDescription: 'Copy the prompt for help with installation and initial setup.',
    copyPrompt: 'Copy AI prompt', promptCopied: 'Copied, paste into your AI assistant', copyFailed: 'Copy failed. Expand the prompt and select the text to copy manually.',
    aiTitle: 'Add AI features after installation',
    aiDescription: 'AI is included and updated with the app. Models for face recognition, OCR and semantic search are downloaded as needed.',
    aiGuide: 'About built-in AI and model preparation'
  }
}
const copy = computed(() => isEnglish.value ? translations.en : translations.zh)
const installModes = computed(() => [
  { key: 'desktop' as const, label: copy.value.desktopEntry },
  { key: 'nas' as const, label: copy.value.nasEntry }
])

function onTabKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const mode = event.key === 'Home' ? 'desktop'
    : event.key === 'End' ? 'nas'
      : activeMode.value === 'nas' ? 'desktop' : 'nas'
  activeMode.value = mode
  document.getElementById(`${mode}-tab`)?.focus()
}

const platforms = computed(() => [
  { key: 'windows' as const, name: 'Windows', icon: 'M2 3.5 11 2v9H2V3.5Zm11-1.8L22 0v11h-9V1.7ZM2 13h9v9l-9-1.5V13Zm11 0h9v11l-9-1.7V13Z', formats: ['Windows 10 / 11', 'x64'], description: isEnglish.value ? 'Windows 10/11 64-bit installer or portable ZIP.' : '适用于 Windows 10/11 的 64 位安装程序或 ZIP 便携版。' },
  { key: 'macos' as const, name: 'macOS', icon: 'M17.1 6.3c-1.4-.1-2.6.8-3.3.8-.7 0-1.8-.8-3-.8-1.6 0-3.1.9-4 2.3-1.7 2.9-.4 7.2 1.2 9.5.8 1.1 1.6 2.4 2.9 2.3 1.2 0 1.6-.7 3.1-.7s1.9.7 3.2.7c1.3 0 2.1-1.2 2.8-2.3.9-1.3 1.3-2.6 1.3-2.7-.1 0-2.5-1-2.5-3.8 0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.7-1.8ZM16.2 4.8c.6-.8 1.1-1.9 1-3-1 .1-2.2.7-2.9 1.5-.6.7-1.2 1.9-1.1 2.9 1.1.1 2.3-.6 3-1.4Z', formats: ['.dmg', isEnglish.value ? 'Apple Silicon' : 'Apple 芯片'], description: isEnglish.value ? 'Installer for Apple Silicon Macs.' : '适用于 Apple Silicon（M 系列芯片）的安装镜像。' },
  { key: 'linux' as const, name: 'Linux', icon: 'M3 3h18v18H3V3Zm2 2v14h14V5H5Zm2 3 4 4-4 4-1.4-1.4L8.2 12 5.6 9.4 7 8Zm5 7h5v2h-5v-2Z', formats: ['.AppImage', '.deb', 'x64'], description: isEnglish.value ? 'Portable AppImage or Debian/Ubuntu package.' : '可选择便携 AppImage 或 Debian/Ubuntu 安装包。' }
])
const featuredPlatform = computed(() => platforms.value.find(item => item.key === (selectedPlatform.value || detectedPlatform.value)) || platforms.value[0])
const featuredKind = computed<DownloadKind>(() => featuredPlatform.value.key === 'linux' ? 'appimage' : 'installer')
const featuredLoadingKey = computed(() => featuredKind.value === 'installer' ? featuredPlatform.value.key : `${featuredPlatform.value.key}-${featuredKind.value}`)
const otherPlatforms = computed(() => platforms.value.filter(item => item.key !== featuredPlatform.value.key))
const platformName = computed(() => detectedPlatform.value
  ? platforms.value.find(item => item.key === detectedPlatform.value)?.name
  : isEnglish.value ? 'please identify my operating system' : '请先识别我的电脑系统')

// 提示词引导助手读取最新官方文档，避免固化易过时的部署命令。
const nasPrompt = computed(() => isEnglish.value
  ? `Please help me deploy TrailSnap (https://trailsnap.cn) on my NAS or home server.
First ask me about my device (including NAS brand and model) and my photo folder path.

1. Read https://trailsnap.cn/llms.txt and use only the current official documentation.
2. Read https://trailsnap.cn/docs/guide/docker/index.md and the preflight guide linked in the documentation.
3. Check Docker support, storage, and network access. Give simple device-specific instructions explaining where to click and which paths to enter.
4. Do not delete or overwrite existing photos. Ask for my approval before executing commands or changing settings.
5. Verify the service is reachable and explain how to open my library on a phone and computer on the same local network.`
  : `我要在服务器或 NAS 上部署 TrailSnap（行影集，一个自托管照片库，官网 https://trailsnap.cn）。请先问我两个问题：
1. 我的安装设备是什么？如果是 NAS，品牌和型号是什么？
2. 我的照片路径是什么？

然后再按下面的步骤给出解答：
1. 先读取 https://trailsnap.cn/llms.txt ，找到相关文档入口。仅以最新官方文档为依据，不使用可能过时的第三方教程。
2. 阅读 Docker 部署指南（https://trailsnap.cn/docs/guide/docker/index.md）和文档中的部署前检查。
3. 根据我的设备检查 Docker 支持、存储空间和网络条件，用普通用户能理解的语言说明在哪里点击、填写什么路径，给出完整部署步骤。
4. 不要删除或覆盖已有照片。若能直接操作设备，请在执行命令或修改配置前征求我的确认。
5. 部署完成后验证服务可访问，告诉我如何在同一局域网的手机和电脑上打开照片库。`)

const desktopPrompt = computed(() => isEnglish.value
  ? `Please help me install the TrailSnap desktop app (https://trailsnap.cn). Detected platform: ${platformName.value}. First confirm my actual operating system and processor architecture.

1. Read https://trailsnap.cn/llms.txt and use only the current official documentation.
2. Read the installation and built-in desktop AI guides linked there as Markdown.
3. Select the matching installer from https://github.com/LC044/TrailSnap/releases/latest and guide me through installation and initial setup in plain language.
4. Do not delete or overwrite existing photos. Ask for my approval before installing software or changing settings.
5. Ask whether I need face recognition, OCR, or semantic search. If so, help me prepare the required models in Settings. The AI runtime is already included.
6. Verify the app launches and explain how to add my photo folder and start using it.`
  : `请帮我在我的电脑上安装 TrailSnap（行影集）桌面版（当前识别平台：${platformName.value}）。请先确认我实际使用的电脑系统和处理器架构。

1. 先读取 https://trailsnap.cn/llms.txt ，找到相关文档入口，仅以最新官方文档为依据。
2. 以 Markdown 原文阅读其中的安装指南和内置 AI 说明。
3. 从 https://github.com/LC044/TrailSnap/releases/latest 选择与我平台和架构匹配的安装包，用普通用户能理解的语言指导我完成安装和初次设置。
4. 不要删除或覆盖已有照片。若能直接操作电脑，请在安装软件或修改设置前征求我的确认。
5. 客户端装好后，询问我需要哪些 AI 能力，并在模型管理中准备对应模型；AI 运行环境已随应用安装。
6. 最后确认应用能正常启动，告诉我如何添加照片文件夹并开始使用。`)

function docLink(path: string) {
  return isEnglish.value ? `/en${path}` : path
}

function matchesPlatform(name: string, platform: PlatformKey, kind: DownloadKind = 'installer') {
  const lower = name.toLowerCase()
  // 兼容历史 Tauri 名称和统一发布名称，不匹配 CLI、AI 或增量更新包。
  if (!/^trailsnap[_-]\d/.test(lower)) return false
  if (lower.includes('cli') || lower.includes('-ai-') || lower.endsWith('.apk')) return false
  if (kind === 'portable') return platform === 'windows' && /-windows-(?:x64|x86_64)-portable\.zip$/.test(lower)
  if (kind === 'appimage' || kind === 'deb') return platform === 'linux' && lower.endsWith(kind === 'appimage' ? '.appimage' : '.deb')
  if (platform === 'windows') return lower.endsWith('-setup.exe')
  if (platform === 'macos') return lower.endsWith('.dmg')
  return lower.endsWith('.appimage') || lower.endsWith('.deb')
}

function assetUrl(platform: PlatformKey, kind: DownloadKind = 'installer') {
  return assets.value.find(asset => matchesPlatform(asset.name, platform, kind))?.browser_download_url || releaseUrl
}

// GitHub 直连在国内多数网络下不稳定，提供公共加速前缀作为备用下载线路。
const accelPrefixes = ['https://gh-proxy.com/', 'https://gh-proxy.at9.net/']

function resolvedAssetUrl(platform: PlatformKey, kind: DownloadKind = 'installer') {
  return assets.value.find(asset => matchesPlatform(asset.name, platform, kind))?.browser_download_url || ''
}

function accelLink(platform: PlatformKey, kind: DownloadKind = 'installer', index = 0) {
  const url = resolvedAssetUrl(platform, kind)
  return url ? `${accelPrefixes[index]}${url}` : ''
}

const featuredAccels = computed<string[]>(() => {
  const url = resolvedAssetUrl(featuredPlatform.value.key, featuredKind.value)
  return url ? accelPrefixes.map(prefix => `${prefix}${url}`) : []
})
const portableAccel = computed(() => accelLink('windows', 'portable'))
const debAccel = computed(() => accelLink('linux', 'deb'))

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

async function onDownload(platform: PlatformKey, event: MouseEvent, kind: DownloadKind = 'installer') {
  // 在 await 之前取消默认跳转，否则会在安装包解析完成前离开页面。
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  if (loadingPlatform.value) return
  if (assets.value.length === 0) {
    loadingPlatform.value = kind === 'installer' ? platform : `${platform}-${kind}`
    const ok = await fetchAssets()
    loadingPlatform.value = ''
    if (!ok) apiUnavailable.value = true
  }
  window.location.assign(assetUrl(platform, kind))
}

onMounted(async () => {
  const userAgent = navigator.userAgent.toLowerCase()
  // 手机浏览器可能包含 Mac/Linux 标识，不将其推荐为桌面设备。
  if (!/android|iphone|ipad|ipod/.test(userAgent) && !(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    detectedPlatform.value = userAgent.includes('windows') ? 'windows' : userAgent.includes('mac') ? 'macos' : userAgent.includes('linux') ? 'linux' : ''
  }
  apiUnavailable.value = !(await fetchAssets())
})
</script>

<style scoped>
.download-page { --vp-c-brand-soft: color-mix(in srgb, var(--vp-c-brand-1) 10%, transparent); min-height: calc(100vh - 64px); padding: 108px 24px 24px; background: var(--vp-c-bg-alt); color: var(--vp-c-text-1); }
.download-heading { max-width: 820px; margin: 0 auto 24px; text-align: center; }
h1 { margin: 0; font-size: clamp(28px, 3.3vw, 40px); font-weight: 750; line-height: 1.25; letter-spacing: -1px; }
.download-heading > p { margin: 12px 0 0; color: var(--vp-c-text-2); font-size: 15px; line-height: 1.8; }
.install-tabs { display: inline-flex; max-width: 100%; gap: 4px; margin-top: 24px; padding: 4px; border-radius: 14px; background: var(--vp-c-default-soft); }
.install-tabs button { padding: 10px 26px; border-radius: 11px; color: var(--vp-c-text-2); font-size: 14px; font-weight: 600; cursor: pointer; }
.install-tabs button[aria-selected='true'] { background: var(--vp-c-brand-3); color: white; box-shadow: 0 2px 6px var(--vp-c-brand-soft); }
.download-content { max-width: 820px; margin: auto; }
.download-card { background: var(--vp-c-bg); border: 1px solid var(--vp-c-divider); border-radius: 20px; box-shadow: 0 3px 14px rgb(0 0 0 / 2%); }
.featured-card, .nas-card { position: relative; padding: 32px; border-color: var(--vp-c-brand-1); }
.device-badge { display: block; width: fit-content; margin: -8px 0 12px auto; padding: 4px 10px; border-radius: 999px; background: var(--vp-c-brand-soft); color: var(--vp-c-brand-1); font-size: 11px; font-weight: 600; }
.platform-heading { display: flex; align-items: flex-start; gap: 20px; }
.platform-heading > div { min-width: 0; }
.platform-icon { display: inline-flex; align-items: center; justify-content: center; width: 68px; height: 68px; flex-shrink: 0; padding: 17px; border-radius: 16px; background: var(--vp-c-brand-soft); color: var(--vp-c-brand-1); }
.platform-icon svg { width: 100%; height: 100%; }
h2 { margin: 0; font-size: clamp(22px, 2.6vw, 28px); font-weight: 700; line-height: 1.45; }
.platform-heading p { margin-top: 6px; color: var(--vp-c-text-2); font-size: 14px; line-height: 1.8; }
.format-tags { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 24px 88px; }
.format-tags span { padding: 3px 10px; border-radius: 7px; background: var(--vp-c-default-soft); color: var(--vp-c-text-2); font-size: 12px; }
a { color: var(--vp-c-brand-1); text-decoration: none; }
a:hover, .text-action:hover { color: var(--vp-c-brand-2); }
.primary-action { display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 48px; padding: 12px 18px; border-radius: 10px; background: var(--vp-c-brand-3); color: white; font-size: 15px; font-weight: 600; text-align: center; line-height: 1.6; }
.primary-action:hover { background: var(--vp-c-brand-2); color: white; }
.portable-download { margin-top: 16px; text-align: center; font-size: 14px; font-weight: 600; }
.portable-download p { margin-top: 4px; font-size: 12px; font-weight: 400; line-height: 1.8; color: var(--vp-c-text-2); }
.portable-download a + a::before { content: '·'; margin: 0 10px; color: var(--vp-c-text-3); }
.accel-options { margin-top: 12px; text-align: center; font-size: 13px; color: var(--vp-c-text-2); }
.accel-options a { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; font-weight: 600; }
.accel-options a:not(:last-of-type)::after { content: '·'; margin-left: 10px; color: var(--vp-c-text-3); }
.mirror-download { margin-top: 14px; text-align: center; font-size: 13px; color: var(--vp-c-text-2); }
.mirror-download a { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; }
.release-row { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-top: 24px; padding-top: 17px; border-top: 1px solid var(--vp-c-divider); font-size: 12px; color: var(--vp-c-text-2); }
.release-row a, .all-assets a, .preflight-link a, .text-action { display: inline-flex; align-items: center; gap: 5px; }
.other-platforms { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 18px; }
.secondary-card { display: flex; align-items: flex-start; gap: 16px; padding: 22px; }
.platform-icon.small { width: 48px; height: 48px; padding: 12px; border-radius: 12px; color: var(--vp-c-text-1); }
.secondary-card h3 { font-size: 16px; font-weight: 650; }
.secondary-card p { margin: 4px 0 10px; color: var(--vp-c-text-2); font-size: 12px; line-height: 1.7; }
.text-action { color: var(--vp-c-brand-1); font-size: 12px; font-weight: 600; cursor: pointer; }
.all-assets { margin: 18px 0 22px; text-align: center; font-size: 13px; }
.api-warning { margin-bottom: 18px; padding: 14px; border-radius: 12px; background: var(--vp-c-warning-soft); color: var(--vp-c-warning-1); font-size: 13px; line-height: 1.8; }
.deployment-steps { display: grid; gap: 24px; margin: 28px 0; padding: 0; list-style: none; }
.deployment-steps li { display: flex; align-items: flex-start; gap: 16px; }
.step-number { display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; flex-shrink: 0; border-radius: 50%; background: var(--vp-c-brand-soft); color: var(--vp-c-brand-1); font-size: 17px; font-weight: 650; }
.deployment-steps h3 { margin: 0; font-size: 15px; font-weight: 650; line-height: 1.6; }
.deployment-steps p { margin: 3px 0 0; font-size: 13px; line-height: 1.8; color: var(--vp-c-text-2); }
.preflight-link { margin-top: 15px; text-align: center; font-size: 13px; }
.nas-prompt { margin-top: 18px; }
.extension-help { margin-top: 18px; color: var(--vp-c-text-2); font-size: 13px; line-height: 1.8; }
.extension-help summary { cursor: pointer; }
.extension-help p { margin: 12px 0 6px; }
.download-footer { margin-top: 28px; padding-top: 18px; border-top: 1px solid var(--vp-c-divider); text-align: center; color: var(--vp-c-text-3); font-size: 12px; }
button:focus-visible, a:focus-visible, summary:focus-visible, section:focus-visible { outline: 2px solid var(--vp-c-brand-1); outline-offset: 4px; }
@media (max-width: 959px) { .download-page { padding-top: 40px; } }
@media (max-width: 600px) { .download-page { padding: 40px 16px 24px; } .featured-card, .nas-card { padding: 22px; } .platform-heading { gap: 14px; } .platform-icon { width: 50px; height: 50px; padding: 12px; border-radius: 12px; } .format-tags { margin-left: 0; } .other-platforms { gap: 12px; } .secondary-card { flex-direction: column; gap: 12px; padding: 18px; } .install-tabs button { padding: 9px 20px; } }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto; } }
</style>

<style>

/* Keep the download route in the same palette as the official landing page. */
.custom-download-page {
  --vp-c-brand-1: #456854;
  --vp-c-brand-2: #355441;
  --vp-c-brand-3: #456854;
  --vp-c-bg: #f7f8f5;
  --vp-c-bg-alt: #f7f8f5;
  --vp-c-text-1: #25342e;
  --vp-c-text-2: #68756d;
  --vp-c-divider: #dde3db;
}
.dark .custom-download-page {
  --vp-c-brand-1: #aac4ad;
  --vp-c-brand-2: #537b60;
  --vp-c-brand-3: #456854;
  --vp-c-bg: #141c18;
  --vp-c-bg-alt: #141c18;
  --vp-c-text-1: #e9eee7;
  --vp-c-text-2: #a5afa7;
  --vp-c-divider: #354339;
}
</style>
