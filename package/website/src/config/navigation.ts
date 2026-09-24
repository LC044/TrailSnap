import type { Component } from 'vue'
import {
  Home,
  BookHeart,
  Image as ImageIcon,
  Images,
  Layers,
  MapPin,
  Moon,
  Tags,
  Users,
  Settings,
  Ticket,
  Trash2,
  Wrench,
} from 'lucide-vue-next'

export type NavGroup = 'home' | 'photos' | 'search' | 'albums' | 'memories' | 'tickets' | 'tools' | 'more'

export interface AppNavItem {
  label: string
  href: string
  icon: Component
  navGroup: NavGroup
  activeMatch?: 'group' | 'path' | 'exact'
  excludePaths?: string[]
}

export interface AppNavSection {
  label: string
  items: AppNavItem[]
  collapsible?: boolean
}

export const desktopNavSections: AppNavSection[] = [
  {
    label: '图库',
    items: [
      { label: '首页', href: '/', icon: Home, navGroup: 'home' },
      { label: '照片', href: '/photos', icon: ImageIcon, navGroup: 'photos' },
      {
        label: '相册', href: '/album', icon: Images, navGroup: 'albums', activeMatch: 'path',
        excludePaths: ['/album/people', '/album/location', '/album/classification'],
      },
    ],
  },
  {
    label: '探索',
    collapsible: true,
    items: [
      { label: '人物', href: '/album/people', icon: Users, navGroup: 'albums', activeMatch: 'path' },
      { label: '分类', href: '/album/classification', icon: Tags, navGroup: 'albums', activeMatch: 'path' },
      { label: '记忆', href: '/memories', icon: BookHeart, navGroup: 'memories', activeMatch: 'path' },
      { label: '月迹', href: '/moon', icon: Moon, navGroup: 'albums', activeMatch: 'path' },
      { label: '地图', href: '/album/location', icon: MapPin, navGroup: 'albums', activeMatch: 'path' },
    ],
  },
  {
    label: '更多',
    collapsible: true,
    items: [
      { label: '车票', href: '/ticket', icon: Ticket, navGroup: 'tickets', activeMatch: 'exact' },
      { label: '工具箱', href: '/toolbox', icon: Wrench, navGroup: 'tools', activeMatch: 'path' },
      { label: '断舍离', href: '/swipe-filter', icon: Layers, navGroup: 'tools', activeMatch: 'path' },
    ],
  },
]

export const mobileMoreSections: AppNavSection[] = [
  {
    label: '探索',
    items: [
      { label: '人物', href: '/album/people', icon: Users, navGroup: 'albums' },
      { label: '分类', href: '/album/classification', icon: Tags, navGroup: 'albums' },
      { label: '记忆', href: '/memories', icon: BookHeart, navGroup: 'memories' },
      { label: '月迹', href: '/moon', icon: Moon, navGroup: 'albums' },
      { label: '地图', href: '/album/location', icon: MapPin, navGroup: 'albums' },
    ],
  },
  {
    label: '旅程与管理',
    items: [
      { label: '车票', href: '/ticket', icon: Ticket, navGroup: 'tickets' },
      { label: '工具箱', href: '/toolbox', icon: Wrench, navGroup: 'tools' },
      { label: '断舍离', href: '/swipe-filter', icon: Layers, navGroup: 'tools' },
      { label: '回收站', href: '/recycle-bin', icon: Trash2, navGroup: 'more' },
      { label: '设置', href: '/settings', icon: Settings, navGroup: 'more' },
    ],
  },
]

export const systemNavItems = mobileMoreSections.at(-1)!.items
