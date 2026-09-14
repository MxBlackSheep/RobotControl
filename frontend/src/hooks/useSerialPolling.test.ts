import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useSerialPolling } from './useSerialPolling';
import { coalesceRead } from '../utils/coalesceRead';

afterEach(() => vi.useRealTimers());

it('serializes manual refresh, ignores callback churn and keeps hidden-page cadence', async () => {
  vi.useFakeTimers();
  let resolve!: (value: number) => void;
  const request = vi.fn(() => new Promise<number>(done => { resolve = done; }));
  const success = vi.fn();
  const { result, rerender, unmount } = renderHook(() => useSerialPolling({ request, onSuccess: success, interval: 30000 }));
  await act(async () => {});
  rerender();
  act(() => { void result.current.refresh(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(1); });
  expect(success).toHaveBeenCalledWith(1);
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(request).toHaveBeenCalledTimes(2);
  unmount();
  resolve(2);
  await act(async () => {});
  expect(success).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
});

it('retries once per interval and rejects results from an old identity', async () => {
  vi.useFakeTimers();
  const failure = vi.fn().mockRejectedValue(new Error('offline'));
  const success = vi.fn();
  const { result, unmount } = renderHook(() => useSerialPolling({ request: failure, onSuccess: success, interval: 60000, retryInterval: 30000 }));
  await act(async () => {});
  expect(result.current.retries).toBe(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(29999); });
  expect(failure).toHaveBeenCalledTimes(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(failure).toHaveBeenCalledTimes(2);
  unmount();
  const resolvers: ((v: string) => void)[] = [];
  const request = () => new Promise<string>(resolve => resolvers.push(resolve));
  const hook = renderHook(({ identity }) => useSerialPolling({ request, onSuccess: success, interval: 60000, identity }), { initialProps: { identity: 'old' } });
  await act(async () => {});
  hook.rerender({ identity: 'new' });
  await act(async () => {});
  await act(async () => { resolvers[0]('old'); resolvers[1]('new'); });
  expect(success).toHaveBeenCalledTimes(1);
  expect(success).toHaveBeenCalledWith('new');
  hook.unmount();
});

it('coalesces simultaneous reads but retries failures without caching', async () => {
  const read = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue('new');
  const first = coalesceRead('same-user', read);
  expect(coalesceRead('same-user', read)).toBe(first);
  await expect(first).rejects.toThrow('offline');
  await expect(coalesceRead('same-user', read)).resolves.toBe('new');
  expect(read).toHaveBeenCalledTimes(2);
});
