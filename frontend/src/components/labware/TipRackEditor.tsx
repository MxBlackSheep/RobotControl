import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Box, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';

interface Props {
  rack: string;
  headingId: string;
  side: string;
  rows: number;
  columns: number;
  position: number;
  statuses: string[];
  colors: Record<string, string>;
  statusAt: (position: number) => string;
  pendingAt: (position: number) => boolean;
  canUpdate: boolean;
  disabled: boolean;
  active: boolean;
  paint: string | null;
  onPaintChange: (value: string | null) => void;
  onSelect: (position: number) => void;
  onApply: (positions: number[], status: string) => void;
  onGestureChange: (active: boolean) => void;
}

type Press = { pointer: number; first: number; last: number | null; x: number; y: number; dragging: boolean };

export default function TipRackEditor({ rack, headingId, side, rows, columns, position, statuses, colors, statusAt, pendingAt, canUpdate, disabled, active, paint, onPaintChange, onSelect, onApply, onGestureChange }: Props) {
  const [corners, setCorners] = useState<{ first: number; last: number } | null>(null);
  const [cellSize, setCellSize] = useState(44);
  const press = useRef<Press | null>(null);
  const ignoreClick = useRef(false);
  const grid = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const footer = useRef<HTMLDivElement>(null);
  const selecting = useRef(false);
  selecting.current = Boolean(corners || press.current);
  const positions = rows * columns;
  const enabled = active && canUpdate && !disabled && Boolean(paint);
  const rectangle = (first: number, last: number) => {
    const firstRow = (first - 1) % rows, lastRow = (last - 1) % rows;
    const firstColumn = Math.floor((first - 1) / rows), lastColumn = Math.floor((last - 1) / rows);
    const result: number[] = [];
    for (let col = Math.min(firstColumn, lastColumn); col <= Math.max(firstColumn, lastColumn); col++) {
      for (let row = Math.min(firstRow, lastRow); row <= Math.max(firstRow, lastRow); row++) result.push(col * rows + row + 1);
    }
    return result;
  };
  const preview = new Set(corners ? rectangle(corners.first, corners.last) : []);
  const cancel = () => { press.current = null; setCorners(null); onGestureChange(false); };
  useLayoutEffect(() => {
    const element = host.current, area = viewport.current, strip = footer.current;
    if (!element || !area || !strip) return;
    const measure = () => {
      if (!element.clientWidth || selecting.current) return;
      const paper = area.closest<HTMLElement>('[data-rack-editor]')!;
      const style = getComputedStyle(paper);
      const inlinePadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) + 2;
      const dialogScroll = area.closest<HTMLElement>('.MuiDialogContent-root');
      const scrollTop = dialogScroll?.scrollTop ?? window.scrollY;
      const top = area.getBoundingClientRect().top + scrollTop;
      const bottomPadding = parseFloat(style.paddingBottom) + (parseFloat(getComputedStyle(dialogScroll || element.closest('main') || element).paddingBottom) || 0);
      const widthFit = (element.clientWidth - inlinePadding - (columns - 1) * 4) / columns;
      const heightFit = ((window.visualViewport?.height ?? window.innerHeight) - top - strip.offsetHeight - bottomPadding - 12 - (rows - 1) * 4) / rows;
      setCellSize(Math.max(44, Math.min(132, Math.floor(widthFit), Math.floor(heightFit))));
    };
    const resize = () => { if (selecting.current) { ignoreClick.current = true; selecting.current = false; cancel(); } measure(); };
    measure();
    const observer = new ResizeObserver(measure);observer.observe(element);observer.observe(strip);
    window.addEventListener('resize', resize);window.visualViewport?.addEventListener('resize', resize);
    return () => { observer.disconnect();window.removeEventListener('resize', resize);window.visualViewport?.removeEventListener('resize', resize); };
  }, [rack, active, rows, columns, canUpdate, Boolean(corners)]);
  useEffect(() => {
    if (press.current || corners) ignoreClick.current = true;
    cancel();
    return () => onGestureChange(false);
  }, [rack, active, paint]); // A changed context must never complete an earlier gesture.
  useEffect(() => {
    if (disabled || !canUpdate) { if (press.current || corners) ignoreClick.current = true; cancel(); }
  }, [disabled, canUpdate]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && (press.current || corners)) {
        event.preventDefault(); event.stopPropagation(); ignoreClick.current = Boolean(press.current); cancel();
      }
    };
    window.addEventListener('keydown', escape, true);
    return () => window.removeEventListener('keydown', escape, true);
  }, [corners]);

  const apply = (tips: number[]) => { if (enabled && paint) onApply(tips, paint); cancel(); };
  const activate = (tip: number, event: React.MouseEvent) => {
    if (ignoreClick.current && event.detail !== 0) { ignoreClick.current = false; return; }
    ignoreClick.current = false;
    onSelect(tip);
    if (!enabled) return;
    if (corners) apply(rectangle(corners.first, tip));
    else { setCorners({ first: tip, last: tip }); onGestureChange(true); }
  };
  const hit = (x: number, y: number) => {
    const button = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-tip]');
    return button && grid.current?.contains(button) ? Number(button.dataset.tip) : null;
  };
  const keyMove = (event: React.KeyboardEvent, tip: number) => {
    if ((event.key === 'ArrowDown' && tip % rows === 0) || (event.key === 'ArrowUp' && (tip - 1) % rows === 0)) { event.preventDefault(); return; }
    const next = event.key === 'ArrowDown' ? tip + 1 : event.key === 'ArrowUp' ? tip - 1 : event.key === 'ArrowRight' ? tip + rows : event.key === 'ArrowLeft' ? tip - rows : event.key === 'Home' ? 1 : event.key === 'End' ? positions : null;
    if (next === null) return;
    event.preventDefault();
    if (next < 1 || next > positions) return;
    onSelect(next); grid.current?.querySelector<HTMLButtonElement>(`[data-tip="${next}"]`)?.focus();
  };
  const stateName = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
  const dotSize = Math.max(14, Math.round(cellSize * 0.32));
  const fontSize = Math.max(12, Math.min(22, Math.round(cellSize * 0.21)));

  return <Box ref={host} sx={{ minWidth: 0 }}><Paper data-rack-editor variant="outlined" sx={{ p: 1.5, minWidth: 0, width: 'fit-content', maxWidth: '100%', mx: 'auto' }}>
    <Stack gap={1}>
      <Stack direction="row" gap={1} alignItems="baseline" flexWrap="wrap"><Typography id={headingId} variant="h6" component="h2" sx={{ overflowWrap: 'anywhere' }}>{rack}</Typography><Typography variant="caption" color="text.secondary">{side}</Typography></Stack>
      {canUpdate && <Stack direction="row" flexWrap="wrap" alignItems="center" gap={1}>
        <TextField select size="small" label="Set tips to" value={paint || ''} disabled={disabled} onChange={event => onPaintChange(event.target.value || null)} InputLabelProps={{ shrink: true }} SelectProps={{ displayEmpty: true, SelectDisplayProps: { 'aria-label': 'Set tips to', 'aria-labelledby': undefined } }} sx={{ flex: '1 1 136px', maxWidth: 240 }}>
          <MenuItem value="">Choose status</MenuItem>
          {statuses.map(status => <MenuItem key={status} value={status}><Box component="span" aria-hidden="true" sx={{ display: 'inline-block', verticalAlign: 'middle', mr: 1, bgcolor: colors[status] || 'text.disabled', width: 12, height: 12, borderRadius: '50%', border: 1, borderColor: 'divider' }} />{stateName(status)}</MenuItem>)}
        </TextField>
        <Button disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: positions }, (_, index) => index + 1))} sx={{ whiteSpace: 'nowrap' }}>Set entire rack</Button>
      </Stack>}
      <Box ref={viewport} sx={{ overflowX: 'auto', maxWidth: '100%', pb: 0.5 }}>
        <Box ref={grid} role="group" aria-label={`${rack} tips`} onPointerDown={event => {
          ignoreClick.current = false;
          if (!enabled || event.pointerType === 'touch' || event.button !== 0) return;
          const tip = hit(event.clientX, event.clientY); if (!tip) return;
          ignoreClick.current = false;
          press.current = { pointer: event.pointerId, first: tip, last: tip, x: event.clientX, y: event.clientY, dragging: false };
          const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button');
          try { button?.setPointerCapture(event.pointerId); } catch { /* The pointer may already have been canceled. */ }
          onGestureChange(true);
        }} onPointerMove={event => {
          const current = press.current; if (!current || current.pointer !== event.pointerId) return;
          if (Math.hypot(event.clientX - current.x, event.clientY - current.y) > 4) current.dragging = true;
          if (!current.dragging) return;
          current.last = hit(event.clientX, event.clientY);
          setCorners(current.last ? { first: current.first, last: current.last } : null);
        }} onPointerUp={event => {
          const current = press.current; if (!current || current.pointer !== event.pointerId) return;
          press.current = null;
          if (current.dragging) {
            ignoreClick.current = true;
            const lastTip = hit(event.clientX, event.clientY);
            if (lastTip) apply(rectangle(current.first, lastTip)); else cancel();
          } else if (!hit(event.clientX, event.clientY)) { ignoreClick.current = true; cancel(); }
        }} onPointerCancel={event => {
          ignoreClick.current = true;
          // Native touch panning ends this pointer, not the previously chosen corner.
          if (event.pointerType !== 'touch' || press.current) cancel();
        }} onLostPointerCapture={() => { if (press.current) { ignoreClick.current = true; cancel(); } }}
          sx={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, ${cellSize}px)`, gridTemplateRows: `repeat(${rows}, ${cellSize}px)`, gap: 0.5, width: 'max-content', userSelect: 'none', touchAction: 'manipulation' }}>
          {Array.from({ length: positions }, (_, index) => {
            const tip = index + 1, status = statusAt(tip), unsaved = pendingAt(tip);
            return <Button key={tip} data-tip={tip} aria-label={`Tip ${tip}, ${status}`} aria-pressed={position === tip} tabIndex={position === tip ? 0 : -1} onClick={event => activate(tip, event)} onKeyDown={event => keyMove(event, tip)}
              sx={{ gridColumn: Math.floor(index / rows) + 1, gridRow: index % rows + 1, minWidth: 44, minHeight: 44, p: 0.25, display: 'flex', flexDirection: 'column', gap: 0, color: 'text.primary', border: 2, borderColor: position === tip ? 'primary.main' : 'divider', borderStyle: unsaved ? 'dashed' : 'solid', bgcolor: preview.has(tip) ? 'action.selected' : 'background.paper', outline: preview.has(tip) ? '2px solid' : undefined, outlineColor: 'primary.main', outlineOffset: -4 }}>
              <Box component="span" aria-hidden="true" sx={{ width: dotSize, height: dotSize, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography component="span" sx={{ fontSize, lineHeight: 1.2 }}>{tip}{unsaved ? '*' : ''}</Typography>
            </Button>;
          })}
        </Box>
      </Box>
      <Stack ref={footer} gap={0.5}>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" sx={{ minHeight: 44 }}>
          <Typography role="status" variant="body2" sx={{ flex: 1, minWidth: 120 }}>{corners ? `${preview.size} tips · Choose the other corner` : canUpdate ? paint ? 'Drag a block or select two corners.' : 'Choose a status to edit tips.' : `Tip ${position}: ${stateName(statusAt(position))}`}</Typography>
          {corners && <Button onClick={cancel}>Cancel selection</Button>}
        </Stack>
        {!canUpdate && <Stack direction="row" gap={1} flexWrap="wrap" aria-label="Tip status legend">{statuses.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography variant="caption">{stateName(status)}</Typography></Stack>)}</Stack>}
      </Stack>
    </Stack>
  </Paper></Box>;
}
