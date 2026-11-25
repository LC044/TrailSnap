import { test, expect } from '@playwright/test'
import { ensureAuthSession } from '../../helpers/auth'

// Synthetic bytes only exercise queue admission, never RAW decoding or upload.
// Actual RAF/NEF decoding is covered by the server sample regression tests.
test('RAW 文件选择和拖放进入上传队列 @p0', async ({ page, request }, testInfo) => {
  if (!(await ensureAuthSession(request, page, testInfo))) return
  await page.goto('/photos', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '上传照片', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ has: page.getByText('上传到文件夹', { exact: true }) })
  await expect(dialog.getByText(/支持 RAF、NEF/)).toBeVisible()
  const input = dialog.locator('input[type="file"]')
  const accept = (await input.getAttribute('accept'))!.split(',')
  expect(accept).toContain('.raf')
  expect(accept).toContain('.nef')
  await input.setInputFiles([
    { name: 'camera.RAF', mimeType: 'application/octet-stream', buffer: Buffer.from('raf-queue-fixture') },
    { name: 'camera.NEF', mimeType: '', buffer: Buffer.from('nef-queue-fixture') },
  ])
  await expect(dialog.getByText('上传队列 (2)', { exact: true })).toBeVisible()
  await expect(dialog.getByText('camera.RAF', { exact: true })).toBeVisible()
  await expect(dialog.getByText('camera.NEF', { exact: true })).toBeVisible()
  const transfer = await page.evaluateHandle(() => {
    const data = new DataTransfer()
    data.items.add(new File(['drop-fixture'], 'dropped.raf', { type: '' }))
    return data
  })
  await dialog.getByRole('button').filter({ hasText: '添加更多照片 / 视频' }).dispatchEvent('drop', { dataTransfer: transfer })
  await transfer.dispose()
  await expect(dialog.getByText('上传队列 (3)', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: '开始上传', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '清空', exact: true }).click()
  await expect(dialog.getByText('点击或拖拽上传图片/视频')).toBeVisible()
})
