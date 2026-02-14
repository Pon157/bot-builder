import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Добавляем проверку, чтобы сборка не падала, если переменные не заданы
    'process.env.API_KEY': JSON.stringify(process.env.API_KEY || ''),
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // ВАЖНО: Мы полностью удалили rollupOptions с external. 
    // Теперь Vite упакует React, Lucide и Recharts прямо в твой локальный файл.
  },
});
