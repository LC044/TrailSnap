import { expect, test } from '@playwright/test'
import {
  adaptTransferTuning,
  backupUploadAction,
  initialTransferTuning,
  isLanServerUrl,
  takeTransferBatch,
} from '../../../../src/utils/backupTransfer'

const MB = 1024 * 1024

test.describe('P0 - 手机备份自适应传输 @p0', () => {
  test('仅在 Wi-Fi 连接私有地址时启用局域网并发', () => {
    expect(isLanServerUrl('http://192.168.1.8:8000')).toBe(true)
    expect(isLanServerUrl('https://photos.example.com')).toBe(false)

    const lan = initialTransferTuning('http://192.168.1.8:8000', {
      connected: true,
      wifi: true,
      unmetered: true,
    })
    expect(lan).toMatchObject({ isLan: true, mediaConcurrency: 3, chunkConcurrency: 2, chunkSize: 8 * MB })

    const publicWifi = initialTransferTuning('https://photos.example.com', {
      connected: true,
      wifi: true,
      unmetered: true,
    })
    expect(publicWifi).toMatchObject({ isLan: false, mediaConcurrency: 1, chunkConcurrency: 1, chunkSize: 2 * MB })
  })

  test('公网仅在吞吐稳定时有限提速，失败后立即降为单路', () => {
    const initial = initialTransferTuning('https://photos.example.com', {
      connected: true,
      wifi: true,
      unmetered: true,
    })
    const fast = adaptTransferTuning(initial, 6 * MB)
    expect(fast).toMatchObject({ mediaConcurrency: 2, chunkConcurrency: 2, chunkSize: 4 * MB })

    const degraded = adaptTransferTuning(fast, 6 * MB, true)
    expect(degraded).toMatchObject({ mediaConcurrency: 1, chunkConcurrency: 1, chunkSize: 2 * MB })
  })

  test('计费网络始终使用小分片和单路上传', () => {
    const metered = initialTransferTuning('https://photos.example.com', {
      connected: true,
      wifi: false,
      unmetered: false,
    })
    expect(adaptTransferTuning(metered, 20 * MB)).toMatchObject({
      metered: true,
      mediaConcurrency: 1,
      chunkConcurrency: 1,
      chunkSize: MB,
    })
  })

  test('批次同时受媒体并发数和在途字节上限约束', () => {
    const tuning = initialTransferTuning('http://10.0.0.2:8000', {
      connected: true,
      wifi: true,
      unmetered: true,
    })
    const items = [{ size: 50 * MB }, { size: 50 * MB }, { size: MB }]
    expect(takeTransferBatch(items, tuning)).toHaveLength(1)
    expect(takeTransferBatch([{ size: MB }, { size: MB }, { size: MB }, { size: MB }], tuning)).toHaveLength(3)
  })

  test('已完整备份的媒体跳过，只有不完整记录才覆盖上传', () => {
    const presence = {
      existing: new Set(['photo', 'live-complete', 'live-image-only', 'missing-file']),
      complete: new Set(['photo', 'live-complete', 'live-image-only']),
      livePhotos: new Set(['live-complete']),
    }

    expect(backupUploadAction('photo', false, presence)).toBe('skip')
    expect(backupUploadAction('live-complete', true, presence)).toBe('skip')
    expect(backupUploadAction('live-image-only', true, presence)).toBe('replace')
    expect(backupUploadAction('missing-file', false, presence)).toBe('replace')
    expect(backupUploadAction('new-photo', false, presence)).toBe('upload')
  })
})
