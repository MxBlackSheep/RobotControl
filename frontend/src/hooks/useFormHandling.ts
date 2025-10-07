/**
 * useFormHandling Hook - Comprehensive form state management and validation
 * 
 * Provides standardized form handling with validation, submission states, and error management
 * Integrates with existing PyRobot patterns for consistent form behavior
 */

import { useState, useCallback, useMemo } from 'react';
import { useErrorHandling } from './useErrorHandling';

export interface FormField<T = any> {
  value: T;
  error?: string;
  touched?: boolean;
  required?: boolean;
  validator?: (value: T) => string | null;
}

export interface FormState<T extends Record<string, any>> {
  fields: { [K in keyof T]: FormField<T[K]> };
  isValid: boolean;
  isDirty: boolean;
  isSubmitting: boolean;
  hasErrors: boolean;
  touchedFields: (keyof T)[];
}

export interface UseFormOptions<T> {
  /** Initial form values */
  initialValues: T;
  /** Field validation rules */
  validators?: Partial<{ [K in keyof T]: (value: T[K]) => string | null }>;
  /** Required field specifications */
  requiredFields?: (keyof T)[];
  /** Enable real-time validation */
  validateOnChange?: boolean;
  /** Validate only after first blur */
  validateOnBlur?: boolean;
  /** Auto-submit after validation passes */
  autoSubmit?: boolean;
  /** Custom submit handler */
  onSubmit?: (values: T) => Promise<void> | void;
}

/**
 * Custom hook for comprehensive form management
 */
export const useFormHandling = <T extends Record<string, any>>(
  options: UseFormOptions<T>
) => {
  const {
    initialValues,
    validators = {} as UseFormOptions<T>['validators'],
    requiredFields = [],
    validateOnChange = false,
    validateOnBlur = true,
    autoSubmit = false,
    onSubmit
  } = options;

  const errorHandler = useErrorHandling({
    contextPrefix: 'Form Validation',
    autoCategorize: true
  });

  const buildFields = useCallback((values: T): FormState<T>['fields'] => {
    const fields: Partial<FormState<T>['fields']> = {};

    (Object.keys(values) as Array<keyof T>).forEach((key) => {
      const typedKey = key as keyof T;
      fields[typedKey] = {
        value: values[typedKey],
        error: undefined,
        touched: false,
        required: requiredFields.includes(typedKey),
        validator: validators[typedKey],
      } as FormField<T[typeof typedKey]>;
    });

    return fields as FormState<T>['fields'];
  }, [requiredFields, validators]);

  // Initialize form state
  const [formState, setFormState] = useState<FormState<T>>(() => ({
    fields: buildFields(initialValues),
    isValid: true,
    isDirty: false,
    isSubmitting: false,
    hasErrors: false,
    touchedFields: []
  }));

  // Validate a single field
  const validateField = useCallback((fieldName: keyof T, value: T[keyof T]): string | null => {
    const field = formState.fields[fieldName];
    
    // Required field validation
    if (field.required && (value === null || value === undefined || value === '')) {
      return `${String(fieldName)} is required`;
    }

    // Custom validator
    if (field.validator) {
      return field.validator(value);
    }

    return null;
  }, [formState.fields]);

  // Validate all fields
  const validateForm = useCallback((): boolean => {
    let hasErrors = false;
    const updatedFields = { ...formState.fields };

    for (const fieldName of Object.keys(updatedFields) as Array<keyof T>) {
      const field = updatedFields[fieldName];
      const error = validateField(fieldName, field.value);
      
      updatedFields[fieldName] = {
        ...field,
        error
      };

      if (error) hasErrors = true;
    }

    setFormState(prev => ({
      ...prev,
      fields: updatedFields,
      hasErrors,
      isValid: !hasErrors
    }));

    return !hasErrors;
  }, [formState.fields, validateField]);

  // Update field value
  const setFieldValue = useCallback(<K extends keyof T>(
    fieldName: K,
    value: T[K],
    shouldValidate: boolean = validateOnChange
  ) => {
    setFormState(prev => {
      const field = prev.fields[fieldName];
      const error = shouldValidate ? validateField(fieldName, value) : field.error;
      
      const updatedFields = {
        ...prev.fields,
        [fieldName]: {
          ...field,
          value,
          error
        }
      };

      const hasErrors = Object.values(updatedFields).some(f => f.error !== undefined && f.error !== null);
      
      return {
        ...prev,
        fields: updatedFields,
        isDirty: true,
        hasErrors,
        isValid: !hasErrors
      };
    });
  }, [validateField, validateOnChange]);

  // Mark field as touched
  const setFieldTouched = useCallback((fieldName: keyof T, shouldValidate: boolean = validateOnBlur) => {
    setFormState(prev => {
      if (prev.touchedFields.includes(fieldName)) return prev;

      const field = prev.fields[fieldName];
      const error = shouldValidate ? validateField(fieldName, field.value) : field.error;

      const updatedFields = {
        ...prev.fields,
        [fieldName]: {
          ...field,
          touched: true,
          error
        }
      };

      const hasErrors = Object.values(updatedFields).some(f => f.error !== undefined && f.error !== null);

      return {
        ...prev,
        fields: updatedFields,
        touchedFields: [...prev.touchedFields, fieldName],
        hasErrors,
        isValid: !hasErrors
      };
    });
  }, [validateField, validateOnBlur]);

  // Set field error manually
  const setFieldError = useCallback((fieldName: keyof T, error: string | null) => {
    setFormState(prev => ({
      ...prev,
      fields: {
        ...prev.fields,
        [fieldName]: {
          ...prev.fields[fieldName],
          error
        }
      },
      hasErrors: error !== null
    }));
  }, []);

  // Get current form values
  const getValues = useCallback((): T => {
    const values = {} as T;
    for (const fieldName of Object.keys(formState.fields) as Array<keyof T>) {
      values[fieldName] = formState.fields[fieldName].value as T[typeof fieldName];
    }
    return values;
  }, [formState.fields]);

  // Reset form to initial state
  const resetForm = useCallback(() => {
    setFormState({
      fields: buildFields(initialValues),
      isValid: true,
      isDirty: false,
      isSubmitting: false,
      hasErrors: false,
      touchedFields: []
    });

    errorHandler.clearError();
  }, [initialValues, buildFields, errorHandler]);

  // Submit form
  const submitForm = useCallback(async () => {
    if (!onSubmit) return;

    const isValid = validateForm();
    if (!isValid) {
      errorHandler.handleError('Please correct the errors in the form', 'Form Validation');
      return;
    }

    setFormState(prev => ({ ...prev, isSubmitting: true }));

    try {
      await onSubmit(getValues());
      if (autoSubmit) {
        resetForm();
      }
    } catch (error) {
      errorHandler.handleError(error, 'Form Submission');
    } finally {
      setFormState(prev => ({ ...prev, isSubmitting: false }));
    }
  }, [onSubmit, validateForm, getValues, autoSubmit, resetForm, errorHandler]);

  // Get field props for easy input binding
  const getFieldProps = useCallback((fieldName: keyof T) => {
    const field = formState.fields[fieldName];
    
    return {
      name: String(fieldName),
      value: field.value,
      error: field.touched ? field.error : undefined,
      required: field.required,
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const value = e.target.type === 'checkbox' 
          ? (e.target as HTMLInputElement).checked as T[keyof T]
          : e.target.value as T[keyof T];
        setFieldValue(fieldName, value);
      },
      onBlur: () => setFieldTouched(fieldName),
      helperText: field.touched ? field.error : undefined
    };
  }, [formState.fields, setFieldValue, setFieldTouched]);

  // Computed values
  const computedValues = useMemo(() => ({
    values: getValues(),
    errors: Object.fromEntries(
      Object.entries(formState.fields)
        .filter(([, field]) => field.error)
        .map(([name, field]) => [name, field.error])
    ) as Partial<{ [K in keyof T]: string }>,
    touchedFields: formState.touchedFields
  }), [formState.fields, formState.touchedFields, getValues]);

  return {
    // State
    ...formState,
    ...computedValues,
    
    // Actions
    setFieldValue,
    setFieldTouched,
    setFieldError,
    validateField,
    validateForm,
    submitForm,
    resetForm,
    getFieldProps,
    
    // Error handling
    formError: errorHandler.currentError,
    clearFormError: errorHandler.clearError
  };
};

/**
 * Simplified hook for basic forms with common patterns
 */
export const useSimpleForm = <T extends Record<string, string | number | boolean>>(
  initialValues: T,
  onSubmit: (values: T) => Promise<void> | void
) => {
  return useFormHandling({
    initialValues,
    validateOnChange: false,
    validateOnBlur: true,
    onSubmit
  });
};

/**
 * Hook for search forms with debouncing
 */
export const useSearchForm = <T extends Record<string, any>>(
  initialValues: T,
  onSearch: (values: T) => Promise<void> | void,
  debounceMs: number = 300
) => {
  const form = useFormHandling({
    initialValues,
    validateOnChange: true,
    onSubmit: onSearch
  });

  // Debounced search
  const [searchTimeout, setSearchTimeout] = useState<ReturnType<typeof setTimeout> | undefined>();

  const debouncedSearch = useCallback((values: T) => {
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    const timeout = setTimeout(() => {
      onSearch(values);
    }, debounceMs);

    setSearchTimeout(timeout);
  }, [onSearch, debounceMs, searchTimeout]);

  // Override setFieldValue to trigger debounced search
  const originalSetFieldValue = form.setFieldValue;
  const setFieldValue = useCallback(<K extends keyof T>(
    fieldName: K,
    value: T[K],
    shouldValidate?: boolean
  ) => {
    originalSetFieldValue(fieldName, value, shouldValidate);
    debouncedSearch({ ...form.values, [fieldName]: value });
  }, [originalSetFieldValue, debouncedSearch, form.values]);

  return {
    ...form,
    setFieldValue
  };
};