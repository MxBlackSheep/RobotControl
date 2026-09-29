import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { databaseAPI } from "../services/api";
import InspectionWorkspace from "./InspectionWorkspace";
import InspectionTextViewer from "./InspectionTextViewer";

interface Parameter {
  name: string;
  data_type: string;
  mode: string;
  max_length: number | null;
}
interface StoredItem {
  name: string;
  type: string;
  created_date: string | null;
  modified_date: string | null;
  definition: string;
  parameters: Parameter[];
}
const identity = (item: StoredItem) => `${item.type}:${item.name}`;
const normalize = (item: Partial<StoredItem>, type: string): StoredItem => ({
  name: item.name || "Unnamed",
  type: item.type || type,
  created_date: item.created_date || null,
  modified_date: item.modified_date || null,
  definition: item.definition ?? "Definition not available from server.",
  parameters: Array.isArray(item.parameters)
    ? item.parameters.map((parameter) => ({
        name: parameter.name || "param",
        data_type: parameter.data_type || "UNKNOWN",
        mode: (parameter.mode || "IN").toUpperCase(),
        max_length:
          typeof parameter.max_length === "number"
            ? parameter.max_length
            : null,
      }))
    : [],
});
const dateLabel = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Not available";

export default function StoredProcedures({
  active = true,
  sourceId,
  onError,
}: {
  active?: boolean;
  sourceId?: string;
  onError?: (message: string) => void;
}) {
  const [items, setItems] = useState<StoredItem[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const selectedKeyRef = useRef(selectedKey);
  selectedKeyRef.current = selectedKey;
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [detailOpen, setDetailOpen] = useState(false);
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!active) return;
    let current = true;
    setLoading(true);
    setError("");
    databaseAPI
      .getStoredProcedures(refresh === 0, sourceId)
      .then((response) => {
        if (!current) return;
        const payload = response?.data?.data || {};
        const next = [
          ...(Array.isArray(payload.procedures)
            ? payload.procedures.map((item: Partial<StoredItem>) =>
                normalize(item, "PROCEDURE"),
              )
            : []),
          ...(Array.isArray(payload.functions)
            ? payload.functions.map((item: Partial<StoredItem>) =>
                normalize(item, "FUNCTION"),
              )
            : []),
        ];
        setItems(next);
        if (
          selectedKeyRef.current &&
          !next.some((item) => identity(item) === selectedKeyRef.current)
        ) {
          setSelectedKey("");
          setDetailOpen(false);
          setNotice(
            "The previously selected definition is no longer in the refreshed list.",
          );
        }
      })
      .catch((reason) => {
        if (!current) return;
        const message =
          reason.response?.data?.detail ||
          "Unable to refresh procedures and functions. Previous definitions are retained.";
        setError(String(message));
        onError?.(String(message));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [active, refresh]);

  const filtered = items.filter(
    (item) =>
      (type === "all" || item.type === type) &&
      item.name.toLowerCase().includes(search.toLowerCase()),
  );
  const selected = items.find((item) => identity(item) === selectedKey);
  const selector = (
    <Paper
      variant="outlined"
      sx={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      <Stack spacing={1} sx={{ p: 1.5 }}>
        <Typography variant="h6" component="h2">
          Procedures &amp; functions
        </Typography>
        <TextField
          size="small"
          label="Find a procedure or function"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <TextField
          select
          size="small"
          label="Definition type"
          value={type}
          onChange={(event) => setType(event.target.value)}
        >
          <MenuItem value="all">All definitions</MenuItem>
          <MenuItem value="PROCEDURE">Procedures</MenuItem>
          <MenuItem value="FUNCTION">Functions</MenuItem>
        </TextField>
        <Button
          disabled={loading}
          onClick={() => setRefresh((value) => value + 1)}
        >
          Refresh definitions
        </Button>
      </Stack>
      {loading && <LinearProgress aria-label="Loading definitions" />}
      <List
        aria-label="Procedures and functions"
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}
      >
        {filtered.map((item) => (
          <ListItemButton
            key={identity(item)}
            selected={selectedKey === identity(item)}
            aria-current={selectedKey === identity(item) ? "true" : undefined}
            onClick={() => {
              setSelectedKey(identity(item));
              setDetailOpen(true);
              setTab(0);
              setNotice("");
            }}
            sx={{ minHeight: 52 }}
          >
            <ListItemText
              primary={item.name}
              primaryTypographyProps={{ sx: { overflowWrap: "anywhere" } }}
              secondary={`${item.type === "PROCEDURE" ? "Procedure" : "Function"} · ${item.parameters.length} parameters`}
            />
          </ListItemButton>
        ))}
        {!loading && !filtered.length && (
          <Typography sx={{ p: 2 }}>
            {items.length
              ? "No definitions match this search."
              : "No procedures or functions are available."}
          </Typography>
        )}
      </List>
    </Paper>
  );

  return (
    <>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}
      {notice && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {notice}
        </Alert>
      )}
      <InspectionWorkspace
        label="Stored procedure workspace"
        selector={selector}
        selectorLabel="Definitions"
        detailOpen={detailOpen}
        onBack={() => setDetailOpen(false)}
      >
        {selected ? (
          <Paper
            variant="outlined"
            sx={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <Box sx={{ px: 1.5, pt: 1, minWidth: 0 }}>
              <Typography
                variant="subtitle1"
                component="h2"
                sx={{ overflowWrap: "anywhere" }}
              >
                {selected.name}
              </Typography>
            </Box>
            <Tabs
              value={tab}
              onChange={(_, value) => setTab(value)}
              variant="scrollable"
              scrollButtons="auto"
              aria-label="Definition information"
              sx={{ flexShrink: 0, borderBottom: 1, borderColor: "divider" }}
            >
              <Tab
                label="SQL definition"
                id="definition-sql-tab"
                aria-controls="definition-sql-panel"
              />
              <Tab
                label={`Parameters (${selected.parameters.length})`}
                id="definition-parameters-tab"
                aria-controls="definition-parameters-panel"
              />
              <Tab
                label="Details"
                id="definition-details-tab"
                aria-controls="definition-details-panel"
              />
            </Tabs>
            <Box
              role="tabpanel"
              id="definition-sql-panel"
              aria-labelledby="definition-sql-tab"
              hidden={tab !== 0}
              sx={{
                display: tab === 0 ? "flex" : "none",
                flex: 1,
                minHeight: 0,
                minWidth: 0,
              }}
            >
              <InspectionTextViewer
                key={selectedKey}
                text={selected.definition}
                label="SQL definition"
              />
            </Box>
            <Box
              role="tabpanel"
              id="definition-parameters-panel"
              aria-labelledby="definition-parameters-tab"
              hidden={tab !== 1}
              sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 1.5 }}
            >
              {selected.parameters.length ? (
                <Stack component="dl" spacing={1.5} sx={{ m: 0 }}>
                  {selected.parameters.map((parameter, index) => (
                    <Box key={`${parameter.name}-${index}`}>
                      <Typography
                        component="dt"
                        sx={{
                          fontFamily: "monospace",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {parameter.name}
                      </Typography>
                      <Typography
                        component="dd"
                        sx={{ ml: 0 }}
                        color="text.secondary"
                      >
                        {parameter.data_type}
                        {parameter.max_length === null
                          ? ""
                          : ` (${parameter.max_length})`}{" "}
                        · {parameter.mode}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <Typography>This definition has no parameters.</Typography>
              )}
            </Box>
            <Box
              role="tabpanel"
              id="definition-details-panel"
              aria-labelledby="definition-details-tab"
              hidden={tab !== 2}
              sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 1.5 }}
            >
              <Typography>
                Created: {dateLabel(selected.created_date)}
              </Typography>
              <Typography>
                Modified: {dateLabel(selected.modified_date)}
              </Typography>
            </Box>
          </Paper>
        ) : (
          <Alert severity="info">
            Choose a procedure or function to inspect its SQL definition and
            parameters.
          </Alert>
        )}
      </InspectionWorkspace>
    </>
  );
}
