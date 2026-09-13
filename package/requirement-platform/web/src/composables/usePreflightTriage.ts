import { nextTick, reactive, type Ref } from 'vue'
import { api } from '../api'

type StageStatus = 'waiting' | 'active' | 'done'

export function usePreflightTriage(
  form: object,
  answers: Record<string, string>,
  outputElement: Ref<HTMLElement | null>,
) {
  const progress = reactive({
    percent: 0,
    title: '',
    detail: '',
    done: false,
    failed: false,
    summary: '',
    output: '',
    reasoningOutput: '',
    attempt: 0,
    maxAttempts: 3,
    retryMessages: [] as string[],
    appliedUpdates: [] as string[],
    stages: [] as Array<{ label: string; status: StageStatus }>,
  })

  function setStage(index: number, status: StageStatus) {
    const stage = progress.stages[index]
    if (stage) stage.status = status
  }

  function reset(preserveAppliedUpdates = false) {
    Object.assign(progress, {
      percent: 12,
      title: '正在准备分析',
      detail: '校验输入并整理需求上下文',
      done: false,
      failed: false,
      summary: '',
      output: '',
      reasoningOutput: '',
      attempt: 0,
      maxAttempts: 3,
      retryMessages: [],
      appliedUpdates: preserveAppliedUpdates ? progress.appliedUpdates : [],
      stages: [
        { label: '整理需求信息', status: 'active' },
        { label: '调用分析模型', status: 'waiting' },
        { label: '保存需求与附件', status: 'waiting' },
        { label: '后台结构化分诊', status: 'waiting' },
      ],
    })
  }

  async function run() {
    progress.percent = 30
    progress.title = '正在进行提交前分析'
    progress.detail = 'AI 正在检查信息完整度并判断是否需要追问'
    setStage(0, 'done')
    setStage(1, 'active')
    const result = await api.streamPreflightTriage({ ...form, answers }, event => {
      if (event.type === 'attempt') {
        progress.attempt = event.attempt || 1
        progress.maxAttempts = event.max_attempts || 3
        if (progress.attempt > 1) progress.output += `\n\n—— 第 ${progress.attempt} 次输出 ——\n`
        progress.detail = `AI 正在生成并校验结构化结果（第 ${progress.attempt}/${progress.maxAttempts} 次）`
      } else if (event.type === 'delta' && event.content) {
        if (event.channel === 'reasoning') progress.reasoningOutput += event.content
        else progress.output += event.content
        void nextTick(() => {
          if (outputElement.value) outputElement.value.scrollTop = outputElement.value.scrollHeight
        })
      } else if (event.type === 'retry') {
        progress.retryMessages.push(event.reason || '输出格式不符合要求')
        progress.detail = `本次输出未通过校验，正在自动重试（最多 ${progress.maxAttempts} 次）`
      }
    })
    progress.summary = String(result.analysis?.problem_summary || '')
    const publicSteps = Array.isArray(result.analysis?.analysis_steps)
      ? result.analysis.analysis_steps.filter(Boolean)
      : []
    if (!progress.reasoningOutput && publicSteps.length) {
      progress.reasoningOutput = publicSteps.map((step: string, index: number) => `${index + 1}. ${step}`).join('\n')
    }
    return result
  }

  return { progress, reset, run, setStage }
}
