import 'vue-router'
import type { NavGroup } from '@/config/navigation'

declare module 'vue-router' {
  interface RouteMeta {
    layout?: 'main' | 'blank'
    title?: string
    keepAlive?: boolean
    navGroup?: NavGroup
  }
}

export {}
