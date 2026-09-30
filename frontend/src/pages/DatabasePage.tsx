import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,

  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  Box,
  Stack,

  TextField,
  Typography,
} from "@mui/material";
import { EmptyPanel, PageContent, PageHeader, Panel } from "../components/PageLayout";
import { useModuleSection, isLocalUser } from "../components/navigation";
import SectionPanel from "../components/SectionPanel";
import InspectionWorkspace from "../components/InspectionWorkspace";
import { useAuth } from "../context/AuthContext";
import { api, databaseAPI } from "../services/api";
import DatabaseTable from "../components/DatabaseTable";
import StoredProcedures from "../components/StoredProcedures";
import DatabaseSettings from "../components/DatabaseSettings";
import DatabaseRestore from "../components/DatabaseRestore";
import DatabaseTools, { DatabasePackages } from "../components/DatabaseTools";

import { Source } from "../components/ReportConnections";
import { fontMono, layout } from "../theme";

// has_data is null when the server could not check the table (not the same as empty).
type TableInfo = { name: string; has_data?: boolean | null; is_important?: boolean };

export default function DatabasePage() {
  const { user } = useAuth();
  const [section] = useModuleSection("/database", user);
  const [sources, setSources] = useState<Source[]>([]);
  const sourceId = sources[0]?.id || '';
  useEffect(() => {
    const c = new AbortController();
    if (section === 0 || section === 1) void api.get('/api/database/tools/viewer-sources', {signal:c.signal})
      .then(r => { if (!c.signal.aborted) setSources(r.data); })
      .catch(() => { if (!c.signal.aborted) setError('Unable to load the viewer database.'); });
    return () => c.abort();
  }, [section]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");

  const [showTable, setShowTable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);

  const load = async () => {
    if (!sourceId) return;
    const id = ++request.current;
    setLoading(true);
    setError("");
    try {
      const response = await databaseAPI.getTables(false, sourceId);
      if (id === request.current)
        setTables(response.data.data.table_details || []);
    } catch {
      if (id === request.current)
        setError("Unable to refresh tables. Existing entries are retained.");
    } finally {
      if (id === request.current) setLoading(false);
    }
  };
  const sourceKey = sourceId + '/' + (sources.find(s => s.id === sourceId)?.revision || '');
  useEffect(() => {
    setTables([]); setSelected(''); setShowTable(false); setError('');
  }, [sourceKey]);
  useEffect(() => {
    if (section === 0) void load();
    return () => { request.current++; };
  }, [sourceKey, section]);

  const filtered = tables.filter(
    (table) =>

      table.name.toLowerCase().includes(search.toLowerCase()),
  );
  const selector = (
    <Panel
      title="Tables"
      fill
      inset={false}
      sx={{ flex: 1 }}
      bodySx={{ display: "flex", flexDirection: "column" }}
      actions={<Button size="small" onClick={load} disabled={loading}>Refresh tables</Button>}
    >
      <Box sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "surface.rowLine" }}>
        <TextField
          size="small"
          fullWidth
          label="Find a table"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </Box>
      {loading && <LinearProgress />}
      <List
        aria-label="Database tables"
        disablePadding
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}
      >
        {filtered.map((table) => {
          const state = table.has_data === true ? "Has data" : table.has_data === false ? "Empty"
            : table.has_data === null ? "Could not check" : undefined;
          return (
            <ListItemButton
              key={table.name}
              selected={selected === table.name}
              aria-current={selected === table.name ? "true" : undefined}
              title={table.name}
              onClick={() => {
                setSelected(table.name);
                setShowTable(true);
              }}
              sx={{ minHeight: layout.row, gap: 1, px: 2, borderBottom: 1, borderColor: "surface.rowLine" }}
            >
              <ListItemText
                primary={table.name}
                primaryTypographyProps={{ sx: { fontFamily: fontMono, fontSize: 12, overflowWrap: "anywhere" } }}
              />
              {/* "Could not check" is unknown, not empty: amber like other states that need a look. */}
              {state && <Typography component="span" sx={{ fontSize: 12, flexShrink: 0,
                color: table.has_data === null ? (theme) => theme.palette.tone.attention.fg : table.has_data ? "success.main" : "text.secondary" }}>{state}</Typography>}
            </ListItemButton>
          );
        })}
        {!loading && !filtered.length && (
          <Typography variant="body2" sx={{ p: 2, color: "text.secondary" }}>No tables match this view.</Typography>
        )}
      </List>
    </Panel>
  );

  return (
    <PageContent variant="inspection">
      <PageHeader title="Database" />
      {(section === 0 || section === 1) && <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mb: `${layout.gutter}px` }}>
        {sources[0] && <Typography variant="body2" color="text.secondary">{sources[0].name} · {sources[0].database}</Typography>}
        {!sourceId && <Alert severity="info">Ask an administrator to select a database in Database settings.</Alert>}
      </Stack>}
      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}
      <SectionPanel active={section === 0}>
        <InspectionWorkspace
          label="Database table workspace"
          selector={selector}
          selectorLabel="Tables"
          detailOpen={showTable}
          onBack={() => setShowTable(false)}
        >
          {selected ? (
            <DatabaseTable sourceId={sourceId} tableName={selected} active={section === 0} />
          ) : (
            <EmptyPanel>
              Choose a table to inspect its rows. Browsing does not change
              database records.
            </EmptyPanel>
          )}
        </InspectionWorkspace>
      </SectionPanel>
      <SectionPanel active={section === 1}>
        <StoredProcedures key={sourceKey} sourceId={sourceId} active={section === 1 && !!sourceId} />
      </SectionPanel>
      <SectionPanel active={section === 2}>
        {user?.role === "admin" || isLocalUser(user) ? (
          <DatabaseRestore onError={setError} />
        ) : null}
      </SectionPanel>
      <SectionPanel active={section === 3}>
        {isLocalUser(user) && user?.role === "admin" ? <DatabaseTools kind="operation" active={section === 3} /> : null}
      </SectionPanel>
      <SectionPanel active={section === 4}>
        <DatabaseTools kind="report" active={section === 4} />
      </SectionPanel>
      <SectionPanel active={section === 5}>
        {isLocalUser(user) && user?.role === "admin" ? <DatabasePackages active={section === 5} /> : null}
      </SectionPanel>
      <SectionPanel active={section === 6}>{isLocalUser(user) && user?.role === "admin" ? <DatabaseSettings active={section === 6} /> : null}</SectionPanel>
    </PageContent>
  );
}
