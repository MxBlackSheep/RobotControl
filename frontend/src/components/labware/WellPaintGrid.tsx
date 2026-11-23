import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Box, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { layout } from '../../theme';

type Press = { pointer: number; first: number; last: number | null; x: number; y: number; dragging: boolean };
type PaintChoice = {value:string; label:string; symbol?:string; color?:string};
type Painting = {
  control: React.ReactNode; grid: React.RefObject<HTMLDivElement>; viewport: React.RefObject<HTMLDivElement>;
  handlers: React.HTMLAttributes<HTMLDivElement>; preview: Set<number>; corners: {first:number; last:number} | null;
  enabled:boolean; cancel:()=>void; apply:(positions:number[])=>void;
  activate:(position:number,event:React.MouseEvent)=>void; keyMove:(event:React.KeyboardEvent,position:number)=>void;
};
interface Props {
  rack:string; active:boolean; joined?:boolean; rows:number; columns:number; canUpdate?:boolean; disabled:boolean;
  paint:string|null; onPaintChange:(value:string|null)=>void; onSelect:(position:number)=>void;
  onApply:(positions:number[],paint:string)=>void; onGestureChange?:(active:boolean)=>void;
  activation?:'corners'|'single'; label:string; choices:PaintChoice[]; children:(painting:Painting)=>React.ReactNode;
}
const noGesture = () => {};
/** Owns paint choice and rectangular gestures; callers own well appearance and draft writes.
 * Positions are one-based and column-major, matching Hamilton tip positions.
 */
export default function WellPaintGrid({rack, active, joined=false, rows, columns, canUpdate=true, disabled,
  paint, onPaintChange, onSelect, onApply, onGestureChange=noGesture, activation='corners', label, choices, children}:Props) {
  const [corners, setCorners] = useState<{ first: number; last: number } | null>(null);
  const press = useRef<Press | null>(null);
  const ignoreClick = useRef(false);
  const grid = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const selecting = useRef(false);
  selecting.current = Boolean(corners || press.current);
  const positions = rows * columns;
  const enabled = active && canUpdate && !disabled && paint !== null;
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

  const apply = (tips: number[]) => { if (enabled && paint !== null) onApply(tips, paint); cancel(); };
  const activate = (tip: number, event: React.MouseEvent) => {
    if (ignoreClick.current && event.detail !== 0) { ignoreClick.current = false; return; }
    ignoreClick.current = false;
    onSelect(tip);
    if (!enabled) return;
    if (activation === 'single') apply([tip]);
    else if (corners) apply(rectangle(corners.first, tip));
    else { selecting.current = true; setCorners({ first: tip, last: tip }); onGestureChange(true); }
  };
  const hit = (x: number, y: number) => {
    const button = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-paint-position]');
    return button && grid.current?.contains(button) ? Number(button.dataset.paintPosition) : null;
  };
  const keyMove = (event: React.KeyboardEvent, tip: number) => {
    if ((event.key === 'ArrowDown' && tip % rows === 0) || (event.key === 'ArrowUp' && (tip - 1) % rows === 0)) { event.preventDefault(); return; }
    const next = event.key === 'ArrowDown' ? tip + 1 : event.key === 'ArrowUp' ? tip - 1 : event.key === 'ArrowRight' ? tip + rows : event.key === 'ArrowLeft' ? tip - rows : event.key === 'Home' ? 1 : event.key === 'End' ? positions : null;
    if (next === null) return;
    event.preventDefault();
    if (next < 1 || next > positions) return;
    onSelect(next); grid.current?.querySelector<HTMLButtonElement>(`[data-paint-position="${next}"]`)?.focus();
  };

  const handlers: React.HTMLAttributes<HTMLDivElement> = {
    onPointerDown: event => {
      ignoreClick.current = false;
      if (!enabled || event.pointerType === 'touch' || event.button !== 0) return;
      const tip = hit(event.clientX, event.clientY); if (!tip) return;
      press.current = { pointer: event.pointerId, first: tip, last: tip, x: event.clientX, y: event.clientY, dragging: false };
      selecting.current = true;
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button');
      try { button?.setPointerCapture(event.pointerId); } catch { /* The pointer may already have been canceled. */ }
      onGestureChange(true);
    },
    onPointerMove: event => {
      const current = press.current; if (!current || current.pointer !== event.pointerId) return;
      if (Math.hypot(event.clientX - current.x, event.clientY - current.y) > 4) current.dragging = true;
      if (!current.dragging) return;
      current.last = hit(event.clientX, event.clientY);
      setCorners(current.last ? { first: current.first, last: current.last } : null);
    },
    onPointerUp: event => {
      const current = press.current; if (!current || current.pointer !== event.pointerId) return;
      press.current = null;
      if (current.dragging) {
        ignoreClick.current = true;
        const lastTip = hit(event.clientX, event.clientY);
        if (lastTip) apply(rectangle(current.first, lastTip)); else cancel();
      } else if (!hit(event.clientX, event.clientY)) { ignoreClick.current = true; cancel(); }
    },
    onPointerCancel: event => {
      ignoreClick.current = true;
      // Native touch panning ends this pointer, not the previously chosen corner.
      if (event.pointerType !== 'touch' || press.current) cancel();
    },
    onLostPointerCapture: () => { if (press.current) { ignoreClick.current = true; cancel(); } }
  };
  const control = <ToggleButtonGroup size="small" exclusive value={paint} disabled={disabled} aria-label={label} onChange={(_, value: string | null) => onPaintChange(value)}
            sx={{ flexWrap: 'wrap', gap: 1, '& .MuiToggleButtonGroup-grouped': { m: 0, border: 1, borderColor: 'surface.control', borderRadius: `${layout.radius}px` },
              '& .MuiToggleButtonGroup-grouped.Mui-selected': { borderColor: 'primary.main', bgcolor: theme => theme.palette.tone.running.bg, fontWeight: 600 } }}>
            {choices.map(choice => <ToggleButton key={choice.value} value={choice.value} sx={{ gap: 1, px: 1.5 }}>
              {choice.symbol != null ? <Box component="span" aria-hidden="true">{choice.symbol}</Box> : <Box component="span" aria-hidden="true" sx={{ bgcolor: choice.color || 'text.disabled', width: 10, height: 10, borderRadius: '50%' }} />}{choice.label}
            </ToggleButton>)}
          </ToggleButtonGroup>;
  return <>{children({control, grid, viewport, handlers, preview, corners, enabled, cancel, apply, activate, keyMove})}</>;
}
