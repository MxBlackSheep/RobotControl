import React from 'react';
import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import useMediaQuery from '@mui/material/useMediaQuery';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { visibleNavigation } from './navigation';

type Item = { label: string; path: string };
// The approved phone order (daily pages first); desktop keeps navigationItems' order.
const phoneOrder = ['/', '/scheduling', '/camera', '/labware', '/database', '/maintenance', '/logfile', '/system-status', '/admin'];

/** Phone navigation (below 900px): every permitted page as pills, four per swipeable group. */
export default function PhoneBar() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const attention = !!robotAttention(useRobotStatusContext().status);
  // Four labels fit from 360px; narrower phones get three per group rather than truncated labels.
  const perGroup = useMediaQuery('(max-width:359.95px)') ? 3 : 4;
  const items: Item[] = [...visibleNavigation(user).map(({ label, path }) => ({ label, path }))
    .sort((a, b) => phoneOrder.indexOf(a.path) - phoneOrder.indexOf(b.path)), { label: 'Account', path: '/account' }];
  const groups: Item[][] = [];
  for (let start = 0; start < items.length; start += perGroup) groups.push(items.slice(start, start + perGroup));
  const activeGroup = groups.findIndex(group => group.some(item => item.path === pathname));

  const [group, setGroup] = React.useState(Math.max(activeGroup, 0));
  React.useEffect(() => { if (activeGroup >= 0) setGroup(activeGroup); }, [pathname, activeGroup]);
  const current = Math.min(group, groups.length - 1);

  const [offset, setOffset] = React.useState(0);
  const [dragging, setDragging] = React.useState(false);
  const drag = React.useRef<{ x: number; id: number; active: boolean } | null>(null);
  // A swipe that ends over a pill must not also open that page.
  const moved = React.useRef(false);
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');

  const pointerDown = (event: React.PointerEvent<HTMLElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    drag.current = { x: event.clientX, id: event.pointerId, active: false };
    moved.current = false;
  };
  const pointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const state = drag.current;
    if (!state || state.id !== event.pointerId) return;
    const dx = event.clientX - state.x;
    if (!state.active) {
      if (Math.abs(dx) <= 8) return;
      state.active = true;
      moved.current = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragging(true);
    }
    const pastEnd = (current === 0 && dx > 0) || (current === groups.length - 1 && dx < 0);
    setOffset(pastEnd ? dx * 0.3 : dx);
  };
  const pointerEnd = (event: React.PointerEvent<HTMLElement>, snap: boolean) => {
    const state = drag.current;
    if (!state || state.id !== event.pointerId) return;
    drag.current = null;
    if (!state.active) return;
    const dx = event.clientX - state.x;
    setDragging(false);
    setOffset(0);
    if (!snap) return;
    if (dx < -40) setGroup(Math.min(groups.length - 1, current + 1));
    else if (dx > 40) setGroup(Math.max(0, current - 1));
  };

  const bar = React.useRef<HTMLElement>(null);
  React.useLayoutEffect(() => {
    const element = bar.current;
    if (!element) return;
    const root = document.documentElement.style;
    // Views that fit themselves to the screen (text readers, rack, camera) subtract the main element's
    // bottom padding, which includes this height, and re-measure on window resize. A CSS variable change
    // resizes nothing they observe, so announce it as a resize.
    const observer = new ResizeObserver(() => {
      const value = `${element.offsetHeight}px`;
      if (root.getPropertyValue('--app-bottom-bar-height') === value) return;
      root.setProperty('--app-bottom-bar-height', value);
      // Focus moves and scroll-into-view must stop above the bar, not behind it.
      root.setProperty('scroll-padding-bottom', value);
      window.dispatchEvent(new Event('resize'));
    });
    observer.observe(element);
    return () => { observer.disconnect(); root.setProperty('--app-bottom-bar-height', '0px'); root.removeProperty('scroll-padding-bottom'); };
  }, []);

  const groupHasAttention = (index: number) => attention && groups[index].some(item => item.path === '/scheduling');

  return <Box component="nav" ref={bar} aria-label="Pages" sx={{
    position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: theme => theme.zIndex.appBar,
    bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider', pb: 'env(safe-area-inset-bottom)',
  }}>
    {groups.length > 1 && <Box sx={{ display: 'flex', justifyContent: 'center' }}>
      {groups.map((groupItems, index) => {
        const start = index * perGroup + 1;
        const end = start + groupItems.length - 1;
        const isCurrent = index === current;
        return <ButtonBase key={index} disableRipple aria-label={start === end ? `Page ${start}` : `Pages ${start} to ${end}`}
          aria-current={isCurrent ? 'true' : undefined} onClick={() => setGroup(index)}
          sx={{ minWidth: 44, height: 24, borderRadius: 1 }}>
          <Box component="span" aria-hidden sx={{
            width: isCurrent ? 18 : 6, height: 6, borderRadius: 3,
            bgcolor: isCurrent ? 'primary.main' : groupHasAttention(index) ? 'attentionSurface.action' : 'surface.control',
            transition: reducedMotion ? 'none' : 'width 200ms',
          }} />
        </ButtonBase>;
      })}
    </Box>}
    <Box onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={event => pointerEnd(event, true)} onPointerCancel={event => pointerEnd(event, false)}
      onClickCapture={event => { if (moved.current) { event.preventDefault(); event.stopPropagation(); moved.current = false; } }}
      onKeyDown={() => { moved.current = false; }}
      sx={{ overflow: 'hidden', touchAction: 'pan-y' }}>
      <Box sx={{
        display: 'flex', transform: `translateX(calc(${-current * 100}% + ${offset}px))`,
        transition: dragging || reducedMotion ? 'none' : 'transform 380ms cubic-bezier(.2,.8,.2,1)',
      }}>
        {groups.map((groupItems, index) => {
          const isCurrent = index === current;
          return <Box key={index} aria-hidden={isCurrent ? undefined : true}
            // React 18 does not know `inert`; set it directly so off-screen pills take no focus.
            ref={(element: HTMLElement | null) => { if (element) { if (isCurrent) element.removeAttribute('inert'); else element.setAttribute('inert', ''); } }}
            sx={{ flex: '0 0 100%', minWidth: 0, display: 'grid', gridTemplateColumns: `repeat(${perGroup}, minmax(0, 1fr))`, alignItems: 'center', gap: 1, px: 1.5, minHeight: 58 }}>
            {Array.from({ length: perGroup }, (_, slot) => {
              const item = groupItems[slot];
              if (!item) return <Box key={`empty-${slot}`} aria-hidden />;
              const selected = pathname === item.path;
              const badge = item.path === '/scheduling' && attention;
              return <ButtonBase key={item.path} component={Link} to={item.path} draggable={false}
                aria-current={selected ? 'page' : undefined} aria-label={badge ? `${item.label}, recovery requires attention` : undefined}
                sx={{
                  position: 'relative', minHeight: 44, minWidth: 0, px: 1, borderRadius: '22px', fontSize: 12, fontWeight: 600, lineHeight: 1.15, textAlign: 'center',
                  bgcolor: selected ? 'primary.main' : 'action.hover', color: selected ? 'primary.contrastText' : 'text.primary',
                }}>
                {/* Two-word labels ("System status") may take two lines; the dot sits on the corner so it never costs label width. */}
                <Box component="span" sx={{ minWidth: 0, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflowWrap: 'normal', wordBreak: 'normal' }}>{item.label}</Box>
                {badge && <Box component="span" aria-hidden sx={{ position: 'absolute', top: 4, right: 6, width: 8, height: 8, borderRadius: 4, bgcolor: 'attentionSurface.action', boxShadow: theme => `0 0 0 2px ${theme.palette.background.paper}` }} />}
              </ButtonBase>;
            })}
          </Box>;
        })}
      </Box>
    </Box>
  </Box>;
}
