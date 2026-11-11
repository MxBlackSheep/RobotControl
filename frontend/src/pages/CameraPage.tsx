import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Box, Typography, Button, Paper, Stack, LinearProgress, CircularProgress, Drawer, useMediaQuery } from '@mui/material';
import CameraControls, { type CameraSummary } from '../components/CameraControls';
import CameraViewport from '../components/CameraViewport';
import { createFrameStore } from '../components/LiveFrame';
import { useAuth } from '../context/AuthContext';
import { useModuleSection } from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import { DetailTitle, PageContent, PageHeader } from '../components/PageLayout';
import StatusChip from '../components/StatusChip';
import StatusDialog from '../components/StatusDialog';
import { api } from '@/services/api';
import { useLiveViewSocket } from '../hooks/useLiveViewSocket';
import { useRecordingDownload } from '../hooks/useRecordingDownload';
import VideoArchiveTab, { fileSize, type ExperimentFolder } from '../components/camera/VideoArchiveTab';
import { layout } from '../theme';

/**
 * Layout for the camera's four functions, each with its own owner: live view (useLiveViewSocket),
 * camera choice and health (CameraControls), the archive list (the one request below) and
 * downloads (useRecordingDownload).
 */
const CameraPage: React.FC = () => {
  const { user } = useAuth();
  const [currentTab] = useModuleSection('/camera', user);
  // Wide screens put the controls beside the image; narrower ones list them open below it.
  const sideBySide = useMediaQuery('(min-width:1200px)');
  // Phones open the controls in a bottom sheet from just under the picture instead of a disclosure
  // at the end of the page, which sat far from the image and partly behind the bottom page bar.
  // A phone upright or on its side: rotating must not move the controls between the sheet and the page
  // (that would remount them and drop an unsaved camera choice).
  const phone = useMediaQuery('(max-width:599.95px), (max-height:499.95px) and (pointer: coarse)');
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  // Leaving Live view or the phone layout closes the sheet, so it never reopens by itself on return.
  useEffect(() => { if (currentTab !== 0 || !phone) setSettingsSheetOpen(false); }, [currentTab, phone]);

  const frameStore = useMemo(createFrameStore, []);
  const [hasFrame, setHasFrame] = useState(false);
  const setCurrentFrame = useCallback((value: VideoFrame | null) => {
    const changedAvailability = Boolean(frameStore.getSnapshot()) !== Boolean(value);
    frameStore.set(value);
    if (changedAvailability) setHasFrame(Boolean(value));
  }, [frameStore]);
  const [cameraSummary, setCameraSummary] = useState<CameraSummary>({ text: 'Checking camera · Checking recording', error: null, recording: { label: 'Checking', tone: 'neutral' } });
  const handleSourceChange = useCallback(() => setCurrentFrame(null), [setCurrentFrame]);
  const live = useLiveViewSocket(setCurrentFrame);
  const download = useRecordingDownload();

  const [experimentFolders, setExperimentFolders] = useState<ExperimentFolder[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [archiveError, setArchiveError] = useState('');
  const loadRecordings = async () => {
    setArchiveLoading(true);
    setArchiveError('');
    try {
      const { data } = await api.get('/api/camera/recordings');
      setExperimentFolders(data.data?.experiment_folders || []);
    } catch (err) {
      console.error('Error loading experiment folders:', err);
      setArchiveError('Failed to load experiment folders');
    } finally {
      setArchiveLoading(false);
    }
  };
  // Only the archive section lists recordings.
  useEffect(() => {
    if (currentTab === 1) void loadRecordings();
  }, [currentTab]);

  // One instance owns camera polling and the viewer's summary; on a phone it lives in the sheet,
  // which keeps it mounted while closed.
  const cameraControls = <CameraControls active={currentTab === 0} admin={user?.role === 'admin'}
    onSourceChange={handleSourceChange} onSummaryChange={setCameraSummary} />;
  const closeSettingsSheet = () => setSettingsSheetOpen(false);
  const viewing = live.state !== 'idle';
  const progress = download.progress;

  return (
    <PageContent variant="inspection">
      <PageHeader title="Camera" />

      {/* The row's Download button is the retry. */}
      <StatusDialog
        status={download.error ? { title: 'Download failed', message: download.error, severity: 'error' } : null}
        onClose={download.clearError}
      />

      {progress && (
        <Paper sx={{ mb: 3, p: 2 }}>
          <Stack spacing={1.5}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
              <Typography variant="subtitle1" sx={{ wordBreak: 'break-word' }}>Downloading {progress.filename}</Typography>
              <Button size="small" color="warning" variant="outlined" onClick={download.cancel}>Cancel</Button>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {progress.total ? `${fileSize(progress.received)} / ${fileSize(progress.total)}` : `${fileSize(progress.received)} downloaded`}
              {progress.retrying ? ' · Reconnecting...' : ''}
            </Typography>
            <LinearProgress variant={progress.total ? 'determinate' : 'indeterminate'}
              value={progress.total ? Math.min(100, (progress.received / progress.total) * 100) : undefined} />
          </Stack>
        </Paper>
      )}

      <SectionPanel active={currentTab === 1}>
        <VideoArchiveTab
          experimentFolders={experimentFolders}
          loading={archiveLoading}
          error={archiveError}
          onRefresh={() => void loadRecordings()}
          onDownloadVideo={download.start}
          downloadingFilename={progress?.filename ?? null}
          downloadBusy={Boolean(progress)}
        />
      </SectionPanel>

      {/* The viewer owns display only; camera controls keep polling beside or below it. */}
      <SectionPanel active={currentTab === 0}>
        <Box sx={{ display: 'grid', gap: `${layout.gutter}px`, alignItems: 'start', gridTemplateColumns: sideBySide ? 'minmax(0, 1fr) 360px' : 'minmax(0, 1fr)' }}>
        <Box sx={{ minWidth: 0 }}>
        <CameraViewport
          store={frameStore}
          hasFrame={hasFrame}
          connection={live.unsupported ? 'unavailable' : live.state}
          summary={cameraSummary.text}
          inlineSummary={!sideBySide}
          error={live.unsupported || cameraSummary.error || live.error}
          controls={<>
            {/* Only an in-between state needs words: Start shows stopped, a moving picture shows connected,
                but a dropped view can still show its last (stale) picture. */}
            {viewing && live.state !== 'connected' && <StatusChip tone="neutral" label={`My view: ${live.state}`} />}
            {viewing ? <>
              <Button variant="outlined" onClick={live.stop} disabled={live.busy}>
                {live.busy ? <CircularProgress size={20} /> : 'Stop my live view'}
              </Button>
              <Button onClick={live.reconnect} disabled={live.busy}>Reconnect live view</Button>
            </> : <Button variant="contained" onClick={live.start} disabled={live.busy || Boolean(live.unsupported)}>
              {live.busy ? <CircularProgress size={20} /> : 'Start my live view'}
            </Button>}
          </>}
        />
        {phone && <>
          {/* The sheet's Modal returns focus to this button when it closes. */}
          <Button fullWidth variant="outlined" aria-haspopup="dialog" onClick={() => setSettingsSheetOpen(true)}
            sx={{ mt: `${layout.gutter}px`, minHeight: layout.touchRow, justifyContent: 'space-between', gap: 1 }}>
            Camera and recording
            <StatusChip tone={cameraSummary.recording.tone} label={cameraSummary.recording.label} />
          </Button>
          {/* Errors stay on the viewer's summary line too, so none is only inside a closed sheet. */}
          <Drawer anchor="bottom" open={settingsSheetOpen && currentTab === 0} onClose={closeSettingsSheet} ModalProps={{ keepMounted: true }}
            PaperProps={{ role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'camera-settings-sheet-title',
              sx: { borderTopLeftRadius: 16, borderTopRightRadius: 16, maxHeight: '85dvh', overflow: 'auto',
                px: `${layout.pagePhone}px`, pb: `calc(${layout.pagePhone}px + env(safe-area-inset-bottom))` } }}>
            <Box aria-hidden sx={{ width: 32, height: 4, borderRadius: 2, bgcolor: 'divider', mx: 'auto', mt: 1 }} />
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, py: 1 }}>
              <DetailTitle><span id="camera-settings-sheet-title">Camera and recording</span></DetailTitle>
              <Button onClick={closeSettingsSheet}>Done</Button>
            </Box>
            {cameraControls}
          </Drawer>
        </>}
        </Box>
        {!phone && <Box sx={{ minWidth: 0 }}>{cameraControls}</Box>}
        </Box>
      </SectionPanel>
    </PageContent>
  );
};

export default CameraPage;
