import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Box,
  Button,
  Dialog,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";

interface InspectionTextViewerProps {
  text: string;
  label: string;
  kind?: string;
  preferenceKey?: string;
}

/** A read-only text surface; expanding changes the surface, never the reader state. */
export default function InspectionTextViewer({
  text,
  label,
  kind = "SQL",
  preferenceKey = "sql",
}: InspectionTextViewerProps) {
  const [find, setFind] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const [wrap, setWrap] = useState(() => {
    try {
      return (
        localStorage.getItem(`inspection.wrap.${preferenceKey}`) !== "false"
      );
    } catch {
      return true;
    }
  });
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState("");
  const reader = useRef<HTMLDivElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const scroll = useRef({ top: 0, left: 0 });
  const searchInput = useRef<HTMLInputElement>(null);

  const matches = useMemo(() => {
    if (!find) return [];
    const lower = text.toLocaleLowerCase(),
      term = find.toLocaleLowerCase(),
      result: number[] = [];
    for (let start = 0; result.length < 1000; ) {
      const offset = lower.indexOf(term, start);
      if (offset === -1) break;
      result.push(offset);
      start = offset + term.length;
    }
    return result;
  }, [text, find]);
  useEffect(() => {
    setMatchIndex(0);
  }, [text, find]);
  useEffect(() => {
    try {
      localStorage.setItem(`inspection.wrap.${preferenceKey}`, String(wrap));
    } catch {
      /* Reading still works without browser storage. */
    }
  }, [wrap, preferenceKey]);
  const attachReader = useCallback((element: HTMLDivElement | null) => {
    reader.current = element;
    if (!element) return;
    const position = { ...scroll.current };
    requestAnimationFrame(() => {
      if (reader.current === element)
        element.scrollTo(position.left, position.top);
    });
  }, []);
  useLayoutEffect(() => {
    if (find)
      reader.current
        ?.querySelector<HTMLElement>(`[data-match="${matchIndex}"]`)
        ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [find, matchIndex]);
  const moveMatch = (direction: number) => {
    if (!matches.length) return;
    const next = (matchIndex + direction + matches.length) % matches.length;
    setMatchIndex(next);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(`${kind} copied`);
    } catch {
      setCopied("Copy unavailable. Select and copy the text below.");
    }
  };
  const lines = useMemo(() => {
    let offset = 0;
    return text.split("\n").map((line, index) => {
      const start = offset;
      offset += line.length + 1;
      return { text: line, number: index + 1, start };
    });
  }, [text]);
  const body = (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        minWidth: 0,
        flex: 1,
        overflow: "auto",
        "& .MuiButton-root, & .MuiIconButton-root": {
          minHeight: 44,
          minWidth: 44,
        },
        "& .MuiInputBase-root": { minHeight: 44 },
      }}
    >
      <Stack
        direction="row"
        flexWrap="wrap"
        alignItems="center"
        gap={0.5}
        sx={{ p: 1, flexShrink: 0 }}
      >
        <TextField
          inputRef={searchInput}
          size="small"
          label={`Find in ${kind}`}
          value={find}
          onChange={(event) => {
            setFind(event.target.value);
            setMatchIndex(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              moveMatch(event.shiftKey ? -1 : 1);
            }
          }}
          sx={{ flex: "1 1 170px", minWidth: 120 }}
        />
        <Button
          aria-label="Previous match"
          disabled={!matches.length}
          onClick={() => moveMatch(-1)}
        >
          Previous
        </Button>
        <Button
          aria-label="Next match"
          disabled={!matches.length}
          onClick={() => moveMatch(1)}
        >
          Next
        </Button>
        <Button onClick={copy}>Copy {kind}</Button>
        <Button
          ref={expanded ? undefined : expandButton}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? `Close expanded ${kind}` : `Expand ${kind}`}
        </Button>
        <FormControlLabel
          sx={{ minHeight: 44, mr: 0, ml: 0 }}
          control={
            <Switch
              size="small"
              checked={wrap}
              onChange={(_, value) => setWrap(value)}
            />
          }
          label="Wrap lines"
        />
      </Stack>
      <Stack
        direction="row"
        gap={1}
        flexWrap="wrap"
        sx={{ px: 1.5, pb: 0.5, flexShrink: 0 }}
      >
        <Typography variant="caption" color="text.secondary" aria-live="polite">
          {find
            ? matches.length
              ? `${Math.min(matchIndex + 1, matches.length)} of ${matches.length}${matches.length === 1000 ? "+" : ""} matches`
              : `No matches in this ${kind} definition`
            : `${lines.length} lines · Read only`}
        </Typography>
        <Typography variant="caption" role="status">
          {copied}
        </Typography>
      </Stack>
      <Box
        ref={attachReader}
        role="region"
        aria-label={label}
        tabIndex={0}
        onScroll={() => {
          if (reader.current)
            scroll.current = {
              top: reader.current.scrollTop,
              left: reader.current.scrollLeft,
            };
        }}
        onKeyDown={(event) => {
          if (
            (event.ctrlKey || event.metaKey) &&
            event.key.toLowerCase() === "f"
          ) {
            event.preventDefault();
            searchInput.current?.focus();
          }
        }}
        sx={{
          flex: "1 0 120px",
          minHeight: 120,
          overflow: "auto",
          borderTop: 1,
          borderColor: "divider",
          bgcolor: "grey.50",
          p: 1,
          font: "14px/1.6 Consolas, monospace",
        }}
      >
        {lines.map((line) => {
          const parts: React.ReactNode[] = [];
          let position = 0;
          matches.forEach((offset, index) => {
            if (offset < line.start || offset >= line.start + line.text.length)
              return;
            const local = offset - line.start;
            parts.push(
              line.text.slice(position, local),
              <mark
                data-match={index}
                key={offset}
                style={{
                  background: matchIndex === index ? "#ffb74d" : "#fff59d",
                  color: "#111",
                }}
              >
                {line.text.slice(local, local + find.length)}
              </mark>,
            );
            position = local + find.length;
          });
          parts.push(line.text.slice(position));
          return (
            <Box
              key={line.number}
              sx={{ display: "flex", minWidth: wrap ? 0 : "max-content" }}
            >
              <Box
                aria-hidden="true"
                sx={{
                  userSelect: "none",
                  flexShrink: 0,
                  width: `${String(lines.length).length + 2}ch`,
                  color: "text.secondary",
                  textAlign: "right",
                  pr: 1.5,
                }}
              >
                {line.number}
              </Box>
              <Box
                component="code"
                sx={{
                  font: "inherit",
                  flex: 1,
                  minWidth: 0,
                  whiteSpace: wrap ? "pre-wrap" : "pre",
                  overflowWrap: wrap ? "anywhere" : "normal",
                }}
              >
                {parts.length === 1 && !line.text ? "\u00a0" : parts}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
  return (
    <>
      {!expanded && (
        <Paper
          variant="outlined"
          sx={{
            display: "flex",
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {body}
        </Paper>
      )}
      <Dialog
        fullScreen
        open={expanded}
        onClose={() => setExpanded(false)}
        PaperProps={{
          "aria-label": `Expanded ${label}`,
          sx: {
            height: "100dvh",
            p: "env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)",
          },
        }}
        TransitionProps={{ onExited: () => expandButton.current?.focus() }}
      >
        {expanded && body}
      </Dialog>
    </>
  );
}
