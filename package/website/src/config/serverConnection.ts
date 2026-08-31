import { App as CapacitorApp, type URLOpenListenerEvent } from '@capacitor/app'
import { Capacitor, registerPlugin } from '@capacitor/core'
import {
  CapacitorBarcodeScanner,
  CapacitorBarcodeScannerCameraDirection,
  CapacitorBarcodeScannerScanOrientation,
  CapacitorBarcodeScannerTypeHint,
} from '@capacitor/barcode-scanner'
import { mDNS, type MdnsService } from '@devioarts/capacitor-mdns'
import type { Router } from 'vue-router'
import { isMobileApp, normalizeServerUrl, testServerConnection } from './server'

export const TRAILSNAP_SERVICE_TYPE = '_trailsnap._tcp.'
const DEFAULT_TRAILSNAP_PORT = 8082

interface LanDiscoveryResult {
  services: Array<{ url: string; name: string; version: string }>
  scannedNetworks: number
}

interface LanDiscoveryPlugin {
  discover(options: { port: number; timeoutMs: number }): Promise<LanDiscoveryResult>
}

const LanDiscovery = registerPlugin<LanDiscoveryPlugin>('LanDiscovery')

export interface DiscoveredTrailSnap {
  url: string
  name: string
  version: string
  source: 'mdns' | 'lan'
}

export function createConnectionDeepLink(serverUrl: string): string {
  return `trailsnap://connect?url=${encodeURIComponent(normalizeServerUrl(serverUrl))}`
}

export function parseConnectionLink(value: string): string {
  const candidate = value.trim()
  if (!candidate) throw new Error('二维码或链接中没有 TrailSnap 地址')

  if (/^trailsnap:\/\//i.test(candidate)) {
    const link = new URL(candidate)
    if (link.hostname !== 'connect') throw new Error('这不是 TrailSnap 连接链接')
    const serverUrl = link.searchParams.get('url')
    if (!serverUrl) throw new Error('连接链接中缺少服务器地址')
    return normalizeServerUrl(serverUrl)
  }

  const webLink = new URL(candidate)
  if (webLink.pathname === '/connect' && webLink.searchParams.has('url')) {
    return normalizeServerUrl(webLink.searchParams.get('url') || '')
  }
  return normalizeServerUrl(candidate)
}

export async function scanConnectionQrCode(): Promise<string> {
  const result = await CapacitorBarcodeScanner.scanBarcode({
    hint: CapacitorBarcodeScannerTypeHint.QR_CODE,
    scanInstructions: '扫描 TrailSnap 连接二维码',
    scanButton: false,
    cameraDirection: CapacitorBarcodeScannerCameraDirection.BACK,
    scanOrientation: CapacitorBarcodeScannerScanOrientation.ADAPTIVE,
    cancelButtonAccessibilityLabel: '取消扫码',
    torchButtonOnAccessibilityLabel: '关闭闪光灯',
    torchButtonOffAccessibilityLabel: '打开闪光灯',
  })
  return parseConnectionLink(result.ScanResult)
}

function formatHost(host: string): string {
  return host.includes(':') ? `[${host}]` : host
}

function serviceCandidates(service: MdnsService): string[] {
  const candidates: string[] = []
  if (service.txt?.url) candidates.push(service.txt.url)
  const scheme = service.port === 443 ? 'https' : 'http'
  for (const host of service.hosts) {
    const port = (scheme === 'https' && service.port === 443) || (scheme === 'http' && service.port === 80)
      ? ''
      : `:${service.port}`
    candidates.push(`${scheme}://${formatHost(host)}${port}`)
  }
  return [...new Set(candidates)]
}

export async function discoverTrailSnapServers(): Promise<DiscoveredTrailSnap[]> {
  if (!isMobileApp()) return []
  try {
    const result = await mDNS.discover({ type: TRAILSNAP_SERVICE_TYPE, timeout: 1800, useNW: true })
    const candidates = result.services.flatMap(service => serviceCandidates(service).map(url => ({
      url,
      name: service.name || 'TrailSnap',
      version: service.txt?.version || '',
      source: 'mdns' as const,
    })))
    const verified = await verifyCandidates(candidates)
    if (verified.length) return verified
  } catch (error) {
    console.warn('mDNS discovery unavailable, falling back to LAN probing', error)
  }

  if (Capacitor.getPlatform() !== 'android') return []
  try {
    const result = await LanDiscovery.discover({ port: DEFAULT_TRAILSNAP_PORT, timeoutMs: 400 })
    return verifyCandidates(result.services.map(service => ({ ...service, source: 'lan' as const })))
  } catch (error) {
    console.warn('LAN probing unavailable', error)
    return []
  }
}

async function verifyCandidates(candidates: DiscoveredTrailSnap[]): Promise<DiscoveredTrailSnap[]> {
  const verified = await Promise.all(candidates.map(async candidate => {
    try {
      const url = await testServerConnection(candidate.url, 2500)
      return { ...candidate, url }
    } catch {
      return null
    }
  }))
  const unique = new Map<string, DiscoveredTrailSnap>()
  for (const candidate of verified) {
    if (candidate) unique.set(candidate.url, candidate)
  }
  return [...unique.values()]
}

function connectionUrlFromEvent(event: URLOpenListenerEvent): string | null {
  try {
    return parseConnectionLink(event.url)
  } catch {
    return null
  }
}

export async function registerConnectionDeepLinks(router: Router): Promise<void> {
  if (!isMobileApp()) return

  const open = (url: string) => {
    void router.push({ path: '/server-settings', query: { url } })
  }
  try {
    const launch = await CapacitorApp.getLaunchUrl()
    if (launch?.url) {
      const url = connectionUrlFromEvent({ url: launch.url })
      if (url) open(url)
    }
    await CapacitorApp.addListener('appUrlOpen', event => {
      const url = connectionUrlFromEvent(event)
      if (url) open(url)
    })
  } catch (error) {
    console.warn('Connection deep links are unavailable in this runtime', error)
  }
}
