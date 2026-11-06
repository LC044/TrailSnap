import { defineStore } from 'pinia'
import { ref } from 'vue'
import { faceApi, type FaceClusteringStatus } from '@/api/face'

export const useFaceClusteringStore = defineStore('faceClustering', () => {
  const status = ref<FaceClusteringStatus | null>(null)
  const submitting = ref(false)
  let pendingRequestId: string | null = null

  async function refresh() {
    status.value = await faceApi.clusteringStatus()
    if (status.value.phase === 'failed') pendingRequestId = null
  }

  function createRequestId() {
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 15) | 64
    bytes[8] = (bytes[8] & 63) | 128
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  async function reset() {
    submitting.value = true
    try {
      pendingRequestId ??= createRequestId()
      status.value = await faceApi.resetClustering(pendingRequestId)
      pendingRequestId = null
    } finally {
      submitting.value = false
    }
  }

  async function retry() {
    submitting.value = true
    try {
      status.value = await faceApi.retryClustering()
    } finally {
      submitting.value = false
    }
  }

  return { status, submitting, refresh, reset, retry }
})
