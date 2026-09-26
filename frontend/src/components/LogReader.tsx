import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  LinearProgress,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import {
  logFileApi,
  LogReaderSection,
  LogReaderStatus,
} from "../services/logFileApi";

export type LogSelection = {
  name: string;
  relative: string;
  archive: string;
  entry: string;
};
const errorMessage = (error: any) =>
  error.response?.data?.error?.message || error.message || "Unable to read log";
export default function LogReader({
  sourceId,
  selected,
  active,
  visibleInWorkspace = true,
}: {
  sourceId: string;
  selected: LogSelection;
  active: boolean;
  visibleInWorkspace?: boolean;
}) {
  const [section, setSection] = useState<LogReaderSection | null>(null),
    [status, setStatus] = useState<LogReaderStatus | null>(null);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0),
    [cancelled, setCancelled] = useState(false);
  const [showLive, setShowLive] = useState(false);
  const [follow, setFollow] = useState(false),
    [liveText, setLiveText] = useState(""),
    [livePath, setLivePath] = useState(""),
    [updated, setUpdated] = useState("");
  const [visible, setVisible] = useState(
    document.visibilityState === "visible",
  );
  const [find, setFind] = useState(""),
    [match, setMatch] = useState(0),
    [wrap, setWrap] = useState(true),
    [expanded, setExpanded] = useState(false),
    [details, setDetails] = useState(false),
    [copied, setCopied] = useState("");
  const [menu, setMenu] = useState<HTMLElement | null>(null),
    [jump, setJump] = useState(false);
  const readerId = useRef(""),
    requestVersion = useRef(0),
    initialCursor = useRef("last"),
    scroll = useRef(0),
    atBottom = useRef(true);
  const pane = useRef<HTMLDivElement>(null),
    expandButton = useRef<HTMLButtonElement>(null),
    sectionScroll = useRef(new Map<string, number>());
  const canFollow =
    !selected.archive &&
    !/\.(gz|zip)$/i.test(selected.relative) &&
    !selected.relative.split("/").includes("history");
  useEffect(() => {
    const listener = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", listener);
    return () => document.removeEventListener("visibilitychange", listener);
  }, []);
  useEffect(() => {
    if (!visibleInWorkspace && follow) {
      setFollow(false);
      setCancelled(true);
    }
  }, [visibleInWorkspace, follow]);
  useEffect(() => {
    if (!active && (follow || loading)) {
      setFollow(false);
      setCancelled(true);
      setLoading(false);
    }
  }, [active, follow, loading]);
  useEffect(() => {
    if (follow || cancelled) return;
    let valid = true,
      id = "";
    const abort = new AbortController();
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    setStatus(null);
    const open = async () => {
      try {
        let info = await logFileApi.openReader(
          sourceId,
          selected.archive || selected.relative,
          selected.entry,
        );
        id = info.id;
        if (!valid) {
          void logFileApi.closeReader(id).catch(() => {});
          return;
        }
        readerId.current = id;
        setStatus(info);
        while (info.state === "preparing" && valid) {
          await new Promise((resolve) => window.setTimeout(resolve, 500));
          if (!valid) return;
          info = await logFileApi.readerStatus(id, abort.signal);
          if (valid) setStatus(info);
        }
        if (!valid) return;
        if (info.state === "error")
          throw new Error(info.error || "Unable to prepare log");
        let result = await logFileApi.readerSection(
          id,
          initialCursor.current === "first" ? "first" : "last",
          abort.signal,
        );
        if (initialCursor.current === "older" && result.previous_cursor)
          result = await logFileApi.readerSection(
            id,
            result.previous_cursor,
            abort.signal,
          );
        if (valid && version === requestVersion.current) {
          setSection(result);
          setStatus(result);
          setShowLive(false);
          setMatch(0);
          setUpdated(new Date().toLocaleTimeString());
          scroll.current = initialCursor.current === "last" ? Number.MAX_SAFE_INTEGER : 0;
        }
      } catch (e) {
        if (valid && !abort.signal.aborted) setError(errorMessage(e));
      } finally {
        if (valid) setLoading(false);
      }
    };
    void open();
    return () => {
      valid = false;
      abort.abort();
      requestVersion.current++;
      if (readerId.current === id) readerId.current = "";
      if (id) void logFileApi.closeReader(id).catch(() => {});
    };
  }, [
    sourceId,
    selected.relative,
    selected.archive,
    selected.entry,
    revision,
    follow,
    cancelled,
  ]);
  useEffect(() => {
    if (
      !active ||
      !visible ||
      !visibleInWorkspace ||
      follow ||
      cancelled ||
      !status?.id ||
      status.state !== "ready" ||
      status.id !== readerId.current
    )
      return;
    let valid = true;
    const abort = new AbortController();
    let timer: number;
    const renew = async () => {
      try {
        const info = await logFileApi.readerStatus(status.id, abort.signal);
        if (valid) setStatus(info);
      } catch (e) {
        if (valid && !abort.signal.aborted) {
          setError(errorMessage(e));
          if ([403, 404].includes((e as any).response?.status))
            setCancelled(true);
        }
      } finally {
        if (valid) timer = window.setTimeout(renew, 60000);
      }
    };
    timer = window.setTimeout(renew, 60000);
    return () => {
      valid = false;
      abort.abort();
      clearTimeout(timer);
    };
  }, [
    active,
    visible,
    visibleInWorkspace,
    follow,
    cancelled,
    status?.id,
    status?.state,
  ]);
  useEffect(() => {
    if (!follow || !canFollow || !active || !visible || !visibleInWorkspace)
      return;
    let valid = true,
      timer: number;
    const abort = new AbortController();
    setError("");
    const poll = async () => {
      setLoading(true);
      try {
        const result = await logFileApi.preview(
          sourceId,
          selected.relative,
          "tail",
          1024 * 1024,
          abort.signal,
        );
        if (!valid) return;
        if (result.is_binary)
          throw new Error("This file contains binary data.");
        setLiveText(result.content || "");
        setShowLive(true);
        setLivePath(result.file_path);
        setUpdated(new Date().toLocaleTimeString());
        if (atBottom.current)
          requestAnimationFrame(() => {
            if (valid && pane.current)
              pane.current.scrollTop = pane.current.scrollHeight;
          });
        else setJump(true);
      } catch (e) {
        if (valid && !abort.signal.aborted) {
          setError(errorMessage(e));
          setFollow(false);
          setCancelled(true);
        }
      } finally {
        if (valid) {
          setLoading(false);
          timer = window.setTimeout(poll, 5000);
        }
      }
    };
    void poll();
    return () => {
      valid = false;
      abort.abort();
      clearTimeout(timer);
    };
  }, [
    follow,
    canFollow,
    active,
    visible,
    visibleInWorkspace,
    sourceId,
    selected.relative,
  ]);
  useEffect(() => {
    if (pane.current) pane.current.scrollTop = scroll.current;
  }, [expanded, section?.cursor]);
  const text = showLive ? liveText : section?.content || "";
  const matches = useMemo(() => {
    const result: number[] = [];
    if (find) {
      let pos = 0;
      const lower = text.toLowerCase(),
        term = find.toLowerCase();
      while (result.length < 500) {
        const i = lower.indexOf(term, pos);
        if (i < 0) break;
        result.push(i);
        pos = i + term.length;
      }
    }
    return result;
  }, [text, find]);
  const highlighted = useMemo(() => {
    if (!matches.length) return text;
    const nodes: React.ReactNode[] = [];
    let last = 0;
    matches.forEach((offset, index) => {
      nodes.push(
        text.slice(last, offset),
        <mark
          key={offset}
          data-match={index}
          style={{
            background: index === match ? "#ffb74d" : "#fff59d",
            color: "#111",
          }}
        >
          {text.slice(offset, offset + find.length)}
        </mark>,
      );
      last = offset + find.length;
    });
    nodes.push(text.slice(last));
    return nodes;
  }, [text, matches, match, find]);
  const goMatch = (direction: number) => {
    const next = (match + direction + matches.length) % matches.length;
    setMatch(next);
    pane.current
      ?.querySelector(`[data-match="${next}"]`)
      ?.scrollIntoView({ block: "center" });
  };
  const navigate = async (cursor: string) => {
    if ((cancelled || !readerId.current) && cursor.includes(":")) {
      setError(
        "This captured reader has ended. Reopen the file to read a new version.",
      );
      return;
    }
    initialCursor.current = cursor;
    if (follow || !readerId.current || cancelled) {
      setCancelled(false);
      setFollow(false);
      setRevision((v) => v + 1);
      return;
    }
    if (section)
      sectionScroll.current.set(section.cursor, pane.current?.scrollTop || 0);
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    try {
      const result = await logFileApi.readerSection(readerId.current, cursor);
      if (version === requestVersion.current) {
        scroll.current = cursor === "last" ? Number.MAX_SAFE_INTEGER : sectionScroll.current.get(result.cursor) || 0;
        setSection(result);
        setStatus(result);
        setShowLive(false);
        setMatch(0);
      }
    } catch (e) {
      if (version === requestVersion.current) setError(errorMessage(e));
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };
  const reopen = () => {
    initialCursor.current = "last";
    setCancelled(false);
    setFollow(false);
    setRevision((v) => v + 1);
  };
  const path = showLive ? livePath : status?.file_path || section?.file_path || "";
  const attachPane = useCallback((element: HTMLDivElement | null) => {
    pane.current = element;
    if (element) {
      const saved = scroll.current;
      requestAnimationFrame(() => {
        if (pane.current === element) element.scrollTop = saved;
      });
    }
  }, []);
  const body = (
    <>
      <Stack gap={1} sx={{ p: 1.5, flexShrink: 0 }}>
        <Typography variant="h6" sx={{ overflowWrap: "anywhere" }}>
          {selected.name}
        </Typography>
        <Stack direction="row" gap={0.5} flexWrap="wrap" alignItems="center">
          <Button onClick={reopen} disabled={loading}>
            Refresh
          </Button>
          <Button
            ref={expanded ? undefined : expandButton}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Close expanded reader" : "Expand"}
          </Button>
          <Button
            aria-haspopup="menu"
            onClick={(e) => setMenu(e.currentTarget)}
          >
            More
          </Button>
          {canFollow && (
            <FormControlLabel
              label="Follow latest"
              control={
                <Switch
                  checked={follow}
                  onChange={(_, value) => {
                    setCancelled(false);
                    setFollow(value);
                  }}
                />
              }
            />
          )}
        </Stack>
        <Stack direction="row" gap={0.5} flexWrap="wrap" alignItems="center">
          <TextField
            size="small"
            label="Find in this section"
            value={find}
            onChange={(e) => {
              setFind(e.target.value);
              setMatch(0);
            }}
            sx={{ flex: "1 1 180px", minWidth: 0 }}
          />
          <Button disabled={!matches.length} onClick={() => goMatch(-1)}>
            Previous match
          </Button>
          <Button disabled={!matches.length} onClick={() => goMatch(1)}>
            Next match
          </Button>
        </Stack>
        <Typography variant="caption" role="status">
          {find
            ? `${matches.length}${matches.length === 500 ? "+" : ""} matches in this section. `
            : ""}
          {follow
            ? "Following latest · bounded 1 MiB preview"
            : status?.compressed
              ? "Archive · captured reading copy"
              : "Captured reading copy"}
          {updated && ` · Updated ${updated}`}
        </Typography>
      </Stack>
      {loading && (
        <>
          <LinearProgress />
          <Stack direction="row" alignItems="center" sx={{ px: 1.5 }}>
            <Typography role="status" sx={{ flex: 1 }}>
              Preparing section…{" "}
              {status?.state === "preparing"
                ? `${status.bytes_scanned.toLocaleString()} bytes read`
                : ""}
            </Typography>
            <Button
              onClick={() => {
                setCancelled(true);
                setFollow(false);
                setLoading(false);
              }}
            >
              Cancel
            </Button>
          </Stack>
        </>
      )}
      {cancelled && (
        <Alert
          severity="info"
          action={<Button onClick={reopen}>Reopen</Button>}
        >
          Reading stopped. Displayed text is retained.
        </Alert>
      )}
      {error && (
        <Alert
          severity="error"
          action={<Button onClick={reopen}>Reopen</Button>}
        >
          {error}
          {text && " Previous text is retained."}
        </Alert>
      )}
      {status?.source_changed && (
        <Alert
          severity="info"
          action={<Button onClick={reopen}>Reopen latest</Button>}
        >
          The source has changed. This captured version remains readable.
        </Alert>
      )}
      {!!status?.replacement_characters && (
        <Alert severity="warning">
          Some invalid characters were replaced while decoding this file (
          {status.encoding}).
        </Alert>
      )}
      {section?.line_continues && !showLive && (
        <Typography variant="caption" sx={{ px: 1.5 }}>
          Line continues from the previous section.
        </Typography>
      )}
      {jump && follow && (
        <Button
          onClick={() => {
            if (pane.current)
              pane.current.scrollTop = pane.current.scrollHeight;
            atBottom.current = true;
            setJump(false);
          }}
        >
          Jump to latest
        </Button>
      )}
      <Box
        ref={attachPane}
        tabIndex={0}
        aria-label="Log content"
        onScroll={() => {
          if (pane.current) {
            scroll.current = pane.current.scrollTop;
            atBottom.current =
              pane.current.scrollHeight -
                pane.current.scrollTop -
                pane.current.clientHeight <
              40;
          }
        }}
        sx={{
          flex: 1,
          minHeight: 160,
          overflow: "auto",
          p: 1.5,
          bgcolor: "#14202b",
          color: "#edf4fa",
        }}
      >
        <Box
          component="pre"
          sx={{
            m: 0,
            fontSize: 14,
            lineHeight: 1.55,
            fontFamily: "Consolas, monospace",
            whiteSpace: wrap ? "pre-wrap" : "pre",
            overflowWrap: wrap ? "anywhere" : "normal",
          }}
        >
          {highlighted ||
            (loading
              ? "Preparing log…"
              : section
                ? "This file is empty."
                : "Choose Reopen to read this file.")}
        </Box>
      </Box>
      <Stack
        direction="row"
        gap={0.5}
        alignItems="center"
        flexWrap="wrap"
        sx={{ p: 1, flexShrink: 0 }}
      >
        <Button
          disabled={loading || (!showLive && section?.section_number === 1)}
          onClick={() => void navigate("first")}
        >
          Beginning
        </Button>
        <Button
          disabled={loading || (!showLive && !section?.previous_cursor)}
          onClick={() =>
            void navigate(showLive ? "older" : section!.previous_cursor!)
          }
        >
          Older section
        </Button>
        <Button
          disabled={loading || follow || !section?.next_cursor}
          onClick={() => void navigate(section!.next_cursor!)}
        >
          Newer section
        </Button>
        <Button disabled={loading} onClick={() => void navigate("last")}>
          Latest
        </Button>
        {!showLive && section && (
          <Typography variant="caption">
            Section {section.section_number} of {section.section_count}
          </Typography>
        )}
      </Stack>
    </>
  );
  return (
    <>
      {!expanded && (
        <Paper
          variant="outlined"
          sx={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            "& button": { minHeight: 44 },
          }}
        >
          {body}
        </Paper>
      )}
      <Dialog
        fullScreen
        open={expanded}
        onClose={() => setExpanded(false)}
        aria-label="Expanded log reader"
        PaperProps={{
          sx: {
            height: "100dvh",
            overflow: "auto",
            "& button": { minHeight: 44 },
          },
        }}
        TransitionProps={{ onExited: () => expandButton.current?.focus() }}
      >
        {expanded && body}
      </Dialog>
      <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
        <MenuItem
          onClick={() => {
            setWrap((v) => !v);
            setMenu(null);
          }}
        >
          {wrap ? "Turn wrapping off" : "Wrap lines"}
        </MenuItem>
        <MenuItem
          onClick={() => {
            setDetails(true);
            setMenu(null);
          }}
        >
          Details
        </MenuItem>
      </Menu>
      <Dialog
        open={details}
        onClose={() => setDetails(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Log details</DialogTitle>
        <DialogContent dividers>
          <Typography sx={{ overflowWrap: "anywhere" }}>{path}</Typography>
          {selected.entry && (
            <Typography sx={{ overflowWrap: "anywhere" }}>
              ZIP member: {selected.entry}
            </Typography>
          )}
          <Button
            onClick={() => {
              if (!navigator.clipboard) {
                setCopied("Select and copy the path above.");
                return;
              }
              navigator.clipboard
                .writeText(path)
                .then(() => setCopied("Path copied"))
                .catch(() => setCopied("Select and copy the path above."));
            }}
          >
            Copy path
          </Button>
          <Typography role="status">{copied}</Typography>
          <Typography>Encoding: {status?.encoding || "Preparing"}</Typography>
          <Typography>
            Captured:{" "}
            {status ? new Date(status.captured_at * 1000).toLocaleString() : ""}
          </Typography>
          <Typography>
            Decoded bytes: {status?.bytes_prepared.toLocaleString()}
          </Typography>
          {section && (
            <Typography>
              Section bytes: {section.start_byte.toLocaleString()}–
              {section.end_byte.toLocaleString()}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetails(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
