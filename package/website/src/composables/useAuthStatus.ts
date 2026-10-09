import { onBeforeUnmount, ref } from 'vue';
import { authService } from '@/api/auth';

type AuthStatus = Awaited<ReturnType<typeof authService.getAuthStatus>>;

/** Keep onboarding recoverable when the API starts after the frontend. */
export function useAuthStatus(onReady: (status: AuthStatus) => void | Promise<void>) {
  const state = ref<'checking' | 'ready' | 'unavailable'>('checking');
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let disposed = false;

  const check = async () => {
    if (disposed || controller) return;
    clearTimeout(retryTimer);
    state.value = 'checking';
    controller = new AbortController();
    try {
      const status = await authService.getAuthStatus({ silentError: true, signal: controller.signal });
      if (disposed) return;
      state.value = 'ready';
      await onReady(status);
    } catch {
      if (disposed) return;
      state.value = 'unavailable';
      retryTimer = setTimeout(() => void check(), 3000);
    } finally {
      controller = undefined;
    }
  };

  onBeforeUnmount(() => {
    disposed = true;
    clearTimeout(retryTimer);
    controller?.abort();
  });

  return { state, check };
}
