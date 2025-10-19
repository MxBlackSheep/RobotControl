import React from 'react';

import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';

import { Public as PublicIcon } from '@mui/icons-material';

const GITHUB_URL = 'https://github.com/MxBlackSheep/Shou_OrchestrationSoftware';

const AboutPage: React.FC = () => {
  return (
    <Container
      maxWidth="lg"
      sx={{
        py: { xs: 3, md: 4 },
        px: { xs: 2, md: 3 },
      }}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: { xs: 2.5, md: 3 },
        }}
      >
        <Typography variant="h4" fontWeight={700}>
          About
        </Typography>

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
      </Box>
    </Container>
  );
};

export default AboutPage;
