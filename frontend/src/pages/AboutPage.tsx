import { PageContent, PageHeader } from '../components/PageLayout';
import React from 'react';

import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';

import { Public as PublicIcon } from '@mui/icons-material';

const GITHUB_URL = 'https://github.com/MxBlackSheep/Shou_OrchestrationSoftware';

const AboutPage: React.FC = () => {
  return (
    <PageContent reading>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: { xs: 2.5, md: 3 },
        }}
      >
        <PageHeader title="About" />

        <Card sx={{ width: '100%' }}>
          <CardContent
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              alignItems: { xs: 'flex-start', md: 'center' },
              justifyContent: 'space-between',
              gap: { xs: 2, md: 3 },
              py: { xs: 3, md: 4 },
            }}
          >
            <Box sx={{ maxWidth: 520 }}>
              <Typography variant="h5" gutterBottom>
                Project Repository
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Latest sources and issue tracking are maintained on GitHub.
              </Typography>
            </Box>
            <Button
              variant="contained"
              color="primary"
              startIcon={<PublicIcon />}
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ minHeight: 48 }}
            >
              View Repository
            </Button>
          </CardContent>
        </Card>

        {/* LGPL notice for the bundled encoder; keep the build name in step with build_scripts/fetch_ffmpeg.py. */}
        <Card sx={{ width: '100%' }}>
          <CardContent sx={{ py: { xs: 3, md: 4 } }}>
            <Typography variant="h5" gutterBottom>
              Open-source components
            </Typography>
            <Typography variant="body2" color="text.secondary">
              RobotControl includes FFmpeg (build n9.0.2-17, LGPL 3.0) with OpenH264 (BSD) as
              ffmpeg.exe beside RobotControl.exe, for camera live view. Licences, source locations
              and build details are in the THIRD_PARTY_NOTICES folder of the installation.
            </Typography>
          </CardContent>
        </Card>
      </Box>
    </PageContent>
  );
};

export default AboutPage;
