import React from 'react';
import { Box } from '@mui/material';
import { PageContent, PageHeader } from '../components/PageLayout';
import { useAuth } from '../context/AuthContext';
import { useModuleSection } from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import TipTrackingPanel from '../components/labware/TipTrackingPanel';
import CytomatPanel from '../components/labware/CytomatPanel';
export default function LabwarePage() {
  const {user} = useAuth();
  const [section] = useModuleSection('/labware', user);
  return <PageContent variant="spatial"><Box sx={{ maxWidth: section === 0 ? 2200 : 800, mx: 'auto' }}><PageHeader title="Labware" />
    <SectionPanel active={section === 0}><TipTrackingPanel active={section === 0} /></SectionPanel>
    <SectionPanel active={section === 1}><CytomatPanel active={section === 1} /></SectionPanel>
  </Box></PageContent>;
}
