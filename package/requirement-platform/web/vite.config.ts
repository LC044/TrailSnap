import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

const BASE_TOKEN = '__RP_BASE_PATH__'

function normalizePrefix(raw: string | undefined): string {
  const parts = (raw || '').trim().split('/').filter(Boolean)
  return parts.length ? `/${parts.join('/')}` : ''
}

/** In dev, <base> needs a real href immediately. In builds the token survives
 *  so the container can inject RP_BASE_PATH at startup without a rebuild. */
function basePathPlugin(prefix: string): Plugin {
  return {
    name: 'rp-base-path',
    transformIndexHtml(html, ctx) {
      return ctx.server ? html.replaceAll(BASE_TOKEN, prefix) : html
    },
  }
}

export default defineConfig(({ command }) => {
  const prefix = normalizePrefix(process.env.RP_BASE_PATH)
  const stripPrefix = (path: string) => prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path
  return {
    // Relative assets + <base> let one prebuilt image serve any URL prefix.
    base: command === 'serve' ? (prefix || '/') : './',
    plugins: [vue(), basePathPlugin(prefix)],
    server: {
      host: '0.0.0.0',
      port: 5177,
      proxy: {
        [`${prefix}/api`]: { target: 'http://127.0.0.1:8010', changeOrigin: true, rewrite: stripPrefix },
        [`${prefix}/mcp`]: { target: 'http://127.0.0.1:8012', changeOrigin: true, rewrite: stripPrefix },
      },
    },
  }
})
