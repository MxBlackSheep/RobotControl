import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { AppearanceProvider } from './context/AppearanceContext';

// Create QueryClient instance
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppearanceProvider>
          <App />
        </AppearanceProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
