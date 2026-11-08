import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { execSync } from 'node:child_process'
import path from 'path'

type BuildInfo = { build_id: string; sha: string; built_at: string }

/** Which build this is: git short sha + build time. Embedded as __APP_BUILD__ and written to
 *  dist/version.json, which GET /api/version reports so open tabs know a new version is ready. */
function buildInfo(): BuildInfo {
  let sha = process.env.JOBWRIGHT_BUILD_SHA?.slice(0, 7) || ''
  if (!sha) {
    try {
      sha = execSync('git rev-parse --short=7 HEAD', { cwd: __dirname, stdio: ['ignore', 'pipe', 'ignore'] })
        .toString()
        .trim()
    } catch {
      sha = 'unknown'
    }
  }
  const builtAt = new Date().toISOString()
  return { build_id: `${sha}-${Date.parse(builtAt).toString(36)}`, sha, built_at: builtAt }
}

function versionStamp(info: BuildInfo): Plugin {
  return {
    name: 'jobwright-version-stamp',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify(info) + '\n' })
    },
  }
}

export default defineConfig(({ command }) => {
  // The dev server never offers a refresh: its build id is "dev".
  const info: BuildInfo =
    command === 'serve' ? { build_id: 'dev', sha: 'dev', built_at: new Date().toISOString() } : buildInfo()
  return {
    define: { __APP_BUILD__: JSON.stringify(info) },
    plugins: [react(), tailwindcss(), versionStamp(info)],
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
          // Forward the browser's address so dev auth can tell local from LAN callers.
          xfwd: true,
          timeout: 600_000,
        },
      },
      port: Number(process.env.VITE_PORT ?? 5120),
    },
  }
})
