/**
 * HOC for Runtime Prop Validation
 * 
 * Higher-order component that adds runtime validation to React components
 * Useful for development-time prop validation beyond TypeScript
 */

import React from 'react';
import { validateComponentProps } from './validation';
import type { ValidationSchema } from '../types';

/**
 * Higher-order component that adds runtime prop validation
 */
export function withPropValidation<TProps extends Record<string, any>>(
  WrappedComponent: React.ComponentType<TProps>,
  schema: ValidationSchema<TProps>,
  options: {
    displayName?: string;
    strict?: boolean; // Throw errors instead of just logging warnings
  } = {}
) {
  const { displayName, strict = false } = options;
  const componentName = displayName || WrappedComponent.displayName || WrappedComponent.name || 'Component';

  const ValidatedComponent: React.FC<TProps> = (props) => {
    if (import.meta.env.DEV) {
      try {
        validateComponentProps(componentName, props, schema);
      } catch (error) {
        if (strict) {
          throw new Error(`${componentName} prop validation failed: ${error}`);
        } else {
          console.warn(`${componentName} prop validation failed:`, error);
        }
      }
    }

    return <WrappedComponent {...props} />;
  };

  ValidatedComponent.displayName = `withPropValidation(${componentName})`;

  return ValidatedComponent;
}

/**
 * Utility for creating typed prop validation schemas
 */
export function createPropSchema<T extends Record<string, any>>(): {
  schema: <K extends keyof T>(schema: ValidationSchema<Pick<T, K>>) => ValidationSchema<Pick<T, K>>;
  validate: <K extends keyof T>(component: React.ComponentType<Pick<T, K>>) => 
    (schema: ValidationSchema<Pick<T, K>>, options?: { displayName?: string; strict?: boolean }) => 
    React.ComponentType<Pick<T, K>>;
} {
  return {
    schema: <K extends keyof T>(schema: ValidationSchema<Pick<T, K>>) => schema,
    validate: <K extends keyof T>(component: React.ComponentType<Pick<T, K>>) => 
      (schema: ValidationSchema<Pick<T, K>>, options?) => 
      withPropValidation(component, schema, options)
  };
}

/**
 * Example usage and schema definitions
 */

// Example schemas for common components
export const CommonSchemas = {
  button: {
    onClick: { required: false, type: 'function' as const },
    disabled: { required: false, type: 'boolean' as const },
    variant: { 
      required: false, 
      type: 'string' as const,
      custom: (value: string) => {
        const validVariants = ['text', 'outlined', 'contained'];
        return validVariants.includes(value) ? null : `Variant must be one of: ${validVariants.join(', ')}`;
      }
    }
  },

  input: {
    value: { required: true, type: 'string' as const },
    onChange: { required: true, type: 'function' as const },
    placeholder: { required: false, type: 'string' as const, maxLength: 100 },
    disabled: { required: false, type: 'boolean' as const }
  },

  modal: {
    open: { required: true, type: 'boolean' as const },
    onClose: { required: true, type: 'function' as const },
    title: { required: false, type: 'string' as const, maxLength: 200 }
  }
} satisfies Record<string, ValidationSchema<any>>;

/**
 * Decorator for class components (if needed)
 */
export function PropValidation<TProps extends Record<string, any>>(
  schema: ValidationSchema<TProps>,
  options?: { strict?: boolean }
) {
  return function <T extends React.ComponentType<TProps>>(target: T): T {
    const originalRender = target.prototype.render;
    
    target.prototype.render = function() {
      if (import.meta.env.DEV) {
        try {
          validateComponentProps(target.name, this.props, schema);
        } catch (error) {
          if (options?.strict) {
            throw new Error(`${target.name} prop validation failed: ${error}`);
          } else {
            console.warn(`${target.name} prop validation failed:`, error);
          }
        }
      }
      
      return originalRender.call(this);
    };
    
    return target;
  };
}

/**
 * Hook for runtime prop validation within functional components
 */
export function usePropValidation<TProps extends Record<string, any>>(
  componentName: string,
  props: TProps,
  schema: ValidationSchema<TProps>
) {
  React.useEffect(() => {
    if (import.meta.env.DEV) {
      validateComponentProps(componentName, props, schema);
    }
  }, [componentName, props, schema]);
}

/**
 * Type-safe prop validation for specific component types
 */
export const TypedValidation = {
  // For components with loading states
  asyncComponent: <T extends { loading?: boolean; error?: string }>(
    component: React.ComponentType<T>
  ) => withPropValidation(component, {
    loading: { required: false, type: 'boolean' as const },
    error: { required: false, type: 'string' as const }
  }),

  // For form components
  formField: <T extends { value: any; onChange: (value: any) => void }>(
    component: React.ComponentType<T>
  ) => withPropValidation(component, {
    value: { required: true },
    onChange: { required: true, type: 'function' as const }
  }),

  // For data display components
  dataComponent: <T extends { data: any[] }>(
    component: React.ComponentType<T>
  ) => withPropValidation(component, {
    data: { required: true, type: 'array' as const }
  })
};