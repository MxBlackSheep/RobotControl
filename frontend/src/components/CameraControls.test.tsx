import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import CameraControls from './CameraControls';
import { createFrameStore, FrameFreshness } from './LiveFrame';

// CameraControls uses the shared client (token renewal) and the signed-in user.
const api = vi.hoisted(() => ({ get: vi.fn(), request: vi.fn() }));
vi.mock('@/services/api', () => ({ api }));
vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: { user_id: 'fixture' } }) }));

const status = {
  cameras: [{ id: 0, name: 'Robot camera', device_identity: 'a' }, { id: 1, name: 'Bench camera', device_identity: 'b' }],
  health: { device_identity: 'a', generation: 'one', capture_state: 'connected', recording_state: 'recording',
    recording_requested: true, last_frame_age_seconds: 0, operation: null, error: null },
};
const statusResponse = () => Promise.resolve({ data: { data: status } });
afterEach(() => { api.get.mockReset(); api.request.mockReset(); vi.useRealTimers(); vi.restoreAllMocks(); });

it('keeps device controls admin-only and separates capture from recording', async () => {
  api.get.mockImplementation(statusResponse);
  render(<CameraControls admin={false} onSourceChange={() => {}} />);
  await screen.findByText('Camera: Connected · Recording: Recording');
  expect(screen.queryByRole('button', { name: 'Reconnect camera' })).toBeNull();
  expect(screen.getByText(/administrator can select/)).toBeTruthy();
});

it('preserves selection after an operation error and explains recording locks', async () => {
  api.get.mockImplementation(statusResponse);
  api.request.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: 'A camera operation is already in progress' } } });
  render(<CameraControls admin onSourceChange={() => {}} />);
  await screen.findByText('Camera: Connected · Recording: Recording');
  expect(screen.getByText('Stop recording before changing cameras.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Reconnect camera' }));
  await screen.findByText('A camera operation is already in progress');
  expect(screen.getByRole('combobox').textContent).toContain('Robot camera');
});

it('refreshes twice without moving keyboard focus', async () => {
  vi.useFakeTimers();
  const fetcher = api.get.mockImplementation(statusResponse);
  render(<CameraControls admin onSourceChange={() => {}} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  const reconnect = screen.getByRole('button', { name: 'Reconnect camera' });
  reconnect.focus();
  await act(async () => { await vi.advanceTimersByTimeAsync(10001); });
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(document.activeElement).toBe(reconnect);
});

it('cancels an in-flight control request when leaving the page', async () => {
  let signal: AbortSignal | undefined;
  api.get.mockImplementation(statusResponse);
  api.request.mockImplementation(config => { signal = config.signal; return new Promise(() => {}); });
  const view = render(<CameraControls admin onSourceChange={() => {}} />);
  await screen.findByText('Camera: Connected · Recording: Recording');
  fireEvent.click(screen.getByRole('button', { name: 'Reconnect camera' }));
  expect(signal?.aborted).toBe(false);
  view.unmount();
  expect(signal?.aborted).toBe(true);
});

it('marks missing frames stale but identical incoming images remain fresh', async () => {
  vi.useFakeTimers();
  let now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const store = createFrameStore();
  store.set('same image');
  const view = render(<FrameFreshness store={store} />);
  now = 10000;
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByRole('status').textContent).toContain('Stale image');
  store.set('same image');
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByRole('status').textContent).toBe('Live view receiving frames');
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
