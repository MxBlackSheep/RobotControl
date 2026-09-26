import React from 'react';
import { Box, ButtonBase, Paper, Typography } from '@mui/material';
import { TipTrackingFamilyState } from '../../services/labwareApi';

interface Props {
  family: TipTrackingFamilyState;
  rows: number;
  columns: number;
  selected: string;
  colors: Record<string, string>;
  statusAt: (rack: string, position: number) => string;
  pendingAt: (rack: string) => number;
  onOpen: (rack: string) => void;
}

/** The array order is deck geometry. Never sort these racks by name or state. */
export default function TipDeckOverview({ family, rows, columns, selected, colors, statusAt, pendingAt, onOpen }: Props) {
  return <Paper component="section" aria-label="Tip deck" variant="outlined" sx={{ p: 1, minWidth: 0, containerType: 'inline-size' }}>
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1 }}>
      {[['Col A', family.left_racks], ['Col B', family.right_racks]].map(([label, racks]) => <Box key={String(label)} role="group" aria-label={String(label)} sx={{ minWidth: 0 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>{label}</Typography>
        {(racks as string[]).map(rack => {
          const pending = pendingAt(rack);
          return <ButtonBase key={rack} aria-label={`Open rack ${rack}`} aria-current={selected === rack ? 'true' : undefined} onClick={() => onOpen(rack)}
            sx={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch', textAlign: 'left', p: 0.75, mb: 0.75, border: 2, borderColor: selected === rack ? 'primary.main' : 'divider', borderRadius: 1, bgcolor: selected === rack ? 'action.selected' : 'background.paper', '&.Mui-focusVisible': { outline: '3px solid', outlineColor: 'primary.main', outlineOffset: 1 } }}>
            <Typography component="span" variant="caption" sx={{ fontWeight: 600, fontSize: 'clamp(12px, 3cqw, 14px)', overflowWrap: 'anywhere', lineHeight: 1.3 }}>{rack}</Typography>
            <Box aria-hidden="true" sx={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${rows}, clamp(5px, 1.8cqw, 9px))`, rowGap: '1px', mt: 0.5 }}>
              {Array.from({ length: rows * columns }, (_, i) => <Box key={i} sx={{ gridColumn: Math.floor(i / rows) + 1, gridRow: i % rows + 1, width: 'clamp(5px, 1.8cqw, 9px)', height: 'clamp(5px, 1.8cqw, 9px)', justifySelf: 'center', borderRadius: '50%', bgcolor: colors[statusAt(rack, i + 1)] || 'text.disabled', border: '1px solid', borderColor: 'divider' }} />)}
            </Box>
            {pending > 0 && <Typography component="span" variant="caption" color="warning.main" sx={{ lineHeight: 1.2, mt: 0.25 }}>{pending} unsaved</Typography>}
          </ButtonBase>;
        })}
        {!(racks as string[]).length && <Typography variant="caption" color="text.secondary">No racks</Typography>}
      </Box>)}
    </Box>
  </Paper>;
}
