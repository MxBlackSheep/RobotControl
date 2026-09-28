import React, { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,

  LinearProgress,
  MenuItem,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,

  TextField,
  Typography,
} from "@mui/material";
import { PageContent, PageHeader } from "../components/PageLayout";
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

import ReportConnections, { Source } from "../components/ReportConnections";

type TableInfo = { name: string; has_data?: boolean; is_important?: boolean };

export default function DatabasePage() {
  const { user } = useAuth();
  const [section] = useModuleSection("/database", user);
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState(() => localStorage.getItem('database-viewer-source') || '');
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const loadSources = async () => { const r = await api.get('/api/database/tools/viewer-sources'); setSources(r.data); setSourceId(old => r.data.some((s: Source) => s.id === old) ? old : r.data[0]?.id || ''); };
  useEffect(() => { void loadSources().catch(() => setError('Unable to load database connections.')); }, []);
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
    localStorage.setItem('database-viewer-source', sourceId);
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
          Tables
        </Typography>
        <TextField
          size="small"
          label="Find a table"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Button onClick={load} disabled={loading}>
          Refresh tables
        </Button>
      </Stack>
      {loading && <LinearProgress />}
      <List
        aria-label="Database tables"
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}
      >
        {filtered.map((table) => (
          <ListItemButton
            key={table.name}
            selected={selected === table.name}
            aria-current={selected === table.name ? "true" : undefined}
            title={table.name}
            onClick={() => {
              setSelected(table.name);
              setShowTable(true);
            }}
            sx={{ minHeight: 52 }}
          >
            <ListItemText
              primary={table.name}
              primaryTypographyProps={{ sx: { overflowWrap: "anywhere" } }}
              secondary={
                table.has_data === true
                  ? "Has data"
                  : table.has_data === false
                    ? "Empty"
                    : undefined
              }
            />
          </ListItemButton>
        ))}
        {!loading && !filtered.length && (
          <Typography sx={{ p: 2 }}>No tables match this view.</Typography>
        )}
      </List>
    </Paper>
  );

  return (
    <PageContent variant="inspection">
      <PageHeader title="Database" />
      {(section === 0 || section === 1) && <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mb: 1 }}>
        <TextField select size="small" label="Database connection" value={sourceId} onChange={e => setSourceId(e.target.value)} sx={{ flex: 1, minWidth: 200 }}>
          {sources.map(s => <MenuItem key={s.id} value={s.id}>{s.name} · {s.server} / {s.database}</MenuItem>)}
        </TextField>
        {isLocalUser(user) && user?.role === 'admin' && <Button onClick={() => setConnectionsOpen(true)}>Configure connections</Button>}
        {!sourceId && <Alert severity="info">Configure a read-only connection to browse a database.</Alert>}
      </Stack>}
      <ReportConnections open={connectionsOpen} onClose={() => { setConnectionsOpen(false); void loadSources(); }} />
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
            <Alert severity="info">
              Choose a table to inspect its rows. Browsing does not change
              database records.
            </Alert>
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
