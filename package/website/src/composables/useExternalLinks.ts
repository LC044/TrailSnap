import { getServerUrl, isMobileApp, isTauriApp } from '@/config/server'

let installed = false

/**
 * 判断一个 href 是否应交给系统浏览器打开：
 * - mailto:/tel: 一律视为外部
 * - http/https 仅当跨源时才算外部
 * 同源相对链接（/album/...、/settings#...）返回 false，留给 SPA 路由处理。
 *
 * Tauri webview 默认会阻止外部导航，<a target="_blank"> 点击无反应，
 * 因此需要在捕获阶段拦截跨源链接，转交 opener 插件用系统默认程序打开。
 */
function isExternalUrl(href: string): boolean {
  if (!href) return false
  if (/^(mailto:|tel:)/i.test(href)) return true
  if (!/^https?:/i.test(href)) return false
  try {
    const origin = new URL(href, window.location.href).origin
    if (origin === window.location.origin) return false
    if (isMobileApp() && getServerUrl()) {
      return origin !== new URL(getServerUrl(), window.location.href).origin
    }
    return true
  } catch {
    return false
  }
}

async function openExternal(href: string): Promise<void> {
  const { openUrl } = await import('@tauri-apps/plugin-opener')
  await openUrl(href)
}

/**
 * 在 Tauri 桌面端注册全局外部链接拦截：
 * - 捕获阶段拦截 <a> 点击，跨源链接交给系统浏览器
 * - hook window.open，兜住下载 / 外链跳转（如检查更新里的下载链接）
 * Web 与移动端环境下为空操作。
 */
export async function registerExternalLinkOpener(): Promise<void> {
  if ((!isTauriApp() && !isMobileApp()) || installed) return
  installed = true

  if (isMobileApp()) {
    document.addEventListener('click', (event) => {
      const link = (event.target as HTMLElement | null)?.closest?.('a')
      const href = link?.href || link?.getAttribute('href') || ''
      if (!isExternalUrl(href)) return
      event.preventDefault()
      event.stopImmediatePropagation()
      console.warn('[TrailSnap] blocked external link in packaged App')
    }, true)
    return
  }

  // 预热 opener 模块，避免首次点击因动态 import 产生可感延迟
  void import('@tauri-apps/plugin-opener').catch(() => {})

  document.addEventListener(
    'click',
    (event) => {
      // 链接可能嵌在子元素里，向上找最近的 <a>
      const target = event.target as HTMLElement | null
      const link = target?.closest?.('a')
      if (!link) return
      const href = link.href || link.getAttribute('href') || ''
      if (!isExternalUrl(href)) return
      event.preventDefault()
      openExternal(href).catch((error) =>
        console.error('[TrailSnap] 打开外部链接失败', error),
      )
    },
    true, // 捕获阶段：抢在 Vue Router / 默认导航之前
  )

  // 兜住 window.open(externalUrl) 调用
  const originalOpen = window.open
  window.open = function (
    url?: string | URL,
    target?: string,
    features?: string,
  ): Window | null {
    const resolved = typeof url === 'string' ? url : url?.toString() ?? ''
    if (isExternalUrl(resolved)) {
      openExternal(resolved).catch((error) =>
        console.error('[TrailSnap] 打开外部链接失败', error),
      )
      return null
    }
    return originalOpen.call(window, url as any, target as any, features as any)
  } as typeof window.open
}
