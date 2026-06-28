import { test } from '@playwright/test'

test.describe('scan prep', () => {
  test('fixture scan completed in global setup', async () => {
    // 独立扫描入口的实际工作在 globalSetup 中完成；
    // 这里保留一个最小 spec，便于通过 playwright 统一调度。
  })
})
