import { ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { relationsApi } from '@/api/relations'
import { getServerUrl } from '@/config/server'
import { useUserStore } from '@/stores/user'
import type { RelationEdge, RelationNode, RelationPage, RelationType } from '@/types/relations'

export interface CanvasPoint { x: number; y: number }

function edgeKey(edge: RelationEdge) {
  return [edge.source, edge.target].sort().join('|')
}

function positionChildren(
  anchor: CanvasPoint,
  children: RelationNode[],
  positions: Record<string, CanvasPoint>,
  root: boolean,
) {
  const occupied = Object.values(positions)
  const outward = root ? -Math.PI / 2 : Math.atan2(anchor.y, anchor.x)
  children.forEach((node, index) => {
    const angle = root
      ? -Math.PI / 2 + (index * 2 * Math.PI) / Math.max(children.length, 1)
      : outward - 1.05 + (index * 2.1) / Math.max(children.length - 1, 1)
    let point = { x: anchor.x, y: anchor.y }
    for (let attempt = 0; attempt < 360; attempt++) {
      const ring = Math.floor(attempt / 18)
      const swing = attempt % 18
      const offset = swing ? (swing % 2 ? 1 : -1) * Math.ceil(swing / 2) * 0.08 : 0
      const radius = (root ? 185 + (index % 2) * 55 : 165) + ring * 72
      point = { x: anchor.x + Math.cos(angle + offset) * radius, y: anchor.y + Math.sin(angle + offset) * radius }
      if (occupied.every((other) => Math.hypot(point.x - other.x, point.y - other.y) > (root ? 76 : 98))) break
    }
    positions[node.id] = point
    occupied.push(point)
  })
}

interface Visit {
  root: string
  label: string
  types: RelationType[]
  cursor: string | null
  scroll: number
  zoom: number
  pan: number[] | null
  previousCursors: (string | null)[]
}
export const useRelationStore = defineStore('relations', () => {
  const page = ref<RelationPage | null>(null)
  const types = ref<RelationType[]>(['person', 'place', 'memory', 'photo'])
  const visits = ref<Visit[]>([])
  const selected = ref<RelationNode[]>([])
  const comparing = ref(false)
  const loading = ref(false)
  const error = ref('')
  const cursor = ref<string | null>(null)
  const previousCursors = ref<(string | null)[]>([])
  const zoom = ref(1)
  const pan = ref<number[] | null>(null)
  const scroll = ref(0)
  const resultPair = ref<RelationNode[]>([])
  const evidenceMode = ref(false)
  const canvasNodes = ref<RelationNode[]>([])
  const canvasEdges = ref<RelationEdge[]>([])
  const canvasPositions = ref<Record<string, CanvasPoint>>({})
  const canvasParents = ref<Record<string, string>>({})
  const canvasCursors = ref<Record<string, string | null>>({})
  const canvasExpanded = ref<string[]>([])
  const canvasLoading = ref('')
  const canvasError = ref('')
  let generation = 0
  let canvasGeneration = 0
  let canvasScope = ''
  let accountScope = ''
  function clearCanvas() {
    canvasGeneration++
    canvasScope = ''
    canvasNodes.value = []
    canvasEdges.value = []
    canvasPositions.value = {}
    canvasParents.value = {}
    canvasCursors.value = {}
    canvasExpanded.value = []
    canvasLoading.value = ''
    canvasError.value = ''
  }
  function mergeCanvas(data: RelationPage, parentId: string) {
    const known = new Set(canvasNodes.value.map((node) => node.id))
    const fresh = data.nodes.filter((node) => !known.has(node.id))
    const anchor = canvasPositions.value[parentId] || { x: 0, y: 0 }
    const positions = { ...canvasPositions.value }
    positionChildren(anchor, fresh, positions, parentId === data.center.id && parentId === canvasNodes.value[0]?.id)
    canvasPositions.value = positions
    canvasNodes.value = [...canvasNodes.value, ...fresh]
    for (const node of fresh) canvasParents.value[node.id] = parentId
    const edges = new Map(canvasEdges.value.map((edge) => [edgeKey(edge), edge]))
    for (const edge of data.edges) {
      const key = edgeKey(edge)
      const prior = edges.get(key)
      if (!prior || edge.photo_count + edge.memory_count > prior.photo_count + prior.memory_count) edges.set(key, edge)
    }
    canvasEdges.value = [...edges.values()]
    canvasCursors.value[parentId] = data.has_more ? data.next_cursor : null
    if (!canvasExpanded.value.includes(parentId)) canvasExpanded.value = [...canvasExpanded.value, parentId]
    return fresh.length
  }
  function initializeCanvas(data: RelationPage, append = false) {
    const scope = `${data.center.id}|${[...types.value].sort().join(',')}`
    if (!append || canvasScope !== scope) {
      clearCanvas()
      canvasScope = scope
      canvasNodes.value = [data.center]
      canvasPositions.value = { [data.center.id]: { x: 0, y: 0 } }
      zoom.value = 1
      pan.value = [0, 0]
    }
    mergeCanvas(data, data.center.id)
  }
  async function expandCanvas(nodeId: string) {
    checkScope()
    if (canvasLoading.value || !canvasPositions.value[nodeId]) return 0
    const expanded = canvasExpanded.value.includes(nodeId)
    const cursor = expanded ? canvasCursors.value[nodeId] : null
    if (expanded && !cursor) return 0
    const ticket = canvasGeneration
    const scope = canvasScope
    canvasLoading.value = nodeId
    canvasError.value = ''
    try {
      const data = await relationsApi.neighbors(nodeId, types.value, cursor)
      if (ticket !== canvasGeneration || scope !== canvasScope) return 0
      return mergeCanvas(data, nodeId)
    } catch {
      if (ticket === canvasGeneration) canvasError.value = '展开失败，请重试。'
      return 0
    } finally {
      if (ticket === canvasGeneration) canvasLoading.value = ''
    }
  }
  function reset() {
    generation++
    clearCanvas()
    page.value = null
    visits.value = []
    selected.value = []
    comparing.value = false
    types.value = ['person', 'place', 'memory', 'photo']
    error.value = ''
    loading.value = false
    cursor.value = null
    previousCursors.value = []
    zoom.value = 1
    pan.value = null
    scroll.value = 0
    resultPair.value = []
    evidenceMode.value = false
  }
  watch(() => useUserStore().token, reset, { flush: 'sync' })
  function checkScope() {
    const user = useUserStore()
    const scope = `${getServerUrl()}|${user.userInfo?.id || ''}|${user.token || ''}`
    if (scope !== accountScope) {
      reset()
      accountScope = scope
    }
  }
  async function explore(
    root: string,
    mode: 'visit' | 'restore' | 'filter' | 'page' = 'visit',
    nextCursor: string | null = null,
  ) {
    checkScope()
    const ticket = ++generation
    loading.value = true
    error.value = ''
    const oldTypes = [...types.value]
    const snapshot = page.value
      ? {
          root: page.value.center.id,
          label: page.value.center.label,
          types: oldTypes,
          cursor: cursor.value,
          scroll: scroll.value,
          zoom: zoom.value,
          pan: pan.value,
          previousCursors: [...previousCursors.value],
        }
      : null
    try {
      const data = await relationsApi.neighbors(root, types.value, nextCursor)
      if (ticket !== generation) return false
      if (mode === 'visit' && snapshot && snapshot.root !== data.center.id) {
        const earlier = visits.value.findIndex((item) => item.root === data.center.id)
        visits.value = earlier >= 0 ? visits.value.slice(0, earlier) : [...visits.value.slice(-19), snapshot]
      }
      page.value = data
      initializeCanvas(data, mode === 'page' || mode === 'restore')
      cursor.value = nextCursor
      if (mode !== 'page') previousCursors.value = []
      if (mode === 'visit') {
        zoom.value = 1
        pan.value = null
        scroll.value = 0
      }
      return true
    } catch (cause: any) {
      if (ticket !== generation) return false
      const unavailable = cause?.code === 404 || cause?.response?.status === 404
      error.value = unavailable ? '内容已不可用，请返回或选择其他对象。' : '加载失败，请重试。'
      if (unavailable) {
        page.value = null
        selected.value = []
        comparing.value = false
      }
      return false
    } finally {
      if (ticket === generation) loading.value = false
    }
  }
  function toggle(node: RelationNode) {
    const found = selected.value.findIndex((item) => item.id === node.id)
    if (found >= 0) selected.value.splice(found, 1)
    else if (selected.value.length < 2) selected.value.push(node)
    else return false
    return true
  }
  return {
    page,
    types,
    visits,
    selected,
    comparing,
    loading,
    error,
    cursor,
    previousCursors,
    zoom,
    pan,
    scroll,
    resultPair,
    evidenceMode,
    canvasNodes,
    canvasEdges,
    canvasPositions,
    canvasParents,
    canvasCursors,
    canvasExpanded,
    canvasLoading,
    canvasError,
    reset,
    checkScope,
    explore,
    expandCanvas,
    toggle,
  }
})
