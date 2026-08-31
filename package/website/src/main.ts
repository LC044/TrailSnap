import 'mingcute_icon/font/Mingcute.css';
import { createApp } from 'vue'
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

import App from './App.vue'
import router from '@/router';
import { registerPwa } from '@/composables/usePwa'
import { initializeServerConfig, isNativeApp, isTauriApp } from '@/config/server'
import { registerNativeBackButton } from '@/composables/useNativeBackButton'
import { registerExternalLinkOpener } from '@/composables/useExternalLinks'
import { registerElementPlusOverlayBridge } from '@/composables/useOverlayStack'
import { useUserStore } from '@/stores/user'
import { registerConnectionDeepLinks } from '@/config/serverConnection'

async function bootstrap() {
  document.documentElement.classList.toggle('tauri-desktop', isTauriApp())
  await initializeServerConfig()
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
  app.mount('#app');
  registerElementPlusOverlayBridge()

  await router.isReady()
  await registerConnectionDeepLinks(router)
  await registerNativeBackButton(router)
  registerPwa()
}

void bootstrap()

