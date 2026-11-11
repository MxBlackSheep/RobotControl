import React, { useLayoutEffect, useRef, useState } from "react";
import { Alert, Box, Dialog, IconButton, Paper, Stack, Tooltip, Typography, useMediaQuery } from "@mui/material";
import { Close, Fullscreen } from "@mui/icons-material";
import { PanelLabel } from "./PageLayout";
import { layout } from "../theme";
import { heightBelow, observeScrollArea } from "./appShell";
import LiveFrame, { FrameFreshness, type FrameStore } from "./LiveFrame";

interface CameraViewportProps {
  store: FrameStore;
  hasFrame: boolean;
  connection: string;
  /** Camera and recording states. Always shown expanded (the controls are behind the dialog). */
  summary?: string;
  /** Show the summary inline too; false where the camera controls' own chips sit beside the picture. */
  inlineSummary?: boolean;
  controls: React.ReactNode;
  error?: string | null;
}
const touchTarget = { minWidth: 44, minHeight: 44 };
/** A phone, upright or on its side: the viewing controls go below the picture, within thumb reach. */
const COMPACT = "(max-width: 599.95px), (max-height: 499.95px)";
/** An upright phone: the picture uses the whole screen width, not the page's 16px margins. */
const NARROW = "(max-width: 599.95px)";
/** Only in-between states get words; idle shows Start beside the picture, an unsupported browser its reason above it. */
const placeholders: Record<string, string> = { disconnected: "Live view disconnected", connecting: "Connecting to live view…" };

/** The whole frame, undistorted, at every size; Expand shows it full screen. Never changes the camera or the session. */
export default function CameraViewport({ store, hasFrame, connection, summary, inlineSummary = true, controls, error }: CameraViewportProps) {
  const [expanded, setExpanded] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 640, height: 480 });
  const [available, setAvailable] = useState({ width: 640, height: 480 });
  // A state ref: the expanded Dialog mounts its content through a portal one render later,
  // so measuring must start when the element attaches, not when `expanded` changes.
  const [area, setArea] = useState<HTMLDivElement | null>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<HTMLDivElement>(null);
  const compact = useMediaQuery(COMPACT);
  const narrow = useMediaQuery(NARROW);
  const expandRef = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    if (!area) return;
    const measure = () => {
      const bounds = area.getBoundingClientRect();
      const main = area.closest("main");
      // A minimum lets short/zoomed windows scroll without making the image vanish.
      const remaining = heightBelow(area) - 40;
      // On a phone the controls above would leave the picture a sliver: it may fill one screen
      // of the scroll area (the page scrolls to it), and its width usually decides.
      const screen = main ? main.clientHeight - 40 : 0;
      const height = expanded ? bounds.height : Math.max(180, remaining, compact ? screen : 0);
      const width = area.clientWidth || bounds.width;
      setAvailable((previous) =>
        previous.width === width && previous.height === height
          ? previous
          : { width: Math.max(1, width), height: Math.max(1, height) },
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(area);
    observeScrollArea(area, observer);
    if (toolbarRef.current) observer.observe(toolbarRef.current);
    if (controlsRef.current) observer.observe(controlsRef.current);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, [area, expanded, compact]);

  const scale = Math.min(available.width / dimensions.width, available.height / dimensions.height);
  const imageWidth = dimensions.width * scale;
  const imageHeight = dimensions.height * scale;
  const closeExpanded = () => setExpanded(false);

  // Above the picture on wider screens, below it (after the freshness line) on phones,
  // so DOM and tab order follow what is on screen.
  const controlRow = (
    <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" justifyContent="space-between">
      <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ "& button": touchTarget }}>
        {controls}
      </Stack>
      {!expanded && (
        <Stack data-testid="camera-toolbar" direction="row" alignItems="center">
          <Tooltip title="Expand live view">
            <IconButton ref={expandRef} aria-label="Expand live view" onClick={() => setExpanded(true)} sx={touchTarget}>
              <Fullscreen />
            </IconButton>
          </Tooltip>
        </Stack>
      )}
    </Stack>
  );

  const content = (
    <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, height: expanded ? "100%" : "auto" }}>
      <Box ref={toolbarRef} sx={{ flexShrink: 0 }}>
        {/* Only the expanded dialog has a header band: its label names the dialog and holds Close. */}
        {expanded && (
          <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}
            sx={{ minHeight: layout.header, px: 2, bgcolor: "surface.head", borderBottom: 1, borderColor: "surface.headLine" }}>
            <PanelLabel component="h2" id="camera-inspection-title">Live camera inspection</PanelLabel>
            <Tooltip title="Close expanded view">
              <IconButton aria-label="Close expanded view" onClick={closeExpanded} size="small" sx={touchTarget}>
                <Close />
              </IconButton>
            </Tooltip>
          </Stack>
        )}
        {((summary && (expanded || inlineSummary)) || error || !compact) && <Box sx={{ px: 2, py: 1.5 }}>
          {summary && (expanded || inlineSummary) && <Typography variant="body2" aria-live="polite" sx={{ mb: compact && !error ? 0 : 1 }}>
            {summary}
          </Typography>}
          {error && <Alert severity="warning" sx={{ mb: compact ? 0 : 1 }}>{error}</Alert>}
          {!compact && controlRow}
        </Box>}
      </Box>
      <Box ref={setArea} sx={{ width: "100%", minWidth: 0, minHeight: expanded ? 120 : undefined, flex: expanded ? "1 1 0" : undefined,
        display: "flex", justifyContent: "center", alignItems: "center", bgcolor: "grey.900" }}>
        <Box data-testid="camera-stage" sx={{ width: imageWidth, height: imageHeight, maxWidth: "100%", position: "relative", overflow: "hidden", flexShrink: 0 }}>
          {hasFrame ? (
            <LiveFrame store={store} label="Live camera stream"
              onDimensions={(width, height) => {
                if (width !== dimensions.width || height !== dimensions.height) setDimensions({ width, height });
              }}
              sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", userSelect: "none", pointerEvents: "none" }} />
          ) : placeholders[connection] && (
            <Stack justifyContent="center" alignItems="center" sx={{ height: "100%", p: 2, color: "common.white", textAlign: "center" }}>
              <Typography>{placeholders[connection]}</Typography>
            </Stack>
          )}
        </Box>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", minHeight: layout.header, px: 2, flexShrink: 0, borderTop: 1, borderColor: "surface.headLine" }}>
        {/* Empty until live view starts: before Start there are no frames to wait for. */}
        {connection !== "idle" && connection !== "unavailable" && <FrameFreshness store={store} inline />}
      </Box>
      {compact && (
        <Box ref={controlsRef} sx={{ px: 2, py: 1.5, flexShrink: 0, borderTop: 1, borderColor: "surface.headLine" }}>
          {controlRow}
        </Box>
      )}
    </Box>
  );

  return (
    <>
      {!expanded && (
        <Paper variant="outlined" component="section" aria-label="Live camera"
          sx={{ overflow: "hidden", ...(narrow && { mx: `-${layout.pagePhone}px`, borderLeft: 0, borderRight: 0, borderRadius: 0 }) }}>
          {content}
        </Paper>
      )}
      <Dialog fullScreen open={expanded} onClose={closeExpanded} aria-labelledby="camera-inspection-title"
        TransitionProps={{ onExited: () => expandRef.current?.focus() }}
        PaperProps={{ sx: { height: "100dvh", m: 0, pt: "env(safe-area-inset-top)", pb: "env(safe-area-inset-bottom)",
          pl: "env(safe-area-inset-left)", pr: "env(safe-area-inset-right)" } }}>
        {expanded && content}
      </Dialog>
    </>
  );
}
