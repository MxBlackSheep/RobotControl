import { useRef, useState } from 'react';
import { Box, ButtonBase, FormControlLabel, Radio, RadioGroup, Typography } from '@mui/material';

export type WellKind = 'Cells' | 'MediaCtrl';
export type PlateLayout = Record<string, WellKind>;
const rows = 'ABCDEFGH';
const names = { Cells: 'Culture', MediaCtrl: 'Media control', '': 'Empty' };
export const wells = Array.from({length: 96}, (_, i) => `${rows[i % 8]}${Math.floor(i / 8) + 1}`);
export const recentLayout = (): PlateLayout => Object.fromEntries(wells.filter(w => Number(w.slice(1)) <= 5).map(w => [w, w.endsWith('1') ? 'MediaCtrl' : 'Cells']));

export default function ExperimentPlateGrid({value, onChange, disabled}: {value: PlateLayout; onChange: (value: PlateLayout) => void; disabled: boolean}) {
  const [kind, setKind] = useState<WellKind | ''>('Cells');
  const drag = useRef<{start: string; before: PlateLayout} | null>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const mark = (start: string, end: string, before: PlateLayout) => {
    const next = {...before};
    const r = [rows.indexOf(start[0]), rows.indexOf(end[0])].sort((a,b) => a-b);
    const c = [Number(start.slice(1)), Number(end.slice(1))].sort((a,b) => a-b);
    for (let row=r[0]; row<=r[1]; row++) for (let col=c[0]; col<=c[1]; col++) {
      const well = `${rows[row]}${col}`;
      if (kind) next[well] = kind; else delete next[well];
    }
    onChange(next);
  };
  return <Box>
    <RadioGroup row aria-label="Well assignment" value={kind} onChange={e => setKind(e.target.value as WellKind | '')}>
      {Object.entries(names).map(([key, label]) => <FormControlLabel key={key} value={key} control={<Radio />} label={label} disabled={disabled} />)}
    </RadioGroup>
    <Box sx={{overflowX:'auto'}}>
      <Box aria-label="Plate layout" sx={{display:'grid', gridTemplateColumns:'24px repeat(12, minmax(32px, 44px))', gap:0.5, width:'max-content', touchAction:'none'}}
        onPointerMove={e => {
          if (!drag.current || disabled) return;
          const target = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-well]');
          const well = target?.getAttribute('data-well');
          if (well && buttons.current[well] === target) mark(drag.current.start, well, drag.current.before);
        }}
        onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <span />{Array.from({length:12}, (_,i) => <Typography key={i} align="center">{i+1}</Typography>)}
        {Array.from(rows).map(row => <Box key={row} sx={{display:'contents'}}>
          <Typography sx={{alignSelf:'center'}}>{row}</Typography>
          {Array.from({length:12}, (_,i) => `${row}${i+1}`).map(well => <ButtonBase key={well} component="button" type="button" disabled={disabled}
            ref={node => { buttons.current[well] = node; }} data-well={well} aria-label={`${well}: ${names[value[well] || '']}`}
            onPointerDown={e => {
              if (e.button !== 0) return;
              drag.current = {start:well, before:value};
              e.currentTarget.parentElement?.parentElement?.setPointerCapture(e.pointerId);
              mark(well, well, value);
            }}
            onClick={e => { if (e.detail === 0) mark(well, well, value); }}
            onKeyDown={e => {
              const delta: Record<string, [number, number]> = {ArrowUp:[-1,0], ArrowDown:[1,0], ArrowLeft:[0,-1], ArrowRight:[0,1]};
              if (!delta[e.key]) return;
              e.preventDefault();
              const [dr,dc] = delta[e.key];
              const r = Math.max(0,Math.min(7,rows.indexOf(well[0])+dr));
              const c = Math.max(1,Math.min(12,Number(well.slice(1))+dc));
              buttons.current[`${rows[r]}${c}`]?.focus();
            }}
            sx={{width:40, height:40, borderRadius:'50%', border:1, borderColor:'divider',
              bgcolor:value[well] === 'Cells' ? 'success.main' : value[well] === 'MediaCtrl' ? 'info.main' : 'background.paper',
              color:value[well] === 'Cells' ? 'success.contrastText' : value[well] === 'MediaCtrl' ? 'info.contrastText' : 'text.primary'}}>
            {value[well] === 'Cells' ? 'C' : value[well] === 'MediaCtrl' ? 'M' : '-'}
          </ButtonBase>)}
        </Box>)}
      </Box>
    </Box>
    <Typography variant="body2" sx={{mt:1}}>{Object.values(value).filter(v => v === 'Cells').length} cultures, {Object.values(value).filter(v => v === 'MediaCtrl').length} media controls</Typography>
  </Box>;
}
