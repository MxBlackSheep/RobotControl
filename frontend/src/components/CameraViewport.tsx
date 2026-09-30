import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  Alert,
  Box,
  Dialog,
  IconButton,
  Paper,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  Add,
  Remove,
  RestartAlt,
  Fullscreen,
  Close,
  ArrowBack,
  ArrowForward,
  ArrowUpward,
  ArrowDownward,
} from "@mui/icons-material";
import LiveFrame, { FrameFreshness, type FrameStore } from "./LiveFrame";

interface CameraViewportProps {
  store: FrameStore;
  hasFrame: boolean;
  connection: string;
  summary: string;
  sourceRevision: number;
  controls: React.ReactNode;
  error?: string | null;
}
type Point = { x: number; y: number };
const touchTarget = { minWidth: 44, minHeight: 44 };

/** Viewing transforms never change the source camera, recording or stream session. */
export default function CameraViewport({
  store,
  hasFrame,
  connection,
  summary,
  sourceRevision,
  controls,
  error,
}: CameraViewportProps) {
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState<"fit" | "fill">("fit");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [dimensions, setDimensions] = useState({ width: 640, height: 480 });
  const [available, setAvailable] = useState({ width: 640, height: 480 });
  const areaRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<{
    pan: Point;
    zoom: number;
    center: Point;
    distance: number;
  } | null>(null);

  const reset = useCallback(() => {
    setMode("fit");
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);
  useEffect(() => {
    if (!hasFrame) reset();
  }, [hasFrame, reset]);
  useEffect(reset, [sourceRevision, reset]);
  useLayoutEffect(() => {
    // A source reset can disable/remove the focused zoom or pan button. Keep
    // Escape inside this dialog before MUI's periodic focus trap catches up.
    const active = document.activeElement;
    if (
      expanded &&
      (active === document.body ||
        (active instanceof HTMLElement &&
          toolbarRef.current?.contains(active) &&
          active.matches(":disabled")))
    ) {
      stageRef.current?.focus({ preventScroll: true });
    }
  });
  useLayoutEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    const measure = () => {
      const bounds = area.getBoundingClientRect();
      const viewportHeight =
        window.visualViewport?.height ?? window.innerHeight;
      const main = area.closest("main");
      const bottomPadding = main
        ? parseFloat(getComputedStyle(main).paddingBottom) || 0
        : 0;
      // A minimum lets short/zoomed windows scroll without making the image vanish.
      const height = expanded
        ? bounds.height
        : Math.max(
            180,
            viewportHeight - (bounds.top + window.scrollY) - bottomPadding - 40,
          );
      setAvailable((previous) =>
        previous.width === bounds.width && previous.height === height
          ? previous
          : { width: Math.max(1, bounds.width), height: Math.max(1, height) },
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(area);
    if (toolbarRef.current) observer.observe(toolbarRef.current);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, [expanded]);

  const fitScale = Math.min(
    available.width / dimensions.width,
    available.height / dimensions.height,
  );
  const stageWidth =
    expanded || mode === "fill" ? available.width : dimensions.width * fitScale;
  const stageHeight = expanded
    ? available.height
    : dimensions.height * fitScale;
  const scale =
    (mode === "fit"
      ? Math.min(stageWidth / dimensions.width, stageHeight / dimensions.height)
      : Math.max(
          stageWidth / dimensions.width,
          stageHeight / dimensions.height,
        )) * zoom;
  const imageWidth = dimensions.width * scale;
  const imageHeight = dimensions.height * scale;
  const maxPanX = Math.max(0, (imageWidth - stageWidth) / 2);
  const maxPanY = Math.max(0, (imageHeight - stageHeight) / 2);
  const clampPan = (point: Point): Point => ({
    x: Math.max(-maxPanX, Math.min(maxPanX, point.x)),
    y: Math.max(-maxPanY, Math.min(maxPanY, point.y)),
  });
  const visiblePan = clampPan(pan);
  const changeZoom = (next: number) => {
    setZoom(Math.max(1, Math.min(4, next)));
    setPan({ x: 0, y: 0 });
  };
  const move = (x: number, y: number) =>
    setPan((previous) => clampPan({ x: previous.x + x, y: previous.y + y }));
  const closeExpanded = () => setExpanded(false);

  const beginGesture = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!hasFrame || (!expanded && zoom === 1 && mode === "fit")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    const positions = [...pointers.current.values()];
    const center =
      positions.length > 1
        ? {
            x: (positions[0].x + positions[1].x) / 2,
            y: (positions[0].y + positions[1].y) / 2,
          }
        : positions[0];
    gesture.current = {
      pan: visiblePan,
      zoom,
      center,
      distance:
        positions.length > 1
          ? Math.hypot(
              positions[1].x - positions[0].x,
              positions[1].y - positions[0].y,
            )
          : 0,
    };
  };
  const moveGesture = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId) || !gesture.current) return;
    pointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    const positions = [...pointers.current.values()];
    if (positions.length > 1 && gesture.current.distance > 0) {
      const distance = Math.hypot(
        positions[1].x - positions[0].x,
        positions[1].y - positions[0].y,
      );
      setZoom(
        Math.max(
          1,
          Math.min(
            4,
            (gesture.current.zoom * distance) / gesture.current.distance,
          ),
        ),
      );
    } else {
      setPan(
        clampPan({
          x: gesture.current.pan.x + event.clientX - gesture.current.center.x,
          y: gesture.current.pan.y + event.clientY - gesture.current.center.y,
        }),
      );
    }
  };
  const endGesture = (event: React.PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
    const remaining = [...pointers.current.values()];
    gesture.current =
      remaining.length === 1
        ? { pan: visiblePan, zoom, center: remaining[0], distance: 0 }
        : null;
  };

  const content = (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        height: expanded ? "100%" : "auto",
        overflow: expanded ? "auto" : "visible",
      }}
    >
      <Box ref={toolbarRef} sx={{ p: { xs: 1, sm: 1.5 }, flexShrink: 0 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          gap={1}
        >
          <Typography
            component={expanded ? "h2" : "h3"}
            variant="h6"
            id={expanded ? "camera-inspection-title" : undefined}
          >
            Live camera inspection
          </Typography>
          {expanded ? (
            <Tooltip title="Close expanded view">
              <IconButton
                aria-label="Close expanded view"
                onClick={closeExpanded}
                sx={touchTarget}
              >
                <Close />
              </IconButton>
            </Tooltip>
          ) : (
            <Tooltip title="Expand live view">
              <IconButton
                ref={expandRef}
                aria-label="Expand live view"
                onClick={() => setExpanded(true)}
                sx={touchTarget}
              >
                <Fullscreen />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
        <Typography variant="body2" aria-live="polite" sx={{ mb: 1 }}>
          {summary}
        </Typography>
        {error && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}
        <Stack
          direction="row"
          gap={1}
          flexWrap="wrap"
          alignItems="center"
          justifyContent="space-between"
        >
          <Stack
            direction="row"
            gap={1}
            flexWrap="wrap"
            alignItems="center"
            sx={{ "& button": touchTarget }}
          >
            {controls}
          </Stack>
          <Stack
            data-testid="camera-toolbar"
            direction="row"
            gap={0.5}
            flexWrap="wrap"
            alignItems="center"
          >
            <ToggleButtonGroup
              exclusive
              value={mode}
              onChange={(_, value) => {
                if (value) {
                  setMode(value);
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }
              }}
              aria-label="Image sizing"
            >
              <ToggleButton
                value="fit"
                aria-label="Fit entire frame"
                sx={touchTarget}
              >
                Fit
              </ToggleButton>
              <ToggleButton
                value="fill"
                aria-label="Fill area"
                sx={touchTarget}
              >
                Fill
              </ToggleButton>
            </ToggleButtonGroup>
            <Tooltip title="Zoom out">
              <span>
                <IconButton
                  aria-label="Zoom out"
                  disabled={!hasFrame || zoom <= 1}
                  onClick={() => changeZoom(zoom - 0.25)}
                  sx={touchTarget}
                >
                  <Remove />
                </IconButton>
              </span>
            </Tooltip>
            <Typography
              variant="body2"
              sx={{ minWidth: 32, textAlign: "center" }}
            >
              {Number(zoom.toFixed(2))}×
            </Typography>
            <Tooltip title="Zoom in">
              <span>
                <IconButton
                  aria-label="Zoom in"
                  disabled={!hasFrame || zoom >= 4}
                  onClick={() => changeZoom(zoom + 0.25)}
                  sx={touchTarget}
                >
                  <Add />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Reset view">
              <IconButton
                aria-label="Reset view"
                onClick={reset}
                sx={touchTarget}
              >
                <RestartAlt />
              </IconButton>
            </Tooltip>
            {(zoom > 1 || mode === "fill") && (
              <>
                <Tooltip title="Pan left">
                  <IconButton
                    aria-label="Pan left"
                    disabled={!maxPanX}
                    onClick={() => move(60, 0)}
                    sx={touchTarget}
                  >
                    <ArrowBack />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Pan right">
                  <IconButton
                    aria-label="Pan right"
                    disabled={!maxPanX}
                    onClick={() => move(-60, 0)}
                    sx={touchTarget}
                  >
                    <ArrowForward />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Pan up">
                  <IconButton
                    aria-label="Pan up"
                    disabled={!maxPanY}
                    onClick={() => move(0, 60)}
                    sx={touchTarget}
                  >
                    <ArrowUpward />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Pan down">
                  <IconButton
                    aria-label="Pan down"
                    disabled={!maxPanY}
                    onClick={() => move(0, -60)}
                    sx={touchTarget}
                  >
                    <ArrowDownward />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </Stack>
        </Stack>
        {(mode === "fill" || zoom > 1) && (
          <Typography role="status" color="warning.dark" variant="body2">
            Cropped view
          </Typography>
        )}
      </Box>
      <Box
        ref={areaRef}
        sx={{
          width: "100%",
          minHeight: expanded ? 120 : undefined,
          minWidth: 0,
          flex: expanded ? "1 1 0" : undefined,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          bgcolor: "grey.900",
        }}
      >
        <Box
          ref={stageRef}
          data-testid="camera-stage"
          role="region"
          aria-label="Camera image. Use plus and minus to zoom, arrow keys to pan, and zero to reset."
          tabIndex={0}
          onKeyDown={(event) => {
            if (!hasFrame || event.ctrlKey || event.metaKey || event.altKey)
              return;
            const actions: Record<string, () => void> = {
              "+": () => changeZoom(zoom + 0.25),
              "=": () => changeZoom(zoom + 0.25),
              "-": () => changeZoom(zoom - 0.25),
              "0": reset,
              ArrowLeft: () => move(60, 0),
              ArrowRight: () => move(-60, 0),
              ArrowUp: () => move(0, 60),
              ArrowDown: () => move(0, -60),
            };
            if (actions[event.key]) {
              event.preventDefault();
              event.stopPropagation();
              actions[event.key]();
            }
          }}
          onPointerDown={beginGesture}
          onPointerMove={moveGesture}
          onPointerUp={endGesture}
          onPointerCancel={endGesture}
          onLostPointerCapture={endGesture}
          sx={{
            width: stageWidth,
            height: stageHeight,
            maxWidth: "100%",
            position: "relative",
            overflow: "hidden",
            bgcolor: "grey.900",
            flexShrink: 0,
            touchAction:
              expanded || zoom > 1 || mode === "fill"
                ? "none"
                : "pan-y pinch-zoom",
            cursor: zoom > 1 || mode === "fill" ? "grab" : "default",
            outlineOffset: -3,
            "&:focus-visible": {
              outline: "3px solid",
              outlineColor: "primary.main",
            },
          }}
        >
          {hasFrame ? (
            <LiveFrame
              store={store}
              alt="Live camera stream"
              draggable={false}
              onLoad={(event: React.SyntheticEvent<HTMLImageElement>) => {
                const { naturalWidth, naturalHeight } = event.currentTarget;
                if (
                  naturalWidth &&
                  naturalHeight &&
                  (naturalWidth !== dimensions.width ||
                    naturalHeight !== dimensions.height)
                ) {
                  setDimensions({ width: naturalWidth, height: naturalHeight });
                  reset();
                }
              }}
              sx={{
                position: "absolute",
                width: imageWidth,
                height: imageHeight,
                maxWidth: "none",
                left: "50%",
                top: "50%",
                transform: `translate(calc(-50% + ${visiblePan.x}px), calc(-50% + ${visiblePan.y}px))`,
                userSelect: "none",
                pointerEvents: "none",
              }}
            />
          ) : (
            <Stack
              justifyContent="center"
              alignItems="center"
              sx={{
                height: "100%",
                p: 2,
                color: "common.white",
                textAlign: "center",
              }}
            >
              <Typography>
                {connection === "connected"
                  ? "Waiting for camera frames…"
                  : connection === "disconnected"
                    ? "Live view disconnected"
                    : connection === "connecting"
                      ? "Connecting to live view…"
                      : "Start your live view to inspect the camera"}
              </Typography>
            </Stack>
          )}
        </Box>
      </Box>
      <Box sx={{ px: 1.5, py: 0.5, flexShrink: 0 }}>
        <FrameFreshness store={store} inline />
      </Box>
    </Box>
  );

  return (
    <>
      {!expanded && (
        <Paper variant="outlined" sx={{ overflow: "hidden" }}>
          {content}
        </Paper>
      )}
      <Dialog
        fullScreen
        open={expanded}
        onClose={closeExpanded}
        aria-labelledby="camera-inspection-title"
        TransitionProps={{ onExited: () => expandRef.current?.focus() }}
        PaperProps={{
          sx: {
            height: "100dvh",
            m: 0,
            pt: "env(safe-area-inset-top)",
            pb: "env(safe-area-inset-bottom)",
            pl: "env(safe-area-inset-left)",
            pr: "env(safe-area-inset-right)",
          },
        }}
      >
        {expanded && content}
      </Dialog>
    </>
  );
}
