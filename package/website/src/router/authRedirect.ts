/** Accept only internal destinations and avoid returning to the login screen. */
export function safeAuthRedirect(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020]/.test(value)) return '/';
  try {
    const url = new URL(value, 'https://trailsnap.invalid');
    if (url.origin !== 'https://trailsnap.invalid' || /^\/(login|register|forgot-password)(\/|$)/.test(url.pathname)) return '/';
    return url.pathname + url.search + url.hash;
  } catch { return '/'; }
}

export function loginLocation(destination: string, demoFailed = false) {
  return { path: '/login', query: { redirect: safeAuthRedirect(destination), ...(demoFailed ? { demo_failed: '1' } : {}) } };
}
