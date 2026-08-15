/// <reference types="vitepress/client" />
import DefaultTheme from 'vitepress/theme'
import { h, onMounted, watch} from 'vue'
import Comments from './components/Comments.vue'
import Home from './components/Home.vue'
import CliPage from './components/CliPage.vue'
import DownloadPage from './components/DownloadPage.vue'
import './style/style.css'
// import './style/navbar.css'
import {Mermaid} from "@leelaa/vitepress-plugin-extended";
import { enhanceAppWithTabs } from 'vitepress-plugin-tabs/client'
import mediumZoom from 'medium-zoom'
import { useData, inBrowser, useRoute } from 'vitepress'
import { useRouter } from 'vitepress/client'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import './style/vp-code.css'
import './style/vp-code-group.css'
import 'virtual:group-icons.css'
import './style/sidebarIcon.css'
import './style/blur.css'
import './style/custom-block.css'

NProgress.configure({
  showSpinner: false,
  speed: 300,
  minimum: 0.2
})

export default {
  extends: DefaultTheme,

  Layout() {
    const { frontmatter } = useData()

    // VitePress 2.0 正确路由监听
    if (inBrowser) {
      const router = useRouter()
      router.onBeforeRouteChange = () => {
        NProgress.start()
      }
      router.onAfterRouteChange = () => {
        NProgress.done()
      }
    }

    return h(DefaultTheme.Layout, null, {
      'doc-after': () => frontmatter.value.home_custom ? null : h(Comments)
    })
  },

  enhanceApp({ app, router }: { app: any; router: any }) {
    // 全局组件
    app.component('Home', Home)
    app.component('CliPage', CliPage)
    app.component('DownloadPage', DownloadPage)
    app.component('Mermaid', Mermaid)
    enhanceAppWithTabs(app)
  },

  setup() {
    const route = useRoute()
    const initZoom = () => mediumZoom('.vp-doc img', {
      margin: 24,
      background: 'rgba(0,0,0,0.85)'
    })
    onMounted(() => initZoom())
    watch(() => route.path, () => setTimeout(initZoom, 100))
  }
}
