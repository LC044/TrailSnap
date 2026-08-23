import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path';
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { visualizer } from 'rollup-plugin-visualizer'

function pwaPlugin() {
  return {
    name: 'trailsnap-pwa',
    apply: 'build',
    generateBundle(_, bundle) {
      const precache = Object.keys(bundle)
        .filter((fileName) => /\.(?:js|css|woff2?|ttf|svg|png|jpe?g|webp)$/i.test(fileName))
        .map((fileName) => `/${fileName}`)

      const source = `
const CACHE_NAME = 'trailsnap-app-shell-v2';
const PRECACHE_URLS = ${JSON.stringify(['/', '/index.html', '/offline.html', '/manifest.webmanifest', '/logo.svg', '/favicon.ico', '/apple-touch-icon.png', '/icon-192.png', '/icon-512.png', '/icon-maskable-512.png', ...precache])};
self.addEventListener('install', (event) => event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))));
self.addEventListener('activate', (event) => event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('message', (event) => { if (event.data?.type === 'SKIP_WAITING') self.skipWaiting(); });
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then((response) => {
      caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', response.clone()));
      return response;
    }).catch(() => caches.match('/index.html').then((response) => response || caches.match('/offline.html'))));
    return;
  }
  if (request.destination === 'image' || request.destination === 'video') return;
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
    if (response.ok && ['script', 'style', 'font'].includes(request.destination)) caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
    return response;
  })));
});
`

      this.emitFile({ type: 'asset', fileName: 'sw.js', source })
    },
  }
}

// /api 代理目标。优先读环境变量 TS_API_BASE_URL（测试脚本 run-tests.ps1 会注入，
// 例如本地测试后端在 9000）；未设置时回退到默认 dev 后端 8000。
// 这样测试期前端 (9080) 与 e2e 直连后端 (TS_API_BASE_URL) 指向同一个后端，
// 浏览器里也能看到测试后端的真实数据。去掉末尾斜杠以免拼出 //。
const apiTarget = (process.env.TS_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需：仅用 resolver 注册第三方组件，不扫描本地 components 目录
    // （本地组件仍走各文件显式 import，避免行为变化）。
    Components({
      dirs: [],
      // The declaration file is checked in. Rewriting it concurrently while
      // Rollup transforms lazy views intermittently fails on Windows builds.
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
    pwaPlugin(),
    // 产物体积可视化：构建后在 dist/stats.html 查看，便于持续量化首屏构成
    visualizer({
      filename: 'dist/stats.html',
      template: 'treemap',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
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
  build: {
    rollupOptions: {
      output: {
        // 将稳定的框架运行时拆成独立 chunk，便于长期缓存：
        // - vue: vue / vue-router / pinia，几乎每次发布都不变，单独成块后业务代码变动不会让它失效。
        //
        // 注意：不要把 element-plus / echarts 也塞进 manualChunks —— 它们已是按需引入，
        // 强制合并会让懒加载路由专用组件（如 Settings 的 el-table/el-tree）被并入一个
        // 共享块，而 entry 只要引用其中任何一个组件，整块就会被 modulepreload 进首屏。
        // 放开让 Rollup 默认分包：entry 只带自己用到的那小部分，其余随各懒加载路由加载。
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
        },
      },
    },
  },
})
