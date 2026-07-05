import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        // Suppress ECONNREFUSED noise during backend startup window
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code !== 'ECONNREFUSED') console.error('[ws proxy]', err.message);
          });
        },
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
