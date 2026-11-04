import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
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
