import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path';

// /api 代理目标。优先读环境变量 TS_API_BASE_URL（测试脚本 run-tests.ps1 会注入，
// 例如本地测试后端在 9000）；未设置时回退到默认 dev 后端 8000。
// 这样测试期前端 (9080) 与 e2e 直连后端 (TS_API_BASE_URL) 指向同一个后端，
// 浏览器里也能看到测试后端的真实数据。去掉末尾斜杠以免拼出 //。
const apiTarget = (process.env.TS_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'), // 这里定义 @ 代表 src 目录
    },
  },
  server: {
    host: '0.0.0.0', // 允许外部访问，设置为 'localhost' 只允许本地访问
    port: 5176,      // 设置你想要的端口
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
})
