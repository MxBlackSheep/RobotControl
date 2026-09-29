import { Box, ButtonBase, Stack, Typography } from '@mui/material';
import { TipTrackingFamilyState } from '../../services/labwareApi';

interface Props {
  family: TipTrackingFamilyState;
  joined: boolean;
  rows: number;
  columns: number;
  selected: string;
  statuses: string[];
  colors: Record<string, string>;
  statusAt: (rack: string, position: number) => string;
  pendingAt: (rack: string) => number;
  onOpen: (rack: string) => void;
}

/** The array order is deck geometry. Never sort these racks by name or state. */
export default function TipDeckOverview({ family, joined, rows, columns, selected, statuses, colors, statusAt, pendingAt, onOpen }: Props) {
  const rackRows = Math.max(1, family.left_racks.length, family.right_racks.length);
  const mapMinimum = rows * 5 + rows - 1;
  const rackMinimum = mapMinimum + 24; // Title, gap, padding and border.
  const dotSize = `max(5px, min(calc((100cqw - ${columns - 1}px) / ${columns} * 0.7), calc((100cqh - ${rows - 1}px) / ${rows} * 0.7)))`;
  // Query containment belongs on each miniature, never on this subgrid pane:
  // layout containment would make its header/body/footer resolve separately.
  return <Box component="section" aria-label="Tip deck" sx={{ minWidth: 0, display: 'grid', gridColumn: 1, gridRow: '1 / 4', gridTemplateRows: 'subgrid', bgcolor: 'action.hover', borderRight: joined ? 1 : 0, borderColor: 'divider' }}>
    <Box sx={{ gridRow: 1, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1, alignItems: 'end', px: 1.5, py: 1 }}>
      {['Col A', 'Col B'].map(label => <Typography key={label} variant="caption" color="text.secondary">{label}</Typography>)}
    </Box>
    <Box data-tip-overview-body sx={{ gridRow: 2, minWidth: 0, minHeight: rackRows * rackMinimum + (rackRows - 1) * 4, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1, px: 1.25 }}>
      {[['Col A', family.left_racks], ['Col B', family.right_racks]].map(([label, racks]) => <Box key={String(label)} role="group" aria-label={String(label)} sx={{ minWidth: 0, display: 'grid', gridTemplateRows: `repeat(${rackRows}, minmax(min-content, 1fr))`, gap: 0.5 }}>
        {(racks as string[]).map(rack => {
          const pending = pendingAt(rack);
          return <ButtonBase key={rack} disableRipple aria-label={`Open rack ${rack}`} aria-current={selected === rack ? 'true' : undefined} onClick={() => onOpen(rack)}
            sx={{ width: '100%', minWidth: 0, minHeight: rackMinimum, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gridTemplateRows: 'auto minmax(0, 1fr)', alignItems: 'stretch', justifyItems: 'stretch', justifyContent: 'normal', gap: '2px', textAlign: 'left', p: '2px', border: 1, borderColor: selected === rack ? 'primary.main' : 'transparent', borderRadius: 1, bgcolor: selected === rack ? 'action.selected' : 'transparent', '&:hover': { bgcolor: 'action.hover' }, '&.Mui-focusVisible, &:focus-visible': { outline: '3px solid', outlineColor: 'primary.main', outlineOffset: -2 } }}>
            <Box component="span" sx={{ display: 'flex', alignItems: 'baseline', minWidth: 0, minHeight: 16, gap: 0.25, fontSize: 'clamp(12px, 0.6cqw, 18px)', lineHeight: 1.25 }}>
              <Typography component="span" title={rack} sx={{ fontWeight: 600, fontSize: 'inherit', lineHeight: 'inherit', minWidth: 0, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rack}</Typography>
              <Box component="span" aria-label={`${pending} unsaved`} sx={{ color: 'warning.main', flex: `0 0 ${String(rows * columns).length + 1}ch`, textAlign: 'right', visibility: pending ? 'visible' : 'hidden' }}>{pending}*</Box>
            </Box>
            <Box aria-hidden="true" sx={{ containerType: 'size', minHeight: mapMinimum, minWidth: columns * 5 + columns - 1, display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(5px, 1fr))`, gridTemplateRows: `repeat(${rows}, minmax(5px, 1fr))`, gap: '1px' }}>
              {Array.from({ length: rows * columns }, (_, i) => <Box key={i} data-overview-dot sx={{ gridColumn: Math.floor(i / rows) + 1, gridRow: i % rows + 1, width: dotSize, height: dotSize, alignSelf: 'center', justifySelf: 'center', borderRadius: '50%', bgcolor: colors[statusAt(rack, i + 1)] || 'text.disabled' }} />)}
            </Box>
          </ButtonBase>;
        })}
        {!(racks as string[]).length && <Typography variant="caption" color="text.secondary">No racks</Typography>}
      </Box>)}
    </Box>
    <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" aria-label="Tip status legend" sx={{ gridRow: 3, px: 1.5, py: 1 }}>
      {statuses.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled' }} /><Typography variant="caption" color="text.secondary">{status.charAt(0).toUpperCase() + status.slice(1)}</Typography></Stack>)}
    </Stack>
  </Box>;
}
