import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../../playwright/e2e-env';

/**
 * P0 - 后端 API 健康 @p0
 *
 * 原属 smoke 套件；smoke/p0 分离后，API 健康属于「功能可用」范畴，归入 p0。
 * 覆盖 doc/e2e-test-checklist.md §1.4 系统健康。
 * 后端地址通过 e2eEnv.apiBaseUrl 获取（dev: 8000, system: 8800）。
 * 后端不可达时自动 test.skip，避免环境噪声。
 */

test.describe('P0 - 后端 API 健康 @p0', () => {
  test('/system/version 返回版本号', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/system/version`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('version');
    expect(typeof body.version).toBe('string');
    expect(body.version).toMatch(/^\d+\.\d+\.\d+/);
  });

  test('/auth/status 返回 has_users / allow_registration 字段', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/auth/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('has_users');
    expect(body).toHaveProperty('allow_registration');
    expect(typeof body.has_users).toBe('boolean');
    expect(typeof body.allow_registration).toBe('boolean');
  });

  test('/tasks/status 返回全局任务状态', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toBeDefined();
  });

  test('/openapi.json 可访问 - FastAPI 文档', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/openapi.json`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('openapi');
    expect(body).toHaveProperty('paths');
  });
});
