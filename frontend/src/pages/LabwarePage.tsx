import { PageContent, PageHeader } from '../components/PageLayout';
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
    <PageContent>
      <PageHeader title="Labware" />

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
    </PageContent>
  );
};

export default LabwarePage;
