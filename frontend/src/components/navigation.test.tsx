import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';

import { useKeyboardNavigation } from '../hooks/useKeyboardNavigation';
import { allowedSections, allowedSchedulingSections, useSchedulingSection, useSidebarLayout, visibleNavigation } from './navigation';
import useMediaQuery from '@mui/material/useMediaQuery';
vi.mock('@mui/material/useMediaQuery', () => ({default: vi.fn(() => false)}));
const admin = {role: 'admin', session_is_local: true};
function RouteState({user = admin}: {user?: typeof admin}) {
  const location = useLocation(); const navigate = useNavigate(); const [section] = useSchedulingSection(user);
  return <><output aria-label="Location">{location.pathname}{location.search}</output><output aria-label="Section">{section}</output><button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>;
}
beforeEach(() => { localStorage.clear(); vi.mocked(useMediaQuery).mockReturnValue(false); });
it('shares permission filtering for desktop, mobile and direct section links', () => {
  expect(allowedSchedulingSections({role: 'user', session_is_local: false}).map(section => section.id)).toEqual(['schedules','calendar','history','archived','recovery']);
  expect(visibleNavigation({role: 'user'}).some(item => item.path === '/admin')).toBe(false);
  expect(allowedSchedulingSections({role: 'viewer', session_is_local: true})).toEqual([]);
});
it.each(['unknown','methods','notifications'])('redirects an inaccessible or unknown section %s', async section => {
  render(<MemoryRouter initialEntries={['/scheduling?section='+section]}><RouteState user={{role: 'user', session_is_local: false}} /></MemoryRouter>);
  await waitFor(() => expect(screen.getByLabelText('Location').textContent).toBe('/scheduling'));
});
it('defaults by width and remembers an explicit sidebar preference', () => {
  function Preference() { const layout = useSidebarLayout(); return <button onClick={layout.toggle}>{layout.expanded ? 'Expanded' : 'Collapsed'}</button>; }
  const first = render(<Preference />); fireEvent.click(screen.getByRole('button', {name: 'Collapsed'}));
  expect(localStorage.getItem('robotcontrol.sidebar.expanded')).toBe('true'); first.unmount();
  render(<Preference />); expect(screen.getByRole('button', {name: 'Expanded'})).toBeTruthy();
});

it('preserves navigation shortcuts and leaves open dialogs in control', () => {
  function Shortcuts() { useKeyboardNavigation({enabled: true}); return <RouteState />; }
  render(<MemoryRouter><Shortcuts /></MemoryRouter>);
  fireEvent.keyDown(document, {key: '7', altKey: true});
  expect(screen.getByLabelText('Location').textContent).toBe('/scheduling');
  const modal = document.createElement('div'); modal.className = 'MuiModal-root'; document.body.appendChild(modal);
  fireEvent.keyDown(document, {key: '1', altKey: true});
  expect(screen.getByLabelText('Location').textContent).toBe('/scheduling'); modal.remove();
  fireEvent.keyDown(document, {key: '1', altKey: true}); expect(screen.getByLabelText('Location').textContent).toBe('/');
});

it('keeps Database restore admin-or-local and operations local-only', () => {
  expect(allowedSections('/database', {role:'admin', session_is_local:false}).map(s=>s.id)).toEqual(['tables','procedures','restore','retrieval']);
  expect(allowedSections('/database', {role:'viewer', session_is_local:false}).map(s=>s.id)).toEqual(['tables','procedures','retrieval']);
  expect(allowedSections('/database', {role:'admin', session_is_local:true}).map(s=>s.id)).toEqual(['tables','procedures','restore','operations','retrieval','packages','settings']);
  expect(allowedSections('/logfile', {role:'user', session_is_local:false}).map(s=>s.id)).toEqual(['python','hamilton']);
});
