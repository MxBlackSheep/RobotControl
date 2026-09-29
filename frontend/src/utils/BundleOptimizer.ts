import React, { ComponentType, LazyExoticComponent } from 'react';

const RETRY_ATTEMPTS = 3;
const RETRY_DELAY_MS = 1000;

/**
 * Lazy-loads a page chunk, retrying so a brief network drop after a deployment
 * does not leave the route permanently broken.
 */
export function loadComponent<T extends ComponentType<any>>(
  importFn: () => Promise<{ default: T }>
): LazyExoticComponent<T> {
  const componentLoader = async (): Promise<{ default: T }> => {
    for (let attempt = 1; ; attempt++) {
      try {
        return await importFn();
      } catch (error) {
        if (attempt === RETRY_ATTEMPTS) {
          console.error(`Failed to load component after ${RETRY_ATTEMPTS} attempts:`, error);
          throw error;
        }
        console.warn(`Component load attempt ${attempt} failed, retrying in ${RETRY_DELAY_MS * attempt}ms:`, error);
        await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * attempt));
      }
    }
  };

  return React.lazy(componentLoader);
}
