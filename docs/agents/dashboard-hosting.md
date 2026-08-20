# jobwright Kanban dashboard hosting

Dashboard at `jobwright.parthchandak.info` (local API `:8002`, Vite HMR `:5120`).
Same ops shape as litreview: **PM2** for api + ui + tunnel, plus a simple `./scripts/restart.sh`.

## App surfaces (product)

The public URL is the **Kanban board**, not a separate app. Agents should treat these as first-class:

| Surface | Behavior |
|---------|----------|
| **Auto Search** | Full prep pipeline (`discover` → `enrich` → `score` → `portfolio` → `tailor` → `cover` → `docx` → `connect`). After score, backlog junk is pruned (score 1-3 and off-track below 7); human-held and Prepare+ cards are kept. Tailor batch defaults to `APPLY_PREP_LIMIT=25`. Progress + SSE logs live in `AutoSearchControls` so log ticks do not re-render Kanban cards. Closing the dialog does not stop the run; **Stop** sends SIGTERM/SIGKILL. Attaches to in-flight runs via `GET /api/runs` (`web_runs.json`). |
| **WhatsApp** | Header control next to Auto Search. One modal for daily brief time, WhatsApp target, pending job count, **Save** (`PUT /api/profile` writes `users.yaml` and edits existing `jobwright-brief-<user>` via `hermes cron edit`), and **Send now** (`POST /api/notify`). Does not create a missing cron. |
| **Profile** | `/profile`. Auto Search chips (daily/weekly queries, locations, excludes, boards) autosave on edit; resume PDF; cover-letter example PDFs. Identity stays in `profile.json`. |
| **Job drawer** | Summary, stage, job description, connections, materials. **Auto Tailor** starts `jobwright tailor-job` (`POST /api/jobs/{url}/tailor`) with defaults from `GET /api/tailor/defaults`. Click again while running to open logs. **Custom Tailor** edits instructions first. Shared progress UI: `RunProgressDialog`. Deep links: `/jobs/:jobId`. On mobile the drawer is a full-screen native scroller (opaque, no nested `ScrollArea` / glass blur) so WhatsApp in-app browser links stay scrollable. |
| **Apply** | Confirm gate on the card; never from cron. LinkedIn auto-apply blocked. |

Public traffic is the Cloudflare tunnel → `:8002` serving `frontend/dist`. Vite HMR (`:5120`) is local only. Rebuild production UI with `./scripts/restart.sh --prod-ui` (or `./scripts/dashboard_deploy.sh`).

## Local hot-reload (recommended for testing)

```bash
cd /Volumes/ExternalSSD/Projects/jobwright
pip install -e ".[web]"          # once
cd frontend && pnpm install && cd ..

# First time: copy PM2 config
cp ecosystem.config.example.js ecosystem.config.js

# Start / restart API (:8002, --reload) + Vite (:5120, HMR)
./scripts/restart.sh

# Open the hot-reloading UI
open http://127.0.0.1:5120
```

| Command | What it does |
|---------|----------------|
| `./scripts/restart.sh` | Restart `jobwright-api` + `jobwright-ui` |
| `./scripts/restart.sh --backend-only` | API only (after `src/` changes if not using `--reload`) |
| `./scripts/restart.sh --frontend-only` | Vite only |
| `./scripts/restart.sh --tunnel-only` | cloudflared only |
| `./scripts/restart.sh --all` | api + ui + tunnel |
| `./scripts/restart.sh --prod-ui` | `pnpm build` + restart API + health check |
| `./scripts/restart.sh --tmux` | **No PM2:** tmux session with uvicorn `--reload` + Vite |
| `./scripts/restart.sh --status` | `pm2 list` |
| `./scripts/restart.sh stop` | Stop PM2 apps |
| `./scripts/restart.sh stop --tmux` | Kill tmux session `jobwright-dash` |

Alias: `./scripts/ops_pm2.sh` → same script. Deploy helper: `./scripts/dashboard_deploy.sh` (= `--prod-ui`).

### Ports

| Service | Port | Notes |
|---------|------|--------|
| API | `8002` | litreview uses `8001` |
| Vite UI | `5120` | litreview uses `5173`; proxies `/api` → `8002` |
| Prod SPA | same `8002` | FastAPI serves `frontend/dist` after `--prod-ui` |

### Hot reload notes

- **Frontend:** Vite HMR on `:5120` updates instantly. Use this URL while developing.
- **Backend:** ecosystem example includes uvicorn `--reload`. After editing Python, wait a second for reload (or `./scripts/restart.sh --backend-only`).
- **Production URL** (`:8002` serving `dist/`): rebuild with `./scripts/restart.sh --prod-ui`.
- **Do not** restart `jobwright-ui` expecting the public site to update; PM2 `jobwright-ui` is dev-only. Public traffic hits `jobwright-api` + `frontend/dist`.

### tmux alternative (no PM2)

```bash
./scripts/restart.sh --tmux
tmux attach -t jobwright-dash   # windows: api | ui
./scripts/restart.sh stop --tmux
```

---

## Production: Cloudflare tunnel + Zero Trust

### 1. Create tunnel + DNS

```bash
cloudflared tunnel create jobwright
cloudflared tunnel route dns jobwright jobwright.parthchandak.info
```

### 2. Project tunnel config

```bash
cp cloudflared-config-jobwright.example.yml cloudflared-config-jobwright.yml
# Edit tunnel UUID + credentials-file under ~/.cloudflared/
```

### 3. PM2 (prod)

For production, edit `ecosystem.config.js` and **remove `--reload`** from `jobwright-api` args. Prefer not running `jobwright-ui` in prod (API serves `frontend/dist`).

```bash
./scripts/restart.sh start          # or: pm2 start ecosystem.config.js
./scripts/restart.sh --prod-ui      # build + restart api + health
pm2 save
# Optional tunnel:
./scripts/restart.sh --tunnel-only
```

### 4. Cloudflare Zero Trust (dashboard only)

1. Zero Trust → Access → Applications → Self-hosted
2. Domain: `jobwright.parthchandak.info`
3. Policy: Allow + email OTP (same as litreview)

### 5. Verify

```bash
curl -sf http://127.0.0.1:8002/api/health
# Browser: https://jobwright.parthchandak.info  → email OTP → Kanban
# Or local HMR: http://127.0.0.1:5120
```

---

## Process names

| PM2 name | Role |
|----------|------|
| `jobwright-api` | FastAPI / uvicorn `:8002` |
| `jobwright-ui` | Vite dev `:5120` (local only) |
| `jobwright-tunnel` | cloudflared → `jobwright.parthchandak.info` |
