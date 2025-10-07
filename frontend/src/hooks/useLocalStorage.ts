/**
 * useLocalStorage Hook - Persistent state management with localStorage
 * 
 * Provides React state synchronized with localStorage for user preferences
 * Includes type safety, error handling, and automatic serialization
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface UseLocalStorageOptions<T> {
  /** Default value if key doesn't exist */
  defaultValue?: T;
  /** Enable automatic serialization (default: true) */
  serialize?: boolean;
  /** Custom serializer function */
  serializer?: {
    serialize: (value: T) => string;
    deserialize: (value: string) => T;
  };
  /** Sync with other tabs/windows */
  syncAcrossTabs?: boolean;
  /** Prefix for localStorage keys */
  keyPrefix?: string;
}

/**
 * Custom hook for synchronized localStorage state management
 */
export const useLocalStorage = <T>(
  key: string,
  options: UseLocalStorageOptions<T> = {}
) => {
  const {
    defaultValue,
    serialize = true,
    serializer,
    syncAcrossTabs = true,
    keyPrefix = 'pyrobot_'
  } = options;

  const prefixedKey = keyPrefix + key;
  const isInitialized = useRef(false);

  // Default serializer
  const defaultSerializer = {
    serialize: (value: T) => JSON.stringify(value),
    deserialize: (value: string) => JSON.parse(value)
  };

  const actualSerializer = serializer || defaultSerializer;

  // Read from localStorage
  const readFromStorage = useCallback((): T | undefined => {
    try {
      const item = window.localStorage.getItem(prefixedKey);
      if (item === null) return defaultValue;
      
      return serialize 
        ? actualSerializer.deserialize(item)
        : (item as unknown as T);
    } catch (error) {
      console.warn(`Error reading localStorage key "${prefixedKey}":`, error);
      return defaultValue;
    }
  }, [prefixedKey, defaultValue, serialize, actualSerializer]);

  // Initialize state
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === 'undefined') {
      return defaultValue as T;
    }
    return readFromStorage() as T;
  });

  // Write to localStorage
  const setValue = useCallback((value: T | ((val: T) => T)) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);

      const serializedValue = serialize
        ? actualSerializer.serialize(valueToStore)
        : (valueToStore as unknown as string);

      window.localStorage.setItem(prefixedKey, serializedValue);

      // Dispatch custom event for cross-tab synchronization
      if (syncAcrossTabs) {
        window.dispatchEvent(new CustomEvent('localStorage-change', {
          detail: { key: prefixedKey, value: valueToStore }
        }));
      }
    } catch (error) {
      console.warn(`Error setting localStorage key "${prefixedKey}":`, error);
    }
  }, [prefixedKey, storedValue, serialize, actualSerializer, syncAcrossTabs]);

  // Remove from localStorage
  const removeValue = useCallback(() => {
    try {
      window.localStorage.removeItem(prefixedKey);
      setStoredValue(defaultValue as T);

      if (syncAcrossTabs) {
        window.dispatchEvent(new CustomEvent('localStorage-change', {
          detail: { key: prefixedKey, value: null }
        }));
      }
    } catch (error) {
      console.warn(`Error removing localStorage key "${prefixedKey}":`, error);
    }
  }, [prefixedKey, defaultValue, syncAcrossTabs]);

  // Listen for changes in other tabs
  useEffect(() => {
    if (!syncAcrossTabs || typeof window === 'undefined') return;

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === prefixedKey && e.newValue !== null) {
        try {
          const newValue = serialize
            ? actualSerializer.deserialize(e.newValue)
            : (e.newValue as unknown as T);
          setStoredValue(newValue);
        } catch (error) {
          console.warn(`Error parsing localStorage change for "${prefixedKey}":`, error);
        }
      }
    };

    const handleCustomEvent = (e: CustomEvent) => {
      if (e.detail.key === prefixedKey) {
        setStoredValue(e.detail.value ?? defaultValue);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('localStorage-change', handleCustomEvent as EventListener);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('localStorage-change', handleCustomEvent as EventListener);
    };
  }, [prefixedKey, serialize, actualSerializer, syncAcrossTabs, defaultValue]);

  // Initialize from storage on mount
  useEffect(() => {
    if (!isInitialized.current && typeof window !== 'undefined') {
      const initialValue = readFromStorage();
      if (initialValue !== undefined) {
        setStoredValue(initialValue);
      }
      isInitialized.current = true;
    }
  }, [readFromStorage]);

  return [storedValue, setValue, removeValue] as const;
};

/**
 * Specialized hook for boolean preferences
 */
export const useLocalStorageBoolean = (
  key: string,
  defaultValue: boolean = false,
  options: Omit<UseLocalStorageOptions<boolean>, 'defaultValue'> = {}
) => {
  return useLocalStorage(key, { ...options, defaultValue });
};

/**
 * Specialized hook for string preferences
 */
export const useLocalStorageString = (
  key: string,
  defaultValue: string = '',
  options: Omit<UseLocalStorageOptions<string>, 'defaultValue'> = {}
) => {
  return useLocalStorage(key, { ...options, defaultValue });
};

/**
 * Specialized hook for number preferences
 */
export const useLocalStorageNumber = (
  key: string,
  defaultValue: number = 0,
  options: Omit<UseLocalStorageOptions<number>, 'defaultValue'> = {}
) => {
  return useLocalStorage(key, { ...options, defaultValue });
};

/**
 * Hook for managing user preferences with predefined structure
 */
export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  tablePageSize: number;
  showImportantTablesOnly: boolean;
  autoRefreshInterval: number;
  enableNotifications: boolean;
  compactView: boolean;
  language: string;
}

const defaultPreferences: UserPreferences = {
  theme: 'system',
  tablePageSize: 25,
  showImportantTablesOnly: true,
  autoRefreshInterval: 30000,
  enableNotifications: true,
  compactView: false,
  language: 'en'
};

export const useUserPreferences = () => {
  const [preferences, setPreferences, removePreferences] = useLocalStorage<UserPreferences>(
    'user_preferences',
    { defaultValue: defaultPreferences }
  );

  const updatePreference = useCallback(<K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K]
  ) => {
    setPreferences(prev => ({ ...prev, [key]: value }));
  }, [setPreferences]);

  const resetPreferences = useCallback(() => {
    setPreferences(defaultPreferences);
  }, [setPreferences]);

  return {
    preferences,
    setPreferences,
    updatePreference,
    resetPreferences,
    removePreferences
  };
};