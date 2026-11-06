import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { faceApi, type PhotoFace, type SimilarFaceCandidate, type SimilarFaceMatch, type SimilarFaceScope } from '@/api/face'
import type { FaceIdentity } from '@/types/album'

const PAGE_SIZE = 60
const MAX_SELECTION = 500

function errorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

export function useSimilarFaces(
  props: { visible: boolean; reference: PhotoFace },
  onApplied: (photoIds: string[]) => void,
) {
  const reference = ref<SimilarFaceCandidate | null>(null)
  const items = ref<SimilarFaceCandidate[]>([])
  const selected = ref(new Map<number, SimilarFaceCandidate>())
  const target = ref<FaceIdentity | null>(null)
  const assignmentMode = ref<'person' | 'unassigned'>('person')
  const scope = ref<SimilarFaceScope>('all')
  const match = ref<SimilarFaceMatch>('balanced')
  const hideAssigned = ref(true)
  const showSelected = ref(false)
  const page = ref(0)
  const faceCount = ref(0)
  const photoCount = ref(0)
  const hasMore = ref(false)
  const loading = ref(false)
  const appending = ref(false)
  const submitting = ref(false)
  const loadError = ref('')
  const actionError = ref('')
  const successMessage = ref('')
  const undoToken = ref<string | null>(null)
  let requestVersion = 0
  let controller: AbortController | null = null
  let resetting = false
  let pendingReferenceSelection = false

  const lowSimilarity = computed(() => scope.value === 'current_low')
  const destinationId = computed(() => assignmentMode.value === 'unassigned' ? null : target.value?.id)
  const selectedItems = computed(() => [...selected.value.values()].filter(item =>
    item.identity_id !== destinationId.value && (!lowSimilarity.value || item.id !== props.reference.id)))
  const selectedCount = computed(() => selectedItems.value.length)
  const visibleItems = computed(() => showSelected.value
    ? selectedItems.value
    : items.value.filter(item => !hideAssigned.value || item.identity_id !== destinationId.value))
  const reassignCount = computed(() => selectedItems.value.filter(item => item.identity_id).length)
  const manualCount = computed(() => selectedItems.value.filter(item => item.manually_confirmed).length)
  const canSubmit = computed(() => destinationId.value !== undefined && selectedCount.value > 0 && !submitting.value && !loading.value)
  const excludeIdentity = computed(() => hideAssigned.value && assignmentMode.value === 'person' ? target.value?.id : undefined)

  async function load(nextPage = 0, append = false, selectReference = false) {
    if (!props.visible) return
    if (selectReference) pendingReferenceSelection = true
    controller?.abort()
    controller = new AbortController()
    const version = ++requestVersion
    const seed = props.reference
    loading.value = true
    appending.value = append
    loadError.value = ''
    try {
      const result = await faceApi.searchSimilarFaces(seed.photo_id, seed.id, {
        scope: scope.value, match: match.value, skip: nextPage * PAGE_SIZE,
        limit: PAGE_SIZE, exclude_identity_id: excludeIdentity.value,
      }, controller.signal)
      if (version !== requestVersion || !props.visible) return
      reference.value = result.reference
      items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items
      page.value = nextPage
      faceCount.value = result.face_count
      photoCount.value = result.photo_count
      hasMore.value = result.has_more
      // Preserve the snapshots the user selected; never silently accept a later reassignment.
      if (pendingReferenceSelection) {
        if (!lowSimilarity.value) selected.value.set(result.reference.id, result.reference)
        pendingReferenceSelection = false
      }
    } catch (error) {
      if (version === requestVersion && props.visible) {
        loadError.value = errorMessage(error, '查找失败，请检查连接后重试')
      }
    } finally {
      if (version === requestVersion) { loading.value = false; appending.value = false }
    }
  }

  function isSelected(item: SimilarFaceCandidate) {
    return canSelect(item) && selected.value.has(item.id)
  }

  function canSelect(item: SimilarFaceCandidate) {
    return item.identity_id !== destinationId.value && (!lowSimilarity.value || item.id !== props.reference.id)
  }

  function toggle(item: SimilarFaceCandidate) {
    if (submitting.value || !canSelect(item)) return
    actionError.value = ''
    if (selected.value.has(item.id)) selected.value.delete(item.id)
    else if (selected.value.size < MAX_SELECTION) selected.value.set(item.id, item)
    else actionError.value = `每次最多更正 ${MAX_SELECTION} 张人脸，请分批操作`
  }

  function selectPage() {
    if (submitting.value || loading.value || showSelected.value) return
    const start = page.value * PAGE_SIZE
    const rows = items.value.length > PAGE_SIZE ? items.value.slice(start, start + PAGE_SIZE) : items.value
    for (const item of rows) {
      if (canSelect(item) && !selected.value.has(item.id)) {
        if (selected.value.size >= MAX_SELECTION) {
          actionError.value = `每次最多更正 ${MAX_SELECTION} 张人脸，请分批操作`
          break
        }
        selected.value.set(item.id, item)
      }
    }
  }

  function clearSelection() {
    if (!submitting.value) selected.value.clear()
  }

  function chooseTarget(person: FaceIdentity) {
    if (!submitting.value) {
      target.value = person
      assignmentMode.value = 'person'
    }
  }

  async function apply() {
    if (!canSubmit.value || destinationId.value === undefined) return
    const identityId = destinationId.value
    submitting.value = true
    actionError.value = ''
    const version = requestVersion
    try {
      const result = await faceApi.assignSimilarFaces(
        props.reference.photo_id, props.reference.id, identityId, selectedItems.value,
      )
      if (version !== requestVersion || !props.visible) return
      undoToken.value = result.undo_token
      successMessage.value = identityId === null
        ? `已将 ${result.face_count} 张人脸释放为未标记，照片和人脸仍然保留`
        : `已将 ${result.face_count} 张人脸更正为“${target.value?.identity_name || '未命名人物'}”`
      selected.value.clear()
      showSelected.value = false
      onApplied(result.photo_ids)
      await load()
    } catch (error: any) {
      if (version !== requestVersion || !props.visible) return
      actionError.value = errorMessage(error, '更正未保存，请重试')
      if (error?.response?.status === 409) {
        selected.value.clear()
        showSelected.value = false
        await load()
      }
    } finally {
      submitting.value = false
    }
  }

  async function undo() {
    if (!undoToken.value || submitting.value) return
    submitting.value = true
    actionError.value = ''
    const version = requestVersion
    try {
      const result = await faceApi.undoFaceAssignment(undoToken.value)
      if (version !== requestVersion || !props.visible) return
      undoToken.value = null
      successMessage.value = `已撤销本次更正，恢复 ${result.face_count} 张人脸的原归属`
      selected.value.clear()
      showSelected.value = false
      onApplied(result.photo_ids)
      await load()
    } catch (error) {
      if (version !== requestVersion || !props.visible) return
      actionError.value = errorMessage(error, '撤销失败，请重试')
    } finally {
      submitting.value = false
    }
  }

  watch([() => props.visible, () => props.reference.id], ([visible]) => {
    ++requestVersion
    controller?.abort()
    loading.value = false
    pendingReferenceSelection = false
    if (!visible) return
    resetting = true
    reference.value = null
    items.value = []
    selected.value.clear()
    target.value = null
    assignmentMode.value = 'person'
    scope.value = 'all'
    match.value = 'balanced'
    hideAssigned.value = true
    showSelected.value = false
    page.value = 0
    faceCount.value = 0
    photoCount.value = 0
    hasMore.value = false
    actionError.value = ''
    successMessage.value = ''
    undoToken.value = null
    resetting = false
    void load(0, false, true)
  }, { immediate: true })

  watch([scope, match, excludeIdentity], () => {
    if (!props.visible || submitting.value || resetting) return
    if (lowSimilarity.value) {
      selected.value.delete(props.reference.id)
      pendingReferenceSelection = false
    }
    showSelected.value = false
    void load()
  }, { flush: 'sync' })
  onBeforeUnmount(() => { ++requestVersion; controller?.abort() })

  return {
    reference, items, target, assignmentMode, lowSimilarity, scope, match, hideAssigned, showSelected, page,
    faceCount, photoCount, hasMore, loading, appending, submitting, loadError, actionError,
    successMessage, undoToken, selectedItems, selectedCount, visibleItems,
    reassignCount, manualCount, canSubmit, load, isSelected, canSelect, toggle, selectPage,
    clearSelection, chooseTarget, apply, undo,
  }
}
