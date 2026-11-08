import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  define: { __APP_BUILD__: JSON.stringify({ build_id: 'test', sha: 'test', built_at: '2026-01-01T00:00:00Z' }) },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    // tokenContrast.test.ts reads index.css with `?raw`; Vitest blanks CSS it doesn't process.
    css: { include: [/index\.css/] },
  },
})
