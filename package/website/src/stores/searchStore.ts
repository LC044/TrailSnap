import { defineStore } from 'pinia'
import { useStorage } from '@vueuse/core'

export const useSearchStore = defineStore('search', () => {
  const history = useStorage<string[]>('ts-search-history', [])
  const remember = (query: string) => {
    const value = query.trim()
    if (value) history.value = [value, ...history.value.filter(item => item !== value)].slice(0, 12)
  }
  const clearHistory = () => { history.value = [] }
  return { history, remember, clearHistory }
})
