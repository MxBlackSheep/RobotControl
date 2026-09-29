import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { AppearanceProvider } from './context/AppearanceContext';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppearanceProvider>
        <App />
      </AppearanceProvider>
    </BrowserRouter>
  </React.StrictMode>
);
