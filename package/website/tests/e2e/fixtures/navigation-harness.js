import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory, RouterLink, RouterView } from 'vue-router'
import NavigationFeedback from '/src/components/NavigationFeedback.vue'
import { installNavigationFeedback } from '/src/router/navigationFeedback.ts'
import { provideTheme } from '/src/composables/useTheme.ts'
import '/src/style.css'
import '/src/styles/ui.css'

let failures = 0
const router = createRouter({ history: createMemoryHistory(), routes: [
  { path: '/', component: { render: () => h('p', '原页面') } },
  { path: '/photos', meta: { title: '所有照片' }, component: () => import('./navigation-target.js') },
  { path: '/retry', meta: { title: '票夹' }, component: async () => {
    if (++failures === 1) throw Error('Failed to fetch dynamically imported module')
    return { render: () => h('p', '票夹已打开') }
  } },
] })
installNavigationFeedback(router)
const app = createApp({ setup() {
  window.fixtureTheme = provideTheme()
  return () => h('main', { style: 'padding:100px 24px' }, [
    h(RouterLink, { to: '/photos?year=2026#today', class: 'ts-button ts-button-secondary' }, () => '照片'),
    h(RouterLink, { to: '/retry?wallet=all#tickets', class: 'ts-button ts-button-secondary' }, () => '票夹'),
    h(RouterView), h(NavigationFeedback),
  ])
} })
app.use(createPinia()).use(router).mount('#fixture')
window.fixtureRouter = router
