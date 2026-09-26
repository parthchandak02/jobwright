import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          ui: ['radix-ui', '@radix-ui/react-slot', 'lucide-react', 'sonner'],
          markdown: ['react-markdown', 'remark-gfm', 'remark-breaks'],
          dnd: ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
        },
      },
    },
  },
  server: {
    host: process.env.VITE_HOST ?? '127.0.0.1',
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.PORT ?? 8002}`,
        changeOrigin: true,
        timeout: 600_000,
      },
    },
    port: Number(process.env.VITE_PORT ?? 5120),
  },
})
