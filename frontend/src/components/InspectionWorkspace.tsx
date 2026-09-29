import { ReactNode, useLayoutEffect, useRef, useState } from "react";
import { Box, Button, IconButton, Tooltip } from "@mui/material";
import ChevronLeft from '@mui/icons-material/ChevronLeft';
import ChevronRight from '@mui/icons-material/ChevronRight';

interface InspectionWorkspaceProps {
  label: string;
  selector?: ReactNode;
  selectorLabel?: string;
  detailOpen?: boolean;
  onBack?: () => void;
  onDetailVisibilityChange?: (visible: boolean) => void;
  children: ReactNode;
}

/** A bounded reading area. The app header and page heading determine its height. */
export default function InspectionWorkspace({
  label,
  selector,
  selectorLabel = "Items",
  detailOpen = true,
  onBack,
  onDetailVisibilityChange,
  children,
}: InspectionWorkspaceProps) {
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
      else
        catalogue.current
          ?.querySelector<HTMLElement>('[aria-current="true"], .Mui-selected')
          ?.focus({ preventScroll: true });
    }
    previousOpen.current = detailOpen;
  }, [detailOpen, narrow]);

  return (
    <Box
      ref={workspace}
      aria-label={label}
      sx={{
        height: height ?? "70dvh",
        minHeight: 320,
        minWidth: 0,
        width: "100%",
        display: "flex",
        gap: narrow ? 0 : 0.5,
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
            width: narrow ? "100%" : selectorWidth,
            flexShrink: 0,
            minWidth: 0,
            minHeight: 0,
          }}
        >
          {selector}
        </Box>
      )}
      {selector && !narrow && <Box sx={{ width: 28, flexShrink: 0, position: 'relative' }}>
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
          flex: 1,
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
