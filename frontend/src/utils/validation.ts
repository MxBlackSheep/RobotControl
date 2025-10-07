/**
 * Runtime Validation Utilities
 * 
 * Provides runtime validation for TypeScript interfaces
 * Works with the component type definitions for comprehensive type safety
 */

import type { ValidationSchema, ValidationResult } from '../types';

/**
 * Validate data against a schema
 */
export function validateData<T extends Record<string, any>>(
  data: T,
  schema: ValidationSchema<T>
): ValidationResult {
  const errors: Record<string, string> = {};

  for (const [key, rules] of Object.entries(schema) as [keyof T, any][]) {
    const value = data[key];
    const fieldName = String(key);

    // Required validation
    if (rules.required && (value === undefined || value === null || value === '')) {
      errors[fieldName] = `${fieldName} is required`;
      continue;
    }

    // Skip further validation if value is empty and not required
    if (!rules.required && (value === undefined || value === null || value === '')) {
      continue;
    }

    // Type validation
    if (rules.type) {
      const actualType = Array.isArray(value) ? 'array' : typeof value;
      if (actualType !== rules.type) {
        errors[fieldName] = `${fieldName} must be of type ${rules.type}`;
        continue;
      }
    }

    // String validations
    if (typeof value === 'string') {
      if (rules.minLength && value.length < rules.minLength) {
        errors[fieldName] = `${fieldName} must be at least ${rules.minLength} characters`;
      }
      if (rules.maxLength && value.length > rules.maxLength) {
        errors[fieldName] = `${fieldName} must be no more than ${rules.maxLength} characters`;
      }
      if (rules.pattern && !rules.pattern.test(value)) {
        errors[fieldName] = `${fieldName} format is invalid`;
      }
    }

    // Number validations
    if (typeof value === 'number') {
      if (rules.min !== undefined && value < rules.min) {
        errors[fieldName] = `${fieldName} must be at least ${rules.min}`;
      }
      if (rules.max !== undefined && value > rules.max) {
        errors[fieldName] = `${fieldName} must be no more than ${rules.max}`;
      }
    }

    // Custom validation
    if (rules.custom) {
      const customError = rules.custom(value);
      if (customError) {
        errors[fieldName] = customError;
      }
    }
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors
  };
}

/**
 * Common validation schemas for PyRobot components
 */
export const ValidationSchemas = {
  // User authentication
  loginCredentials: {
    username: {
      required: true,
      type: 'string' as const,
      minLength: 1,
      maxLength: 50
    },
    password: {
      required: true,
      type: 'string' as const,
      minLength: 1
    }
  },

  // Schedule creation
  scheduleForm: {
    name: {
      required: true,
      type: 'string' as const,
      minLength: 1,
      maxLength: 100
    },
    experiment_name: {
      required: true,
      type: 'string' as const,
      minLength: 1,
      maxLength: 100
    },
    start_time: {
      required: true,
      type: 'string' as const,
      custom: (value: string) => {
        const date = new Date(value);
        if (isNaN(date.getTime())) {
          return 'Invalid date format';
        }
        if (date < new Date()) {
          return 'Start time must be in the future';
        }
        return null;
      }
    },
    interval_minutes: {
      type: 'number' as const,
      min: 1,
      max: 10080 // 7 days
    },
    repeat_count: {
      required: true,
      type: 'number' as const,
      min: 1,
      max: 1000
    },
    priority: {
      required: true,
      type: 'string' as const,
      custom: (value: string) => {
        if (!['low', 'medium', 'high'].includes(value)) {
          return 'Priority must be low, medium, or high';
        }
        return null;
      }
    }
  },

  // Camera settings
  cameraInfo: {
    name: {
      required: true,
      type: 'string' as const,
      minLength: 1,
      maxLength: 50
    },
    url: {
      required: true,
      type: 'string' as const,
      pattern: /^https?:\/\/.+/
    },
    fps: {
      required: true,
      type: 'number' as const,
      min: 1,
      max: 60
    }
  },

  // Database connection
  databaseConnection: {
    server: {
      required: true,
      type: 'string' as const,
      minLength: 1
    },
    database: {
      required: true,
      type: 'string' as const,
      minLength: 1
    }
  }
} satisfies Record<string, ValidationSchema<any>>;

/**
 * Validate component props at runtime (for development)
 */
export function validateComponentProps<T extends Record<string, any>>(
  componentName: string,
  props: T,
  schema: ValidationSchema<T>
): T {
  if (import.meta.env.DEV) {
    const validation = validateData(props, schema);
    if (!validation.isValid) {
      console.warn(
        `Component ${componentName} received invalid props:`,
        validation.errors
      );
    }
  }
  return props;
}

/**
 * Type guard utilities
 */
export const TypeGuards = {
  isNonEmpty: <T>(value: T | null | undefined): value is T => {
    return value !== null && value !== undefined;
  },

  isString: (value: any): value is string => {
    return typeof value === 'string';
  },

  isNumber: (value: any): value is number => {
    return typeof value === 'number' && !isNaN(value);
  },

  isBoolean: (value: any): value is boolean => {
    return typeof value === 'boolean';
  },

  isArray: <T>(value: any): value is T[] => {
    return Array.isArray(value);
  },

  isObject: (value: any): value is Record<string, any> => {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  },

  hasProperty: <T extends object, K extends string | number | symbol>(
    obj: T,
    prop: K
  ): obj is T & Record<K, unknown> => {
    return prop in obj;
  }
};

/**
 * API response validation
 */
export function validateApiResponse<T>(
  response: any,
  dataValidator?: (data: any) => data is T
): response is { success: boolean; data?: T; error?: string } {
  if (!TypeGuards.isObject(response)) {
    return false;
  }

  if (!TypeGuards.hasProperty(response, 'success') || !TypeGuards.isBoolean(response.success)) {
    return false;
  }

  if (response.success && response.data && dataValidator) {
    return dataValidator(response.data);
  }

  return true;
}

/**
 * Email validation
 */
export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/**
 * URL validation
 */
export const isValidUrl = (url: string): boolean => {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
};

/**
 * Date validation utilities
 */
export const DateValidation = {
  isValidDate: (dateString: string): boolean => {
    const date = new Date(dateString);
    return !isNaN(date.getTime());
  },

  isInFuture: (dateString: string): boolean => {
    const date = new Date(dateString);
    return date > new Date();
  },

  isInPast: (dateString: string): boolean => {
    const date = new Date(dateString);
    return date < new Date();
  },

  formatForInput: (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  }
};