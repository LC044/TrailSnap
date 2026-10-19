import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Requirement } from '../api'

type Receipt = { id: string; number: number; token: string }
const key = 'rp_anonymous_receipts_v1'

export const useAnonymousReceipts = defineStore('anonymous-receipts', () => {
  const receipts = ref<Receipt[]>([])
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) || '[]')
    if (Array.isArray(value)) receipts.value = value.filter((item): item is Receipt =>
      !!item && typeof item.id === 'string' && Number.isInteger(item.number) && item.number > 0 &&
      typeof item.token === 'string' && /^[A-Za-z0-9_-]{43,128}$/.test(item.token))
  } catch { /* Unavailable storage must not prevent feedback. */ }

  function save(requirement: Requirement, token: string): boolean {
    if (!requirement.public_number) return false
    const receipt = { id: requirement.id, number: requirement.public_number, token }
    receipts.value = [receipt, ...receipts.value.filter(item => item.id !== requirement.id)]
    try { localStorage.setItem(key, JSON.stringify(receipts.value)); return true } catch { return false }
  }
  function tokenFor(id: string) { return receipts.value.find(item => item.id === id)?.token }
  function managementLink(requirement: Requirement) {
    const token = tokenFor(requirement.id)
    return token ? `${location.origin}/requirements/REQ-${requirement.public_number}#edit_token=${encodeURIComponent(token)}` : ''
  }
  return { receipts, save, tokenFor, managementLink }
})

export function newEditToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
