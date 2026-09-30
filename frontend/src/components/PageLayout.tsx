import React from 'react';
import { Box, Stack, Tab, Tabs, Typography, type SxProps, type Theme } from '@mui/material';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { allowedSections, moduleSectionUrl, useModuleSection } from './navigation';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { layout, type StatusTone } from '../theme';

/*
 * Layout primitives of design system A. Pages compose these; spacing, heights and borders come
 * from the theme's layout tokens here, not from page-local numbers:
 *   PageContent > PageHeader + PageGrid > Panel (header 40, body, optional footer 40) > ListRow (40).
 */

export function PageContent({ children, reading = false, variant = 'overview' }: { children: React.ReactNode; reading?: boolean; variant?: 'overview' | 'inspection' | 'spatial' | 'task' }) {
  // Pages use the full width; only long-form reading keeps a text measure.
  return <Box data-page-pattern={variant} sx={{ width: '100%', minWidth: 0, maxWidth: reading ? 1120 : 'none', containerType: 'inline-size', containerName: 'workspace' }}>{children}</Box>;
}

/** Title, the module's permitted sections as tabs (kept in `?section=`) and page actions, on one 40px row. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const sections = allowedSections(pathname, user);
  const [selected] = useModuleSection(pathname, user);
  const attention = robotAttention(useRobotStatusContext().status);
  const tabbed = sections.length > 1;
  return <Box component="header" sx={{ mb: `${layout.gutter}px` }}>
    <Box sx={{ display: 'flex', alignItems: 'center', minHeight: layout.header, columnGap: 3, rowGap: 1, flexWrap: 'wrap' }}>
      <Typography component="h1" variant="h1" sx={{ fontSize: { xs: 20, sm: 24 } }}>{title}</Typography>
      {tabbed && <Tabs value={sections.some(section => section.index === selected) ? selected : false} variant="scrollable" scrollButtons={false}
        aria-label={`${title} sections`} sx={{ alignSelf: 'stretch', minWidth: 0, flex: '1 1 auto', order: { xs: 3, md: 0 }, flexBasis: { xs: '100%', md: 'auto' } }}>
        {sections.map(section => <Tab key={section.id} value={section.index} component={Link} to={moduleSectionUrl(pathname, section.index)}
          label={section.id === 'recovery' && attention
            ? <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>{section.label}
                <Box component="span" aria-label="requires attention" sx={{ minWidth: 18, height: 18, px: 0.5, borderRadius: 9, bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{attention.kind === 'recovery' ? attention.count : '!'}</Box></Box>
            : section.label} />)}
      </Tabs>}
      {actions && <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ ml: 'auto' }}>{actions}</Stack>}
    </Box>
    {description && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{description}</Typography>}
  </Box>;
}

type Span = number | { xs?: number; sm?: number; md?: number; lg?: number };
const spanColumn = (span: Span | undefined) => {
  if (span === undefined) return { xs: '1 / -1' };
  const spans = typeof span === 'number' ? { md: span } : span;
  return Object.fromEntries([['xs', '1 / -1'], ...Object.entries(spans).map(([key, value]) => [key, value >= 12 ? '1 / -1' : `span ${value}`])]);
};

/** The 12-column page grid: one column on narrow screens, twelve from md. */
export function PageGrid({ children, rows, sx }: { children: React.ReactNode; rows?: string; sx?: SxProps<Theme> }) {
  return <Box sx={[{ display: 'grid', gap: `${layout.gutter}px`, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(12, minmax(0, 1fr))' },
    gridTemplateRows: rows, alignItems: 'stretch', minWidth: 0 }, ...(Array.isArray(sx) ? sx : [sx])]}>{children}</Box>;
}

/** The 11px uppercase label that names a panel or a column. */
export function PanelLabel({ children, component = 'h2', tone }: { children: React.ReactNode; component?: React.ElementType; tone?: 'attention' }) {
  return <Typography component={component} variant="overline" sx={{ display: 'block', textTransform: 'uppercase', whiteSpace: 'nowrap', color: tone === 'attention' ? 'attentionSurface.text' : 'surface.label' }}>{children}</Typography>;
}

/** A panel's 40px header band: label, then anything else, with actions at the end. */
export function PanelHeader({ title, actions, tone, children }: { title: React.ReactNode; actions?: React.ReactNode; tone?: 'attention'; children?: React.ReactNode }) {
  return <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, height: layout.header, boxSizing: 'border-box', px: `${layout.inset}px`, minWidth: 0,
    bgcolor: tone === 'attention' ? 'attentionSurface.head' : 'surface.head', borderBottom: 1, borderColor: 'surface.headLine' }}>
    {typeof title === 'string' ? <PanelLabel tone={tone}>{title}</PanelLabel> : title}
    {children}
    {actions && <Stack direction="row" alignItems="center" gap={1} sx={{ ml: 'auto', minWidth: 0 }}>{actions}</Stack>}
  </Box>;
}

/**
 * The one panel shape: 40px header band, body and an optional fixed 40px footer. Panels in one
 * PageGrid row share its height. `inset` pads the body by 16px; lists pass `inset={false}`.
 */
export function Panel({ title, label, actions, headerExtra, tone, span, footer, inset = true, fill = false, component = 'section', sx, bodySx, children }: {
  title: React.ReactNode; label?: string; actions?: React.ReactNode; headerExtra?: React.ReactNode; tone?: 'attention'; span?: Span;
  footer?: React.ReactNode; inset?: boolean; fill?: boolean; component?: React.ElementType; sx?: SxProps<Theme>; bodySx?: SxProps<Theme>; children?: React.ReactNode;
}) {
  const name = label ?? (typeof title === 'string' ? title : undefined);
  return <Box component={component} aria-label={name} sx={[{
    gridColumn: spanColumn(span), minWidth: 0, minHeight: 0, display: 'grid', overflow: 'hidden',
    gridTemplateRows: `${layout.header}px ${fill ? 'minmax(0, 1fr)' : 'auto'}${footer ? ` ${layout.header}px` : ''}`, alignContent: 'start',
    bgcolor: 'background.paper', border: 1, borderColor: tone === 'attention' ? 'attentionSurface.line' : 'divider', borderRadius: `${layout.radius}px`,
  }, ...(Array.isArray(sx) ? sx : [sx])]}>
    <PanelHeader title={title} actions={actions} tone={tone}>{headerExtra}</PanelHeader>
    <Box sx={[{ minWidth: 0, minHeight: 0, ...(inset && { p: `${layout.inset}px` }) }, ...(Array.isArray(bodySx) ? bodySx : [bodySx])]}>{children}</Box>
    {footer && <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, px: `${layout.inset}px`, minWidth: 0, borderTop: 1, borderColor: 'surface.headLine', fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden' }}>{footer}</Box>}
  </Box>;
}

type Columns = string | { xs?: string; sm?: string; md?: string; lg?: string };

/** A single-line 40px row; `columns` is its grid-template-columns (responsive values allowed). */
export function ListRow({ columns, children, component = 'div', sx, ...rest }: { columns: Columns; children: React.ReactNode; component?: React.ElementType; sx?: SxProps<Theme> } & Record<string, unknown>) {
  return <Box component={component} {...rest} sx={[{ display: 'grid', gridTemplateColumns: columns, columnGap: `${layout.gutter}px`, alignItems: 'center',
    height: layout.row, flexShrink: 0, px: `${layout.inset}px`, minWidth: 0, borderBottom: 1, borderColor: 'surface.rowLine', fontSize: 13,
    '& > *': { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, ...(Array.isArray(sx) ? sx : [sx])]}>{children}</Box>;
}

/** A status as a coloured dot and label, for strips and compact rows (chips stay for emphasis). */
export function StatusDot({ tone, label }: { tone: StatusTone; label: string }) {
  return <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', color: theme => theme.palette.tone[tone].fg }}>
    <Box component="span" aria-hidden sx={{ width: 8, height: 8, borderRadius: 4, flexShrink: 0, bgcolor: theme => theme.palette.tone[tone].dot }} />{label}
  </Box>;
}

/** The name of the selected item in a detail panel (a run, a schedule, a folder, a recovery). */
export function DetailTitle({ children, component = 'h2' }: { children: React.ReactNode; component?: React.ElementType }) {
  return <Typography component={component} sx={{ fontSize: 20, fontWeight: 600, lineHeight: '28px', overflowWrap: 'anywhere', minWidth: 0 }}>{children}</Typography>;
}

/** A detail panel with nothing chosen yet: a plain prompt inside the panel shape, not an alert. */
export function EmptyPanel({ children }: { children: React.ReactNode }) {
  return <Box sx={{ flex: 1, p: `${layout.inset}px`, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px` }}>
    <Typography variant="body2" color="text.secondary">{children}</Typography>
  </Box>;
}
