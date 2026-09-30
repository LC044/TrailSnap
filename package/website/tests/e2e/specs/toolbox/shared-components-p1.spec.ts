import { expect, test } from '@playwright/test'
import { ensureAuthSession } from '../../helpers/auth'

const response = (data: unknown) => ({ contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data }) })

test.describe('P1 - 公共任务、目录与设置组件', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  for (const tool of ['rename', 'organize', 'time-from-filename']) {
    test(`${tool} 恢复任务并在完成后解除表单禁用`, async ({ page }) => {
      const task = { id: 'shared-task', type: 'TEST', status: 'processing', total_items: 10, processed_items: 3 }
      let completed = false
      await page.route(`**/api/toolbox/${tool}/tasks/latest`, route => route.fulfill(response(task)))
      await page.route('**/api/tasks/shared-task', route => route.fulfill(response(completed ? { ...task, status: 'completed', processed_items: 10 } : task)))
      await page.goto(`/toolbox/${tool}`)
      await expect(page.getByText('3 / 10', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: '选择目录', exact: true })).toBeDisabled()
      completed = true
      await expect(page.getByText('任务状态: 已完成')).toBeVisible({ timeout: 10000 })
      await expect(page.getByRole('button', { name: '选择目录', exact: true })).toBeEnabled()
    })
  }

  test('目录加载失败可重试，取消选择不会修改已确认路径', async ({ page }) => {
    await page.route('**/api/toolbox/rename/tasks/latest', route => route.fulfill(response(null)))
    let fail = true
    await page.route('**/api/settings/directories/tree*', async route => {
      if (fail) await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary error' }) })
      else await route.fulfill(response({ directories: [{ name: '照片目录', path: '/photos', is_leaf: true }] }))
    })
    await page.goto('/toolbox/rename')
    await page.getByRole('button', { name: '选择目录', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('alert')).toContainText('加载目录失败')
    fail = false
    await dialog.getByRole('button', { name: '重试', exact: true }).click()
    await dialog.getByText('照片目录', { exact: true }).click()
    await dialog.getByRole('button', { name: '确认', exact: true }).click()
    const input = page.getByPlaceholder('请选择要进行重命名操作的文件夹')
    await expect(input).toHaveValue('/photos')
    await page.getByRole('button', { name: '选择目录', exact: true }).click()
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await expect(input).toHaveValue('/photos')
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
      } }))
    })
    await page.goto('/settings?tab=basic')
    await page.locator('.el-collapse-item__header').filter({ hasText: 'AI 服务与人脸设置' }).click()
    await expect(page.getByRole('textbox', { name: 'AI API 地址', exact: true })).toHaveValue('http://ai-service:8001')
    await page.getByRole('button', { name: '保存 AI 配置', exact: true }).click()
    await expect.poll(() => payloads.length).toBe(1)
    expect(payloads[0].ai.ai_api_url).toBe('http://ai-service:8001')
    expect(payloads[0].ai).not.toHaveProperty('connections')
    expect(payloads[0].ai).not.toHaveProperty('chat_model_name')
  })
})
