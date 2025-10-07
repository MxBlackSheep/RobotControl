/**
 * PyRobot Database Backup/Restore API Client
 * 
 * Provides a type-safe client for backup and restore operations.
 * Handles API communication, error handling, and response transformation.
 * 
 * CRITICAL: This API client addresses the common axios response.data vs response.data.data 
 * issue by properly handling the standardized API response format from the backend.
 */

import { AxiosResponse } from 'axios';
import { api } from './api';
import {
  BackupInfo,
  BackupResult,
  RestoreResult,
  BackupDetails,
  DeleteBackupResult,
  CreateBackupRequest,
  ApiResponse,
  BackupListResponse,
  BackupCreateResponse,
  BackupDetailsResponse,
  RestoreResponse,
  DeleteResponse,
  BackupHealthStatus,
  BackupHealthResponse,
  BackupError,
  isApiResponse
} from '../types/backup';

/**
 * Custom error class for backup API errors
 */
export class BackupApiError extends Error {
  constructor(
    message: string,
    public code: string = 'BACKUP_API_ERROR',
    public details?: string,
    public statusCode?: number
  ) {
    super(message);
    this.name = 'BackupApiError';
  }
}

/**
 * Backup API client class
 * 
 * Provides methods for all backup and restore operations with comprehensive
 * error handling and response validation.
 */
export class BackupApiClient {
  private readonly baseUrl = '/api/admin/backup';

  /**
   * Handle API response and extract data properly
   * 
   * CRITICAL: This method ensures we handle the standardized API response format
   * correctly to prevent the axios response.data vs response.data.data confusion.
   */
  private handleApiResponse<T>(response: AxiosResponse<ApiResponse<T>>): T {
    const responseData = response.data;
    
    // Validate response structure
    if (!isApiResponse(responseData)) {
      throw new BackupApiError(
        'Invalid API response format',
        'INVALID_RESPONSE',
        `Expected ApiResponse structure but got: ${JSON.stringify(responseData)}`
      );
    }

    if (!responseData.success) {
      throw new BackupApiError(
        responseData.message || 'API operation failed',
        'API_OPERATION_FAILED',
        JSON.stringify(responseData),
        response.status
      );
    }

    return responseData.data;
  }

  /**
   * Handle API errors and transform them into BackupApiError
   */
  private handleApiError(error: any): never {
    if (error instanceof BackupApiError) {
      throw error;
    }

    // Handle axios errors
    if (error.response) {
      const status = error.response.status;
      const responseData = error.response.data;
      
      // Try to extract error message from response
      let message = 'An error occurred during backup operation';
      let details = '';
      
      if (responseData && typeof responseData === 'object') {
        if (responseData.message) {
          message = responseData.message;
        }
        if (responseData.detail) {
          details = responseData.detail;
        }
        details = details || JSON.stringify(responseData);
      }

      // Handle specific HTTP status codes
      switch (status) {
        case 401:
          throw new BackupApiError('Authentication required', 'AUTH_REQUIRED', details, status);
        case 403:
          throw new BackupApiError('Admin access required for backup operations', 'ACCESS_DENIED', details, status);
        case 404:
          throw new BackupApiError('Backup resource not found', 'NOT_FOUND', details, status);
        case 500:
          throw new BackupApiError('Internal server error during backup operation', 'SERVER_ERROR', details, status);
        default:
          throw new BackupApiError(message, 'HTTP_ERROR', details, status);
      }
    } else if (error.request) {
      // Network error
      throw new BackupApiError(
        'Network error: Unable to connect to backup service',
        'NETWORK_ERROR',
        error.message
      );
    } else {
      // Other error
      throw new BackupApiError(
        'Unexpected error during backup operation',
        'UNKNOWN_ERROR',
        error.message
      );
    }
  }

  /**
   * Create a new database backup
   */
  async createBackup(description: string): Promise<BackupResult> {
    try {
      const request: CreateBackupRequest = { description };
      const response: AxiosResponse<BackupCreateResponse> = await api.post(
        `${this.baseUrl}/create`,
        request
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Get list of all available backups
   */
  async listBackups(): Promise<BackupInfo[]> {
    try {
      const response: AxiosResponse<BackupListResponse> = await api.get(
        `${this.baseUrl}/list`
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Get detailed information about a specific backup
   */
  async getBackupDetails(filename: string): Promise<BackupDetails> {
    try {
      const response: AxiosResponse<BackupDetailsResponse> = await api.get(
        `${this.baseUrl}/${encodeURIComponent(filename)}/details`
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Restore database from backup file
   * 
   * WARNING: This operation will temporarily make the database unavailable
   */
  async restoreBackup(filename: string): Promise<RestoreResult> {
    try {
      const response: AxiosResponse<RestoreResponse> = await api.post(
        `${this.baseUrl}/restore/${encodeURIComponent(filename)}`
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Delete backup file and associated metadata
   */
  async deleteBackup(filename: string): Promise<DeleteBackupResult> {
    try {
      const response: AxiosResponse<DeleteResponse> = await api.delete(
        `${this.baseUrl}/${encodeURIComponent(filename)}`
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Get backup service health status
   */
  async getHealthStatus(): Promise<BackupHealthStatus> {
    try {
      const response: AxiosResponse<BackupHealthResponse> = await api.get(
        `${this.baseUrl}/health`
      );
      
      return this.handleApiResponse(response);
    } catch (error) {
      this.handleApiError(error);
    }
  }

  /**
   * Validate backup filename format
   */
  validateBackupFilename(filename: string): { isValid: boolean; errors: string[] } {
    const errors: string[] = [];
    
    if (!filename) {
      errors.push('Filename cannot be empty');
    }
    
    if (filename && !filename.endsWith('.bak')) {
      errors.push('Backup filename must end with .bak extension');
    }
    
    if (filename && filename.includes('/')) {
      errors.push('Filename cannot contain path separators');
    }
    
    if (filename && filename.includes('\\')) {
      errors.push('Filename cannot contain path separators');
    }
    
    if (filename && filename.includes('..')) {
      errors.push('Filename cannot contain directory traversal sequences');
    }
    
    const forbiddenChars = ['<', '>', ':', '"', '|', '?', '*'];
    const foundForbiddenChars = forbiddenChars.filter(char => filename.includes(char));
    if (foundForbiddenChars.length > 0) {
      errors.push(`Filename contains forbidden characters: ${foundForbiddenChars.join(', ')}`);
    }
    
    return {
      isValid: errors.length === 0,
      errors
    };
  }

  /**
   * Validate backup description
   */
  validateDescription(description: string): { isValid: boolean; errors: string[] } {
    const errors: string[] = [];
    
    if (!description || description.trim().length === 0) {
      errors.push('Description cannot be empty');
    }
    
    if (description && description.length > 1000) {
      errors.push('Description cannot exceed 1000 characters');
    }
    
    return {
      isValid: errors.length === 0,
      errors
    };
  }
}

// Create singleton instance
const backupApiClient = new BackupApiClient();

// Export singleton instance as default
export default backupApiClient;

// Export individual API functions for convenience
export const backupAPI = {
  /**
   * Create a new database backup
   */
  createBackup: (description: string): Promise<BackupResult> =>
    backupApiClient.createBackup(description),

  /**
   * Get list of all available backups
   */
  listBackups: (): Promise<BackupInfo[]> =>
    backupApiClient.listBackups(),

  /**
   * Get detailed information about a specific backup
   */
  getBackupDetails: (filename: string): Promise<BackupDetails> =>
    backupApiClient.getBackupDetails(filename),

  /**
   * Restore database from backup file
   */
  restoreBackup: (filename: string): Promise<RestoreResult> =>
    backupApiClient.restoreBackup(filename),

  /**
   * Delete backup file and associated metadata
   */
  deleteBackup: (filename: string): Promise<DeleteBackupResult> =>
    backupApiClient.deleteBackup(filename),

  /**
   * Get backup service health status
   */
  getHealthStatus: (): Promise<BackupHealthStatus> =>
    backupApiClient.getHealthStatus(),

  /**
   * Validate backup filename format
   */
  validateFilename: (filename: string) =>
    backupApiClient.validateBackupFilename(filename),

  /**
   * Validate backup description
   */
  validateDescription: (description: string) =>
    backupApiClient.validateDescription(description),
};

// Re-export types for convenience
export type {
  BackupInfo,
  BackupResult,
  RestoreResult,
  BackupDetails,
  DeleteBackupResult,
  BackupHealthStatus,
  BackupError
} from '../types/backup';