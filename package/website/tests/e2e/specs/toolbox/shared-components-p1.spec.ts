import { expect, test } from '@playwright/test'
import { ensureAuthSession } from '../../helpers/auth'

const response = (data: unknown) => ({ contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data }) })

test.describe('P1 - 公共任务、目录与设置组件', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  // 三个工具页现在共用 ToolWorkflowPage：旧版 `/api/toolbox/<tool>/tasks/latest`
  // 轮询、进度条「3 / 10」和「选择目录」禁用态都已移除，任务进度改由持久化预览计划呈现。
  for (const tool of [
    { path: 'rename', title: '批量重命名' },
    { path: 'organize', title: '影像整理' },
    { path: 'time-from-filename', title: '修正拍摄信息' },
  ]) {
    test(`${tool.path} 使用统一预览计划工作流而非旧任务轮询`, async ({ page }) => {
      await page.goto(`/toolbox/${tool.path}`)
      await expect(page.locator('h1.ts-page-title', { hasText: tool.title })).toBeVisible({ timeout: 10_000 })
      await expect(page.getByRole('list', { name: '操作步骤' })).toBeVisible()
      await expect(page.getByRole('link', { name: '操作记录' })).toHaveAttribute('href', '/toolbox')
      await expect(page.getByRole('button', { name: '下一步：设置规则' })).toBeDisabled()
    })
  }

  test('范围来源切换不会隐式带入目录，文件夹需显式选择', async ({ page }) => {
    await page.goto('/toolbox/rename')
    const sources = page.getByRole('group', { name: '范围来源' })

    await sources.getByRole('button', { name: '文件夹' }).click()
    await expect(page.getByRole('button', { name: '选择文件夹' })).toBeVisible()
    await expect(page.getByText('包含子文件夹', { exact: true })).toBeVisible()
    await expect(page.getByText('这些是服务器或桌面图库中的实际目录，不是手机本地相册。')).toBeVisible()
    await expect(page.getByText('尚未选择文件夹')).toBeVisible()
    // 旧版目录树「加载失败/重试/确认/取消」与文件夹输入框随直连表单移除，
    // 目录现在作为范围的一部分显式列出，不再写回输入框。
    await expect(page.getByPlaceholder('请选择要进行重命名操作的文件夹')).toHaveCount(0)

    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('全部图库（主动选择）')).toBeVisible()
    await sources.getByRole('button', { name: '文件夹' }).click()
    await expect(page.getByText('尚未选择文件夹')).toBeVisible()
  })

  test('AI 服务分区保存不会提交大模型连接或默认模型', async ({ page }) => {
    const payloads: Array<{ ai: Record<string, unknown> }> = []
    await page.route('**/api/settings/', async route => {
      if (route.request().method() === 'PUT') {
        payloads.push(route.request().postDataJSON())
        await route.fulfill(response({ status: 'success' }))
      } else await route.fulfill(response({ ai: {
        ai_api_url: 'http://ai-service:8001', face_recognition_threshold: 0.7,
        connections: [{ id: 'existing-connection' }], chat_model_name: 'existing-model',
      }, runtime: { managedAI: false } }))
    })
    // 设置重组后 AI 服务地址输入框只出现在「本地识别模型」（recognition）页的服务分区，
    // 不再挂在与大模型共用的 basic 页；recognition 页面还请求 ai-models 列表，一并桩掉。
    await page.route('**/api/settings/ai-models', route => route.fulfill(response({ models: [], tasks: {} })))
    await page.goto('/settings#recognition')
    // runtime.managedAI=false 时才渲染 AI API 地址输入框；等输入框出现即代表 loadData 已应用服务端值。
    await expect(page.getByRole('textbox', { name: 'AI API 地址', exact: true })).toHaveValue('http://ai-service:8001', { timeout: 10_000 })
    await page.getByRole('button', { name: '保存服务地址', exact: true }).click()
    await expect.poll(() => payloads.length).toBe(1)
    expect(payloads[0].ai.ai_api_url).toBe('http://ai-service:8001')
    expect(payloads[0].ai).not.toHaveProperty('connections')
    expect(payloads[0].ai).not.toHaveProperty('chat_model_name')
  })
})
