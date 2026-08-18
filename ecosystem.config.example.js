const path = require('path')

// Resolved automatically from repo root; copy to ecosystem.config.js (gitignored).
const PROJECT_DIR = path.resolve(__dirname)

// Production vs development:
// - Production: jobwright-api serves frontend/dist on port 8002. Do NOT run jobwright-ui
//   under PM2 in production. Deploy: ./scripts/restart.sh --prod-ui
// - Development: start jobwright-ui for Vite on 5120 (HMR); API on 8002.
//   Vite proxies /api → 8002. Open http://127.0.0.1:5120
//
// Port notes: litreview uses 8001 + 5173; jobwright uses 8002 + 5120.

const RESTART_POLICY = {
  autorestart: true,
  watch: false,
  min_uptime: '10s',
  max_restarts: 15,
  restart_delay: 4000,
  exp_backoff_restart_delay: 100,
  kill_timeout: 8000,
  listen_timeout: 15000,
}

const API_RESTART_POLICY = {
  ...RESTART_POLICY,
  kill_timeout: 45000,
}

// Prefer venv uvicorn when present; else python3 -m uvicorn.
const fs = require('fs')
const venvUvicorn = `${PROJECT_DIR}/.venv/bin/uvicorn`
const useVenv = fs.existsSync(venvUvicorn)

const apiApp = useVenv
  ? {
      script: venvUvicorn,
      args: 'jobwright.web.app:app --host 127.0.0.1 --port 8002 --reload',
      interpreter: 'none',
    }
  : {
      script: 'python3',
      args: '-m uvicorn jobwright.web.app:app --host 127.0.0.1 --port 8002 --reload',
      interpreter: 'none',
    }

module.exports = {
  apps: [
    {
      name: 'jobwright-api',
      // --reload: local hot-reload for Python. Remove for production PM2.
      ...apiApp,
      cwd: PROJECT_DIR,
      exec_mode: 'fork',
      env: {
        PORT: '8002',
        JOBWRIGHT_DASHBOARD_USER: 'richa',
        PYTHONPATH: `${PROJECT_DIR}/src`,
        JOBWRIGHT_CORS_ORIGINS:
          'http://127.0.0.1:5120,http://localhost:5120,http://127.0.0.1:8002,http://localhost:8002',
      },
      max_memory_restart: '1G',
      error_file: `${process.env.HOME}/.cloudflared/jobwright-error.log`,
      out_file: `${process.env.HOME}/.cloudflared/jobwright.log`,
      ...API_RESTART_POLICY,
    },
    {
      name: 'jobwright-tunnel',
      script: '/opt/homebrew/bin/cloudflared',
      args: `tunnel --config ${PROJECT_DIR}/cloudflared-config-jobwright.yml run`,
      cwd: PROJECT_DIR,
      error_file: `${process.env.HOME}/.pm2/logs/jobwright-tunnel-error.log`,
      out_file: `${process.env.HOME}/.pm2/logs/jobwright-tunnel-out.log`,
      max_memory_restart: '512M',
      ...RESTART_POLICY,
    },
    {
      name: 'jobwright-ui',
      // Dev-only Vite (HMR). Omit in production when API serves frontend/dist.
      script: `${PROJECT_DIR}/frontend/node_modules/.bin/vite`,
      args: '--port 5120 --host 0.0.0.0',
      cwd: `${PROJECT_DIR}/frontend`,
      interpreter: 'none',
      exec_mode: 'fork',
      env: { PORT: '8002' },
      autorestart: false,
      watch: false,
    },
  ],
}
