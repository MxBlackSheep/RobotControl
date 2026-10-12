import React from 'react';
import { Box, ButtonBase, IconButton, Link as MuiLink, Menu, MenuItem, Stack, Tab, Tabs, Typography, type SxProps, type Theme } from '@mui/material';
import ChevronLeft from '@mui/icons-material/ChevronLeft';
import ExpandMore from '@mui/icons-material/ExpandMore';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { allowedSections, moduleSectionUrl, moreItemFor, phoneBack, useModuleSection, useSidebarLayout } from './navigation';
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

/**
 * Title, the module's permitted sections as tabs (kept in `?section=`) and page actions, on one 40px row.
 * Below 900px (the phone tabs) the heading is the current section, a menu on a tab's own page.
 */
export function PageHeader({ title, actions, sectionMenu = true }: { title: string; actions?: React.ReactNode; sectionMenu?: boolean }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const sections = allowedSections(pathname, user);
  // Sections this user would have on the RobotControl computer (remote sessions, e.g. the tunnel).
  const localOnly = allowedSections(pathname, user && { ...user, session_is_local: true })
    .filter(section => !sections.some(allowed => allowed.id === section.id));
  const [selected] = useModuleSection(pathname, user);
  const attention = robotAttention(useRobotStatusContext().status);
  const tabbed = sections.length > 1;
  // Phones keep the local-only note behind an info button so the page content starts higher.
  const [noteOpen, setNoteOpen] = React.useState(false);
  const noteId = React.useId();
  const { mobile } = useSidebarLayout();
  const [menuAnchor, setMenuAnchor] = React.useState<HTMLElement | null>(null);
  const menuId = React.useId();
  const infoButton = localOnly.length > 0 && <IconButton aria-label="Sections on the RobotControl computer only" aria-expanded={noteOpen} aria-controls={noteId}
    onClick={() => setNoteOpen(open => !open)} onKeyDown={event => { if (event.key === 'Escape') setNoteOpen(false); }} sx={{ display: { xs: 'inline-flex', sm: 'none' }, ml: -2, color: 'text.secondary' }}>
    <InfoOutlined fontSize="small" />
  </IconButton>;
  const recoveryBadge = (show: boolean) => show && attention && <Box component="span" aria-label="requires attention" sx={{ minWidth: 18, height: 18, px: 0.5, borderRadius: 9, bgcolor: 'attentionSurface.action', color: 'attentionSurface.actionText', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{attention.kind === 'recovery' ? attention.count : '!'}</Box>;
  const actionRow = actions && <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ ml: { xs: 0, sm: 'auto' } }}>{actions}</Stack>;
  const note = localOnly.length > 0 && <Typography id={noteId} variant="body2" color="text.secondary" sx={{ mt: 1, display: { xs: noteOpen ? 'block' : 'none', sm: 'block' } }}>
    On the RobotControl computer only: {localOnly.map(section => section.label).join(', ')}.
  </Typography>;

  if (mobile) {
    // Phones: a tab's own page titles its current section, with a menu of sections; a page opened
    // from More shows the name that was tapped and a way back. No module label, dots or local-only
    // note: More lists what stays on the workstation.
    // `sectionMenu={false}`: the page shows its own section control (Runs) under a plain title.
    const current = tabbed && sectionMenu ? sections.find(section => section.index === selected) ?? sections[0] : undefined;
    const back = phoneBack(pathname);
    const fromMore = back?.to === '/more';
    const heading = fromMore ? moreItemFor(pathname, selected === 0 ? undefined : current?.id)?.label ?? current?.label ?? title : current?.label ?? title;
    return <Box component="header" sx={{ mb: 1.5 }}>
      {back && <MuiLink component={Link} to={back.to} underline="none" sx={{ display: 'inline-flex', alignItems: 'center', minHeight: 32, ml: -0.75, fontWeight: 600, fontSize: 15 }}>
        <ChevronLeft aria-hidden />{back.label}
      </MuiLink>}
      <Box sx={{ display: 'flex', alignItems: 'center', minHeight: layout.header, columnGap: 2, rowGap: 1, flexWrap: 'wrap' }}>
        <Typography component="h1" variant="h1" sx={{ fontSize: 24, minWidth: 0 }}>
          {current && !fromMore ? <ButtonBase aria-haspopup="menu" aria-expanded={Boolean(menuAnchor)} aria-controls={menuAnchor ? menuId : undefined}
            onClick={event => setMenuAnchor(event.currentTarget)}
            sx={{ font: 'inherit', color: 'inherit', textAlign: 'left', minHeight: 44, gap: 0.5, borderRadius: 1, maxWidth: '100%' }}>
            <Box component="span" sx={{ overflowWrap: 'anywhere' }}>{heading}</Box>
            {recoveryBadge(sections.some(section => section.id === 'recovery') && current.id !== 'recovery')}
            <ExpandMore aria-hidden sx={{ fontSize: 22, color: 'text.secondary', flexShrink: 0 }} />
          </ButtonBase> : heading}
        </Typography>
        {current && !fromMore && <Menu id={menuId} anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
          {sections.map(section => <MenuItem key={section.id} component={Link} to={moduleSectionUrl(pathname, section.index)}
            selected={section.index === current.index} onClick={() => setMenuAnchor(null)} sx={{ minHeight: 44, gap: 1 }}>
            {section.label}{recoveryBadge(section.id === 'recovery')}
          </MenuItem>)}
        </Menu>}
        {actionRow}
      </Box>
    </Box>;
  }

  return <Box component="header" sx={{ mb: `${layout.gutter}px` }}>
    <Box sx={{ display: 'flex', alignItems: 'center', minHeight: layout.header, columnGap: 3, rowGap: 1, flexWrap: 'wrap' }}>
      <Typography component="h1" variant="h1" sx={{ fontSize: { xs: 20, sm: 24 } }}>{title}</Typography>
      {infoButton}
      {tabbed && <Tabs value={sections.some(section => section.index === selected) ? selected : false} variant="scrollable" scrollButtons={false}
        aria-label={`${title} sections`} sx={{ alignSelf: 'stretch', minWidth: 0, flex: '1 1 auto', order: { xs: 3, md: 0 }, flexBasis: { xs: '100%', md: 'auto' } }}>
        {sections.map(section => <Tab key={section.id} value={section.index} component={Link} to={moduleSectionUrl(pathname, section.index)}
          label={section.id === 'recovery' && attention
            ? <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>{section.label}
                {recoveryBadge(true)}</Box>
            : section.label} />)}
      </Tabs>}
      {/* On phones the actions wrap below the title and start at the page edge like everything else. */}
      {actionRow}
    </Box>
    {note}
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
export function PanelLabel({ children, component = 'h2', tone, id }: { children: React.ReactNode; component?: React.ElementType; tone?: 'attention'; id?: string }) {
  return <Typography component={component} id={id} variant="overline" sx={{ display: 'block', textTransform: 'uppercase', whiteSpace: 'nowrap', color: tone === 'attention' ? 'attentionSurface.text' : 'surface.label' }}>{children}</Typography>;
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
  // Clip, not hidden: a hidden panel is a scroll container, so bars pinned inside it (phone lists) would not stick to the screen.
  return <Box component={component} aria-label={name} sx={[{
    gridColumn: spanColumn(span), minWidth: 0, minHeight: 0, display: 'grid', overflow: 'clip',
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

/**
 * A detail panel with nothing chosen yet: a plain prompt, not an alert. It has the same 40px header
 * band as the list panel beside it, so both tops line up.
 */
export function EmptyPanel({ children, title = 'Details' }: { children: React.ReactNode; title?: string }) {
  return <Panel title={title} fill sx={{ flex: 1 }}>
    <Typography variant="body2" color="text.secondary">{children}</Typography>
  </Panel>;
}
