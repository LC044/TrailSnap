import { expect, request, test } from '@playwright/test'

import { apiBaseUrl, readBootstrapState } from '../helpers/env'

test.describe('系统 API 冒烟 @smoke', () => {
  test('照片导入链路可用', async () => {
    const bootstrapState = readBootstrapState()
    const api = await request.newContext({
      baseURL: apiBaseUrl,
      extraHTTPHeaders: {
        Authorization: `Bearer ${bootstrapState.accessToken}`,
        Accept: 'application/json',
      },
    })

    try {
      const photosResponse = await api.get('/photos', {
        params: { limit: 20 },
      })
      expect(photosResponse.ok()).toBeTruthy()
      const photos = await photosResponse.json() as Array<Record<string, unknown>>
      expect(photos.length).toBeGreaterThan(0)
      expect(photos[0].id).toBeTruthy()
      expect(photos[0].filename).toBeTruthy()

      const tasksResponse = await api.get('/tasks/', {
        params: { limit: 200 },
      })
      expect(tasksResponse.ok()).toBeTruthy()
      const tasks = await tasksResponse.json() as Array<{ status: string }>
      const failedTasks = tasks.filter(task => task.status === 'FAILED')
      expect(failedTasks).toHaveLength(0)

      const detailResponse = await api.get('/photos/detail', {
        params: { limit: 5 },
      })
      expect(detailResponse.ok()).toBeTruthy()
      const details = await detailResponse.json() as Array<{ id?: string, metadata_info?: { file_path?: string } }>
      expect(details.length).toBeGreaterThan(0)
      console.log('Photo detail response:', JSON.stringify(details[0], null, 2))
      expect(details[0].id).toBeTruthy()
    } finally {
      await api.dispose()
    }
  })
})
