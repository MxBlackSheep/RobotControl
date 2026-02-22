import React, { useState } from 'react';
import {
  Box,
  Button,
  Container,
  Paper,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Science as LabwareIcon,
  ViewModule as TipTrackingIcon,
  TableChart as CytomatIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

import TipTrackingPanel from '../components/labware/TipTrackingPanel';
import CytomatPanel from '../components/labware/CytomatPanel';

interface TabPanelProps {
  children?: React.ReactNode;
  value: number;
  index: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <div role="tabpanel" hidden={value !== index}>
    {value === index && (
      <Box sx={{ pt: 2 }}>
        {children}
      </Box>
    )}
  </div>
);

const LabwarePage: React.FC = () => {
  const navigate = useNavigate();
  const [tabIndex, setTabIndex] = useState(0);

  return (
    <Container
      maxWidth="xl"
      sx={{
        mt: { xs: 2, md: 4 },
        mb: { xs: 2, md: 4 },
        px: { xs: 1, sm: 2 },
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          mb: 2,
          flexWrap: 'wrap',
        }}
      >
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/')}
          sx={{ minHeight: { xs: 44, sm: 36 } }}
        >
          Back
        </Button>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <LabwareIcon color="primary" />
          <Typography variant="h5">Labware</Typography>
        </Box>
      </Box>

      <Paper sx={{ p: 1.5 }}>
        <Tabs
          value={tabIndex}
          onChange={(_, newValue) => setTabIndex(newValue)}
          aria-label="labware module tabs"
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
        >
          <Tab icon={<TipTrackingIcon />} iconPosition="start" label="TipTracking" />
          <Tab icon={<CytomatIcon />} iconPosition="start" label="Cytomat" />
        </Tabs>
      </Paper>

      <TabPanel value={tabIndex} index={0}>
        <TipTrackingPanel />
      </TabPanel>
      <TabPanel value={tabIndex} index={1}>
        <CytomatPanel />
      </TabPanel>
    </Container>
  );
};

export default LabwarePage;
