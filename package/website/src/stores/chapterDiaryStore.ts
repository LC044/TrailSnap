import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { chapterApi } from '@/api/chapter'
import type { ChapterDiaryDraft } from '@/types/chapter'

// Keep in-flight requests and drafts available when the reader closes the editor.
export const useChapterDiaryStore = defineStore('chapterDiary', () => {
  const drafts = reactive<Record<string, ChapterDiaryDraft>>({})
  const generating = reactive<Record<string, boolean>>({})
  const errors = reactive<Record<string, string>>({})
  function key(id: string, year: number | null) { return `${id}:${year ?? 'introduction'}` }
  async function generate(id: string, year: number | null, version: number, notes: string) {
    const draftKey = key(id, year)
    if (generating[draftKey]) return
    generating[draftKey] = true
    delete errors[draftKey]
    try {
      drafts[draftKey] = await chapterApi.generateDiary(id, {
        scope: year === null ? 'introduction' : 'year', year: year ?? undefined, version, notes,
      })
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      errors[draftKey] = typeof detail === 'string' ? detail : '生成暂时失败，请稍后重试'
    } finally { generating[draftKey] = false }
  }
  return { drafts, generating, errors, key, generate }
})
