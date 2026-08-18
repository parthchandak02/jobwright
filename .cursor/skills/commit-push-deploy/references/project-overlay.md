# Project Overlay (jobwright)

Pointer: canonical overlay lives at [.cursor/commit-overlay.md](../../../commit-overlay.md).

Deploy section for `commit-push-deploy`:

## Deploy commands

| Target | Command |
|--------|---------|
| Frontend → production | `./scripts/restart.sh --prod-ui` |
| Backend only | `./scripts/restart.sh --backend-only` |
| Tunnel only | `./scripts/restart.sh --tunnel-only` |
| Local dev (HMR) | `./scripts/restart.sh` (api + ui; not for public site) |

## Skip deploy when

- Only `docs/`, `tests/` (no runtime change), or `.cursor/skills/` changed
- User asked commit/push only (no deploy trigger)

## Never for production

- Restarting `jobwright-ui` — Vite dev server does not serve `jobwright.parthchandak.info`
