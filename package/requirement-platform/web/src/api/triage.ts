export type TriageStreamEvent = {
  type: 'attempt' | 'delta' | 'retry' | 'complete' | 'error'
  attempt?: number
  max_attempts?: number
  model?: string
  content?: string
  channel?: 'reasoning' | 'content'
  reason?: string
  available?: boolean
  questions?: Array<{ question_id: string; target_field?: string; question: string; rationale: string; suggested_options: string[] }>
  analysis?: Record<string, any>
  connection_id?: string
}

export async function streamPreflightTriage(
  data: unknown,
  onEvent: (event: TriageStreamEvent) => void,
): Promise<TriageStreamEvent> {
  const baseUrl = import.meta.env.VITE_REQUIREMENT_API_URL || '/api'
  const token = localStorage.getItem('rp_token')
  const response = await fetch(`${baseUrl}/requirements/preflight-triage/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(data),
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || `AI 分析请求失败（HTTP ${response.status}）`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal: TriageStreamEvent | null = null
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const dataLine = block.split('\n').find(line => line.startsWith('data:'))
      if (!dataLine) continue
      const event = JSON.parse(dataLine.slice(5).trim()) as TriageStreamEvent
      onEvent(event)
      if (event.type === 'complete' || event.type === 'error') terminal = event
    }
    if (done) break
  }
  if (!terminal) throw new Error('AI 分析连接提前结束，请重试')
  return terminal
}
