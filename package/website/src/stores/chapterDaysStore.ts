import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { chapterApi } from '@/api/chapter'

export const useChapterDaysStore = defineStore('chapterDays', () => {
  const text = reactive<Record<string, { caption: string; source: 'ai' | 'manual' }>>({})
  const generating = reactive<Record<string, boolean>>({})
  const errors = reactive<Record<string, string>>({})
  const errorStatus = reactive<Record<string, number>>({})
  const requests = new Map<string, Promise<void>>()
  const key = (id: string, day: string) => `${id}:${day}`
  function generate(id: string, day: string): Promise<void> {
    const k = key(id, day)
    if (requests.has(k)) return requests.get(k)!
    generating[k] = true
    delete errors[k]
    delete errorStatus[k]
    const request = chapterApi.generateDay(id, day).then(result => { text[k] = result }).catch((error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      errors[k] = typeof detail === 'string' ? detail : '暂时无法整理文字，请稍后重试'
      errorStatus[k] = (error as { response?: { status?: number } }).response?.status ?? 0
    }).finally(() => { generating[k] = false; requests.delete(k) })
    requests.set(k, request)
    return request
  }
  async function save(id: string, day: string, caption: string) {
    const k = key(id, day)
    text[k] = await chapterApi.saveDay(id, day, caption)
    delete errors[k]
  }
  return { text, generating, errors, errorStatus, key, generate, save }
})
