
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.API_KEY': JSON.stringify(process.env.API_KEY),
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV),
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      external: [
        'react',
        'react-dom',
        'recharts',
        'lucide-react',
        '@google/genai'
      ],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
          recharts: 'Recharts',
          'lucide-react': 'Lucide',
          '@google/genai': 'GoogleGenAI'
        }
      }
    }
  },
});
