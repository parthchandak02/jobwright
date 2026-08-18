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
  server: {
    host: '0.0.0.0',
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
