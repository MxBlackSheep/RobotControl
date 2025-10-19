/**
 * LiveCamerasTab Component Tests
 * 
 * Tests for the refactored live cameras management component
 * Validates camera display, status handling, and user interactions
 */

import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { renderWithTheme, mockCameraInfo } from '../../../utils/test-utils';
import LiveCamerasTab from '../LiveCamerasTab';
import type { CameraInfo } from '../LiveCamerasTab';

const mockCameras: CameraInfo[] = [
  {
    ...mockCameraInfo,
    id: 'camera1',
    name: 'Camera 1',
    status: 'online'
  },
  {
    ...mockCameraInfo,
    id: 'camera2',
    name: 'Camera 2',
    status: 'offline'
  },
  {
    ...mockCameraInfo,
    id: 'camera3',
    name: 'Camera 3',
    status: 'error',
    error_message: 'Connection timeout'
  }
];

describe('LiveCamerasTab', () => {
  const defaultProps = {
    cameras: mockCameras,
    loading: false,
    error: '',
    onRefresh: jest.fn(),
    onShowStatus: jest.fn()
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Camera display', () => {
    it('renders all cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('Camera 1')).toBeInTheDocument();
      expect(screen.getByText('Camera 2')).toBeInTheDocument();
      expect(screen.getByText('Camera 3')).toBeInTheDocument();
    });

    it('shows camera status chips', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('online')).toBeInTheDocument();
      expect(screen.getByText('offline')).toBeInTheDocument();
      expect(screen.getByText('error')).toBeInTheDocument();
    });

    it('displays camera details', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('Resolution: 1920x1080')).toBeInTheDocument();
      expect(screen.getByText('FPS: 30')).toBeInTheDocument();
    });

    it('shows error message for failed cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('Error: Connection timeout')).toBeInTheDocument();
    });

    it('displays last frame time when available', () => {
      const camerasWithFrameTime = mockCameras.map(camera => ({
        ...camera,
        last_frame_time: '2024-01-01T12:00:00Z'
      }));
      
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps} 
          cameras={camerasWithFrameTime} 
        />
      );
      
      // Should show formatted time
      expect(screen.getAllByText(/Last Frame:/)).toHaveLength(3);
    });
  });

  describe('Status indicators', () => {
    it('shows green icon for online cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      const cameraIcons = screen.getAllByTestId(/videocam-icon/i);
      expect(cameraIcons[0]).toHaveStyle({ color: 'success.main' });
    });

    it('shows red icon for offline/error cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      const cameraIcons = screen.getAllByTestId(/videocam-icon/i);
      expect(cameraIcons[1]).toHaveStyle({ color: 'error.main' });
      expect(cameraIcons[2]).toHaveStyle({ color: 'error.main' });
    });

    it('shows appropriate status chip colors', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      const onlineChip = screen.getByText('online');
      const offlineChip = screen.getByText('offline');
      const errorChip = screen.getByText('error');
      
      expect(onlineChip).toHaveClass(/success/i);
      expect(offlineChip).toHaveClass(/error/i);
      expect(errorChip).toHaveClass(/error/i);
    });
  });

  describe('Camera feed display', () => {
    it('shows live feed placeholder for online cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('Live Feed: Camera 1')).toBeInTheDocument();
    });

    it('shows offline message for offline cameras', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('Camera Offline')).toBeInTheDocument();
    });

    it('applies correct styling to feed containers', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      const feedContainers = screen.getAllByTestId(/camera-feed/i);
      feedContainers.forEach(container => {
        expect(container).toHaveStyle({
          width: '100%',
          height: '200px'
        });
      });
    });
  });

  describe('User interactions', () => {
    it('calls onRefresh when refresh button is clicked', async () => {
      const onRefresh = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <LiveCamerasTab {...defaultProps} onRefresh={onRefresh} />
      );
      
      const refreshButton = screen.getByText('Refresh Cameras');
      await user.click(refreshButton);
      
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });

    it('calls onShowStatus when info button is clicked', async () => {
      const onShowStatus = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <LiveCamerasTab {...defaultProps} onShowStatus={onShowStatus} />
      );
      
      const infoButtons = screen.getAllByLabelText(/camera info/i);
      await user.click(infoButtons[0]);
      
      expect(onShowStatus).toHaveBeenCalledTimes(1);
    });

    it('calls onCameraSettings when settings button is clicked', async () => {
      const onCameraSettings = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps} 
          onCameraSettings={onCameraSettings} 
        />
      );
      
      const settingsButtons = screen.getAllByLabelText(/camera settings/i);
      await user.click(settingsButtons[0]);
      
      expect(onCameraSettings).toHaveBeenCalledWith(mockCameras[0]);
    });

    it('disables refresh button while loading', () => {
      renderWithTheme(
        <LiveCamerasTab {...defaultProps} loading={true} />
      );
      
      const refreshButton = screen.getByText(/refresh/i);
      expect(refreshButton).toBeDisabled();
    });
  });

  describe('Error handling', () => {
    it('shows error alert when error prop is provided', () => {
      const errorMessage = 'Failed to load cameras';
      
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps} 
          error={errorMessage}
        />
      );
      
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('shows retry button in error state', async () => {
      const onRefresh = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps}
          error="Connection failed"
          onRefresh={onRefresh}
        />
      );
      
      const retryButton = screen.getByText(/retry/i);
      await user.click(retryButton);
      
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  describe('Empty state', () => {
    it('shows empty state when no cameras', () => {
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps} 
          cameras={[]}
        />
      );
      
      expect(screen.getByText('No cameras detected')).toBeInTheDocument();
      expect(screen.getByText(/ensure cameras are connected/i)).toBeInTheDocument();
    });

    it('shows check again button in empty state', async () => {
      const onRefresh = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps}
          cameras={[]}
          onRefresh={onRefresh}
        />
      );
      
      const checkButton = screen.getByText('Check Again');
      await user.click(checkButton);
      
      expect(onRefresh).toHaveBeenCalled();
    });

    it('shows loading spinner in check again button when loading', () => {
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps}
          cameras={[]}
          loading={true}
        />
      );
      
      expect(screen.getByTestId(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Loading states', () => {
    it('shows loading spinner while refreshing', () => {
      renderWithTheme(
        <LiveCamerasTab {...defaultProps} loading={true} />
      );
      
      expect(screen.getByTestId(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Responsive behavior', () => {
    it('renders camera cards in responsive grid', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      // Camera cards should be in a grid container
      const gridContainer = screen.getByTestId(/camera-grid/i);
      expect(gridContainer).toBeInTheDocument();
    });

    it('adjusts card content for mobile view', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 400
      });
      
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      // Typography should use smaller variants on mobile
      const cameraNames = screen.getAllByText(/Camera \d+/);
      cameraNames.forEach(name => {
        expect(name).toHaveClass(/subtitle2|h6/i);
      });
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels for interactive elements', () => {
      renderWithTheme(
        <LiveCamerasTab 
          {...defaultProps} 
          onCameraSettings={jest.fn()} 
        />
      );
      
      expect(screen.getAllByLabelText(/camera settings/i)).toHaveLength(3);
      expect(screen.getAllByLabelText(/camera info/i)).toHaveLength(3);
    });

    it('has semantic card structure', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      // Each camera should be in a card
      const cards = screen.getAllByRole('region');
      expect(cards.length).toBeGreaterThanOrEqual(3);
    });

    it('provides descriptive text for camera status', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getByText('online')).toHaveAttribute('title');
      expect(screen.getByText('offline')).toHaveAttribute('title');
      expect(screen.getByText('error')).toHaveAttribute('title');
    });
  });

  describe('Integration scenarios', () => {
    it('handles mixed camera states correctly', () => {
      renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      // Should show all three different states
      expect(screen.getByText('Live Feed: Camera 1')).toBeInTheDocument();
      expect(screen.getByText('Camera Offline')).toBeInTheDocument();
      expect(screen.getByText('Error: Connection timeout')).toBeInTheDocument();
    });

    it('updates display when camera list changes', () => {
      const { rerender } = renderWithTheme(<LiveCamerasTab {...defaultProps} />);
      
      expect(screen.getAllByText(/Camera \d+/)).toHaveLength(3);
      
      // Update with fewer cameras
      rerender(
        <LiveCamerasTab 
          {...defaultProps} 
          cameras={[mockCameras[0]]} 
        />
      );
      
      expect(screen.getAllByText(/Camera \d+/)).toHaveLength(1);
      expect(screen.getByText('Camera 1')).toBeInTheDocument();
    });
  });
});
