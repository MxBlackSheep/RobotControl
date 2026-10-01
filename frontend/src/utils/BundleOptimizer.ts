import React, { ComponentType, LazyExoticComponent } from 'react';

const RETRY_ATTEMPTS = 3;
const RETRY_DELAY_MS = 1000;
const RELOADED_KEY = 'robotcontrol:chunk-reload';

/**
 * One reload fetches the current index.html, whose chunk names match an upgraded server.
 * Only when the server answers: reloading over a dropped connection would replace the app
 * with the browser's (or the tunnel's) error page instead of the page's Reload notice.
 */
async function reloadOnce(): Promise<boolean> {
  try {
    if (sessionStorage.getItem(RELOADED_KEY) || !navigator.onLine) return false;
    const health = await fetch('/health', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
    if (!health.ok) return false;
    sessionStorage.setItem(RELOADED_KEY, String(Date.now()));
  } catch {
    return false;
  }
  window.location.reload();
  return true;
}

/**
 * Lazy-loads a page chunk, retrying so a brief network drop does not leave the route
 * broken. If the chunk is still missing (the server was upgraded and old chunk names
 * now 404), reload the page once; after that the page's error boundary offers Reload.
 */
export function loadComponent<T extends ComponentType<any>>(
  importFn: () => Promise<{ default: T }>
): LazyExoticComponent<T> {
  const componentLoader = async (): Promise<{ default: T }> => {
    for (let attempt = 1; ; attempt++) {
      try {
        const loaded = await importFn();
        try { sessionStorage.removeItem(RELOADED_KEY); } catch { /* storage unavailable */ }
        return loaded;
      } catch (error) {
        if (attempt === RETRY_ATTEMPTS) {
          console.error(`Failed to load component after ${RETRY_ATTEMPTS} attempts:`, error);
          if (await reloadOnce()) return new Promise<never>(() => {});
          throw error;
        }
        console.warn(`Component load attempt ${attempt} failed, retrying in ${RETRY_DELAY_MS * attempt}ms:`, error);
        await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * attempt));
      }
    }
  };

  return React.lazy(componentLoader);
}
