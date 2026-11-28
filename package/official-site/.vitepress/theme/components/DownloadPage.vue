<template>
  <div class="trailsnap-home trailsnap-subpage" :class="{ 'is-en': isEnglish }">
    <SiteChrome current="download" />
    <main class="subpage-main download-page">
      <section class="subpage-hero">
        <div class="sub-wrap">
          <p class="kicker"><span>01</span>{{ isEnglish ? 'DOWNLOAD / INSTALL' : '下载 / DOWNLOAD' }}</p>
          <div class="download-hero-grid">
            <div>
              <h1 class="subpage-title">
                {{ isEnglish ? 'Bring your photos' : '准备好照片' }}<br>
                <span class="title-accent">{{ isEnglish ? ' home.' : '开始你的行影集' }}</span>
              </h1>
              <p class="subpage-lead">{{ copy.description }}</p>
            </div>
            <aside class="release-card" aria-live="polite">
              <span>LATEST RELEASE</span>
              <strong>{{ releaseName || (isEnglish ? 'Checking…' : '正在检查…') }}</strong>
              <small>{{ isEnglish ? 'Windows · macOS · Linux · fnOS · Android' : 'Windows · macOS · Linux · 飞牛 fnOS · Android' }}</small>
            </aside>
          </div>
          <div role="tablist" :aria-label="copy.badge" class="install-tabs">
            <button v-for="mode in installModes" :id="`${mode.key}-tab`" :key="mode.key" type="button" role="tab"
              :aria-selected="activeMode === mode.key" :aria-controls="mode.key" :tabindex="activeMode === mode.key ? 0 : -1"
              @click="activeMode = mode.key" @keydown="onTabKeydown">{{ mode.label }}</button>
          </div>
        </div>
      </section>

      <div class="sub-wrap download-content">
        <section v-show="activeMode === 'desktop'" id="desktop" role="tabpanel" aria-labelledby="desktop-tab" tabindex="0">
          <article class="download-card featured-card">
            <span v-if="featuredPlatform.key === detectedPlatform" class="device-badge">{{ copy.recommended }}</span>
            <div class="featured-grid">
              <div class="featured-main">
                <div class="platform-heading">
                  <span class="platform-icon"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path :d="featuredPlatform.icon" /></svg></span>
                  <div><h2>{{ copy.download }} {{ featuredPlatform.name }} {{ copy.edition }}</h2><p>{{ copy.desktopTitle }}</p></div>
                </div>
                <div class="format-tags"><span v-for="format in featuredPlatform.formats" :key="format">{{ format }}</span></div>
              </div>
              <div class="featured-side">
                <a ref="featuredDownload" :href="assetUrl(featuredPlatform.key, featuredKind)" class="primary-action" :aria-busy="loadingPlatform === featuredLoadingKey" @click="onDownload(featuredPlatform.key, $event, featuredKind)">
                  <Download :size="18" aria-hidden="true" />{{ loadingPlatform === featuredLoadingKey ? copy.preparing : `${copy.download} ${featuredPlatform.name} ${featuredPlatform.key === 'linux' ? 'AppImage' : copy.installer}` }}
                </a>
                <p v-if="featuredAccels.length" class="accel-options">
                  <span>{{ copy.accelHint }}</span>
                  <a v-for="(url, index) in featuredAccels" :key="index" :href="url" target="_blank" rel="noopener noreferrer">{{ copy.accelLines[index] }} <ArrowUpRight :size="13" aria-hidden="true" /></a>
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
                <p class="mirror-download">{{ copy.mirrorHint }} <a :href="mirrorUrl" target="_blank" rel="noopener noreferrer">{{ copy.mirrorLink }} <ArrowUpRight :size="13" aria-hidden="true" /></a></p>
              </div>
            </div>
            <div class="release-row"><span>{{ releaseName ? `${copy.latest}: ${releaseName}` : copy.releaseHint }}</span><a :href="docLink('/docs/guide/changelog')">{{ copy.changelog }} <ArrowUpRight :size="13" aria-hidden="true" /></a></div>
          </article>

          <div class="other-platforms">
            <article v-for="item in otherPlatforms" :key="item.key" class="download-card secondary-card">
              <span class="platform-icon small"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path :d="item.icon" /></svg></span>
              <div class="min-w-0"><h3>{{ item.name }}</h3><p>{{ item.description }}</p><button type="button" class="text-action" @click="selectPlatform(item.key)">{{ copy.chooseInstaller }} <ArrowRight :size="13" aria-hidden="true" /></button></div>
            </article>
          </div>
          <p class="all-assets"><a :href="releaseUrl">{{ copy.allAssets }} <ArrowUpRight :size="13" aria-hidden="true" /></a></p>
          <p v-if="apiUnavailable" role="status" class="api-warning">{{ copy.apiUnavailable }}</p>
          <InstallPrompt :title="copy.desktopPromptTitle" :description="copy.desktopPromptDescription" :prompt="desktopPrompt" :copy-label="copy.copyPrompt" :copied-label="copy.promptCopied" :error-label="copy.copyFailed" :show-label="copy.showPrompt" :hide-label="copy.hidePrompt" />
          <aside class="download-help">
            <span>{{ isEnglish ? 'Not sure which package fits your device?' : '不确定哪个安装包适合你的设备？' }}</span>
            <a :href="docLink('/docs/guide/install')">{{ isEnglish ? 'Read the installation guide' : '阅读安装指南' }} <span aria-hidden="true">↗</span></a>
          </aside>
        </section>

        <section v-show="activeMode === 'nas'" id="nas" role="tabpanel" aria-labelledby="nas-tab" tabindex="0">
          <article class="download-card nas-card fnos-card">
            <div class="platform-heading"><span class="platform-icon"><Server :size="32" aria-hidden="true" /></span><div><h2>{{ copy.fnosTitle }}</h2><p>{{ copy.fnosDescription }}</p></div></div>
            <div class="format-tags"><span>fnOS · x86 · CPU</span><span>.fpk</span></div>
            <a :href="fnosAssetUrl()" class="primary-action" :aria-busy="loadingPlatform === 'fnos'" @click="onFnosDownload"><Download :size="18" aria-hidden="true" />{{ loadingPlatform === 'fnos' ? copy.preparing : hasFnosAsset ? copy.fnosDownload : copy.fnosBrowse }}</a>
            <p v-if="!hasFnosAsset" class="preflight-link" role="status">{{ copy.fnosPending }}</p>
            <p class="preflight-link"><a :href="docLink('/docs/guide/fnos')">{{ copy.fnosGuide }} <ArrowUpRight :size="13" aria-hidden="true" /></a></p>
          </article>
          <article class="download-card nas-card">
            <div class="platform-heading"><span class="platform-icon"><Server :size="32" aria-hidden="true" /></span><div><h2>{{ copy.nasTitle }}</h2><p>{{ copy.nasDescription }}</p></div></div>
            <div class="format-tags"><span>{{ copy.nasLabel }}</span><span>{{ copy.dockerLabel }}</span></div>
            <ol class="deployment-steps"><li v-for="(step, index) in copy.nasSteps" :key="step.title"><span class="step-number">{{ index + 1 }}</span><div><h3>{{ step.title }}</h3><p>{{ step.description }}</p></div></li></ol>
            <a :href="docLink('/docs/guide/docker/')" class="primary-action">{{ copy.dockerGuide }} <ArrowUpRight :size="17" aria-hidden="true" /></a>
            <p class="preflight-link"><a :href="docLink('/docs/guide/preflight')">{{ copy.preflight }} <ArrowUpRight :size="13" aria-hidden="true" /></a></p>
          </article>
          <InstallPrompt class="nas-prompt" :title="copy.nasPromptTitle" :description="copy.nasPromptDescription" :prompt="nasPrompt" :copy-label="copy.copyPrompt" :copied-label="copy.promptCopied" :error-label="copy.copyFailed" :show-label="copy.showPrompt" :hide-label="copy.hidePrompt" />
        </section>

        <section v-show="activeMode === 'mobile'" id="mobile" role="tabpanel" aria-labelledby="mobile-tab" tabindex="0">
          <aside class="mobile-notice" role="note">
            <span class="notice-mark" aria-hidden="true">!</span>
            <div>
              <h2>{{ copy.mobileNoticeTitle }}</h2>
              <p>{{ copy.mobileNoticeBody }}</p>
              <div class="notice-links">
                <a :href="docLink('/docs/guide/install')">{{ copy.mobileNoticeDeploy }} <span aria-hidden="true">↗</span></a>
                <a :href="docLink('/docs/guide/mobile-app')">{{ copy.mobileNoticeConnect }} <span aria-hidden="true">↗</span></a>
              </div>
            </div>
          </aside>

          <article class="download-card mobile-card">
            <div class="platform-heading">
              <span class="platform-icon"><Smartphone :size="32" aria-hidden="true" /></span>
              <div><h2>{{ copy.mobileTitle }}</h2><p>{{ copy.mobileDescription }}</p></div>
            </div>
            <div class="format-tags"><span>Android 8.0+</span><span>.apk</span><span>{{ copy.mobileClientOnly }}</span></div>
            <a :href="apkUrl" class="primary-action" :aria-busy="loadingPlatform === 'mobile'" @click="onApkDownload">
              <Download :size="18" aria-hidden="true" />{{ loadingPlatform === 'mobile' ? copy.preparing : hasApk ? copy.mobileDownload : copy.mobileBrowse }}
            </a>
            <p v-if="mobileAccel" class="accel-options">
              <span>{{ copy.accelHint }}</span>
              <a :href="mobileAccel" target="_blank" rel="noopener noreferrer">{{ copy.accelLines[0] }} <ArrowUpRight :size="13" aria-hidden="true" /></a>
            </p>
            <p v-if="!hasApk" class="preflight-link" role="status">{{ copy.mobilePending }}</p>
            <p class="mobile-note">{{ copy.mobileIos }}</p>
            <p class="mirror-download">{{ copy.mobileGuideHint }} <a :href="docLink('/docs/guide/mobile-app')">{{ copy.mobileGuide }} <ArrowUpRight :size="13" aria-hidden="true" /></a></p>
            <figure v-if="apkQr" class="apk-qr">
              <img :src="apkQr" :alt="copy.mobileQrAlt" width="112" height="112">
              <figcaption>
                <strong>{{ copy.mobileQrTitle }}</strong>
                <span>{{ copy.mobileQrHint }}</span>
              </figcaption>
            </figure>
          </article>

          <article class="download-card mobile-card">
            <div class="platform-heading">
              <span class="platform-icon"><Server :size="32" aria-hidden="true" /></span>
              <div><h2>{{ copy.mobileStepsTitle }}</h2><p>{{ copy.mobileStepsDescription }}</p></div>
            </div>
            <ol class="deployment-steps"><li v-for="(step, index) in copy.mobileSteps" :key="step.title"><span class="step-number">{{ index + 1 }}</span><div><h3>{{ step.title }}</h3><p>{{ step.description }}</p></div></li></ol>
            <a :href="docLink('/docs/guide/install')" class="primary-action">{{ copy.mobileDeployAction }} <ArrowUpRight :size="17" aria-hidden="true" /></a>
          </article>
        </section>
      </div>
    </main>
    <ContactFooter />
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useData } from 'vitepress'
import InstallPrompt from './InstallPrompt.vue'
import ContactFooter from './ContactFooter.vue'
import SiteChrome from './SiteChrome.vue'
import { ArrowRight, ArrowUpRight, Download, Server, Smartphone } from 'lucide-vue-next'
import '../landing/home.css'
import '../landing/subpage.css'

type PlatformKey = 'windows' | 'macos' | 'linux'
type InstallMode = 'nas' | 'desktop' | 'mobile'
type DownloadKind = 'installer' | 'portable' | 'appimage' | 'deb'
type ReleaseAsset = { name: string; browser_download_url: string }

const { lang } = useData()
const isEnglish = computed(() => lang.value.startsWith('en'))
const releaseUrl = 'https://github.com/LC044/TrailSnap/releases/latest'
const mirrorUrl = 'https://demo.trailsnap.cn/downloads/'
const assets = ref<ReleaseAsset[]>([])
const releaseName = ref('')
const detectedPlatform = ref<PlatformKey | ''>('')
const loadingPlatform = ref<string>('')
const apiUnavailable = ref(false)
const activeMode = ref<InstallMode>('desktop')
const selectedPlatform = ref<PlatformKey | ''>('')
const featuredDownload = ref<HTMLAnchorElement | null>(null)
const apkQr = ref('')

async function selectPlatform(platform: PlatformKey) {
  selectedPlatform.value = platform
  await nextTick()
  featuredDownload.value?.focus({ preventScroll: true })
}

const translations = {
  zh: {
    edition: '版', installer: '安装包', chooseInstaller: '选择安装包', dockerLabel: 'Docker 部署', releaseHint: '版本与文件以最新发布为准', changelog: '更新日志', showPrompt: '查看提示词', hidePrompt: '收起提示词', footer: '照片与回忆，始终属于你。',
    badge: '选择适合你的使用方式', title: '开始使用 TrailSnap',
    description: '选择照片存放的设备，开启你的私人照片库',
    nasEntry: 'NAS / 服务器', desktopEntry: '桌面版', latest: '最新版本',
    nasLabel: 'NAS / 家庭服务器', nasTitle: '把 NAS 变成家庭照片库',
    nasDescription: '照片集中存储，同一局域网内的手机、平板和电脑都能通过浏览器访问',
    nasSteps: [{ title: '准备设备与照片路径', description: '确认 NAS 型号、Docker 支持和存储位置' }, { title: '按指南完成部署', description: '配置照片目录，启动 TrailSnap 服务' }, { title: '打开你的照片库', description: '通过浏览器访问，开始整理与浏览' }],
    dockerGuide: 'NAS 相册 Docker 部署指南', preflight: '查看设备与环境要求',
    fnosTitle: '飞牛 NAS 安装包', fnosDescription: '在应用中心手动安装，填写端口和照片、数据目录，即可开始使用',
    fnosDownload: '下载飞牛安装包', fnosBrowse: '查看飞牛安装包', fnosGuide: '飞牛 NAS 相册安装教程',
    fnosPending: '暂未找到可下载的飞牛安装包，请在版本页面查看可用文件',
    nasPromptTitle: '让 AI 帮你部署',
    nasPromptDescription: '告诉 AI 设备型号和照片路径，获取分步部署指导',
    desktopLabel: '方式二 · 个人电脑', desktopTitle: '在自己的电脑上，整理照片与回忆',
    desktopDescription: '适合照片主要存放在电脑上的用户。选择对应系统的安装包，下载并安装；遇到不熟悉的步骤，也可以用下面的提示词请 AI 帮忙',
    installerTitle: '下载安装包', recommended: '适合当前设备', download: '下载', preparing: '准备中…',
    downloadZip: '下载 ZIP 便携版', portableHint: '完整便携包，解压后运行 TrailSnap.exe，无需安装',
    accelHint: '下载慢？', accelLines: ['加速线路一', '加速线路二'], accelInline: '国内加速',
    mirrorHint: '仍无法下载？', mirrorLink: '从备用地址下载',
    assetHint: '没有找到合适的安装包？查看', allAssets: '全部版本与文件',
    apiUnavailable: '暂时无法获取最新安装包。下载按钮将打开 GitHub 版本页面，你可以在那里选择对应系统的安装包',
    desktopPromptTitle: '让 AI 帮你安装',
    desktopPromptDescription: '复制专用提示词，跟着 AI 完成安装与初始设置',
    copyPrompt: '复制提示词', promptCopied: '已复制，粘贴给 AI 助手', copyFailed: '复制失败，请展开提示词后选中文字手动复制',
    aiTitle: '装好后，再按需开启 AI 功能',
    aiDescription: '安装包已包含 AI 运行环境，随应用统一更新。人脸识别、文字识别和语义搜索所需模型按需下载',
    aiGuide: '了解内置 AI 与模型准备',
    mobileEntry: '移动端 App',
    mobileNoticeTitle: '先部署服务，才能使用 App',
    mobileNoticeBody: '行影集 App 只是手机上的客户端，本身不含照片库。请先在电脑或 NAS 上部署 TrailSnap，再在 App 里填写服务器地址登录；没有部署服务，App 无法使用。',
    mobileNoticeDeploy: '查看部署指南',
    mobileNoticeConnect: '已有服务？看连接说明',
    mobileTitle: 'Android App',
    mobileDescription: '连接你自己的服务器，在手机上浏览、搜索与备份照片',
    mobileClientOnly: '仅客户端',
    mobileDownload: '下载 Android APK',
    mobileBrowse: '查看最新版本文件',
    mobilePending: '暂未找到当前版本的 APK，请在版本页面选择 Android 安装包',
    mobileIos: 'iOS 暂无独立 App，可用 Safari 打开你的 TrailSnap 网页版，再「添加到主屏幕」当作 App 使用。',
    mobileGuideHint: '第一次连接服务器？',
    mobileGuide: '移动 App 使用指南',
    mobileStepsTitle: '三步开始使用',
    mobileStepsDescription: 'App 不连接任何公共云端，账号与照片始终留在你自己的设备上',
    mobileSteps: [{ title: '部署服务', description: '在电脑或 NAS 上完成部署，并用同一局域网内的浏览器打开 TrailSnap' }, { title: '安装 App', description: '下载 APK 后按系统提示允许「安装未知应用」，请只从官方 GitHub 仓库获取安装包' }, { title: '连接服务器', description: '在 App 中填写 http://局域网IP:3180，或扫描「设置 → 连接手机 App」页面上的二维码' }],
    mobileDeployAction: '先看部署指南',
    mobileQrTitle: '扫码下载',
    mobileQrHint: '用手机扫描二维码，直接下载 Android APK',
    mobileQrAlt: 'Android APK 下载二维码'
  },
  en: {
    edition: '', installer: 'installer', chooseInstaller: 'Choose installer', dockerLabel: 'Docker deployment', releaseHint: 'See the latest release for available files', changelog: 'Changelog', showPrompt: 'View prompt', hidePrompt: 'Hide prompt', footer: 'Your photos and memories, always yours.',
    badge: 'Choose how you want to use it', title: 'Get started with TrailSnap',
    description: 'Choose where your photos live. Start your own photo library',
    nasEntry: 'NAS deployment', desktopEntry: 'Desktop app', latest: 'Latest release',
    nasLabel: 'NAS / home server', nasTitle: 'Turn your NAS into a family photo library',
    nasDescription: 'For photos stored on a NAS or home server. Keep your library in one place and access it from phones, tablets, and computers on the same local network',
    nasSteps: [{ title: 'Prepare your device and photo path', description: 'Check your NAS model, Docker support, and storage' }, { title: 'Follow the deployment guide', description: 'Configure the photo folder and start TrailSnap' }, { title: 'Open your photo library', description: 'Visit in your browser to start organizing and browsing' }],
    dockerGuide: 'Read the Docker deployment guide', preflight: 'Device and setup requirements',
    fnosTitle: 'Installer for fnOS NAS', fnosDescription: 'Install through App Center, choose a port and your photo and data folders, then open TrailSnap',
    fnosDownload: 'Download fnOS installer', fnosBrowse: 'Browse fnOS installers', fnosGuide: 'fnOS installation and user guide',
    fnosPending: 'An fnOS installer could not be found. Browse the release page for available files',
    nasPromptTitle: 'Let AI guide your NAS setup',
    nasPromptDescription: 'Tell AI your device model and photo path for step-by-step guidance',
    desktopLabel: 'Option two · Personal computer', desktopTitle: 'Manage photos on your own computer',
    desktopDescription: 'For photos stored on your computer. Download the installer for your operating system. For help with installation, use the AI prompt below',
    installerTitle: 'Download an installer', recommended: 'For this device', download: 'Download for', preparing: 'Preparing...',
    downloadZip: 'Download portable ZIP', portableHint: 'Full portable package. Extract it and run TrailSnap.exe without installing',
    accelHint: 'Slow download?', accelLines: ['Fast link 1', 'Fast link 2'], accelInline: 'China mirror',
    mirrorHint: 'Still not working?', mirrorLink: 'Get them from an alternate mirror',
    assetHint: 'Need a different installer? Browse', allAssets: 'all versions and assets',
    apiUnavailable: 'The latest installers could not be loaded. Download buttons open the GitHub release page so you can choose an installer manually',
    desktopPromptTitle: 'Need help installing? Ask AI',
    desktopPromptDescription: 'Copy the prompt for help with installation and initial setup',
    copyPrompt: 'Copy AI prompt', promptCopied: 'Copied, paste into your AI assistant', copyFailed: 'Copy failed. Expand the prompt and select the text to copy manually',
    aiTitle: 'Add AI features after installation',
    aiDescription: 'AI is included and updated with the app. Models for face recognition, OCR and semantic search are downloaded as needed',
    aiGuide: 'About built-in AI and model preparation',
    mobileEntry: 'Mobile app',
    mobileNoticeTitle: 'Deploy the server first',
    mobileNoticeBody: 'The TrailSnap app is only a mobile client and does not include a photo library. Deploy TrailSnap on your computer or NAS first, then enter that address in the app. Without a deployment the app cannot be used.',
    mobileNoticeDeploy: 'Read the deployment guide',
    mobileNoticeConnect: 'Already deployed? Connection guide',
    mobileTitle: 'Android app',
    mobileDescription: 'Connect to your own server to browse, search and back up photos on your phone',
    mobileClientOnly: 'client only',
    mobileDownload: 'Download Android APK',
    mobileBrowse: 'Browse the latest release',
    mobilePending: 'No APK was found for this version. Pick the Android package on the release page',
    mobileIos: 'There is no iOS app yet. Open your TrailSnap site in Safari and use "Add to Home Screen" instead.',
    mobileGuideHint: 'Connecting for the first time?',
    mobileGuide: 'Mobile app guide',
    mobileStepsTitle: 'Three steps to get started',
    mobileStepsDescription: 'The app never connects to a public cloud. Your account and photos stay on your own device',
    mobileSteps: [{ title: 'Deploy the server', description: 'Deploy TrailSnap on your computer or NAS, then open it in a browser on the same local network' }, { title: 'Install the app', description: 'Download the APK and allow "Install unknown apps" when prompted. Only install packages from the official GitHub release' }, { title: 'Connect to the server', description: 'Enter http://LAN-IP:3180 in the app, or scan the QR code under Settings → Connect mobile app' }],
    mobileDeployAction: 'Deploy first',
    mobileQrTitle: 'Scan to download',
    mobileQrHint: 'Scan with your phone to download the Android APK directly',
    mobileQrAlt: 'QR code for the Android APK download'
  }
}
const copy = computed(() => isEnglish.value ? translations.en : translations.zh)
const installModes = computed(() => [
  { key: 'desktop' as const, label: copy.value.desktopEntry },
  { key: 'mobile' as const, label: copy.value.mobileEntry },
  { key: 'nas' as const, label: copy.value.nasEntry }
])

function onTabKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const keys = installModes.value.map(mode => mode.key)
  const current = keys.indexOf(activeMode.value)
  const next = event.key === 'Home' ? 0
    : event.key === 'End' ? keys.length - 1
      : event.key === 'ArrowRight' ? (current + 1) % keys.length : (current - 1 + keys.length) % keys.length
  activeMode.value = keys[next]
  document.getElementById(`${keys[next]}-tab`)?.focus()
}

const platforms = computed(() => [
  { key: 'windows' as const, name: 'Windows', icon: 'M2 3.5 11 2v9H2V3.5Zm11-1.8L22 0v11h-9V1.7ZM2 13h9v9l-9-1.5V13Zm11 0h9v11l-9-1.7V13Z', formats: ['Windows 10 / 11', 'x64'], description: isEnglish.value ? 'Windows 10/11 64-bit installer or portable ZIP' : '适用于 Windows 10/11 的 64 位安装程序或 ZIP 便携版' },
  { key: 'macos' as const, name: 'macOS', icon: 'M17.1 6.3c-1.4-.1-2.6.8-3.3.8-.7 0-1.8-.8-3-.8-1.6 0-3.1.9-4 2.3-1.7 2.9-.4 7.2 1.2 9.5.8 1.1 1.6 2.4 2.9 2.3 1.2 0 1.6-.7 3.1-.7s1.9.7 3.2.7c1.3 0 2.1-1.2 2.8-2.3.9-1.3 1.3-2.6 1.3-2.7-.1 0-2.5-1-2.5-3.8 0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.7-1.8ZM16.2 4.8c.6-.8 1.1-1.9 1-3-1 .1-2.2.7-2.9 1.5-.6.7-1.2 1.9-1.1 2.9 1.1.1 2.3-.6 3-1.4Z', formats: ['.dmg', isEnglish.value ? 'Apple Silicon' : 'Apple 芯片'], description: isEnglish.value ? 'Installer for Apple Silicon Macs' : '适用于 Apple Silicon（M 系列芯片）的安装镜像' },
  { key: 'linux' as const, name: 'Linux', icon: 'M3 3h18v18H3V3Zm2 2v14h14V5H5Zm2 3 4 4-4 4-1.4-1.4L8.2 12 5.6 9.4 7 8Zm5 7h5v2h-5v-2Z', formats: ['.AppImage', '.deb', 'x64'], description: isEnglish.value ? 'Portable AppImage or Debian/Ubuntu package' : '可选择便携 AppImage 或 Debian/Ubuntu 安装包' }
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

function fnosAssetUrl() {
  return assets.value.find(asset => /^TrailSnap-\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?-fnos-x86\.fpk$/.test(asset.name))?.browser_download_url || releaseUrl
}
const hasFnosAsset = computed(() => fnosAssetUrl() !== releaseUrl)

// APK 只随标签发布产出；文件名与 build-mobile-app 工作流保持一致。
function apkAssetUrl() {
  return assets.value.find(asset => /-mobile-android-[a-z0-9]+.*\.apk$/.test(asset.name))?.browser_download_url || releaseUrl
}
const apkUrl = computed(() => apkAssetUrl())
const hasApk = computed(() => apkAssetUrl() !== releaseUrl)

// 只用到 toDataURL，本地声明类型避免引入额外的 @types 包。
type QrEncoder = { toDataURL(text: string, options?: Record<string, unknown>): Promise<string> }

// 二维码内容与下载按钮一致，直接指向 APK；取不到附件时退回版本页面。
// 只在浏览器端加载二维码库，避免静态构建阶段执行 Node 版本。
async function renderApkQr() {
  try {
    const { default: QRCode } = (await import('qrcode')) as unknown as { default: QrEncoder }
    apkQr.value = await QRCode.toDataURL(apkAssetUrl(), {
      errorCorrectionLevel: 'M',
      margin: 1,
      width: 320,
      color: { dark: '#17130d', light: '#ffffff' },
    })
  } catch {
    apkQr.value = ''
  }
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

function primaryMirrorUrl(original: string) {
  const prefix = 'https://github.com/LC044/TrailSnap/releases/'
  if (!original.startsWith(prefix)) return ''
  const path = original.slice(prefix.length)
  return /^download\/v\d+\.\d+\.\d+\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(path)
    ? `https://download.trailsnap.cn/LC044/TrailSnap/releases/${path}`
    : ''
}

async function preferredDownloadUrl(original: string) {
  const mirror = primaryMirrorUrl(original)
  if (!mirror) return original
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 1500)
  try {
    const response = await fetch(mirror, { method: 'HEAD', signal: controller.signal, redirect: 'error' })
    return response.ok ? mirror : original
  } catch {
    return original
  } finally {
    clearTimeout(timeout)
  }
}

const featuredAccels = computed<string[]>(() => {
  const url = resolvedAssetUrl(featuredPlatform.value.key, featuredKind.value)
  return url ? accelPrefixes.map(prefix => `${prefix}${url}`) : []
})
const portableAccel = computed(() => accelLink('windows', 'portable'))
const debAccel = computed(() => accelLink('linux', 'deb'))
const mobileAccel = computed(() => {
  const url = assets.value.find(asset => /-mobile-android-[a-z0-9]+.*\.apk$/.test(asset.name))?.browser_download_url
  return url ? `${accelPrefixes[0]}${url}` : ''
})

async function fetchAssets(): Promise<boolean> {
  try {
    const response = await fetch('/version.json', { cache: 'no-cache' })
    if (!response.ok) return false
    const versions = await response.json()
    if (!Array.isArray(versions) || versions.length === 0) return false
    // 与安卓更新检查一致：版本清单按发布时间排列，最后一项为最新版本。
    const version = versions[versions.length - 1]?.version
    if (typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version)) return false
    // 与发布脚本的统一命名保持一致；这里不请求 GitHub API 查询附件。
    const names = [
      `TrailSnap-${version}-desktop-windows-x64-setup.exe`,
      `TrailSnap-${version}-desktop-windows-x64-portable.zip`,
      `TrailSnap-${version}-desktop-macos-arm64.dmg`,
      `TrailSnap-${version}-desktop-linux-x64.AppImage`,
      `TrailSnap-${version}-desktop-linux-x64.deb`,
      `TrailSnap-${version}-fnos-x86.fpk`,
      `TrailSnap-${version}-mobile-android-universal-debug.apk`,
    ]
    releaseName.value = `v${version}`
    assets.value = names.map(name => ({
      name,
      browser_download_url: `https://github.com/LC044/TrailSnap/releases/download/v${version}/${name}`,
    }))
    return true
  } catch {
    return false
  }
}

async function onDownload(platform: PlatformKey, event: MouseEvent, kind: DownloadKind = 'installer') {
  // 在 await 之前取消默认跳转，否则会在安装包解析完成前离开页面。
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  if (loadingPlatform.value) return
  loadingPlatform.value = kind === 'installer' ? platform : `${platform}-${kind}`
  try {
    if (assets.value.length === 0 && !(await fetchAssets())) apiUnavailable.value = true
    window.location.assign(await preferredDownloadUrl(assetUrl(platform, kind)))
  } finally {
    loadingPlatform.value = ''
  }
}

async function onFnosDownload(event: MouseEvent) {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  if (loadingPlatform.value) return
  loadingPlatform.value = 'fnos'
  try {
    if (assets.value.length === 0 && !(await fetchAssets())) apiUnavailable.value = true
    window.location.assign(await preferredDownloadUrl(fnosAssetUrl()))
  } finally {
    loadingPlatform.value = ''
  }
}

async function onApkDownload(event: MouseEvent) {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  if (loadingPlatform.value) return
  loadingPlatform.value = 'mobile'
  try {
    if (assets.value.length === 0 && !(await fetchAssets())) apiUnavailable.value = true
    window.location.assign(await preferredDownloadUrl(apkAssetUrl()))
  } finally {
    loadingPlatform.value = ''
  }
}

onMounted(async () => {
  if (window.location.hash === '#nas') activeMode.value = 'nas'
  if (window.location.hash === '#mobile') activeMode.value = 'mobile'
  const userAgent = navigator.userAgent.toLowerCase()
  // 手机浏览器可能包含 Mac/Linux 标识，不将其推荐为桌面设备。
  if (!/android|iphone|ipad|ipod/.test(userAgent) && !(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    detectedPlatform.value = userAgent.includes('windows') ? 'windows' : userAgent.includes('mac') ? 'macos' : userAgent.includes('linux') ? 'linux' : ''
  } else if (userAgent.includes('android') && window.location.hash !== '#nas' && window.location.hash !== '#desktop') {
    // Android 手机直接看移动端安装方式，桌面与 NAS 标签仍在标签栏可切换。
    activeMode.value = 'mobile'
  }
  apiUnavailable.value = !(await fetchAssets())
  await renderApkQr()
})
</script>
