import { ref, provide, inject, type Ref, type InjectionKey, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Images, User, MapPin, Tag, Bookmark } from 'lucide-vue-next'
import { navApi, type NavItemRef, type ResolvedNavItem } from '@/api/nav'
import { thumbnailUrl } from '@/utils/mediaUrl'

// --- Types ---

export type { NavItemRef, ResolvedNavItem }
export type { NavEntityType } from '@/api/nav'

export interface NavItemsProvide {
  items: Ref<ResolvedNavItem[]>
  loading: Ref<boolean>
  fetchItems(): Promise<void>
  updateItems(refs: NavItemRef[]): Promise<void>
  removeItem(entityType: string, entityId: string): Promise<void>
  addItem(ref: NavItemRef): Promise<void>
  isAdded(entityType: string, entityId: string): boolean
}

// --- 共享辅助：快捷访问项的图标与缩略图 ---

/** 自定义导航项的实体类型 -> 图标组件（Sidebar / BottomNav 共用） */
export const getNavIcon = (entityType: string) => {
  const map: Record<string, any> = {
    'album': Images,
    'person': User,
    'location': MapPin,
    'classification': Tag
  }
  return map[entityType] || Bookmark
}

/** 自定义导航项的封面缩略图 URL（person 用 medium 尺寸，其余默认） */
export const getThumbnailUrl = (item: ResolvedNavItem) => {
  if (item.entity_type === 'person' && item.cover_photo_id) {
    return thumbnailUrl(item.cover_photo_id, 'medium')
  }
  if (item.cover_photo_id) {
    return thumbnailUrl(item.cover_photo_id)
  }
  return ''
}

// --- Cache ---

const CACHE_KEY = 'trailsnap:nav-items'
const CACHE_TTL = 30 * 60 * 1000 // 30 minutes

interface CacheRecord {
  timestamp: number
  data: ResolvedNavItem[]
}

function readCache(): ResolvedNavItem[] | null {
  try {
    const json = localStorage.getItem(CACHE_KEY)
    if (!json) return null
    const record = JSON.parse(json) as CacheRecord
    if (Date.now() - record.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_KEY)
      return null
    }
    return record.data
  } catch {
    return null
  }
}

function writeCache(items: ResolvedNavItem[]) {
  try {
    const record: CacheRecord = { timestamp: Date.now(), data: items }
    localStorage.setItem(CACHE_KEY, JSON.stringify(record))
  } catch {
    // QuotaExceededError - ignore
  }
}

// --- Core composable ---

function useNavItemsLogic(): NavItemsProvide {
  const items = ref<ResolvedNavItem[]>([]) as Ref<ResolvedNavItem[]>
  const loading = ref(false)
  let lastFetchTime = 0

  // Load from cache immediately
  const cached = readCache()
  if (cached) {
    items.value = cached
  }

  const fetchItems = async () => {
    loading.value = true
    try {
      const res = await navApi.getItems()
      items.value = res?.items || []
      writeCache(items.value)
      lastFetchTime = Date.now()
    } catch (e) {
      console.error('Failed to fetch nav items', e)
    } finally {
      loading.value = false
    }
  }

  const updateItems = async (refs: NavItemRef[]) => {
    loading.value = true
    try {
      const res = await navApi.updateItems(refs)
      items.value = res?.items || []
      writeCache(items.value)
    } catch (e) {
      console.error('Failed to update nav items', e)
    } finally {
      loading.value = false
    }
  }

  const removeItem = async (entityType: string, entityId: string) => {
    loading.value = true
    try {
      const res = await navApi.deleteItem(entityType, entityId)
      items.value = res?.items || []
      writeCache(items.value)
    } catch (e) {
      console.error('Failed to remove nav item', e)
    } finally {
      loading.value = false
    }
  }

  const addItem = async (ref: NavItemRef) => {
    const currentRefs: NavItemRef[] = items.value.map(item => ({
      entity_type: item.entity_type as NavItemRef['entity_type'],
      entity_id: item.entity_id
    }))
    // Avoid duplicates
    if (currentRefs.some(r => r.entity_type === ref.entity_type && r.entity_id === ref.entity_id)) {
      return
    }
    currentRefs.push(ref)
    await updateItems(currentRefs)
  }

  const isAdded = (entityType: string, entityId: string): boolean => {
    return items.value.some(item => item.entity_type === entityType && item.entity_id === entityId)
  }

  // Initial fetch (background, after cache load)
  fetchItems()

  // Auto-refresh on route change (5 min debounce)
  const route = useRoute()
  watch(() => route.path, () => {
    if (Date.now() - lastFetchTime > 5 * 60 * 1000) {
      fetchItems()
    }
  })

  return {
    items,
    loading,
    fetchItems,
    updateItems,
    removeItem,
    addItem,
    isAdded
  }
}

// --- Provide / Inject ---

const NavItemsInjectionKey: InjectionKey<NavItemsProvide> = Symbol('navItems')

export function provideNavItems(): NavItemsProvide {
  const navItems = useNavItemsLogic()
  provide(NavItemsInjectionKey, navItems)
  return navItems
}

export function injectNavItems(): NavItemsProvide {
  const navItems = inject(NavItemsInjectionKey)
  if (!navItems) {
    throw new Error('Nav items not provided! Call provideNavItems() in App.vue')
  }
  return navItems
}
