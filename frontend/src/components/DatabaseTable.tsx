import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  LinearProgress,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import SearchIcon from "@mui/icons-material/Search";
import { databaseAPI } from "../services/api";
import { InspectionName, pinnedBarSx, usePhoneWorkspace } from "./InspectionWorkspace";
import { collectMatchingRows, formatExport } from "./databaseExport";
import { fontMono } from "../theme";
type Filter = { column: string; operator: string; value: string };
type Query = {
  page: number;
  limit: number;
  search: string;
  filters: Filter[];
  order: string;
  direction: "asc" | "desc";
};
const initialQuery: Query = {
  page: 0,
  limit: 25,
  search: "",
  filters: [],
  order: "",
  direction: "asc",
};
export const queryParams = (query: Query) => ({
  search: query.search || undefined,
  order_by: query.order || undefined,
  sort_direction: query.direction,
  filters: JSON.stringify(
    Object.fromEntries(
      query.filters
        .filter((f) => f.column && f.value.trim())
        .map((f) => [f.column, { operator: f.operator, value: f.value }]),
    ),
  ),
});
const errorText = (error: any) =>
  error.response?.data?.error?.details ||
  error.response?.data?.detail ||
  error.message ||
  "Unable to load table";
const displayValue = (value: any) =>
  value == null
    ? "NULL"
    : value === ""
      ? "(empty string)"
      : typeof value === "object"
        ? JSON.stringify(value, null, 2)
        : String(value);
export default function DatabaseTable(props: {
  tableName: string;
  sourceId?: string;
  onError?: (message: string) => void;
  active?: boolean;
}) {
  return <TableView key={`${props.sourceId}/${props.tableName}`} {...props} />;
}
function TableView({
  tableName,
  sourceId,
  active = true,
}: {
  tableName: string;
  sourceId?: string;
  active?: boolean;
}) {
  const [query, setQuery] = useState<Query>(initialQuery),
    [draft, setDraft] = useState(""),
    [filterDraft, setFilterDraft] = useState<Filter[]>([]);
  const [displayedQuery, setDisplayedQuery] = useState<Query>(initialQuery);
  const [pageDraft, setPageDraft] = useState("1");
  const [data, setData] = useState<{
    columns: string[];
    rows: Record<string, any>[];
    total_count: number;
  } | null>(null);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [updated, setUpdated] = useState(""),
    [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState<"filters" | "columns" | "export" | null>(
      null,
    ),
    [hidden, setHidden] = useState<string[]>([]),
    [cell, setCell] = useState<{ column: string; value: any } | null>(null);
  const [scope, setScope] = useState("page"),
    [format, setFormat] = useState<"csv" | "json">("csv"),
    [progress, setProgress] = useState<number | null>(null),
    [exportMessage, setExportMessage] = useState("");
  const [expanded, setExpanded] = useState(false),
    [more, setMore] = useState<HTMLElement | null>(null),
    [wrap, setWrap] = useState(false);
  const [record, setRecord] = useState<{
      row: Record<string, any>;
      number: number;
    } | null>(null),
    [copied, setCopied] = useState("");
  const tableScroll = useRef<HTMLDivElement>(null),
    expandButton = useRef<HTMLButtonElement>(null);
  // Phones: rows scroll with the page; headings pin in a separate strip that follows sideways scroll.
  const phone = usePhoneWorkspace();
  const flow = phone && !expanded;
  const [pageDialog, setPageDialog] = useState(false),
    [widths, setWidths] = useState<number[]>([]),
    [moreRight, setMoreRight] = useState(false);
  const headingStrip = useRef<HTMLDivElement>(null),
    sizingHead = useRef<HTMLTableSectionElement>(null),
    rowsTop = useRef<HTMLDivElement>(null);
  const scroll = useRef({ top: 0, left: 0 });
  const attachTable = useCallback((element: HTMLDivElement | null) => {
    tableScroll.current = element;
    if (!element) return;
    const position = { ...scroll.current };
    requestAnimationFrame(() => {
      if (tableScroll.current === element)
        element.scrollTo(position.left, position.top);
    });
  }, []);
  const copyValue = async (value: any) => {
    try {
      await navigator.clipboard.writeText(
        value == null
          ? "NULL"
          : typeof value === "object"
            ? JSON.stringify(value, null, 2)
            : String(value),
      );
      setCopied("Value copied");
    } catch {
      setCopied("Copy unavailable. Select and copy the value below.");
    }
  };
  const exportAbort = useRef<AbortController | null>(null);
  useEffect(() => () => exportAbort.current?.abort(), []);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    let current = true;
    setLoading(true);
    setError("");
    databaseAPI
      .getTableData(
        tableName,
        query.page + 1,
        query.limit,
        { ...queryParams(query), source_id: sourceId },
        abort.signal,
      )
      .then((response) => {
        if (!current) return;
        const payload = response.data.data;
        const lastPage = Math.max(0, Math.ceil(payload.total_count / query.limit) - 1);
        if (query.page > lastPage) {
          setQuery((previous) => ({ ...previous, page: lastPage }));
          return;
        }
        setData(payload);
        setDisplayedQuery(query);
        setPageDraft(String(query.page + 1));
        if (query !== displayedQuery) {
          scroll.current.top = 0;
          if (tableScroll.current) tableScroll.current.scrollTop = 0;
          // A phone pages from the bottom bar; show the new page from its first row.
          const top = rowsTop.current?.getBoundingClientRect().top;
          const header = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--app-header-height")) || 52;
          if (top !== undefined && top < header) window.scrollBy(0, top - header);
        }
        setUpdated(new Date().toLocaleTimeString());
      })
      .catch((error) => {
        if (current && !abort.signal.aborted)
          setError(String(errorText(error)));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      abort.abort();
    };
  }, [tableName, query, refresh, active, sourceId]);
  const apply = () =>
    setQuery((q) => ({
      ...q,
      page: 0,
      search: draft.trim(),
      filters: filterDraft.map((f) => ({ ...f })),
    }));
  const exportData = async () => {
    if (!data) return;
    const abort = new AbortController();
    exportAbort.current = abort;
    setProgress(0);
    setExportMessage("");
    try {
      const columns = data.columns.filter((c) => !hidden.includes(c));
      const rows =
        scope === "page"
          ? data.rows
          : await collectMatchingRows(
              async (page, limit) => {
                const response = await databaseAPI.getTableData(
                  tableName,
                  page,
                  limit,
                   { ...queryParams(displayedQuery), source_id: sourceId },
                  abort.signal,
                );
                return response.data.data;
              },
              abort.signal,
              setProgress,
            );
      if (abort.signal.aborted) return;
      const text = formatExport(columns, rows, format);
      const url = URL.createObjectURL(
        new Blob([text], {
          type:
            format === "csv" ? "text/csv;charset=utf-8" : "application/json",
        }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${tableName}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportMessage(`Exported ${rows.length.toLocaleString()} rows.`);
    } catch (error) {
      setExportMessage(
        abort.signal.aborted ? "Export cancelled." : String(errorText(error)),
      );
    } finally {
      setProgress(null);
      exportAbort.current = null;
    }
  };
  const columns = data?.columns.filter((c) => !hidden.includes(c)) || [];
  const pageCount = Math.max(1, Math.ceil((data?.total_count || 0) / displayedQuery.limit));
  const targetPage = Number(pageDraft);
  const validPage = Number.isInteger(targetPage) && targetPage >= 1 && targetPage <= pageCount;
  const rowNumber = (index: number) => displayedQuery.page * displayedQuery.limit + index + 1;
  const followRows = () => {
    const rows = tableScroll.current;
    if (!rows) return;
    if (headingStrip.current) headingStrip.current.scrollLeft = rows.scrollLeft;
    setMoreRight(rows.scrollLeft + rows.clientWidth < rows.scrollWidth - 1);
  };
  const measureColumns = useCallback(() => {
    const cells = sizingHead.current?.rows[0]?.cells;
    if (cells) {
      const next = Array.from(cells, (cell) => cell.getBoundingClientRect().width);
      setWidths((previous) =>
        previous.length === next.length && previous.every((width, index) => Math.abs(width - next[index]) < 0.5) ? previous : next);
    }
    followRows();
  }, []);
  const columnKey = columns.join("\n");
  useLayoutEffect(() => {
    if (!flow) return;
    measureColumns();
    const observer = new ResizeObserver(measureColumns);
    if (sizingHead.current?.parentElement) observer.observe(sizingHead.current.parentElement);
    if (tableScroll.current) observer.observe(tableScroll.current);
    return () => observer.disconnect();
  }, [flow, data, columnKey, wrap, measureColumns]);
  const sortLabel = (column: string, focusable = true) => (
    <TableSortLabel
      tabIndex={focusable ? undefined : -1}
      active={displayedQuery.order === column}
      direction={displayedQuery.order === column ? displayedQuery.direction : "asc"}
      sx={{
        minHeight: 44,
        maxWidth: 260,
        overflowWrap: "anywhere",
      }}
      onClick={() =>
        setQuery({
          ...displayedQuery,
          page: 0,
          order: column,
          direction:
            displayedQuery.order === column && displayedQuery.direction === "asc"
              ? "desc"
              : "asc",
        })
      }
    >
      {column}
    </TableSortLabel>
  );
  const rowHeading = {
    position: "sticky",
    left: 0,
    zIndex: 3,
    bgcolor: "background.paper",
  } as const;
  const bodyRows = (
    <TableBody>
      {data?.rows.map((row, index) => (
        <TableRow key={index} hover>
          <TableCell
            sx={{
              position: "sticky",
              left: 0,
              zIndex: 1,
              bgcolor: "background.paper",
            }}
          >
            <Button
              aria-label={`Inspect row ${rowNumber(index)}`}
              onClick={() => {
                setRecord({
                  row,
                  number: rowNumber(index),
                });
                setCopied("");
              }}
            >
              {rowNumber(index)}
            </Button>
          </TableCell>
          {columns.map((column) => (
            <TableCell key={column} sx={{ maxWidth: 284 }}>
              <Box
                component="button"
                onClick={() => {
                  setCell({ column, value: row[column] });
                  setCopied("");
                }}
                aria-label={`View ${column}, row ${rowNumber(index)}`}
                sx={{
                  display: "block",
                  border: 0,
                  bgcolor: "transparent",
                  color:
                    row[column] == null ? "text.secondary" : "inherit",
                  textAlign: "left",
                  font: "inherit",
                  fontFamily: fontMono,
                  fontSize: 13,
                  cursor: "pointer",
                  minHeight: 44,
                  minWidth: 80,
                  maxWidth: 260,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: wrap ? "pre-wrap" : "nowrap",
                  overflowWrap: wrap ? "anywhere" : "normal",
                }}
              >
                {displayValue(row[column])}
              </Box>
            </TableCell>
          ))}
        </TableRow>
      ))}
      {!loading && !data?.rows.length && (
        <TableRow>
          <TableCell colSpan={columns.length + 1}>
            {error
              ? "Table unavailable."
              : displayedQuery.search || displayedQuery.filters.length
                ? "No rows match the applied search and filters."
                : "This table is empty."}
          </TableCell>
        </TableRow>
      )}
    </TableBody>
  );
  const pageForm = (
    <Box component="form" onSubmit={(event) => { event.preventDefault(); if (validPage && !loading) { setQuery({ ...displayedQuery, page: targetPage - 1 }); setPageDialog(false); } }} sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap", py: 0.5 }}>
      <Typography variant="caption" sx={{ mr: 0.5 }}>Page {displayedQuery.page + 1} of {pageCount}</Typography>
      <TextField type="number" size="small" label="Page" value={pageDraft} onChange={(event) => setPageDraft(event.target.value)} inputProps={{ min: 1, max: pageCount, step: 1 }} disabled={loading || !data?.total_count} sx={{ width: 78 }} />
      <Button type="submit" aria-label="Go to page" disabled={loading || !data?.total_count || !validPage}>Go</Button>
    </Box>
  );
  const moreButton = (
    <Button
      ref={phone && !expanded ? expandButton : undefined}
      aria-label="More table options"
      aria-haspopup="menu"
      aria-expanded={!!more}
      onClick={(event) => setMore(event.currentTarget)}
      sx={phone ? { flexShrink: 0 } : undefined}
    >
      More
    </Button>
  );
  // Phones: the name on one line (tap shows it whole) and one search field; the rest is in More.
  const phoneHeader = (
    <>
      <Stack direction="row" gap={1} alignItems="center">
        <InspectionName name={tableName} sx={{ flex: 1, fontFamily: fontMono, fontSize: 16, fontWeight: 500 }} />
        {expanded && <Button onClick={() => setExpanded(false)} sx={{ flexShrink: 0 }}>Close expanded table</Button>}
        {moreButton}
      </Stack>
      <Box
        component="form"
        onSubmit={(event) => {
          event.preventDefault();
          apply();
        }}
      >
        <TextField
          size="small"
          fullWidth
          label="Search all supported columns"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          inputProps={{ maxLength: 200, enterKeyHint: "search" }}
          InputProps={{ endAdornment: <InputAdornment position="end"><IconButton type="submit" edge="end" aria-label="Apply"><SearchIcon fontSize="small" /></IconButton></InputAdornment> }}
        />
      </Box>
    </>
  );
  const desktopHeader = (
    <>
        <Stack
          direction="row"
          gap={1}
          alignItems="center"
          justifyContent="space-between"
        >
          <Typography
            component="h2"
            sx={{ overflowWrap: "anywhere", minWidth: 0, fontFamily: fontMono, fontSize: 16, fontWeight: 500 }}
          >
            {tableName}
          </Typography>
          <Button
            ref={expanded ? undefined : expandButton}
            onClick={() => setExpanded((value) => !value)}
            sx={{ flexShrink: 0 }}
          >
            {expanded ? "Close expanded table" : "Expand table"}
          </Button>
        </Stack>
        <Box
          component="form"
          onSubmit={(event) => {
            event.preventDefault();
            apply();
          }}
          sx={{
            display: "flex",
            gap: 0.5,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <TextField
            size="small"
            label="Search all supported columns"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            inputProps={{ maxLength: 200 }}
            sx={{ flex: "1 1 210px", minWidth: 150 }}
          />
          <Button type="submit" variant="contained">
            Apply
          </Button>
          <Button onClick={() => setDialog("filters")}>
            Filters ({displayedQuery.filters.filter((f) => f.value).length})
          </Button>
          <Button onClick={() => setRefresh((v) => v + 1)} disabled={loading}>
            Refresh
          </Button>
          {moreButton}
        </Box>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Typography variant="caption" color="text.secondary">
            {data
              ? `${data.total_count.toLocaleString()} matching rows`
              : "Search uses text, numeric and date columns."}
          </Typography>
          {updated && (
            <Typography variant="caption" color="text.secondary">
              Updated {updated}
            </Typography>
          )}
        </Stack>
    </>
  );
  const scrollingTable = (
      <TableContainer
        ref={attachTable}
        sx={{ flex: "1 0 120px", minHeight: 120, overflow: "auto" }}
        tabIndex={0}
        aria-label={`${tableName} rows`}
        onScroll={() => {
          if (tableScroll.current)
            scroll.current = {
              top: tableScroll.current.scrollTop,
              left: tableScroll.current.scrollLeft,
            };
        }}
      >
        <Table
          size="small"
          stickyHeader
          sx={{ minWidth: "100%", width: "max-content" }}
        >
          <TableHead>
            <TableRow>
              <TableCell sx={rowHeading}>
                Row
              </TableCell>
              {columns.map((column) => (
                <TableCell
                  key={column}
                  sortDirection={
                      displayedQuery.order === column ? displayedQuery.direction : false
                  }
                >
                  {sortLabel(column)}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          {bodyRows}
        </Table>
      </TableContainer>
  );
  // The rows table keeps an invisible, zero-height copy of the headings so each column is at
  // least as wide as its heading; the pinned strip copies those widths.
  const hiddenHeading = { height: 0, py: 0, borderBottom: 0 } as const;
  const flowingTable = (
    <Box ref={rowsTop} sx={{ position: "relative", minWidth: 0 }}>
      <Box ref={headingStrip} sx={{ position: "sticky", top: "var(--app-header-height, 52px)", zIndex: 2, overflow: "hidden", bgcolor: "surface.head", borderBottom: 1, borderColor: "surface.headLine" }}>
        <Table size="small" sx={{ tableLayout: "fixed", width: widths.length ? widths.reduce((sum, width) => sum + width, 0) : "max-content" }}>
          <colgroup>{widths.map((width, index) => <col key={index} style={{ width }} />)}</colgroup>
          <TableHead>
            <TableRow>
              <TableCell sx={{ ...rowHeading, borderBottom: 0 }}>Row</TableCell>
              {columns.map((column) => (
                <TableCell key={column} sx={{ borderBottom: 0 }}
                  sortDirection={displayedQuery.order === column ? displayedQuery.direction : false}>
                  {sortLabel(column)}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
        </Table>
      </Box>
      <TableContainer
        ref={attachTable}
        sx={{ overflowX: "auto", overflowY: "hidden" }}
        tabIndex={0}
        aria-label={`${tableName} rows`}
        onScroll={() => {
          if (tableScroll.current)
            scroll.current = { top: 0, left: tableScroll.current.scrollLeft };
          followRows();
        }}
      >
        <Table size="small" sx={{ minWidth: "100%", width: "max-content" }}>
          {/* inert: aria-hidden alone still exposes the copies' sort buttons to screen readers. */}
          <TableHead ref={sizingHead} aria-hidden {...{ inert: "" }}>
            <TableRow>
              <TableCell sx={hiddenHeading}><Box sx={{ height: 0, overflow: "hidden" }}>Row</Box></TableCell>
              {columns.map((column) => (
                <TableCell key={column} sx={hiddenHeading}><Box sx={{ height: 0, overflow: "hidden" }}>{sortLabel(column, false)}</Box></TableCell>
              ))}
            </TableRow>
          </TableHead>
          {bodyRows}
        </Table>
      </TableContainer>
      {moreRight && <Box aria-hidden sx={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 32, zIndex: 2, pointerEvents: "none",
        background: (theme) => `linear-gradient(to right, ${alpha(theme.palette.background.paper, 0)}, ${theme.palette.background.paper})` }} />}
    </Box>
  );
  const view = (
    <Paper
      variant="outlined"
      sx={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: flow ? "clip" : "auto",
        borderRadius: 2,
        "& .MuiButton-root, & .MuiIconButton-root": {
          minHeight: 44,
          minWidth: 44,
        },
        "& .MuiInputBase-root": { minHeight: 44 },
      }}
    >
      <Stack spacing={phone ? 1 : 0.5} sx={{ p: 1.5, flexShrink: 0 }}>
        {phone ? phoneHeader : desktopHeader}
        {error && (
          <Alert severity="error">
            {error}
            {data && " Previous rows are shown; refresh to retry."}
          </Alert>
        )}
      </Stack>
      {loading && (
        <LinearProgress aria-label="Loading table" sx={{ flexShrink: 0 }} />
      )}
      {flow ? flowingTable : scrollingTable}
      {phone ? (
        <Box sx={[{ flexShrink: 0, px: 1 }, pinnedBarSx]}>
          <TablePagination
            component="div"
            count={data?.total_count || 0}
            page={displayedQuery.page}
            rowsPerPage={displayedQuery.limit}
            rowsPerPageOptions={[]}
            showFirstButton
            showLastButton
            disabled={loading || !data}
            onPageChange={(_, page) => setQuery({ ...displayedQuery, page })}
            sx={{
              "& .MuiTablePagination-toolbar": { px: 0, minHeight: 52 },
              "& .MuiTablePagination-spacer": { display: "none" },
              "& .MuiTablePagination-displayedRows": { flex: 1 },
              "& .MuiTablePagination-actions": { ml: 0 },
            }}
          />
        </Box>
      ) : (
      <Stack direction="row" alignItems="center" flexWrap="wrap" gap={0.5} sx={{ flexShrink: 0, borderTop: 1, borderColor: "divider", px: 1 }}>
      <TablePagination
        component="div"
        count={data?.total_count || 0}
        page={displayedQuery.page}
        rowsPerPage={displayedQuery.limit}
        rowsPerPageOptions={[25, 50, 100]}
        showFirstButton
        showLastButton
        disabled={loading || !data}
        onPageChange={(_, page) => setQuery({ ...displayedQuery, page })}
        onRowsPerPageChange={(e) =>
          setQuery({ ...displayedQuery, page: 0, limit: Number(e.target.value) })
        }
        sx={{
          flex: "1 1 330px",
          minWidth: 0,
          "& .MuiTablePagination-toolbar": { flexWrap: "wrap", px: 1 },
          "& .MuiTablePagination-spacer": { display: "none" },
          "& .MuiTablePagination-actions": { ml: 0 },
        }}
      />
      {pageForm}
      </Stack>
      )}
    </Paper>
  );
  return (

    <>
      {!expanded && view}
      <Dialog
        fullScreen
        open={expanded}
        onClose={() => setExpanded(false)}
        PaperProps={{
          "aria-label": `Expanded table ${tableName}`,
          sx: {
            height: "100dvh",
            p: "env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)",
          },
        }}
        TransitionProps={{ onExited: () => expandButton.current?.focus() }}
      >
        {expanded && view}
      </Dialog>
      <Menu anchorEl={more} open={!!more} onClose={() => setMore(null)}>
        {phone && [
          <MenuItem key="filters" onClick={() => { setMore(null); setDialog("filters"); }}>
            Filters ({displayedQuery.filters.filter((f) => f.value).length})
          </MenuItem>,
          <MenuItem key="refresh" disabled={loading} onClick={() => { setMore(null); setRefresh((v) => v + 1); }}>
            <ListItemText primary="Refresh" secondary={updated && `Updated ${updated}`} />
          </MenuItem>,
          !expanded && (
            <MenuItem key="expand" onClick={() => { setMore(null); setExpanded(true); }}>
              Expand table
            </MenuItem>
          ),
          <MenuItem key="page" disabled={!data} onClick={() => { setMore(null); setPageDialog(true); }}>
            Page and rows
          </MenuItem>,
        ]}
        <MenuItem
          disabled={!data}
          onClick={() => {
            setMore(null);
            setDialog("columns");
          }}
        >
          Columns
        </MenuItem>
        <MenuItem
          disabled={!data || loading || !!error}
          onClick={() => {
            setMore(null);
            setExportMessage("");
            setDialog("export");
          }}
        >
          Export
        </MenuItem>
        <MenuItem
          onClick={() => {
            setMore(null);
            setWrap((value) => !value);
          }}
        >
          {wrap ? "Do not wrap cells" : "Wrap cells"}
        </MenuItem>
        <MenuItem
          onClick={() => {
            setMore(null);
            setDraft("");
            setFilterDraft([]);
            setQuery((q) => ({ ...q, page: 0, search: "", filters: [] }));
          }}
        >
          Clear search and filters
        </MenuItem>
      </Menu>
      <Dialog open={pageDialog} onClose={() => setPageDialog(false)} fullWidth maxWidth="xs">
        <DialogTitle>Page and rows</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            {pageForm}
            <TextField
              select
              size="small"
              label="Rows per page"
              value={displayedQuery.limit}
              disabled={loading || !data}
              onChange={(event) => {
                setQuery({ ...displayedQuery, page: 0, limit: Number(event.target.value) });
                setPageDialog(false);
              }}
            >
              {[25, 50, 100].map((limit) => <MenuItem key={limit} value={limit}>{limit}</MenuItem>)}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPageDialog(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={!!record}
        onClose={() => setRecord(null)}
        fullWidth
        maxWidth="md"
        aria-labelledby="record-title"
      >
        <DialogTitle id="record-title">
          Row {record?.number} · {tableName}
        </DialogTitle>
        <DialogContent dividers>
          <Typography role="status" sx={{ mb: 1 }}>
            {copied}
          </Typography>
          <Stack component="dl" spacing={2} sx={{ m: 0 }}>
            {data?.columns.map((column) => (
              <Box key={column}>
                <Stack
                  direction="row"
                  alignItems="center"
                  gap={1}
                  justifyContent="space-between"
                >
                  <Typography
                    component="dt"
                    sx={{ fontWeight: 600, overflowWrap: "anywhere" }}
                  >
                    {column}
                  </Typography>
                  <Button
                    aria-label={`Copy ${column} value`}
                    onClick={() => copyValue(record?.row[column])}
                    sx={{ minHeight: 44, flexShrink: 0 }}
                  >
                    Copy
                  </Button>
                </Stack>
                <Box
                  component="dd"
                  sx={{
                    m: 0,
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere",
                    fontFamily: "monospace",
                  }}
                >
                  {displayValue(record?.row[column])}
                </Box>
              </Box>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            autoFocus
            onClick={() => setRecord(null)}
            sx={{ minHeight: 44 }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={!!cell}
        onClose={() => setCell(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>{cell?.column}</DialogTitle>
        <DialogContent dividers>
          <Typography role="status">{copied}</Typography>
          <Box
            component="pre"
            sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", m: 0 }}
          >
            {displayValue(cell?.value)}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => copyValue(cell?.value)} sx={{ minHeight: 44 }}>
            Copy value
          </Button>
          <Button
            autoFocus
            onClick={() => setCell(null)}
            sx={{ minHeight: 44 }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={dialog === "columns"}
        onClose={() => setDialog(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Visible columns</DialogTitle>
        <DialogContent dividers>
          {data?.columns.map((column) => (
            <FormControlLabel
              key={column}
              sx={{ display: "flex" }}
              label={column}
              control={
                <Checkbox
                  checked={!hidden.includes(column)}
                  disabled={columns.length === 1 && !hidden.includes(column)}
                  onChange={(_, checked) =>
                    setHidden((h) =>
                      checked ? h.filter((c) => c !== column) : [...h, column],
                    )
                  }
                />
              }
            />
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Done</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={dialog === "filters"}
        onClose={() => setDialog(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Column filters</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2">
              All conditions must match. Changes apply only when you choose
              Apply filters.
            </Typography>
            {filterDraft.map((filter, index) => (
              <Stack key={index} spacing={1}>
                <TextField
                  select
                  size="small"
                  label="Column"
                  value={filter.column}
                  onChange={(e) =>
                    setFilterDraft((f) =>
                      f.map((v, i) =>
                        i === index ? { ...v, column: e.target.value } : v,
                      ),
                    )
                  }
                >
                  {data?.columns.map((c) => (
                    <MenuItem
                      key={c}
                      value={c}
                      disabled={filterDraft.some(
                        (f, i) => i !== index && f.column === c,
                      )}
                    >
                      {c}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  size="small"
                  label="Condition"
                  value={filter.operator}
                  onChange={(e) =>
                    setFilterDraft((f) =>
                      f.map((v, i) =>
                        i === index ? { ...v, operator: e.target.value } : v,
                      ),
                    )
                  }
                >
                  {["contains", "equals", "starts_with", "ends_with"].map(
                    (op) => (
                      <MenuItem key={op} value={op}>
                        {op.replace(/_/g, " ")}
                      </MenuItem>
                    ),
                  )}
                </TextField>
                <TextField
                  size="small"
                  label="Value"
                  value={filter.value}
                  onChange={(e) =>
                    setFilterDraft((f) =>
                      f.map((v, i) =>
                        i === index ? { ...v, value: e.target.value } : v,
                      ),
                    )
                  }
                />
                <Button
                  onClick={() =>
                    setFilterDraft((f) => f.filter((_, i) => i !== index))
                  }
                >
                  Remove condition
                </Button>
              </Stack>
            ))}
            <Button
              onClick={() =>
                setFilterDraft((f) => [
                  ...f,
                  { column: "", operator: "contains", value: "" },
                ])
              }
            >
              Add condition
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Keep draft</Button>
          <Button
            variant="contained"
            onClick={() => {
              apply();
              setDialog(null);
            }}
          >
            Apply filters
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={dialog === "export"}
        onClose={() => {
          if (progress === null) setDialog(null);
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Export table data</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              select
              label="Rows"
              value={scope}
              disabled={progress !== null}
              onChange={(e) => setScope(e.target.value)}
            >
              <MenuItem value="page">Current page</MenuItem>
              <MenuItem value="all">All matching rows</MenuItem>
            </TextField>
            <TextField
              select
              label="Format"
              value={format}
              disabled={progress !== null}
              onChange={(e) => setFormat(e.target.value as "csv" | "json")}
            >
              <MenuItem value="csv">CSV</MenuItem>
              <MenuItem value="json">JSON</MenuItem>
            </TextField>
            <Alert severity="info">
              Uses the applied search, filters, sort and visible columns.
              Concurrent database writes may change rows during export; this is
              not a database snapshot. Exports exceeding 50 MB must be narrowed
              with filters.
            </Alert>
            {progress !== null && (
              <>
                <LinearProgress />
                <Typography>
                  {progress.toLocaleString()} rows collected
                </Typography>
              </>
            )}
            {exportMessage && <Alert severity="info">{exportMessage}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          {progress !== null ? (
            <Button onClick={() => exportAbort.current?.abort()}>
              Cancel export
            </Button>
          ) : (
            <>
              <Button onClick={() => setDialog(null)}>Close</Button>
              <Button variant="contained" onClick={exportData}>
                Download
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
}
