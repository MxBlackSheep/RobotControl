import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  ButtonGroup,
  IconButton,
  InputAdornment,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  TablePagination,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowUpward from "@mui/icons-material/ArrowUpward";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import {
  logFileApi,
  LogFileSource,
  LogFileListItem,
  BrowseOptions,
} from "../services/logFileApi";
import InspectionWorkspace from "./InspectionWorkspace";
import { EmptyPanel } from "./PageLayout";
import LogReader, { LogSelection } from "./LogReader";
import { fontMono } from "../theme";
type Location = { folder: string; archive: string; entry: string };
const root: Location = { folder: "", archive: "", entry: "" };
const defaults: BrowseOptions = {
  page: 1,
  limit: 50,
  search: "",
  sort_by: "modified",
  sort_direction: "desc",
  file_type: "all",
};
const parent = (path: string) => path.split("/").slice(0, -1).join("/");
const join = (path: string, name: string) =>
  [path, name].filter(Boolean).join("/");
const same = (a: Location, b: Location) =>
  a.folder === b.folder && a.archive === b.archive && a.entry === b.entry;
const message = (error: any) =>
  error.response?.data?.error?.message ||
  error.message ||
  "Unable to browse logs";
export default function LogSourceBrowser({
  source,
  active,
}: {
  source: LogFileSource;
  active: boolean;
}) {
  const [intent, setIntent] = useState({
    location: root,
    query: defaults,
    revision: 0,
  });
  const [listing, setListing] = useState<{
    location: Location;
    items: LogFileListItem[];
    total: number;
    query: BrowseOptions;
  } | null>(null);
  const [listLoading, setListLoading] = useState(false),
    [listError, setListError] = useState(""),
    [search, setSearch] = useState(""),
    [filtersOpen, setFiltersOpen] = useState(false);
  const [selected, setSelected] = useState<LogSelection | null>(null),
    [reading, setReading] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const listIdentity = useRef(root);
  const current = listing?.location || intent.location;
  const selectedKey = selected
    ? JSON.stringify([
        source.id,
        selected.relative,
        selected.archive,
        selected.entry,
      ])
    : "";
  useEffect(() => {
    if (!active) return;
    let valid = true;
    const abort = new AbortController();
    setListLoading(true);
    setListError("");
    const { location, query } = intent;
    const request = location.archive
      ? logFileApi.browseArchive(
          source.id,
          location.archive,
          location.entry,
          query,
          abort.signal,
        )
      : logFileApi.browse(source.id, location.folder, query, abort.signal);
    request
      .then((result) => {
        if (!valid) return;
        if (!same(listIdentity.current, location)) {
          setSelected(null);
          setReading(false);
          listIdentity.current = location;
        }
        setListing({
          location,
          query,
          items: result.items,
          total: result.total_items,
        });
      })
      .catch((error) => {
        if (valid && !abort.signal.aborted) setListError(message(error));
      })
      .finally(() => {
        if (valid) setListLoading(false);
      });
    return () => {
      valid = false;
      abort.abort();
    };
  }, [source.id, intent, active]);
  const browse = (location: Location) => {
    setIntent((v) => ({
      location,
      query: { ...v.query, page: 1, search: "" },
      revision: v.revision + 1,
    }));
    setSearch("");
  };
  const query = (patch: BrowseOptions) =>
    setIntent((v) => ({
      location: current,
      query: { ...v.query, ...patch, page: patch.page ?? 1 },
      revision: v.revision + 1,
    }));
  const openItem = (item: LogFileListItem) => {
    if (item.is_directory) {
      browse(
        current.archive
          ? {
              ...current,
              entry: item.entry_path || join(current.entry, item.name),
            }
          : { ...root, folder: join(current.folder, item.name) },
      );
      return;
    }
    if (!current.archive && item.extension?.toLowerCase() === ".zip") {
      browse({
        ...current,
        archive: join(current.folder, item.name),
        entry: "",
      });
      return;
    }
    setSelected({
      name: item.name,
      relative: join(current.folder, item.name),
      archive: current.archive,
      entry: item.entry_path || "",
    });
    setReading(true);
  };
  const up = () =>
    browse(
      current.archive
        ? current.entry
          ? { ...current, entry: parent(current.entry) }
          : { ...root, folder: current.folder }
        : { ...root, folder: parent(current.folder) },
    );
  const parts = (current.archive ? current.entry : current.folder)
    .split("/")
    .filter(Boolean);
  const selector = (
    <Paper
      variant="outlined"
      sx={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
        borderRadius: 2,
      }}
    >
      <Stack
        direction="row"
        gap={0.5}
        flexWrap="wrap"
        alignItems="center"
        sx={{ px: 1, pt: 1 }}
      >
        {!!source.shortcuts?.length && <ButtonGroup size="small" variant="outlined" aria-label="Log folders">
          {source.shortcuts.map((shortcut) => (
            <Button
              key={shortcut.label}
              onClick={() => browse({ ...root, folder: shortcut.relative_path })}
            >
              {shortcut.label}
            </Button>
          ))}
        </ButtonGroup>}
        <Box sx={{ flex: 1 }} />
        <Breadcrumbs
          aria-label="Log folder"
          maxItems={3}
          sx={{
            order: 1,
            flexBasis: "100%",
            minWidth: 0,
            "& .MuiBreadcrumbs-ol": { flexWrap: "nowrap" },
            "& .MuiBreadcrumbs-li": { minWidth: 0 },
            "& button": {
              maxWidth: "100%",
              display: "block",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            },
          }}
        >
          <Button onClick={() => browse(root)}>{source.label}</Button>
          {current.archive && (
            <Button onClick={() => browse({ ...current, entry: "" })}>
              {current.archive.split("/").pop()}
            </Button>
          )}
          {parts.map((part, index) => (
            <Button
              key={index}
              onClick={() =>
                browse(
                  current.archive
                    ? { ...current, entry: parts.slice(0, index + 1).join("/") }
                    : { ...root, folder: parts.slice(0, index + 1).join("/") },
                )
              }
            >
              {part}
            </Button>
          ))}
        </Breadcrumbs>
        <Tooltip title="Up one folder">
          <span>
            <IconButton
              aria-label="Up"
              disabled={(!current.folder && !current.archive) || listLoading}
              onClick={up}
            >
              <ArrowUpward fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh files">
          <span>
            <IconButton
              aria-label="Refresh files"
              disabled={listLoading}
              onClick={() =>
                setIntent((v) => ({
                  ...v,
                  location: current,
                  revision: v.revision + 1,
                }))
              }
            >
              <RefreshIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
      {listError && (
        <Alert severity="error">
          {listError}
          {listing && " Previous results are retained."}
        </Alert>
      )}
      <Box
        component="form"
        onSubmit={(e) => {
          e.preventDefault();
          query({ search: search.trim() });
        }}
        sx={{ display: "flex", gap: 0.5, p: 1 }}
      >
        <TextField
          size="small"
          label="Find filenames"
          inputProps={{ maxLength: 200 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 1, minWidth: 0 }}
          InputProps={{ endAdornment: <InputAdornment position="end"><IconButton type="submit" edge="end" aria-label="Search"><SearchIcon fontSize="small" /></IconButton></InputAdornment> }}
        />
      </Box>
      <Stack direction="row" gap={0.5} sx={{ px: 1, pb: 1 }}>
        <TextField
          select
          size="small"
          label="Sort"
          value={intent.query.sort_by}
          onChange={(e) => query({ sort_by: e.target.value })}
          sx={{ flex: 1, minWidth: 0 }}
        >
          {["name", "modified", "size"].map((value) => (
            <MenuItem key={value} value={value}>
              {value[0].toUpperCase() + value.slice(1)}
            </MenuItem>
          ))}
        </TextField>
        <Button
          aria-label="Reverse file sort"
          onClick={() =>
            query({
              sort_direction:
                intent.query.sort_direction === "asc" ? "desc" : "asc",
            })
          }
        >
          {intent.query.sort_direction === "asc" ? "↑" : "↓"}
        </Button>
        <Button onClick={() => setFiltersOpen((v) => !v)}>Filters</Button>
      </Stack>
      {filtersOpen && (
        <Stack spacing={1} sx={{ p: 1.5 }}>
          <TextField
            select
            size="small"
            label="File type"
            value={intent.query.file_type}
            onChange={(e) => query({ file_type: e.target.value })}
          >
            {["all", "text", "traces", "archives"].map((type) => (
              <MenuItem key={type} value={type}>
                {type === "text" ? "Non-archive files" : type}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            type="date"
            label="Modified from"
            InputLabelProps={{ shrink: true }}
            value={intent.query.modified_from || ""}
            onChange={(e) =>
              query({ modified_from: e.target.value || undefined })
            }
          />
          <TextField
            size="small"
            type="date"
            label="Modified to"
            InputLabelProps={{ shrink: true }}
            value={intent.query.modified_to || ""}
            onChange={(e) =>
              query({ modified_to: e.target.value || undefined })
            }
          />
          <Button
            onClick={() => {
              setSearch("");
              query({ ...defaults, limit: intent.query.limit });
            }}
          >
            Clear filters and search
          </Button>
        </Stack>
      )}
      {listLoading && <LinearProgress aria-label="Loading files" />}
      <List
        aria-label="Log files"
        disablePadding
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden", borderTop: 1, borderColor: "divider" }}
      >
        {listing?.items.map((item) => (
          <ListItemButton
            key={item.entry_path || item.path || item.name}
            title={item.path || item.entry_path || item.name}
            selected={
              !item.is_directory &&
              selected?.name === item.name &&
              selected.archive === current.archive &&
              selected.relative === join(current.folder, item.name)
            }
            onClick={() => openItem(item)}
            sx={{ px: 1.5, borderBottom: 1, borderColor: "divider" }}
          >
            <ListItemText
              primary={(item.is_directory ? "▸ " : "") + item.name}
              secondaryTypographyProps={{ sx: { fontSize: 12 } }}
              primaryTypographyProps={{
                sx: {
                  fontFamily: item.is_directory ? undefined : fontMono,
                  fontSize: 13,
                  overflowWrap: "anywhere",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                },
              }}
              secondary={
                item.is_directory
                  ? "Folder"
                  : `${item.modified_date || "Metadata unavailable"} · ${item.size_formatted || "Unknown size"}`
              }
            />
          </ListItemButton>
        ))}
        {!listLoading && !listing?.items.length && (
          <Typography sx={{ p: 2 }}>
            No files match this folder view.
          </Typography>
        )}
      </List>
      <TablePagination
        component="div"
        count={listing?.total || 0}
        page={Math.max(0, (listing?.query.page || 1) - 1)}
        rowsPerPage={listing?.query.limit || 50}
        rowsPerPageOptions={[25, 50, 100]}
        onPageChange={(_, page) => query({ page: page + 1 })}
        onRowsPerPageChange={(e) => query({ limit: Number(e.target.value) })}
        sx={{
          "& .MuiTablePagination-toolbar": { flexWrap: "wrap", px: 1 },
          "& .MuiTablePagination-spacer": { display: "none" },
        }}
      />
    </Paper>
  );
  return (
    <>
      <InspectionWorkspace
        label="Log inspection"
        selector={selector}
        selectorLabel="files"
        detailOpen={reading}
        onBack={() => setReading(false)}
        onDetailVisibilityChange={setDetailVisible}
      >
        {selected ? (
          <LogReader
            key={selectedKey}
            sourceId={source.id}
            selected={selected}
            active={active}
            visibleInWorkspace={detailVisible}
          />
        ) : (
          <EmptyPanel>Choose a file to read it.</EmptyPanel>
        )}
      </InspectionWorkspace>
    </>
  );
}
