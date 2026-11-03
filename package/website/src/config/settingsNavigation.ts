/** Keep links saved by earlier clients working after settings regrouping. */
export function resolveSettingsTab(hash: string, queryTab: unknown): string {
  const raw = hash ? hash.slice(1) : typeof queryTab === 'string' ? queryTab : ''
  const aliases: Record<string, string> = {
    'task-management': 'tasks',
    captions: 'ai-models',
    'mobile-backup-settings': 'mobile-backup',
  }
  return aliases[raw] ?? raw
}
