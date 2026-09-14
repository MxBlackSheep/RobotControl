import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Breadcrumbs, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress, List, ListItemButton, ListItemText, MenuItem, Paper, Stack, Switch, TablePagination, TextField, Typography } from '@mui/material';
import { logFileApi, LogFileSource, LogFileListItem, LogFilePreview, BrowseOptions, PreviewMode } from '../services/logFileApi';
type Location = {
    folder: string;
    archive: string;
    entry: string;
};
type Selected = {
    name: string;
    relative: string;
    archive: string;
    entry: string;
};
const root: Location = { folder: '', archive: '', entry: '' };
const defaults: BrowseOptions = { page: 1, limit: 50, search: '', sort_by: 'modified', sort_direction: 'desc', file_type: 'all' };
const parent = (path: string) => path.split('/').slice(0, -1).join('/');
const join = (path: string, name: string) => [path, name].filter(Boolean).join('/');
const same = (a: Location, b: Location) => a.folder === b.folder && a.archive === b.archive && a.entry === b.entry;
const message = (error: any) => error.response?.data?.error?.message || error.response?.data?.message || error.response?.data?.detail || error.message || 'Request failed';
export default function LogSourceBrowser({ source, active }: {
    source: LogFileSource;
    active: boolean;
}) {
    const [visible, setVisible] = useState(document.visibilityState === 'visible');
    useEffect(() => {
        const changed = () => setVisible(document.visibilityState === 'visible');
        document.addEventListener('visibilitychange', changed);
        return () => document.removeEventListener('visibilitychange', changed);
    }, []);
    // Keep the last successful folder alongside its rows when a navigation request fails.
    const [intent, setIntent] = useState({ location: root, query: defaults, revision: 0 });
    const [listing, setListing] = useState<{
        location: Location;
        items: LogFileListItem[];
        total: number;
        query: BrowseOptions;
    } | null>(null);
    const [listLoading, setListLoading] = useState(false), [listError, setListError] = useState(''), [search, setSearch] = useState(''), [filtersOpen, setFiltersOpen] = useState(false);
    const [selected, setSelected] = useState<Selected | null>(null), [preview, setPreview] = useState<{
        key: string;
        data: LogFilePreview;
    } | null>(null), [previewError, setPreviewError] = useState(''), [previewLoading, setPreviewLoading] = useState(false), [previewRefresh, setPreviewRefresh] = useState(0);
    const [mode, setMode] = useState<PreviewMode>('tail'), [follow, setFollow] = useState(false), [wrap, setWrap] = useState(true), [expanded, setExpanded] = useState(false), [details, setDetails] = useState(false), [copied, setCopied] = useState('');
    const [find, setFind] = useState(''), [matchIndex, setMatchIndex] = useState(0), [jump, setJump] = useState(false), [reading, setReading] = useState(false), [showFiles, setShowFiles] = useState(true), [toolsOpen, setToolsOpen] = useState(false);
    const expandButton = useRef<HTMLButtonElement | null>(null);
    const reader = useRef<HTMLDivElement | null>(null), atBottom = useRef(true), scrollPosition = useRef(0), listIdentity = useRef(root);
    // A filename alone is not an identity: sources and archive entries may share names.
    const selectedKey = selected ? JSON.stringify([source.id, selected.relative, selected.archive, selected.entry]) : '';
    const current = listing?.location || intent.location;
    const data = preview?.key === selectedKey ? preview.data : null;
    useEffect(() => {
        if (!active)
            return;
        const abort = new AbortController();
        let valid = true;
        setListLoading(true);
        setListError('');
        const { location, query } = intent;
        const request = location.archive ? logFileApi.browseArchive(source.id, location.archive, location.entry, query, abort.signal) : logFileApi.browse(source.id, location.folder, query, abort.signal);
        request.then(result => {
            if (!valid)
                return;
            if (!same(listIdentity.current, location)) {
                setSelected(null);
                setPreview(null);
                setReading(false);
                setFollow(false);
                listIdentity.current = location;
            }
            setListing({ location, query, items: result.items, total: result.total_items });
        }).catch(error => { if (valid && !abort.signal.aborted)
            setListError(message(error)); }).finally(() => { if (valid)
            setListLoading(false); });
        return () => { valid = false; abort.abort(); };
    }, [source.id, intent, active]);
    useEffect(() => {
        if (!active || !selected)
            return;
        const abort = new AbortController();
        let valid = true;
        setPreviewLoading(true);
        setPreviewError('');
        const request = selected.archive ? logFileApi.previewArchive(source.id, selected.archive, selected.entry, mode, 1024 * 1024, abort.signal) : logFileApi.preview(source.id, selected.relative, mode, 1024 * 1024, abort.signal);
        request.then(result => {
            if (!valid)
                return;
            setPreview({ key: selectedKey, data: result });
            if (result.is_binary || result.file_locked)
                setFollow(false);
            if (atBottom.current) {
                requestAnimationFrame(() => { if (valid && reader.current)
                    reader.current.scrollTop = reader.current.scrollHeight; });
            }
            else
                setJump(true);
        }).catch(error => { if (valid && !abort.signal.aborted) {
            setPreviewError(message(error));
            setFollow(false);
        } }).finally(() => { if (valid)
            setPreviewLoading(false); });
        return () => { valid = false; abort.abort(); };
    }, [source.id, selectedKey, mode, previewRefresh, active]);
    useEffect(() => { if (!active)
        setFollow(false); }, [active]);
    useEffect(() => {
        if (!active || !visible || !follow || previewLoading || previewError || !selected || selected.archive || /\.(gz|zip)$/i.test(selected.relative))
            return;
        // Schedule only after the previous request settles, so slow reads cannot overlap.
        const timer = window.setTimeout(() => setPreviewRefresh(v => v + 1), 5000);
        return () => window.clearTimeout(timer);
    }, [active, visible, follow, previewLoading, previewError, selectedKey, previewRefresh]);
    useEffect(() => { if (reader.current)
        reader.current.scrollTop = scrollPosition.current; }, [expanded, reading]);
    const browse = (location: Location) => { setIntent(v => ({ location, query: { ...v.query, page: 1, search: '' }, revision: v.revision + 1 })); setSearch(''); };
    const query = (patch: BrowseOptions) => setIntent(v => ({ location: current, query: { ...v.query, ...patch, page: patch.page ?? 1 }, revision: v.revision + 1 }));
    const openItem = (item: LogFileListItem) => {
        if (item.is_directory) {
            browse(current.archive ? { ...current, entry: item.entry_path || join(current.entry, item.name) } : { ...root, folder: join(current.folder, item.name) });
            return;
        }
        if (!current.archive && item.extension?.toLowerCase() === '.zip') {
            browse({ ...current, archive: join(current.folder, item.name), entry: '' });
            return;
        }
        setSelected({ name: item.name, relative: join(current.folder, item.name), archive: current.archive, entry: item.entry_path || '' });
        setPreview(null);
        setFollow(false);
        setFind('');
        setMatchIndex(0);
        setJump(false);
        setReading(true);
        atBottom.current = mode === 'tail';
        scrollPosition.current = 0;
    };
    const up = () => browse(current.archive ? current.entry ? { ...current, entry: parent(current.entry) } : { ...root, folder: current.folder } : { ...root, folder: parent(current.folder) });
    const content = data?.content || '';
    const matches = useMemo(() => { if (!find)
        return []; const lower = content.toLocaleLowerCase(), term = find.toLocaleLowerCase(); const indices: number[] = []; for (let offset = 0; indices.length < 500;) {
        const next = lower.indexOf(term, offset);
        if (next < 0)
            break;
        indices.push(next);
        offset = next + term.length;
    } return indices; }, [content, find]);
    const highlighted = useMemo(() => { if (!matches.length)
        return content; const parts: React.ReactNode[] = []; let start = 0; matches.forEach((offset, index) => { parts.push(content.slice(start, offset), <mark key={offset} data-match={index} style={{ background: index === matchIndex ? '#ffb74d' : '#fff59d', color: '#111' }}>{content.slice(offset, offset + find.length)}</mark>); start = offset + find.length; }); parts.push(content.slice(start)); return parts; }, [content, matches, find, matchIndex]);
    const nextMatch = () => { const next = (matchIndex + 1) % Math.max(matches.length, 1); setMatchIndex(next); reader.current?.querySelector(`[data-match="${next}"]`)?.scrollIntoView({ block: 'center' }); };
    const pathLabel = selected ? (selected.archive ? `${source.path}\\${selected.archive} / ${selected.entry}` : `${source.path}\\${selected.relative}`) : source.path;
    const readerBody = <>
   <Stack spacing={1} sx={{ p: 1.5 }}>
     <Typography variant="h6" sx={{ overflowWrap: 'anywhere' }}>{selected?.name || 'Choose a file'}</Typography>
     {selected && <>
        <Typography variant="caption" color="text.secondary">{data?.modified_date ? `Modified ${data.modified_date} · ` : ''}{data?.bytes_returned?.toLocaleString() || 0} bytes shown · Preview limited to 1 MB</Typography>
       <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
         <Button aria-label="Refresh preview" disabled={previewLoading} onClick={() => setPreviewRefresh(v => v + 1)}>Refresh</Button>
         <TextField select size="small" label="Show" value={mode} onChange={e => { setMode(e.target.value as PreviewMode); setFollow(false); atBottom.current = e.target.value === 'tail'; }} sx={{ width: 120 }}>
        <MenuItem value="tail">Latest</MenuItem>
        <MenuItem value="head">Beginning</MenuItem>
        </TextField>
         <Button aria-label={expanded ? 'Close expanded preview' : 'Expand preview'} ref={expanded ? undefined : expandButton} onClick={() => setExpanded(v => !v)}>{expanded ? 'Close expanded preview' : 'Expand'}</Button>
         <Button sx={{ display: { xs: 'inline-flex', md: 'none' } }} aria-expanded={toolsOpen} onClick={() => setToolsOpen(v => !v)}>Reading tools</Button>
       </Stack>
       <Box sx={{ display: { xs: toolsOpen ? 'block' : 'none', md: 'block' } }}>
        <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
        <TextField size="small" label="Find in preview" value={find} onChange={e => { setFind(e.target.value); setMatchIndex(0); }} helperText={find ? `${matches.length}${matches.length === 500 ? '+' : ''} matches in shown text only` : 'Searches the shown text only'} sx={{ flex: '1 1 190px' }}/>
        <Button disabled={!matches.length} onClick={nextMatch}>Next match</Button>
         {!selected.archive && !/\.(gz|zip)$/i.test(selected.relative) && <FormControlLabel label="Follow latest (5s)" control={<Switch checked={follow} disabled={mode !== 'tail' || !!previewError || !!data?.is_binary} onChange={(_, value) => { setFollow(value); if (value)
            setPreviewRefresh(v => v + 1); }}/>}/>}
       <FormControlLabel label="Wrap lines" control={<Switch checked={wrap} onChange={(_, value) => setWrap(value)} size="small"/>}/>
        <Button onClick={() => setDetails(true)}>Details</Button>
        </Stack>
        </Box>
        </>}
   </Stack>
   {previewLoading && <LinearProgress aria-label="Loading preview"/>}{previewError && <Alert severity="error">{previewError}{data && ' Previous preview retained; it may be stale.'}</Alert>}
   {data?.is_binary && <Alert severity="info">This file contains binary data and cannot be shown as text.</Alert>}{data?.file_locked && <Alert severity="warning">The file is locked. Retry when its writer permits access.</Alert>}
   {data?.truncated && <Typography variant="caption" sx={{ px: 1.5 }}>Showing {data.mode === 'tail' ? 'the latest' : 'the beginning'} portion only. Find does not search the rest of this file.</Typography>}
   {jump && <Button onClick={() => { if (reader.current)
        reader.current.scrollTop = reader.current.scrollHeight; atBottom.current = true; setJump(false); }}>Jump to latest</Button>}
   <Box ref={reader} tabIndex={0} aria-label="Log preview" onScroll={() => { const element = reader.current; if (!element)
        return; scrollPosition.current = element.scrollTop; atBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40; if (atBottom.current)
        setJump(false); }} sx={{ flex: expanded ? 1 : undefined, minHeight: expanded ? 180 : undefined, height: expanded ? undefined : 'max(300px, calc(100dvh - 380px))', overflow: 'auto', p: 1.5, bgcolor: '#14202b', color: '#edf4fa' }}>
     <Box component="pre" sx={{ m: 0, fontSize: 14, lineHeight: 1.55, fontFamily: 'Consolas, monospace', whiteSpace: wrap ? 'pre-wrap' : 'pre', overflowWrap: wrap ? 'anywhere' : 'normal' }}>{!selected ? 'Select a log file to read it.' : !data ? (previewLoading ? 'Loading preview…' : previewError ? 'Preview unavailable.' : 'No preview loaded.') : data.is_binary ? '' : content ? highlighted : 'This file is empty.'}</Box>
   </Box>
 </>;
    const parts = (current.archive ? current.entry : current.folder).split('/').filter(Boolean);
    return <Stack spacing={1}>
   <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
    <Breadcrumbs aria-label="Log folder" sx={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
    <Button onClick={() => browse(root)}>{source.label}</Button>{current.archive && <Button onClick={() => browse({ ...current, entry: '' })}>{current.archive.split('/').pop()}</Button>}{parts.map((part, index) => <Button key={index} onClick={() => browse(current.archive ? { ...current, entry: parts.slice(0, index + 1).join('/') } : { ...root, folder: parts.slice(0, index + 1).join('/') })}>{part}</Button>)}</Breadcrumbs>
    <Button disabled={!current.folder && !current.archive || listLoading} onClick={up}>Up</Button>
    <Button disabled={listLoading} onClick={() => setIntent(v => ({ location: current, query: listing?.query || v.query, revision: v.revision + 1 }))}>Refresh files</Button>
    </Stack>
   {listError && <Alert severity="error">{listError}{listing && ' Previous folder and results are retained. Refresh files to retry.'}</Alert>}
   <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start', '@container workspace (max-width: 899px)': { flexDirection: 'column' } }}>
     <Paper variant="outlined" sx={{ width: 360, maxWidth: '100%', minWidth: 0, flexShrink: 0, display: showFiles ? 'block' : 'none', '@container workspace (max-width: 899px)': { width: '100%', display: reading ? 'none' : 'block' } }}>
       <Box component="form" onSubmit={e => { e.preventDefault(); query({ search: search.trim() }); }} sx={{ display: 'flex', gap: 1, p: 1.5 }}>
    <TextField size="small" label="Find filenames in this folder" inputProps={{ maxLength: 200 }} value={search} onChange={e => setSearch(e.target.value)} sx={{ flex: 1 }}/>
    <Button type="submit">Search</Button>
    </Box>
       <Stack direction="row" gap={1} sx={{ px: 1.5, pb: 1 }}>
    <TextField select size="small" label="Sort" value={intent.query.sort_by} onChange={e => query({ sort_by: e.target.value })} sx={{ flex: 1 }}>{['name', 'modified', 'size'].map(value => <MenuItem key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</MenuItem>)}</TextField>
    <Button aria-label="Reverse file sort" onClick={() => query({ sort_direction: intent.query.sort_direction === 'asc' ? 'desc' : 'asc' })}>{intent.query.sort_direction === 'asc' ? 'Ascending' : 'Descending'}</Button>
    <Button onClick={() => setFiltersOpen(v => !v)}>Filters</Button>
    </Stack>
       {filtersOpen && <Stack spacing={1} sx={{ p: 1.5 }}>
        <TextField select size="small" label="File type" value={intent.query.file_type} onChange={e => query({ file_type: e.target.value })}>{['all', 'text', 'traces', 'archives'].map(type => <MenuItem key={type} value={type}>{type === 'text' ? 'Non-archive files' : type}</MenuItem>)}</TextField>
        <TextField size="small" type="date" label="Modified from" InputLabelProps={{ shrink: true }} value={intent.query.modified_from || ''} onChange={e => query({ modified_from: e.target.value || undefined })}/>
        <TextField size="small" type="date" label="Modified to" InputLabelProps={{ shrink: true }} value={intent.query.modified_to || ''} onChange={e => query({ modified_to: e.target.value || undefined })}/>
        <Button onClick={() => { setSearch(''); query({ ...defaults, limit: intent.query.limit }); }}>Clear filters and search</Button>
        </Stack>}
       {listLoading && <LinearProgress aria-label="Loading files"/>}
       <List aria-label="Log files" sx={{ maxHeight: 'max(260px, calc(100dvh - 365px))', overflowY: 'auto', overflowX: 'hidden' }}>{listing?.items.map(item => <ListItemButton key={item.entry_path || item.path || item.name} title={item.path || item.entry_path || item.name} selected={!item.is_directory && selected?.name === item.name && selected.archive === current.archive && selected.relative === join(current.folder, item.name)} onClick={() => openItem(item)}>
        <ListItemText primary={(item.is_directory ? '▸ ' : '') + item.name} primaryTypographyProps={{ sx: { overflowWrap: 'anywhere', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } }} secondary={item.is_directory ? 'Folder' : `${item.modified_date || 'Metadata unavailable'} · ${item.size_formatted || 'Unknown size'}`}/>
        </ListItemButton>)}{!listLoading && !listing?.items.length && <Typography sx={{ p: 2 }}>No files match this folder view.</Typography>}</List>
       <TablePagination component="div" count={listing?.total || 0} page={Math.max(0, (listing?.query.page || 1) - 1)} rowsPerPage={listing?.query.limit || 50} rowsPerPageOptions={[25, 50, 100]} onPageChange={(_, page) => query({ page: page + 1 })} onRowsPerPageChange={e => query({ limit: Number(e.target.value) })} sx={{ '& .MuiTablePagination-toolbar': { flexWrap: 'wrap', px: 1 }, '& .MuiTablePagination-spacer': { display: 'none' } }}/>
     </Paper>
     <Box sx={{ flex: 1, minWidth: 0, width: '100%', '@container workspace (max-width: 899px)': { display: reading ? 'block' : 'none' } }}>
       <Button sx={{ mb: 1, '@container workspace (max-width: 899px)': { display: 'none' } }} onClick={() => setShowFiles(v => !v)}>{showFiles ? 'Hide files' : 'Show files'}</Button>
    <Button sx={{ display: 'none', mb: 1, '@container workspace (max-width: 899px)': { display: 'inline-flex' } }} onClick={() => { setReading(false); setFollow(false); }}>Back to files</Button>
       {!expanded && <Paper variant="outlined" sx={{ overflow: 'hidden' }}>{readerBody}</Paper>}
     </Box>
   </Box>
   <Dialog fullScreen open={expanded} onClose={() => setExpanded(false)} PaperProps={{ 'aria-label': 'Expanded log preview' }} TransitionProps={{ onExited: () => expandButton.current?.focus() }}>{expanded && readerBody}</Dialog>
   <Dialog open={details} onClose={() => setDetails(false)} fullWidth maxWidth="sm">
    <DialogTitle>Log file details</DialogTitle>
    <DialogContent dividers>
    <Typography sx={{ overflowWrap: 'anywhere' }}>{pathLabel}</Typography>
    <Button onClick={() => navigator.clipboard.writeText(pathLabel).then(() => setCopied('Path copied')).catch(() => setCopied('Copy unavailable. Select and copy the path above.'))}>Copy path</Button>
    <Typography role="status">{copied}</Typography>
    <Typography>Encoding: {data?.encoding_used || 'Unknown'}</Typography>
    <Typography>Modified: {data?.modified_date || 'Unknown'}</Typography>
    <Typography>File size: {data?.file_size_formatted || data?.entry_size_formatted || 'Unknown'}</Typography>
    <Typography>Bytes scanned: {data?.bytes_scanned?.toLocaleString() || 0}</Typography>
    </DialogContent>
    <DialogActions>
    <Button onClick={() => setDetails(false)}>Close</Button>
    </DialogActions>
    </Dialog>
 </Stack>;
}
