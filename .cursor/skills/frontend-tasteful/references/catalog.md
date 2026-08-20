# jobwright dashboard catalog (curated)

Source of truth for **what to reuse**. Paths under `frontend/src/`. Orient with graphify (`explain "Chip"`, `explain "laneTone"`, `query "JobSummary"`) then read the file.

Do not dump every component or every CSS value here. If a pattern is missing, read peers + `index.css`, then promote when it becomes shared.

## Layers

| Layer | Where | Role |
|-------|-------|------|
| Tokens | `index.css` (`:root`, `.dark`, `@layer components`) | Color, glass, stage, job-card, sidebar, table, drawer |
| shadcn | `components/ui/` | Button, Tabs, Badge, Dialog, Sheet, Input, Select, … |
| Domain | `components/` (not `ui/`) | Product layout |
| Pages | `App.tsx`, `ProfilePage`, `JobDrawer` | Composition only |

Reuse order: shadcn defaults → domain primitive → new token/class. Tailwind v4 is CSS-first (`@theme inline` in `index.css`; no `tailwind.config`).

## Must-reuse primitives

### Shell and nav

| Use | Primitive |
|-----|-----------|
| Desktop rail (hover expand + click pin) | `AppSidebar` |
| Stage filters | `SidebarNav` + `NavItem` |
| Profile / theme rows in the rail | `SidebarActionButton` |
| 56px header chrome | `BrandLogo` (`APP_SHELL_HEADER`) |
| Light / dark | `ThemeToggle` (`sidebar` vs icon) |
| Board vs table | `ViewModeTabs` (default pill `TabsList`) |

### Jobs

| Use | Primitive |
|-----|-----------|
| Card / drawer job header | `JobSummary` (uses `JobCardLayout` slots) |
| Kanban card / DnD | `JobCardView` / `SortableJobCard` |
| Lane column | `KanbanColumn` (sets `--lane`) |
| Status pills | `Chip` (icon-led; `tone` for `--stage-*`) |
| Stage as chip | `StageBadge` |
| Work model / sponsorship / materials / WhatsApp | `WorkModelBadge`, `SponsorshipBadge`, `JobMetaBadges` |
| Meta rows (`Label: NA`) | `MetaField` |
| Fit score | `ScoreBadge` / `ScoreEditor` (`lib/scoreColor.ts`) |
| Stage color anywhere | `laneTone()` / `STAGE_TONE` from `lib/api.ts` |

### Drawer, materials, runs

| Use | Primitive |
|-----|-----------|
| Drawer section chrome / prev-next stage | `DrawerSection`, `DrawerStageNav` |
| Per-job resume/cover + Auto/Custom Tailor | `MaterialsPanel` |
| Profile documents (PDF iframe + markdown) | `ProfileMaterials` + `ResumePreview` |
| Live pipeline / tailor logs | `RunProgressDialog` + `RunProgressButton` |
| Board Auto Search dialog | `AutoSearchDialog` (wrapper over `RunProgressDialog`) |
| Edit tailor instructions then run | `CustomTailorDialog` |
| LinkedIn-tinted contacts | `ConnectionsPanel` |
| Gated dialogs | `CloseJobDialog`, `ManualAddModal`, `DailyBriefDialog` (WhatsApp brief time + send) |

### Profile / forms

| Use | Primitive |
|-----|-----------|
| Labeled field + help | `FormField`, `FieldHint`, `SectionLabel` |
| Auto Search editors | `ChipInput`, `QueryChipInput`, `LocationChipInput`, `BoardToggles` |
| Read-only pairs in dialogs | `DetailRow` / `DetailGrid` |

### Buttons

`Button` from `ui/button`: `size="sm"` for actions; `outline` secondary; default primary; `variant="ai"` tailor; `prepare` for lane-tinted prepare CTAs; `icon-sm` for icon-only. Nav rows and list rows may use raw `<button>` (existing exception).

**Chip vs Badge:** Chip = job/domain status. Badge = generic counts / run-stage chips in progress UI. Do not restyle `Badge` as a job chip.

## Token families (extend these; do not re-hardcode)

| Family | Tokens / classes |
|--------|------------------|
| Semantic (shadcn) | `--background`, `--foreground`, `--card`, `--primary`, `--muted`, `--destructive`, `--border`, `--ring`, `--sidebar*` |
| Stages | `--stage-backlog/prepare/applied/in-progress/offer/closed`; runtime `--lane` |
| Query cadence | `--query-daily` (aliases offer), `--query-weekly` |
| Glass | `--glass*`, `.glass`, `.glass-strong`, `.glass-interactive`, `.lane-card` |
| Job card | `--job-card-*`, `.job-card-*` |
| Table | `--jobs-table-*`, `.jobs-table*` |
| Sidebar | `--sidebar-rail` 3.5rem, `--sidebar-panel` 14rem, `.sidebar-label` |
| LinkedIn | `--linkedin*` , `.connections-*` |
| Tailor | `--tailor*` (also `Button variant="ai"`) |
| Motion | `--ease-glass`; honor `prefers-reduced-motion` |

Theme: `lib/theme.tsx` + `.dark` on `<html>` (`jobwright-theme`). Dark neutrals are greyscale; stage / LinkedIn / tailor keep chroma.

Typography: IBM Plex Sans. Cards: `text-sm` title, `text-xs` meta. Do not add `text-[10px]` / `text-[11px]`; add a token or class if you need a new size.

## Little things (keep these)

- **Sidebar:** hover open ~80ms / close ~180ms; click pins; Escape + outside click unpins; job drawer forces unpin; labels fade via `.sidebar-label`.
- **Stage labels** on sidebar, column headers, and drawer current stage: ALL CAPS + `laneTone` on label and count. Table `StageBadge` stays Title Case inside Chip (do not "fix" unless promoting a new convention).
- **Glass on narrow viewports (≤767px):** drop backdrop-filter; opaque `--card` (WhatsApp / iOS scroll).
- **Closing `RunProgressDialog` does not stop the run;** Stop does.
- **Empty meta:** `MetaField` → `NA`; muted Chip for missing work model.
- **Focus:** shadcn `focus-visible:ring-[3px] ring-ring/50` on controls.
- **Header height:** `h-14` / `APP_SHELL_HEADER`, not a one-off.

## Do not reinvent (still missing as primitives)

Prefer extending the closest primitive. Do **not** promote these until they are reused in more than one place:

- Header search field in `App.tsx`
- Empty / loading copy (board, table, drawer, connections each differ)
- `JobsTable` local `FilterChip` (not `Chip`)
- `MaterialsPanel` markdown preview vs `ResumePreview` PDF+md

`ui/Card` and `ui/ScrollArea` exist but are unused; do not start using them without a reason (Sheet/Dialog already cover overlays).
