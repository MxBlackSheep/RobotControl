/**
 * Skip Link Component for PyRobot
 * 
 * Provides a "skip to main content" link for keyboard users and screen readers
 * to quickly navigate past navigation elements.
 */

import React from 'react';
import { styled } from '@mui/material/styles';
import { Button } from '@mui/material';

const SkipLinkButton = styled(Button)(({ theme }) => ({
  position: 'absolute',
  top: -1000,
  left: 0,
  width: 'auto',
  height: 'auto',
  padding: theme.spacing(1, 2),
  backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText,
  fontSize: '1rem',
  fontWeight: 600,
  textDecoration: 'none',
  border: `2px solid ${theme.palette.primary.main}`,
  borderRadius: theme.shape.borderRadius,
  zIndex: 9999,
  
  '&:focus': {
    position: 'absolute',
    top: theme.spacing(1),
    left: theme.spacing(1),
    width: 'auto',
    height: 'auto',
    clip: 'auto',
  }
}));

interface SkipLinkProps {
  targetId?: string;
  text?: string;
}

const SkipLink: React.FC<SkipLinkProps> = ({ 
  targetId = 'main-content',
  text = 'Skip to main content'
}) => {
  const handleSkipToContent = (event: React.MouseEvent) => {
    event.preventDefault();
    
    const target = document.getElementById(targetId) || 
                  document.querySelector('main') || 
                  document.querySelector('[role="main"]');
    
    if (target) {
      target.focus();
      target.scrollIntoView();
      
      // Ensure the target is focusable
      if (!target.hasAttribute('tabindex')) {
        target.setAttribute('tabindex', '-1');
      }
    }
  };

  return (
    <SkipLinkButton
      onClick={handleSkipToContent}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleSkipToContent(e as any);
        }
      }}
    >
      {text}
    </SkipLinkButton>
  );
};

export default SkipLink;