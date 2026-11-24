import { Box, Button, Stack, Typography } from '@mui/material';
import { fontMono, layout, touchMedia } from '../../theme';
import WellPaintGrid from './WellPaintGrid';
import { usePhoneWorkspace } from '../InspectionWorkspace';

interface Props {
  rack: string;
  headingId: string;
  joined: boolean;
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

export default function TipRackEditor({ rack, headingId, joined, rows, columns, position, choices, legend, colors, statusAt, pendingAt, canUpdate, disabled, active, paint, onPaintChange, onSelect, onApply, onGestureChange }: Props) {
  const positions = rows * columns;
  const stateName = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
  const tips = Array.from({ length: positions }, (_, index) => index + 1);
  const hasDrafts = tips.some(pendingAt);
  const afterSaving = hasDrafts ? legend.map(status => [status, tips.filter(tip => statusAt(tip) === status).length] as const)
    .filter(([, count]) => count).map(([status, count]) => `${count} ${status}`).join(' · ') : '';
  // On a phone the rack dialog must show all twelve columns: 12 x 44px cannot fit at 320-390px,
  // so tips narrow to the available width (24px WCAG 2.5.8 floor, about 25px at 320px with the
  // dialog's 8px padding as the only side gutter) and keep 44px height. The same dialog on tablets
  // and narrow desktop windows (below ~928px of workspace) keeps the 44px geometry.
  const phone = usePhoneWorkspace();
  const compact = !joined && phone;
  const tipWidth = compact ? 24 : 44, tipGap = compact ? 0 : 4;
  const dotSize = `max(14px, min(calc((100cqw - ${(columns - 1) * tipGap}px) / ${columns} * 0.32), calc((100cqh - ${(rows - 1) * tipGap}px) / ${rows} * 0.32)))`;
  const fontSize = `clamp(12px, min(calc(100cqw / ${columns} * 0.21), calc(100cqh / ${rows} * 0.21)), 22px)`;

  // Four rows shared with the deck through subgrid: 40px header band, status row, tips, fixed footer.
  // "Set entire rack" is placed in the header band by CSS but follows the status buttons in the DOM,
  // so keyboard order stays: heading, choose a status, then apply it.
  return <WellPaintGrid rack={rack} active={active} joined={joined} rows={rows} columns={columns} canUpdate={canUpdate} disabled={disabled}
    paint={paint} onPaintChange={onPaintChange} onSelect={onSelect} onApply={onApply} onGestureChange={onGestureChange}
    label="Set tips to" choices={choices.map(status => ({value:status, label:stateName(status), color:colors[status]}))}>
    {({control, grid, viewport, handlers, preview, corners, enabled, cancel, apply, activate, keyMove}) => <Box data-rack-editor sx={{ minWidth: 0, display: 'grid', gridColumn: joined ? 2 : undefined, gridRow: joined ? '1 / 5' : undefined,
    gridTemplateRows: joined ? 'subgrid' : `minmax(${layout.header}px, auto) auto minmax(min-content, 1fr) minmax(${layout.header}px, auto)`,
    bgcolor: 'background.paper', border: joined ? 1 : 0, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'hidden' }}>
    <Box sx={{ gridRow: 1, gridColumn: 1, display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, px: 2, pr: canUpdate ? 17 : 2, bgcolor: 'surface.head', borderBottom: 1, borderColor: 'surface.headLine' }}>
      <Typography id={headingId} component="h2" sx={{ fontFamily: fontMono, fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={rack}>{rack}</Typography>
    </Box>
    <Box sx={{ gridRow: 2, gridColumn: 1, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, minWidth: 0, px: 2, py: 1, borderBottom: 1, borderColor: 'surface.rowLine' }}>
      {canUpdate
        ? /* Pick a status, then click or drag tips; pressing the chosen status again clears it. */
          control
        : <Stack direction="row" gap={1.5} flexWrap="wrap" aria-label="Tip status legend">{legend.map(status => <Stack key={status} direction="row" gap={0.5} alignItems="center"><Box aria-hidden="true" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled' }} /><Typography variant="caption">{stateName(status)}</Typography></Stack>)}</Stack>}
    </Box>
    {canUpdate && <Button size="small" disabled={!enabled || Boolean(corners)} onClick={() => apply(Array.from({ length: positions }, (_, index) => index + 1))}
      sx={{ gridRow: 1, gridColumn: 1, justifySelf: 'end', alignSelf: 'center', mr: 1, whiteSpace: 'nowrap' }}>Set entire rack</Button>}
      <Box ref={viewport} data-tip-editor-body sx={{ gridRow: 3, gridColumn: 1, minWidth: 0, minHeight: rows * 44 + (rows - 1) * tipGap + 24, height: '100%', px: compact ? 0 : 2, py: 1.5, boxSizing: 'border-box', overflowX: 'auto', overflowY: 'hidden' }}>
        <Box ref={grid} role="group" aria-label={`${rack} tips`} {...handlers}
          sx={{ containerType: 'size', display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(${tipWidth}px, 1fr))`, gridTemplateRows: `repeat(${rows}, minmax(44px, 1fr))`, gap: `${tipGap}px`, width: '100%', height: '100%', minWidth: columns * tipWidth + (columns - 1) * tipGap, minHeight: rows * 44 + (rows - 1) * tipGap, userSelect: 'none', touchAction: 'manipulation' }}>
          {Array.from({ length: positions }, (_, index) => {
            const tip = index + 1, status = statusAt(tip), unsaved = pendingAt(tip);
            return <Button key={tip} disableRipple data-tip={tip} data-paint-position={tip} aria-label={`Tip ${tip}, ${status}`} aria-pressed={position === tip} tabIndex={position === tip ? 0 : -1} onClick={event => activate(tip, event)} onKeyDown={event => keyMove(event, tip)}
              sx={{ gridColumn: Math.floor(index / rows) + 1, gridRow: index % rows + 1, minWidth: tipWidth, [touchMedia]: { minWidth: tipWidth }, minHeight: 44, p: compact ? 0 : 0.25, display: 'flex', flexDirection: 'column', gap: 0, color: 'text.primary', border: 2, borderColor: position === tip || preview.has(tip) ? 'primary.main' : unsaved ? 'warning.main' : 'transparent', borderStyle: unsaved ? 'dashed' : 'solid', bgcolor: preview.has(tip) ? 'action.selected' : 'transparent', transition: 'none', '&.Mui-focusVisible, &:focus-visible': { outline: '3px solid', outlineColor: 'primary.main', outlineOffset: -3 } }}>
              <Box component="span" data-tip-dot aria-hidden="true" sx={{ width: dotSize, height: dotSize, flexShrink: 0, borderRadius: '50%', bgcolor: colors[status] || 'text.disabled', border: 1, borderColor: 'divider' }} /><Typography component="span" sx={{ fontSize, lineHeight: 1.2 }}>{tip}{unsaved ? '*' : ''}</Typography>
            </Button>;
          })}
        </Box>
      </Box>
      {/* One fixed line: the draft summary never adds a row, so neither diagram moves when edits start. */}
      <Box data-tip-editor-footer sx={{ gridRow: 4, gridColumn: 1, display: 'flex', alignItems: 'center', gap: 2, minWidth: 0, px: 2, borderTop: 1, borderColor: 'surface.headLine', whiteSpace: 'nowrap' }}>
        <Typography role="status" variant="body2" sx={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{corners ? `${preview.size} tips selected` : canUpdate ? '' : `Tip ${position}: ${stateName(statusAt(position))}`}</Typography>
        <Button size="small" onClick={cancel} disabled={!corners} aria-hidden={!corners} tabIndex={corners ? 0 : -1} sx={{ visibility: corners ? 'visible' : 'hidden', flexShrink: 0 }}>Cancel selection</Button>
        {canUpdate && hasDrafts && <Typography aria-label="This rack after saving" title={`After saving: ${afterSaving}`}
          sx={{ ml: 'auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>After saving: {afterSaving}</Typography>}
      </Box>
  </Box>}
  </WellPaintGrid>;
}
