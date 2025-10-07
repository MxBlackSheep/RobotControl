/**
 * Example implementations of NavigationBreadcrumbs usage
 * This file demonstrates various use cases and configurations
 * 
 * NOTE: This is an example file for documentation purposes.
 * Import and use these patterns in actual components as needed.
 */

import React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import NavigationBreadcrumbs from '../NavigationBreadcrumbs';
import CompactBreadcrumbs from '../CompactBreadcrumbs';

// Example 1: Basic usage in a page header
export const PageHeaderExample: React.FC = () => (
  <Box sx={{ mb: 3 }}>
    <NavigationBreadcrumbs showIcons={true} maxItems={5} />
    <Typography variant="h4" sx={{ mt: 2 }}>
      Page Title
    </Typography>
  </Box>
);

// Example 2: Compact usage in a card or smaller section
export const CardHeaderExample: React.FC = () => (
  <Card>
    <CardContent>
      <CompactBreadcrumbs maxItems={3} />
      <Typography variant="h6" sx={{ mt: 1 }}>
        Section Content
      </Typography>
    </CardContent>
  </Card>
);

// Example 3: Custom styled breadcrumbs
export const CustomStyledExample: React.FC = () => (
  <Box sx={{ 
    bgcolor: 'primary.main',
    color: 'primary.contrastText',
    p: 2,
    borderRadius: 1
  }}>
    <NavigationBreadcrumbs 
      showIcons={false}
      compact={true}
      maxItems={4}
      separator="›"
    />
  </Box>
);

// Example 4: Integration in AdminPage sub-sections
export const AdminPageSubsectionExample: React.FC<{ title: string }> = ({ title }) => (
  <Box>
    <Box sx={{ mb: 2, pb: 1, borderBottom: 1, borderColor: 'divider' }}>
      <CompactBreadcrumbs />
    </Box>
    <Typography variant="h5" gutterBottom>
      {title}
    </Typography>
    {/* Page content would go here */}
  </Box>
);

// Usage patterns:
// 
// 1. In main App.tsx (already implemented):
//    <NavigationBreadcrumbs showIcons={true} maxItems={4} />
//
// 2. In individual pages for sub-navigation:
//    <CompactBreadcrumbs maxItems={3} />
//
// 3. In modal dialogs or sidebars:
//    <NavigationBreadcrumbs compact={true} showIcons={false} />
//
// 4. For mobile responsive design:
//    <NavigationBreadcrumbs compact={true} maxItems={2} />

export default {
  PageHeaderExample,
  CardHeaderExample,
  CustomStyledExample,
  AdminPageSubsectionExample,
};