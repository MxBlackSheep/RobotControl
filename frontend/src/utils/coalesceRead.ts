/** Share simultaneous reads only; completed results are never cached. */
const pending = new Map<string, Promise<unknown>>();

export function coalesceRead<T>(key: string, read: () => Promise<T>): Promise<T> {
  const existing = pending.get(key);
  if (existing) return existing as Promise<T>;
  const request = Promise.resolve().then(read).finally(() => {
    if (pending.get(key) === request) pending.delete(key);
  });
  pending.set(key, request);
  return request;
}
