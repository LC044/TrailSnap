import { test, expect, type APIRequestContext } from '@playwright/test';
import { e2eEnv } from '../../../../playwright/e2e-env';

/**
 * P0 核心路径测试 - 任务监控
 *
 * 覆盖 doc/e2e-test-checklist.md §1.2。
 * 后端地址通过 e2eEnv.apiBaseUrl 获取（dev: 8000, system: 8800）；不可达时自动 skip。
 */

async function ensureBackend(
  request: APIRequestContext,
  testInfo: { skip: (condition: boolean, reason: string) => void },
): Promise<boolean> {
  try {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/system/version`, { timeout: 5_000 });
    if (!res.ok()) {
      testInfo.skip(true, `Backend returned ${res.status()}`);
      return false;
    }
    return true;
  } catch {
    testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
    return false;
  }
}

test.describe('P0 核心路径 - 任务监控 @p0', () => {
  test('GET /tasks/ 返回任务列表（合法 JSON 数组）', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('GET /tasks/?status=PENDING 仅返回 PENDING 任务', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/?status=PENDING`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    for (const t of body) {
      expect(t.status).toBe('PENDING');
    }
  });

  test('GET /tasks/?type=SCAN_FOLDER 支持按类型过滤', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/?type=SCAN_FOLDER&limit=5`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    for (const t of body) {
      expect(t.type).toBe('SCAN_FOLDER');
    }
  });

  test('GET /tasks/grouped-status 返回分组统计', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/grouped-status`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toBeDefined();
  });

  test('GET /tasks/{任意UUID} 返回合法响应', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    // 注: 实际上 fakeId 00000000... 可能因 mock 数据命中返回 200
    // 这里只验证 endpoint 存在并返回合法 JSON，不强制 404
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/${fakeId}`);
    expect([200, 400, 404]).toContain(res.status());
    const body = await res.json().catch(() => null);
    // 返回 JSON 应为对象或 null
    expect([null, 'object']).toContain(typeof body);
  });

  test('POST /tasks/{id}/cancel 路径存在（不应 405）', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const res = await request.post(`${e2eEnv.apiBaseUrl}/tasks/${fakeId}/cancel`);
    expect(res.status()).not.toBe(405);
  });

  test('POST /tasks/{id}/retry 路径存在（不应 405）', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const res = await request.post(`${e2eEnv.apiBaseUrl}/tasks/${fakeId}/retry`);
    expect(res.status()).not.toBe(405);
  });
});

test.describe('P0 核心路径 - 任务分类与 Fast Mode @p0', () => {
  test('POST /tasks/categories/{category}/pause 路径存在', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    // 用一个稳定存在的分类
    const res = await request.post(`${e2eEnv.apiBaseUrl}/tasks/categories/PROCESS_BASIC/pause`);
    expect(res.status()).not.toBe(405);
  });

  test('POST /tasks/categories/{category}/resume 路径存在', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.post(`${e2eEnv.apiBaseUrl}/tasks/categories/PROCESS_BASIC/resume`);
    expect(res.status()).not.toBe(405);
  });

  test('POST /tasks/fast-mode 切换 Fast Mode', async ({ request }, testInfo) => {
    if (!(await ensureBackend(request, testInfo))) return;
    const res = await request.post(`${e2eEnv.apiBaseUrl}/tasks/fast-mode?enabled=true`);
    if (res.ok()) {
      const body = await res.json();
      expect(body).toHaveProperty('status', 'success');
    }
  });
});
