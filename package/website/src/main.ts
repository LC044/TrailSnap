import 'mingcute_icon/font/Mingcute.css';
import { Capacitor } from '@capacitor/core'
import { createApp, h } from 'vue'
import { createPinia } from 'pinia'  // 1. 导入 createPinia
// Element Plus 按需引入：模板组件（el-dialog / el-select 等）与 v-loading 指令由
// unplugin-vue-components + ElementPlusResolver 自动注册并注入对应样式，无需 app.use(ElementPlus)
// 与全量 dist/index.css。这里仅补齐以函数方式调用的 programmatic service 所需样式：
// ElMessage / ElMessageBox / ElNotification / ElLoading（v-loading 指令复用 loading 样式）。
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'

import './style.css'
import './styles/ui.css'

import App from './App.vue'
import router from '@/router';
import { registerPwa } from '@/composables/usePwa'
import { getServerUrl, initializeServerConfig, isNativeApp, isTauriApp } from '@/config/server'
import { registerNativeBackButton } from '@/composables/useNativeBackButton'
import { registerExternalLinkOpener } from '@/composables/useExternalLinks'
import { registerElementPlusOverlayBridge } from '@/composables/useOverlayStack'
import { useUserStore } from '@/stores/user'
import { registerConnectionDeepLinks } from '@/config/serverConnection'
import { installNativeNetworkPolicy } from '@/config/nativeNetworkPolicy'
import { registerButtonMotion } from '@/composables/useButtonMotion'
import { useNavigationStore } from '@/stores/navigation'
import { commonPageLoaders } from '@/router/commonPages'
import { schedulePagePreloads } from '@/router/preload'

async function bootstrap() {
  document.documentElement.classList.toggle('capacitor-android', Capacitor.getPlatform() === 'android')
  document.documentElement.classList.toggle('tauri-desktop', isTauriApp())
  // Load the initial route while the sidecar starts, rather than after login.
  // Keep errors handled here; Vue Router still owns navigation error reporting.
  if (isTauriApp()) {
    void import('@/views/HomePage.vue').catch(error => console.warn('Home preload failed', error))
  }
  await initializeServerConfig()
  installNativeNetworkPolicy(getServerUrl)
  document.documentElement.classList.toggle('capacitor-native', isNativeApp())
  const app = createApp(App);
  // 2. 创建 Pinia 实例
  const pinia = createPinia()
  app.use(pinia)
  if (isTauriApp()) {
    await useUserStore().initializeDesktopSession()
  }
  await registerExternalLinkOpener()
  app.use(router);
  // Resolve authentication before App starts background protected requests.
  // Otherwise their early 401 can cancel a demo entry and lose its destination.
  await router.isReady()
  app.mount('#app');
  if (isTauriApp()) {
    void import('@/api/desktopPort').then(async ({ getDesktopPortConfig }) => {
      const config = await getDesktopPortConfig()
      if (config.notice) {
        const { ElNotification } = await import('element-plus')
        ElNotification({ title: '手机连接端口已更换', message: config.notice, type: 'warning', duration: 0 })
      }
    }).catch(error => console.warn('读取端口通知失败', error))
  }
  registerElementPlusOverlayBridge()
  registerButtonMotion()

  schedulePagePreloads(commonPageLoaders, () => !!useUserStore().token && !useNavigationStore().pending)
  await registerConnectionDeepLinks(router)
  await registerNativeBackButton(router)
  registerPwa()
}

void bootstrap().catch(async error => {
  console.error('Application startup failed', error)
  const container = document.querySelector<HTMLElement>('.boot-splash__content')
  if (!container) return
  container.classList.add('max-h-[100dvh]', 'overflow-y-auto', 'w-full')
  container.replaceChildren()
  const title = document.createElement('h1')
  title.className = 'text-xl font-semibold'
  title.textContent = '行影集未能启动'
  const detail = document.createElement('p')
  detail.className = 'ts-muted my-4 max-w-xl break-words'
  detail.textContent = String(error)
  container.append(title, detail)
  if (isTauriApp()) {
    try {
      const { getDesktopPortConfig } = await import('@/api/desktopPort')
      if ((await getDesktopPortConfig()).error) {
        const { default: DesktopPortSettings } = await import('@/components/settings/DesktopPortSettings.vue')
        const { provideTheme } = await import('@/composables/useTheme')
        const recovery = document.createElement('div')
        recovery.className = 'my-4 w-full max-w-xl'
        container.append(recovery)
        // Startup failed before App mounted, so this recovery root owns the theme.
        container.parentElement?.style.setProperty('background', 'var(--ts-color-page)')
        container.parentElement?.style.setProperty('color', 'var(--ts-color-text)')
        createApp({ setup() {
          provideTheme()
          return () => h(DesktopPortSettings, { recovery: true })
        } }).use(createPinia()).mount(recovery)
      }
    } catch (cause) { detail.textContent += `\n读取端口配置失败：${cause}` }
    const { invoke } = await import('@tauri-apps/api/core')
    for (const [label, command] of [['打开数据与日志目录', 'desktop_open_data_directory'], ['重新启动', 'desktop_restart']]) {
      const button = document.createElement('button')
      button.className = 'ts-button ts-button-secondary mt-3'
      button.textContent = label
      button.onclick = () => { void invoke(command).catch(cause => { detail.textContent = String(cause) }) }
      container.append(button)
    }
  }
})

