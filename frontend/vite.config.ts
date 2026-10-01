import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig(({ mode }) => ({
  // dist/ is embedded in the packaged app and reachable through the remote tunnel, so source
  // maps and the bundle report are opt-in: SOURCEMAP=1, or `npm run bundle-analyze` (--mode analyze).
  plugins: [
    react(),
    ...(mode === 'analyze' ? [visualizer({
      filename: 'dist/bundle-analysis.html',
      open: false,
      gzipSize: true,
    })] : []),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3005,
    strictPort: true,
    open: true,
    cors: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://localhost:8005',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    outDir: 'dist',
    sourcemap: process.env.SOURCEMAP === '1',
    minify: 'esbuild',
    // Configure for unified port serving
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        // Simplified chunk splitting to avoid dependency issues
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-mui': ['@mui/material', '@emotion/react', '@emotion/styled'],
        },
      },
    },
  },
}));