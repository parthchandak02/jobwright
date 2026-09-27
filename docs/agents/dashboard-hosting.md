# jobwright Kanban dashboard hosting

Dashboard at `jobwright.parthchandak.info` (local API `:8002`, Vite HMR `:5120`).
Same ops shape as litreview: **PM2** for api + ui + tunnel, plus a simple `./scripts/restart.sh`.

## App surfaces (product)

The public URL is the **Kanban board**, not a separate app. Agents should treat these as first-class:

| Surface | Behavior |
|---------|----------|
| **Auto Search** | Full prep pipeline (`discover` → `enrich` → `score` → `portfolio` → `tailor` → `cover` → `docx` → `connect`). After score, backlog junk is pruned (score 1-3 and off-track below 7); human-held and Prepare+ cards are kept. Tailor batch defaults to `APPLY_PREP_LIMIT=25`. Progress + SSE logs live in `AutoSearchControls` so log ticks do not re-render Kanban cards. Closing the dialog does not stop the run; **Stop** sends SIGTERM/SIGKILL. Attaches to in-flight runs via `GET /api/runs` (`web_runs.json`). |
| **WhatsApp** | Header control next to Auto Search opens `DailyBriefDialog`: pending job count, next send, **Send now** (`POST /api/notify`), and "Change chat or time" → `/profile?tab=whatsapp`. There, `WhatsAppChatPicker` (`GET /api/whatsapp/chats`; admins see every chat Hermes can post to, others only chats that include their phone) with a test message (`POST /api/whatsapp/test`) and the brief time; **Save** (`PUT /api/profile`) writes `users.yaml` and creates or edits `jobwright-brief-<user>` (`--no-agent --deliver local`). |
| **Profile** | `/profile`. Auto Search chips (daily/weekly queries, locations, excludes, boards) autosave on edit; resume PDF; cover-letter example PDFs; **WhatsApp** tab (chat picker, test message, brief time); **Match rules** (`CriteriaEditor`, `GET`/`PUT /api/criteria`, "Suggest from my ratings" `POST /api/criteria/suggest`). Identity stays in `profile.json`. |
| **Job drawer** | Summary, `MatchExplanation` (gates, fit, confidence, reasoning), `RateJob` (thumbs + reason chips → append-only label), `StagePicker`, `DismissDialog` ("Not for me" asks why → label), job description, connections, materials. **Auto Tailor** starts `jobwright tailor-job` (`POST /api/jobs/{url}/tailor`) with defaults from `GET /api/tailor/defaults`. Click again while running to open logs. **Custom Tailor** edits instructions first. Shared progress UI: `RunProgressDialog`. Deep links: `/jobs/:jobId`. On mobile the drawer is a full-screen native scroller (opaque, no nested `ScrollArea` / glass blur) so WhatsApp in-app browser links stay scrollable. |
| **Apply** | Confirm gate on the card; never from cron. LinkedIn auto-apply blocked. |
| **Onboarding** | `/welcome` (`AppGate` sends logins with no profile here): create profile bound to the login email, upload resume, review the LLM draft (profile, searches, match criteria), confirm, then WhatsApp chat + time (`/api/onboarding/*`). |
| **Match quality** | `/quality`: ratings count, sent-and-advanced rate, latest eval, token use; run eval / rescore (`/api/quality/*`). |
| **Admin** | `/admin` (admins only): profiles with emails, human gate, notify cap, brief health; admins list; `ops_target`; create watchdog cron; send test alert (`/api/admin/*`). |
| **Profile switcher / status** | `ProfileSwitcher` lists profiles this login may open (`GET /api/me`, `POST /api/session`). `StatusBanner` shows a failed last run, an ops warning, or WhatsApp bridge down (`GET /api/status`). |

Public traffic is the Cloudflare tunnel → `:8002` serving `frontend/dist`. Vite HMR (`:5120`) is local only. Rebuild production UI with `./scripts/restart.sh --prod-ui` (or `./scripts/dashboard_deploy.sh`).

## Local hot-reload (recommended for testing)

```bash
cd "$JOBWRIGHT_REPO"
pip install -e ".[web]"          # once
cd frontend && pnpm install && cd ..

# First time: copy PM2 config
cp ecosystem.config.example.js ecosystem.config.js

# Dev: tmux with API --reload (JOBWRIGHT_AUTH_MODE=dev, JOBWRIGHT_HERMES_DRY_RUN=1) + Vite (:5120, HMR)
./scripts/restart.sh --tmux
# or PM2 (uses ecosystem.config.js; prod-like, auth cloudflare, no --reload)
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
| `./scripts/restart.sh --tmux` | **No PM2:** tmux session with uvicorn `--reload` (dev auth, Hermes dry-run) + Vite |
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
- **Backend:** `--tmux` runs uvicorn `--reload`. The PM2 ecosystem example does not (production); after editing Python there, `./scripts/restart.sh --backend-only`.
- **Auth locally:** `--tmux` sets `JOBWRIGHT_AUTH_MODE=dev`; you are an anonymous admin unless `JOBWRIGHT_DEV_EMAIL` is set (use it to test a non-admin login). Dev mode refuses requests that carry Cloudflare headers.
- **Sandboxes/worktrees:** keep `JOBWRIGHT_HERMES_DRY_RUN=1` so saving a schedule or a test send never touches real Hermes crons or WhatsApp. Vite binds `127.0.0.1` (override with `VITE_HOST`).
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

The ecosystem example runs `jobwright-api` **without `--reload`** and with `JOBWRIGHT_AUTH_MODE=cloudflare`. Put `JOBWRIGHT_CF_TEAM_DOMAIN` and `JOBWRIGHT_CF_AUD` in the repo `.env`. Prefer not running `jobwright-ui` in prod (API serves `frontend/dist`). Run prod from a dedicated checkout on the internal disk (recommended `/Users/parthchandak/apps/jobwright`), never from a working tree agents edit; the external SSD holds backups only (`JOBWRIGHT_BACKUP_DIR`).

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
3. Policy: Allow + email OTP (same as litreview). **Every user's email must be allowed** (automatic with the allowlist sync below); the app then maps the email to a profile via `users.yaml` `emails`
4. Copy the application **AUD tag** into `JOBWRIGHT_CF_AUD` and the team domain (`<team>.cloudflareaccess.com`) into `JOBWRIGHT_CF_TEAM_DOMAIN`. The API verifies `Cf-Access-Jwt-Assertion` (RS256, team JWKS, audience, issuer); a missing or invalid token is 401, a missing config is 503
5. **Session duration:** set Application session to **30 days** (`720h`) so household devices re-auth monthly, not daily. Dashboard: Application → Configure → Session Duration. CLI (requires `CLOUDFLARE_API_TOKEN` with Access edit):

```bash
source ~/.hermes/.env
cloudflare-pp-cli accounts access applications-update-an-application \
  <app_id> "$CLOUDFLARE_ACCOUNT_ID" \
  --body-json '{"type":"self_hosted","name":"jobwright","domain":"jobwright.parthchandak.info","session_duration":"720h","app_launcher_visible":false,"destinations":[{"type":"public","uri":"jobwright.parthchandak.info"}],"allowed_idps":["<idp_id>"]}' \
  --agent --yes
```

Optional: Zero Trust → Settings → Authentication → Global session duration → match (7–30d). WhatsApp in-app browser uses a separate cookie jar; users may OTP once per in-app context even with 30d app session.

#### Allowlist sync (`jobwright access`)

jobwright owns one allow policy on the Access app, named **`jobwright users`**, and keeps its include list equal to every `users.yaml` profile email plus admins (lowercased, deduped). Other policies are read for reporting and never modified.

- Env: `CLOUDFLARE_API_TOKEN` (Account → Access: Apps and Policies → Edit) and `CLOUDFLARE_ACCOUNT_ID` (falls back to the `accountID` in `~/.cloudflared/cert.pem`; its embedded token is never used). The app is found by `JOBWRIGHT_CF_AUD`, else by `JOBWRIGHT_CF_HOSTNAME` (default `jobwright.parthchandak.info`).
- `jobwright access status` prints current / desired / add / remove and emails allowed by other policies. `jobwright access sync` is a dry-run diff; `--yes` applies (creates the policy after the existing ones if missing). An empty desired list is refused.
- Dashboard: Admin → Cloudflare Access card (`GET /api/admin/access`, `POST /api/admin/access/sync`). Changing a profile's emails, the admin list, or creating a profile (admin or `/welcome`) triggers a best-effort sync when the token is set; the response carries `access_sync` and the request never fails because of it.
- Removing an email from `jobwright users` does not revoke access if another allow policy still includes it (see `other_policies_emails`).

### 5. Verify

```bash
curl -sf http://127.0.0.1:8002/api/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/api/me   # 401 in cloudflare mode (no token)
# Browser: https://jobwright.parthchandak.info  → email OTP → your profile (or /welcome for a new email)
# Or local HMR: http://127.0.0.1:5120
```

---

## Process names

| PM2 name | Role |
|----------|------|
| `jobwright-api` | FastAPI / uvicorn `:8002` |
| `jobwright-ui` | Vite dev `:5120` (local only) |
| `jobwright-tunnel` | cloudflared → `jobwright.parthchandak.info` |
