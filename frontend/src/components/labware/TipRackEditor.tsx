import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, Paper, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';

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
  const [tool, setTool] = useState<'paint' | 'rectangle'>('paint');
  const [corners, setCorners] = useState<{ first: number; last: number } | null>(null);
  const [firstInput, setFirstInput] = useState('1');
  const [lastInput, setLastInput] = useState('1');
  const press = useRef<Press | null>(null);
  const ignoreClick = useRef(false);
  const grid = useRef<HTMLDivElement>(null);
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
    if (tool === 'paint') apply([tip]);
    else if (corners) apply(rectangle(corners.first, tip));
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
  const first = Number(firstInput), last = Number(lastInput);
  const validRange = Number.isInteger(first) && Number.isInteger(last) && first >= 1 && last >= 1 && first <= positions && last <= positions;

  return <Paper variant="outlined" sx={{ p: 1.5, minWidth: 0 }}>
    <Stack gap={1}>
      <Box><Typography id={headingId} variant="h6" component="h2" sx={{ overflowWrap: 'anywhere' }}>{rack}</Typography><Typography variant="caption" color="text.secondary">{side} · {rows} rows × {columns} columns</Typography></Box>
      {canUpdate && <>
        <Stack direction="row" flexWrap="wrap" gap={0.5} aria-label="Paint status">
          <ToggleButton value="inspect" selected={paint === null} disabled={disabled} onClick={() => onPaintChange(null)} sx={{ px: 1 }}>Inspect</ToggleButton>
          {statuses.map(status => <ToggleButton key={status} value={status} selected={paint === status} disabled={disabled} aria-label={`Paint ${status}`} onClick={() => onPaintChange(status)} sx={{ px: 1, gap: 0.5 }}>
            <Box aria-hidden="true" sx={{ bgcolor: colors[status] || 'text.disabled', width: 12, height: 12, borderRadius: '50%', border: 1, borderColor: 'divider' }} />{status}
          </ToggleButton>)}
        </Stack>
        {paint && <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
          <ToggleButtonGroup value={tool} exclusive size="small" aria-label="Paint tool" onChange={(_, value) => { if (value) { cancel(); setTool(value); } }} disabled={!enabled}>
            <ToggleButton value="paint">Paint</ToggleButton><ToggleButton value="rectangle">Rectangle</ToggleButton>
          </ToggleButtonGroup>
          {tool === 'rectangle' && <Typography variant="caption" color="text.secondary">Drag or tap two corners.</Typography>}
        </Stack>}
      </>}
      <Box sx={{ overflowX: 'auto', pb: 0.5 }}>
        <Box ref={grid} role="group" aria-label={`${rack} tips`} onPointerDown={event => {
          ignoreClick.current = false;
          if (!enabled || tool !== 'rectangle' || event.pointerType === 'touch' || event.button !== 0) return;
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
        }} onPointerCancel={() => { ignoreClick.current = true; cancel(); }} onLostPointerCapture={() => { if (press.current) { ignoreClick.current = true; cancel(); } }}
          sx={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, 44px)`, gridTemplateRows: `repeat(${rows}, 44px)`, gap: 0.5, width: 'max-content', userSelect: 'none', touchAction: 'auto' }}>
          {Array.from({ length: positions }, (_, index) => {
            const tip = index + 1, status = statusAt(tip), unsaved = pendingAt(tip);
            return <Button key={tip} data-tip={tip} aria-label={`Tip ${tip}, ${status}`} aria-pressed={position === tip} tabIndex={position === tip ? 0 : -1} onClick={event => activate(tip, event)} onKeyDown={event => keyMove(event, tip)}
              sx={{ gridColumn: Math.floor(index / rows) + 1, gridRow: index % rows + 1, minWidth: 44, minHeight: 44, p: 0.25, display: 'flex', flexDirection: 'column', gap: 0, color: 'text.primary', border: 2, borderColor: position === tip ? 'primary.main' : 'divider', borderStyle: unsaved ? 'dashed' : 'solid', bgcolor: preview.has(tip) ? 'action.selected' : 'background.paper', outline: preview.has(tip) ? '2px solid' : undefined, outlineColor: 'primary.main', outlineOffset: -4 }}>
              <Box component="span" aria-hidden="true" sx={{ width: 14, height: 14, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography component="span" variant="caption" sx={{ lineHeight: 1.1 }}>{tip}{unsaved ? '*' : ''}</Typography>
            </Button>;
          })}
        </Box>
      </Box>
      {corners && <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><Typography role="status" variant="body2">From tip {corners.first} · {preview.size} tips</Typography><Button onClick={cancel}>Cancel rectangle</Button></Stack>}
      <Typography variant="caption" color="text.secondary">Tip {position}: {statusAt(position)}{canUpdate ? ' · * Unsaved.' : ''} Arrow keys move{canUpdate && paint ? '; Enter paints.' : '.'}</Typography>
      {canUpdate && <>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Button disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: columns }, (_, col) => col * rows + (position - 1) % rows + 1))}>Paint row</Button>
          <Button disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: rows }, (_, row) => Math.floor((position - 1) / rows) * rows + row + 1))}>Paint column</Button>
          <Button disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: positions }, (_, index) => index + 1))}>Paint rack</Button>
        </Stack>
        <Box component="details"><Typography component="summary" variant="body2" sx={{ cursor: 'pointer', minHeight: 44, display: 'list-item', alignContent: 'center' }}>By tip number</Typography>
          <Stack direction="row" gap={1} flexWrap="wrap" sx={{ pt: 1 }}>
            <TextField label="First corner" type="number" size="small" value={firstInput} onChange={event => setFirstInput(event.target.value)} inputProps={{ min: 1, max: positions }} sx={{ width: 112 }} />
            <TextField label="Last corner" type="number" size="small" value={lastInput} onChange={event => setLastInput(event.target.value)} inputProps={{ min: 1, max: positions }} sx={{ width: 112 }} />
            <Button disabled={!enabled || !validRange || Boolean(corners)} onClick={() => apply(rectangle(first, last))}>Paint range</Button>
          </Stack>
        </Box>
      </>}
      {!canUpdate && <Stack direction="row" gap={1} flexWrap="wrap" aria-label="Tip status legend">{statuses.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography variant="caption">{status}</Typography></Stack>)}</Stack>}
    </Stack>
  </Paper>;
}
