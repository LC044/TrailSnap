import { createApp } from 'vue'
import ElementPlus, { ID_INJECTION_KEY } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './style.css'

createApp(App)
  .use(ElementPlus, { locale: zhCn })
  .provide(ID_INJECTION_KEY, { prefix: 1024, current: 0 })
  .mount('#app')
