import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Box, Button, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { fontMono, layout } from '../../theme';

interface Props {
  rack: string;
  headingId: string;
  joined: boolean;
  side: string;
  rows: number;
  columns: number;
  position: number;
  /** Statuses the user may set. */
  choices: string[];
  /** Statuses shown on this rack (choices plus any hidden status a tip still has), in backend order. */
  legend: string[];
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

export default function TipRackEditor({ rack, headingId, joined, side, rows, columns, position, choices, legend, colors, statusAt, pendingAt, canUpdate, disabled, active, paint, onPaintChange, onSelect, onApply, onGestureChange }: Props) {
  const [corners, setCorners] = useState<{ first: number; last: number } | null>(null);
  const press = useRef<Press | null>(null);
  const ignoreClick = useRef(false);
  const grid = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
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
  const cancel = () => { selecting.current = false; press.current = null; setCorners(null); onGestureChange(false); };
  useLayoutEffect(() => {
    const area = viewport.current; if (!area) return;
    let previous = { width: area.clientWidth, height: area.clientHeight };
    const cancelOnResize = () => { if (selecting.current) { ignoreClick.current = true; cancel(); } };
    const changed = () => {
      const next = { width: area.clientWidth, height: area.clientHeight };
      if (!next.width || !next.height) return;
      if (next.width !== previous.width || next.height !== previous.height) cancelOnResize();
      previous = next;
    };
    // CSS fits the two pitches. This observer never writes dimensions, so it
    // cannot feed its own measurement back into layout or pulse during polls.
    const observer = new ResizeObserver(changed); observer.observe(area);
    window.addEventListener('resize', cancelOnResize);
    return () => { observer.disconnect(); window.removeEventListener('resize', cancelOnResize); };
  }, [rack, active, joined]);
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
    else { selecting.current = true; setCorners({ first: tip, last: tip }); onGestureChange(true); }
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
  const tips = Array.from({ length: positions }, (_, index) => index + 1);
  const hasDrafts = tips.some(pendingAt);
  const afterSaving = hasDrafts ? legend.map(status => [status, tips.filter(tip => statusAt(tip) === status).length] as const)
    .filter(([, count]) => count).map(([status, count]) => `${count} ${status}`).join(' · ') : '';
  const dotSize = `max(14px, min(calc((100cqw - ${(columns - 1) * 4}px) / ${columns} * 0.32), calc((100cqh - ${(rows - 1) * 4}px) / ${rows} * 0.32)))`;
  const fontSize = `clamp(12px, min(calc(100cqw / ${columns} * 0.21), calc(100cqh / ${rows} * 0.21)), 22px)`;

  // Four rows shared with the deck through subgrid: 40px header band, status row, tips, fixed footer.
  // "Set entire rack" is placed in the header band by CSS but follows the status buttons in the DOM,
  // so keyboard order stays: heading, choose a status, then apply it.
  return <Box data-rack-editor sx={{ minWidth: 0, display: 'grid', gridColumn: joined ? 2 : undefined, gridRow: joined ? '1 / 5' : undefined,
    gridTemplateRows: joined ? 'subgrid' : `minmax(${layout.header}px, auto) auto minmax(min-content, 1fr) minmax(${layout.header}px, auto)`,
    bgcolor: 'background.paper', border: joined ? 1 : 0, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'hidden' }}>
    <Box sx={{ gridRow: 1, gridColumn: 1, display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, px: 2, pr: canUpdate ? 17 : 2, bgcolor: 'surface.head', borderBottom: 1, borderColor: 'surface.headLine' }}>
      <Typography id={headingId} component="h2" sx={{ fontFamily: fontMono, fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={rack}>{rack}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>{side}</Typography>
    </Box>
    <Box sx={{ gridRow: 2, gridColumn: 1, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, minWidth: 0, px: 2, py: 1, borderBottom: 1, borderColor: 'surface.rowLine' }}>
      {canUpdate
        ? /* Pick a status, then click or drag tips; pressing the chosen status again clears it. */
          <ToggleButtonGroup size="small" exclusive value={paint} disabled={disabled} aria-label="Set tips to" onChange={(_, value: string | null) => onPaintChange(value)}
            sx={{ flexWrap: 'wrap', gap: 1, '& .MuiToggleButtonGroup-grouped': { m: 0, border: 1, borderColor: 'surface.control', borderRadius: `${layout.radius}px` },
              '& .MuiToggleButtonGroup-grouped.Mui-selected': { borderColor: 'primary.main', bgcolor: theme => theme.palette.tone.running.bg, fontWeight: 600 } }}>
            {choices.map(status => <ToggleButton key={status} value={status} sx={{ gap: 1, px: 1.5 }}>
              <Box component="span" aria-hidden="true" sx={{ bgcolor: colors[status] || 'text.disabled', width: 10, height: 10, borderRadius: '50%' }} />{stateName(status)}
            </ToggleButton>)}
          </ToggleButtonGroup>
        : <Stack direction="row" gap={1.5} flexWrap="wrap" aria-label="Tip status legend">{legend.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled' }} /><Typography variant="caption">{stateName(status)}</Typography></Stack>)}</Stack>}
    </Box>
    {canUpdate && <Button size="small" disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: positions }, (_, index) => index + 1))}
      sx={{ gridRow: 1, gridColumn: 1, justifySelf: 'end', alignSelf: 'center', mr: 1, whiteSpace: 'nowrap' }}>Set entire rack</Button>}
      <Box ref={viewport} data-tip-editor-body sx={{ gridRow: 3, gridColumn: 1, minWidth: 0, minHeight: rows * 44 + (rows - 1) * 4 + 24, height: '100%', px: 2, py: 1.5, boxSizing: 'border-box', overflowX: 'auto', overflowY: 'hidden' }}>
        <Box ref={grid} role="group" aria-label={`${rack} tips`} onPointerDown={event => {
          ignoreClick.current = false;
          if (!enabled || event.pointerType === 'touch' || event.button !== 0) return;
          const tip = hit(event.clientX, event.clientY); if (!tip) return;
          ignoreClick.current = false;
          press.current = { pointer: event.pointerId, first: tip, last: tip, x: event.clientX, y: event.clientY, dragging: false };
          selecting.current = true;
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
          sx={{ containerType: 'size', display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(44px, 1fr))`, gridTemplateRows: `repeat(${rows}, minmax(44px, 1fr))`, gap: 0.5, width: '100%', height: '100%', minWidth: columns * 44 + (columns - 1) * 4, minHeight: rows * 44 + (rows - 1) * 4, userSelect: 'none', touchAction: 'manipulation' }}>
          {Array.from({ length: positions }, (_, index) => {
            const tip = index + 1, status = statusAt(tip), unsaved = pendingAt(tip);
            return <Button key={tip} disableRipple data-tip={tip} aria-label={`Tip ${tip}, ${status}`} aria-pressed={position === tip} tabIndex={position === tip ? 0 : -1} onClick={event => activate(tip, event)} onKeyDown={event => keyMove(event, tip)}
              sx={{ gridColumn: Math.floor(index / rows) + 1, gridRow: index % rows + 1, minWidth: 44, minHeight: 44, p: 0.25, display: 'flex', flexDirection: 'column', gap: 0, color: 'text.primary', border: 2, borderColor: position === tip || preview.has(tip) ? 'primary.main' : unsaved ? 'warning.main' : 'transparent', borderStyle: unsaved ? 'dashed' : 'solid', bgcolor: preview.has(tip) ? 'action.selected' : 'transparent', transition: 'none', '&.Mui-focusVisible, &:focus-visible': { outline: '3px solid', outlineColor: 'primary.main', outlineOffset: -3 } }}>
              <Box component="span" data-tip-dot aria-hidden="true" sx={{ width: dotSize, height: dotSize, flexShrink: 0, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography component="span" sx={{ fontSize, lineHeight: 1.2 }}>{tip}{unsaved ? '*' : ''}</Typography>
            </Button>;
          })}
        </Box>
      </Box>
      {/* One fixed line: the draft summary never adds a row, so neither diagram moves when edits start. */}
      <Box sx={{ gridRow: 4, gridColumn: 1, display: 'flex', alignItems: 'center', gap: 2, minWidth: 0, px: 2, borderTop: 1, borderColor: 'surface.headLine', whiteSpace: 'nowrap' }}>
        <Typography role="status" variant="body2" sx={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{corners ? `${preview.size} tips selected` : canUpdate ? paint ? 'Choose two corners or drag.' : 'Choose a status to edit tips.' : `Tip ${position}: ${stateName(statusAt(position))}`}</Typography>
        <Button size="small" onClick={cancel} disabled={!corners} aria-hidden={!corners} tabIndex={corners ? 0 : -1} sx={{ visibility: corners ? 'visible' : 'hidden', flexShrink: 0 }}>Cancel selection</Button>
        {canUpdate && hasDrafts && <Typography aria-label="This rack after saving" title={`After saving: ${afterSaving}`}
          sx={{ ml: 'auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>After saving: {afterSaving}</Typography>}
      </Box>
  </Box>;
}
