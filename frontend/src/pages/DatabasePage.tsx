import React, { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  FormControlLabel,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { PageContent, PageHeader } from "../components/PageLayout";
import { useModuleSection, isLocalUser } from "../components/navigation";
import SectionPanel from "../components/SectionPanel";
import InspectionWorkspace from "../components/InspectionWorkspace";
import { useAuth } from "../context/AuthContext";
import { databaseAPI } from "../services/api";
import DatabaseTable from "../components/DatabaseTable";
import StoredProcedures from "../components/StoredProcedures";
import DatabaseRestore from "../components/DatabaseRestore";
import DatabaseOperations from "../components/DatabaseOperations";

type TableInfo = { name: string; has_data?: boolean; is_important?: boolean };

export default function DatabasePage() {
  const { user } = useAuth();
  const [section] = useModuleSection("/database", user);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [important, setImportant] = useState(true);
  const [showTable, setShowTable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);

  const load = async () => {
    const id = ++request.current;
    setLoading(true);
    setError("");
    try {
      const response = await databaseAPI.getTables(false);
      if (id === request.current)
        setTables(response.data.data.table_details || []);
    } catch {
      if (id === request.current)
        setError("Unable to refresh tables. Existing entries are retained.");
    } finally {
      if (id === request.current) setLoading(false);
    }
  };
  useEffect(() => {
    void load();
    return () => {
      request.current++;
    };
  }, []);

  const filtered = tables.filter(
    (table) =>
      (!important || table.is_important) &&
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
        <FormControlLabel
          control={
            <Switch
              checked={important}
              onChange={(_, checked) => setImportant(checked)}
            />
          }
          label="Important tables only"
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
                    : "Availability unknown"
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
            <DatabaseTable tableName={selected} active={section === 0} />
          ) : (
            <Alert severity="info">
              Choose a table to inspect its rows. Browsing does not change
              database records.
            </Alert>
          )}
        </InspectionWorkspace>
      </SectionPanel>
      <SectionPanel active={section === 1}>
        <StoredProcedures active={section === 1} />
      </SectionPanel>
      <SectionPanel active={section === 2}>
        {user?.role === "admin" || isLocalUser(user) ? (
          <DatabaseRestore onError={setError} />
        ) : null}
      </SectionPanel>
      <SectionPanel active={section === 3}>
        {isLocalUser(user) ? <DatabaseOperations onError={setError} /> : null}
      </SectionPanel>
    </PageContent>
  );
}
