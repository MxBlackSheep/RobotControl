import { ReactNode, useLayoutEffect, useRef, useState } from "react";
import { Box, Button, IconButton, Tooltip, Typography, useMediaQuery } from "@mui/material";
import ChevronLeft from '@mui/icons-material/ChevronLeft';
import ChevronRight from '@mui/icons-material/ChevronRight';
import type { SystemStyleObject } from "@mui/system";
import type { Theme } from "@mui/material/styles";

/** Phones: under 600 px (MUI's xs). */
const phoneQuery = '(max-width: 599.95px)';

/** True on phones, where the workspace flows with the page instead of keeping a measured height. */
export const usePhoneWorkspace = () => useMediaQuery(phoneQuery, { noSsr: true });

/** A bar pinned to the bottom of the screen while its list scrolls with the page (phones). */
export const pinnedBarSx = {
  position: 'sticky', bottom: 0, zIndex: 3, bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider',
  pb: 'env(safe-area-inset-bottom)',
} as const;

/**
 * The open table's or definition's name. Phones show one line (tap shows it whole; screen
 * readers always get the full name); wider screens wrap it.
 */
export function InspectionName({ name, variant, sx }: { name: string; variant?: 'subtitle1'; sx?: SystemStyleObject<Theme> }) {
  const phone = usePhoneWorkspace();
  const [whole, setWhole] = useState(false);
  const oneLine = phone && !whole;
  return <Typography component="h2" variant={variant} title={name} onClick={phone ? () => setWhole(value => !value) : undefined}
    sx={{ minWidth: 0, ...sx, ...(oneLine ? { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', cursor: 'pointer' } : { overflowWrap: 'anywhere' }) }}>
    {name}
  </Typography>;
}

/** "50 of 2,072 files" with Load more: a phone list grows in place instead of paging. `noun` is singular. */
export function LoadMoreBar({ shown, total, noun, loading = false, onMore }: {
  shown: number; total: number; noun: string; loading?: boolean; onMore: () => void;
}) {
  return <Box sx={[{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, minHeight: 52 }, pinnedBarSx]}>
    <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: 0 }}>
      {shown.toLocaleString()} of {total.toLocaleString()} {noun}{total === 1 ? '' : 's'}
    </Typography>
    {shown < total && <Button onClick={onMore} disabled={loading}>Load more</Button>}
  </Box>;
}

interface InspectionWorkspaceProps {
  label: string;
  selector?: ReactNode;
  selectorLabel?: string;
  detailOpen?: boolean;
  onBack?: () => void;
  onDetailVisibilityChange?: (visible: boolean) => void;
  /** "table": the selector is a wide table and the detail a fixed side panel (Scheduling). */
  layout?: 'list' | 'table';
  /**
   * The detail is a text reader with its own scrolling pane (SQL, log). On phones it keeps the
   * measured height while lists and tables flow with the page.
   */
  boundedDetail?: boolean;
  children: ReactNode;
}

/**
 * A bounded reading area. The app header and page heading determine its height. On phones it
 * has no height of its own: lists and tables scroll with the page (one scroll), apart from a
 * `boundedDetail` reader.
 */
export default function InspectionWorkspace({
  label,
  selector,
  selectorLabel = "Items",
  detailOpen = true,
  onBack,
  onDetailVisibilityChange,
  layout = 'list',
  boundedDetail = false,
  children,
}: InspectionWorkspaceProps) {
  const tableLayout = layout === 'table';
  const workspace = useRef<HTMLDivElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const catalogue = useRef<HTMLDivElement>(null);
  const previousOpen = useRef(detailOpen);
  const [height, setHeight] = useState<number>();
  const [narrow, setNarrow] = useState(false);
  const [selectorVisible, setSelectorVisible] = useState(true);
  const [selectorWidth, setSelectorWidth] = useState(300);
  const resizeStart = useRef<{ x: number; width: number } | null>(null);
  const resize = (value: number) => setSelectorWidth(Math.max(240, Math.min(480, value)));
  const detailVisible = !selector || !narrow || detailOpen;
  const phone = usePhoneWorkspace();
  const flow = phone && !(boundedDetail && detailVisible);

  useLayoutEffect(() => {
    onDetailVisibilityChange?.(detailVisible);
  }, [detailVisible, onDetailVisibilityChange]);

  useLayoutEffect(() => {
    const element = workspace.current;
    if (!element) return;
    const measure = () => {
      const bounds = element.getBoundingClientRect();
      if (!bounds.width) return; // A visited, hidden section keeps its previous size.
      const main = element.closest("main");
      const bottomSpace = main
        ? parseFloat(getComputedStyle(main).paddingBottom) || 0
        : 0;
      const viewportHeight =
        window.visualViewport?.height ?? window.innerHeight;
      setHeight(
        Math.max(
          320,
          Math.floor(
            viewportHeight - (bounds.top + window.scrollY) - bottomSpace,
          ),
        ),
      );
      setNarrow(bounds.width < 900);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.parentElement) observer.observe(element.parentElement);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, []);

  useLayoutEffect(() => {
    if (narrow && detailOpen !== previousOpen.current) {
      if (detailOpen) detail.current?.focus({ preventScroll: true });
      else {
        // The open item first: a selected filter button is also .Mui-selected.
        const list = catalogue.current;
        (list?.querySelector<HTMLElement>('[aria-current="true"]') ?? list?.querySelector<HTMLElement>('.Mui-selected'))
          ?.focus({ preventScroll: true });
      }
    }
    previousOpen.current = detailOpen;
  }, [detailOpen, narrow]);

  return (
    <Box
      ref={workspace}
      aria-label={label}
      sx={{
        height: flow ? "auto" : height ?? "70dvh",
        minHeight: flow ? 0 : 320,
        minWidth: 0,
        width: "100%",
        display: "flex",
        gap: narrow ? 0 : tableLayout ? 2 : 0.5,
      }}
    >
      {selector && (
        <Box
          ref={catalogue}
          component="aside"
          aria-label={selectorLabel}
          sx={{
            display: (narrow ? !detailOpen : selectorVisible) ? "flex" : "none",
            flexDirection: "column",
            width: narrow ? "100%" : tableLayout ? "auto" : selectorWidth,
            flex: tableLayout && !narrow ? 1 : undefined,
            flexShrink: 0,
            minWidth: 0,
            minHeight: 0,
          }}
        >
          {selector}
        </Box>
      )}
      {selector && !narrow && !tableLayout && <Box sx={{ width: 28, flexShrink: 0, position: 'relative' }}>
        <Tooltip title={`${selectorVisible ? 'Hide' : 'Show'} ${selectorLabel.toLowerCase()}`}>
          <IconButton size="small" aria-label={`${selectorVisible ? 'Hide' : 'Show'} ${selectorLabel.toLowerCase()}`} aria-expanded={selectorVisible} onClick={() => setSelectorVisible(value => !value)} sx={{ position: 'relative', zIndex: 1, width: 28 }}>
            {selectorVisible ? <ChevronLeft fontSize="small" /> : <ChevronRight fontSize="small" />}
          </IconButton>
        </Tooltip>
        {selectorVisible && <Box role="separator" aria-label={`Resize ${selectorLabel.toLowerCase()}`} aria-orientation="vertical" aria-valuenow={selectorWidth} aria-valuemin={240} aria-valuemax={480} tabIndex={0}
          onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); resize(selectorWidth + (event.key === 'ArrowLeft' ? -20 : 20)); } }}
          onPointerDown={event => { resizeStart.current = { x: event.clientX, width: selectorWidth }; event.currentTarget.setPointerCapture(event.pointerId); }}
          onPointerMove={event => { if (resizeStart.current) resize(resizeStart.current.width + event.clientX - resizeStart.current.x); }}
          onPointerUp={() => { resizeStart.current = null; }} onPointerCancel={() => { resizeStart.current = null; }}
          sx={{ position: 'absolute', top: 44, bottom: 0, left: 4, right: 4, cursor: 'col-resize', touchAction: 'none', '&:hover, &:focus-visible': { bgcolor: 'action.hover' }, '&::after': { content: '""', position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: 1, borderColor: 'divider' } }} />}
      </Box>}
      <Box
        ref={detail}
        tabIndex={-1}
        sx={{
          display: detailVisible ? "flex" : "none",
          flex: tableLayout && !narrow ? "0 0 400px" : 1,
          flexDirection: "column",
          minWidth: 0,
          minHeight: 0,
          outline: "none",
        }}
      >
        {selector && narrow && (
          <Box sx={{ flexShrink: 0, pb: 0.5 }}>
              <Button onClick={onBack}>
                Back to {selectorLabel.toLowerCase()}
              </Button>
          </Box>
        )}
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minWidth: 0,
            minHeight: 0,
          }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
}
