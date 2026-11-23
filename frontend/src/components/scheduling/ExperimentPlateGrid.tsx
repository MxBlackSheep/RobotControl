import { useState } from 'react';
import { Box, ButtonBase, Typography } from '@mui/material';

import WellPaintGrid from '../labware/WellPaintGrid';

export type WellKind = string;
export type PlateAssignment = {value:string; label:string; symbol:string};
export type PlateLayout = Record<string, WellKind>;
const rows = 'ABCDEFGH';
export const wells = Array.from({length: 96}, (_, i) => `${rows[i % 8]}${Math.floor(i / 8) + 1}`);

export default function ExperimentPlateGrid({assignments, value, onChange, disabled}: {assignments:PlateAssignment[]; value: PlateLayout; onChange: (value: PlateLayout) => void; disabled: boolean}) {
  const [kind, setKind] = useState<WellKind | null>(assignments[0]?.value ?? '');
  const names: Record<string,string> = Object.fromEntries([...assignments.map(a => [a.value,a.label]), ['', 'Empty']]);
  const tones = ['completed', 'running', 'attention', 'neutral'] as const;
  const tone = (well:string) => tones[assignments.findIndex(a => a.value === value[well]) % tones.length] ?? 'neutral';
  const [position, setPosition] = useState(1);
  return <WellPaintGrid rack="experiment" rows={8} columns={12} active disabled={disabled} activation="single"
    paint={kind} onPaintChange={setKind} label="Well assignment" choices={[...assignments, {value:'', label:'Empty', symbol:'-'}]}
    onSelect={setPosition} onApply={(positions, paint) => {
      const next = {...value};
      for (const position of positions) { if (paint) next[wells[position - 1]] = paint; else delete next[wells[position - 1]]; }
      onChange(next);
    }}>
    {({control, viewport, grid, handlers, preview, activate, keyMove}) => <Box sx={{display:'flex', flexDirection:'column', flex:1}}>
    <Box sx={{mb:1.5, '@media (min-width:1280px)':{mb:4}}}>{control}</Box>
    <Box ref={viewport} sx={{overflowX:'auto', display:'flex', flex:1}}>
      <Box ref={grid} aria-label="Plate layout" {...handlers} sx={{display:'grid', gridTemplateColumns:'20px repeat(12, minmax(0, 1fr))', gap:0.5, width:'100%', maxWidth:644, mx:'auto', '@media (min-width:1280px)':{maxWidth:'none', gridTemplateRows:'40px repeat(8, 1fr)', justifyItems:'center', alignItems:'center'}, touchAction:'manipulation'}}>
        <span />{Array.from({length:12}, (_,i) => <Typography key={i} align="center">{i+1}</Typography>)}
        {Array.from(rows).map(row => <Box key={row} sx={{display:'contents'}}>
          <Typography sx={{alignSelf:'center'}}>{row}</Typography>
          {Array.from({length:12}, (_,i) => `${row}${i+1}`).map(well => <ButtonBase key={well} component="button" type="button" disabled={disabled}
            data-well={well} data-paint-position={wells.indexOf(well)+1} aria-label={`${well}: ${names[value[well] || '']}`}
            tabIndex={position === wells.indexOf(well)+1 ? 0 : -1}
            onClick={e => activate(wells.indexOf(well)+1, e)} onKeyDown={e => keyMove(e, wells.indexOf(well)+1)}
            sx={{outline:preview.has(wells.indexOf(well)+1) ? '2px solid' : undefined, outlineColor:'primary.main', '&:focus-visible':{outline:'3px solid',outlineColor:'primary.main'}, width:'100%', maxWidth:48, aspectRatio:'1', minWidth:0, minHeight:0, borderRadius:'50%', border:1,
              borderColor:theme => value[well] ? theme.palette.tone[tone(well)].dot : theme.palette.divider,
              bgcolor:theme => value[well] ? theme.palette.tone[tone(well)].bg : theme.palette.background.paper,
              color:theme => value[well] ? theme.palette.tone[tone(well)].fg : theme.palette.text.secondary,
              '@media (pointer: coarse), (max-width: 600px)': {minWidth:0, minHeight:0}, fontSize:{xs:10,sm:13}}}>
            {assignments.find(a => a.value === value[well])?.symbol ?? '-'}
          </ButtonBase>)}
        </Box>)}
      </Box>
    </Box>
  </Box>}
  </WellPaintGrid>;
}
