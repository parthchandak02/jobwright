# jobwright dashboard catalog (curated)

Source of truth for **what to reuse**. Paths under `frontend/src/`. Orient with graphify (`explain "Chip"`, `explain "laneTone"`, `query "JobSummary"`) then read the file.

Do not dump every component or every CSS value here. If a pattern is missing, read peers + `index.css`, then promote when it becomes shared. Design direction and spec: `docs/agents/design-v2-audit.md` section 2 ("calm & refined").

## Layers

| Layer | Where | Role |
|-------|-------|------|
| Tokens | `index.css` (`@theme`, `@theme inline`, `:root`, `.dark`, `@utility`, `@layer components`) | Colour, type scale, spacing, radius, elevation, motion, stage, job-card, sidebar, table, drawer |
| shadcn / Radix | `components/ui/` | Button, Input, Textarea, Select, Checkbox, Switch, Segmented, Tabs, Dialog, Sheet, Popover, DropdownMenu, Tooltip, Badge, Skeleton, … |
| Domain | `components/` (not `ui/`) | Product layout |
| Pages | `App.tsx` (board), `ProfilePage` ("Settings", `/profile`), `JobDrawer`, `pages/` (`WelcomePage`, `QualityPage`, `AdminPage`) | Composition only; page sections live in `components/welcome/`, `components/profile/`, `components/admin/` |
| Data / identity | `lib/api.ts` (typed API), `lib/me.tsx` (`MeProvider` / `useMe`: login, admin, profiles), `lib/reasons.ts`, `lib/useRunStream.ts` | Shared hooks; no page-local fetch wrappers |

New UI must use the primitives below; do not add page-local headers, save indicators, chips, confirm dialogs or tab bars.

Reuse order: shadcn defaults → domain primitive → new token/class. Tailwind v4 is CSS-first (no `tailwind.config`). Always merge classes with `cn()` (`lib/utils.ts`): it is a `tailwind-merge` configured for the custom `text-*`, `shadow-e*`, `rounded-popover`, container and spacing tokens.

## Must-reuse primitives

### Page shell, sections, forms (design v2)

| Use | Primitive (key props) |
|-----|-----------|
| Whole non-board page: own scroll container, header, content column | `Page` from `PageHeader.tsx` (`title`, `description`, `actions`, `mobileActions`, `width` `form`/`wide`/`full`, `headerExtra` e.g. underline tabs, `bodyClassName`) |
| Title block + phone sticky 56px bar with the menu button | `PageHeader` (same props; `children` render under the title). First child of a scroll container |
| Centred column with page padding | `PageColumn` (`width`) |
| Section title + visible description + right slot | `SectionHeader` (`title`, `description`, `actions`, `help`, `as`, `id`); adds `mt-section` unless first child, 16px below. `SectionLabel` is the legacy compact variant |
| Label → control → visible hint → error | `FormField` (`label`, `htmlFor`, `hint` visible text, `help` popover, `optional`, `error`, `labelAction`); wires `id` / `aria-describedby` / `aria-invalid` onto a single child element |
| Long explanation behind "?" (tap and click) | `FieldHint` (`text`, `label`); Popover, not Tooltip |
| Autosave indicator (one per section) | `SaveStatus` (`state` `idle`/`saving`/`saved`/`error`, `savedAt`, `onRetry`, `errorText`) |
| Sticky bottom primary actions / unsaved changes | `ActionBar` (`open`, `message`, `onSave`, `onDiscard`, `saveLabel`, `discardLabel`, `saving`, `saveDisabled`, or custom `children`). Last child of the scroll container |
| Empty states | `EmptyState` (`icon`, `title`, `description`, `action`, `size` `inline`/`page`, `children`) |
| Phone menu (stages, Match quality, Admin for admins, "Profile & settings", theme); on every page | `MobileNavProvider` + `MobileNav` (rendered once in `App.tsx`) + `MobileNavTrigger` / `useMobileNav()` |
| Removable value chip (28px, 32px phone, 32px hit area on the x) | `ValueChip` (= `Chip size="md"`: `onRemove`, `tone`, `trailing`) |
| Chip list editor | `ChipInput` (`values`, `onChange`, `placeholder` as an instruction, `addLabel`, `tone` semantic only, `collapseAfter`, `renderActions`, `disabled`, `id`, `aria-describedby`); splits pasted commas/newlines |

### shadcn / Radix (`components/ui/`)

| Use | Primitive |
|-----|-----------|
| Buttons | `Button`: `variant` `primary`, `secondary`, `ghost`, `destructive`, `destructive-ghost`, `link`, `ai` (aliases: `default` = primary, `outline` = secondary). `size` `default` 40/44px, `sm` 36/44px, `lg` 44/48px, `xs` 28px desktop-dense + hit area, `icon` 40/44px, `icon-sm` 32/36px + hit area (desktop/phone) |
| Text inputs | `Input`, `Textarea` (auto-grows by default via `field-sizing: content` with a JS fallback; `rows` = minimum rows; `autoGrow={false}` opts out). 40px desktop / 44px phone, 16px text on phone |
| Choice | `Select` (+ `SelectGroup`, `SelectLabel`, `SelectSeparator`), `Checkbox`, `Switch`, `Segmented` (`value`, `onValueChange`, `options`, `size` `sm`/`md`, `aria-label`) |
| Menus | `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem` (`variant="destructive"`), checkbox/radio items, label, separator. Use for "⋯" row actions, Remove, and chip move actions |
| Tabs | `TabsList variant="underline"` for page-level navigation (44px, 2px accent indicator, horizontal scroll with edge fade, active tab scrolled into view). Default `pill` for small toggles (Board/Table, PDF/Markdown) |
| Overlays | `Dialog` (`DialogContent size` `form` 480px / `picker` 640px / `wide`; bottom sheet under 640px with handle and safe area), `Sheet` (`side="bottom"` has handle + safe area), `Popover`, `Tooltip` (desktop extra only; never the only place for help) |
| Loading | `Skeleton` |
| Counts / run-stage pills | `Badge` (`default`, `secondary`, `outline`, `success`, `warning`, `info`, `destructive`; tinted ones use `tone-tint`) |

### Shell and nav

| Use | Primitive |
|-----|-----------|
| Desktop rail (hover expand + click pin) | `AppSidebar` |
| Stage filters | `SidebarNav` + `NavItem` (44px rows on phone) |
| Profile / theme rows in the rail | `SidebarActionButton` |
| Switch profile (admins: all) | `ProfileSwitcher` (reloads the app) |
| Identity gate (no profile → `/welcome`) | `AppGate` |
| Last run / ops / WhatsApp bridge warning | `StatusBanner` |
| 56px board header chrome | `BrandLogo` (`APP_SHELL_HEADER`); other pages use `PageHeader` |
| Light / dark | `ThemeToggle` (`sidebar` vs icon) |
| Board vs table | `ViewModeTabs` (default pill `TabsList`) |

### Jobs

| Use | Primitive |
|-----|-----------|
| Card / drawer job header | `JobSummary` (uses `JobCardLayout` slots) |
| Kanban card / DnD | `JobCardView` / `SortableJobCard` |
| Lane column | `KanbanColumn` (sets `--lane`) |
| Status pills | `Chip` (icon-led, neutral by default; `tone` = CSS var for the `tone-tint` recipe, e.g. `--stage-applied`, `--destructive`, `--success`) |
| Stage as chip | `StageBadge` |
| Work model / key chips | `WorkModelBadge` (+ `workModelLabel`), `JobKeyChips` / `jobChips` (`JobMetaBadges.tsx`) |
| Meta rows (`Label: NA`) | `MetaField` |
| Fit score (number + plain meaning) | `ScoreBadge` (`label`) / `ScoreEditor` (`lib/scoreColor.ts`) |
| Why this score (gates, fit, confidence, reasoning) | `MatchExplanation` |
| One-tap relevance rating (thumbs + reasons → label) | `RateJob` |
| Multi-select reason pills | `ReasonChips` (options from `lib/reasons.ts`, merged with the user's dealbreakers) |
| Move to any lane (scrolls on narrow screens) | `StagePicker` |
| Stage color anywhere | `laneTone()` / `STAGE_TONE` from `lib/api.ts` |

### Drawer, materials, runs

| Use | Primitive |
|-----|-----------|
| Drawer section chrome | `DrawerSection` |
| Per-job resume/cover + Auto/Custom Tailor | `JobResumeMaterials`, `JobCoverMaterials`, `JobMaterialsPreview` |
| Profile documents (resume row, cover letter list with drop zone, preview on demand) | `ProfileMaterials` + `ResumePreview` (PDF / Text `Segmented`, "Open PDF" link; phones default to Text) |
| Live pipeline / tailor logs | `RunProgressDialog` + `RunProgressButton`; attach to a started run with `useRunStream` |
| Board Auto Search dialog | `AutoSearchDialog` (wrapper over `RunProgressDialog`) |
| Edit tailor instructions then run | `CustomTailorDialog` |
| LinkedIn-tinted contacts | `ConnectionsPanel` |
| Gated dialogs | `DismissDialog` (close with outcome; "Not for me" asks why), `ManualAddModal`, `DailyBriefDialog` (pending count, next send, Send now; links to Settings → Daily list) |
| WhatsApp chat selection + test send (admins only; `GET /api/whatsapp/chats` is admin-only) | `WhatsAppChatPicker` (Settings Daily list tab, Welcome and Admin when the caller is an admin; `hideTest` when the caller owns test-send; `onChange(target, chat?)`; `chatDisplayName` shows "Unnamed group · …4902" for raw ids) |

### Profile / forms

| Use | Primitive |
|-----|-----------|
| Labeled field + help | `FormField` (visible `hint`, `help` popover), `FieldHint`, `SectionHeader` |
| Auto Search editors | `ChipInput`, `QueryChipInput` (`mode` `auto`/`chips`/`list`: above 12 titles a divided list with a Daily/Weekly `Segmented` per row; chips mode moves via a chip menu), `LocationChipInput` (neutral, Enter only so "City, ST" stays one chip), `BoardToggles` (empty value = `DEFAULT_BOARDS` shown on) |
| Settings tabs (`TabsList variant="underline"`: Search, Match rules, Documents, Daily list (value `whatsapp`), About you; one save model: autosave + `SaveStatus`; Match rules uses a sticky `ActionBar`) | `components/profile/` `SearchTab`, `RulesTab`, `DocumentsTab`, `DailyListTab`, `AboutTab`; `useAutosave` (debounced 700ms save with `state`/`savedAt`/`schedule`/`flush`/`retry`, flushes on unmount); `ConfirmAction` (confirm before real sends) |
| Connected chat for non-admins (read-only name from `whatsapp_chat_name`; "Send test" goes to the caller's own chat) | `ConnectedChat` (`target`, `name`, `hideTest` on Welcome so setup never posts) |
| Read-only pairs in dialogs | `DetailRow` / `DetailGrid` |
| Match rules (fit, dealbreakers, locations, level, pay) | `CriteriaEditor` (`compact` in onboarding; grouped with h3 subheadings otherwise; dealbreakers and pluses are divided lists with inline fields; Radix `Select` for the cutoff) |

### Welcome (`components/welcome/`)

| Use | Primitive |
|-----|-----------|
| Page shell (560px column, progress over 6 steps: About you, Resume, Your search, How we judge fit, Daily list, Cover letters) and one step (title, description, back, actions, submit) | `WelcomeShell` (+ `PROGRESS_LABELS`), `WelcomeStep` |
| Steps (composed by `pages/WelcomePage.tsx`) | `StepAbout`, `StepResume`, `StepSearch`, `StepFit`, `StepDailyList` (picker for admins, `ConnectedChat hideTest` otherwise), `StepLetters`, `StepFinish` (review + start) |
| Welcome-local helpers (not yet promoted) | `parts.tsx`: `Disclosure` (optional/advanced fields), `DropZone` (PDF-only drop/upload), `MutedList` |

### Admin (`components/admin/`)

| Use | Primitive |
|-----|-----------|
| System health list (bridge, login access + Sync, group instructions + Apply, alerts chat + Pick); one "All systems working" line when healthy, inline details disclosure | `SystemStrip` |
| People list: `variant="table"` (lg+, `PeopleHeader` column labels, inline expand) or `variant="card"` (two-line phone row that opens `PersonSheet`) | `PersonRow` (+ `PeopleHeader`, `PersonRowSkeleton`) |
| Status dot: filled success / warning / destructive, hollow = unknown, dashed = setup pending; always paired with text on phone | `StatusDot` (+ `STATUS_TEXT`) |
| Phone/tablet person editor: 92dvh bottom sheet, sticky header + actions | `PersonSheet` |
| Inline auto-saving person settings grouped Login / Daily list (no Save button; optimistic + rollback in `AdminPage`; `SaveStatus` at the top) | `PersonSettings` (+ `PersonHealth`, `PersonActionBar`: ghost navigation, secondary sends, Remove in "⋯") |
| Current chat on one line (raw ids shown as "Unnamed group · …4902"), "Change" opens `WhatsAppChatPicker`, debounced commit | `ChatField` |
| Create profile (name, email, optional chat) | `AddPersonDialog` |
| Confirm before anything that reaches a real chat or deletes | `ConfirmDialog` (reject in `onConfirm` keeps it open) |
| Collapsed-by-default page section with aria-expanded header | `CollapsibleSection` (`AdminsAlertsSection`, `AiUsageSection`) |
| Status / time / usage / chat-name formatting | `adminFormat.ts` (`personStatus`, `STATUS_LABEL`, `fmtLastBrief`, `fmtUsage`, `chatDisplay`, `reportAccessSync`) |
| Debounced save that flushes on unmount | `lib/useDebouncedCallback.ts` (600ms default) |
| Table vs card / sheet switch | `useMediaQuery` (`useSyncExternalStore` over `matchMedia`) |

### Buttons

Hierarchy: one `primary` per view; `secondary` for ordinary actions; `ghost` for tertiary and navigation; `destructive` only inside confirm dialogs; list-level Remove is `destructive-ghost` (or a destructive `DropdownMenuItem`) inside a "⋯" menu; `ai` (accent tint + `Sparkles`) for AI actions. Real-world side effects (send WhatsApp, run search) are `secondary` with an icon and always confirm. `xs` is desktop-dense only (admin rows, status strip). `RunProgressButton variant="prepare"` is a lane-tinted secondary. Nav rows and list rows may use raw `<button>` (existing exception) but must add `touch-target` or a 44px min height on phone.

**Chip vs Badge:** `Chip` = job/domain status (`size="sm"`, dense) or a removable form value (`ValueChip`). `Badge` = generic counts / run-stage chips in progress UI. Do not restyle `Badge` as a job chip. A chip is either a status or a removable value: no embedded secondary buttons or labels; use `trailing` with a `DropdownMenu` trigger, or a `Segmented` per row.

## Token families (extend these; do not re-hardcode)

| Family | Tokens / classes |
|--------|------------------|
| Neutrals | `--background`, `--surface`, `--surface-muted`, `--foreground`, `--muted-foreground`, `--subtle-foreground` (placeholder/disabled only), `--border`, `--border-strong` (= `--input`); `--card` / `--popover` / `--secondary` / `--muted` alias them |
| Accent + semantic | `--primary` (indigo, hue 262), `--accent` / `--accent-foreground` (selected tint), `--ring`, `--destructive`, `--success`, `--warning`, `--overlay`, `--pill-active` |
| Tints | `tone-tint` utility + `--tone` (10% fill, 22% border, 75% text mix, mixed `in oklab` so white surfaces don't shift the hue); used by `Chip tone`, `Badge`, score pills, stage pills; `.lane-label` = the text mix for `--lane` |
| Stages | `--stage-backlog/prepare/applied/in-progress/offer/closed` (softened chroma); runtime `--lane`; `.lane-card` = 7% tint; `--tone-neutral` (`--query-daily` / `--query-weekly` alias it) |
| Type | `text-display` 28, `text-title` 22, `text-heading` 17, `text-subheading` 15, `text-body` 15 phone / 14 desktop, `text-label` 14/500, `text-caption` 13, `text-micro` 12 (floor); `--font-sans` = system stack |
| Spacing / layout | `space-y-field` (20px), `mt-section` (40/32px), `px-page-x` (32/16px), `pt-page-top` (40/20px), `max-w-form` (720px), `max-w-wide` (960px), `max-w-welcome` (560px), `--safe-bottom` |
| Radius | `--radius` 10px; `rounded-md` 8px (controls), `rounded-lg` / `rounded-xl` 12px (cards, dialogs), `rounded-popover` 10px (menus), `rounded-2xl` sheet tops, `rounded-full` chips |
| Elevation | `shadow-e1`, `shadow-e2`; `.surface`, `.surface-muted`. `.glass`, `.glass-strong`, `.glass-interactive` are migration aliases (flat surface, no blur, no hover lift) |
| Motion | `ease-out` (`--ease-glass` alias), `duration-(--dur-1)` 120ms / `--dur-2` 180ms / `--dur-3` 240ms; global `prefers-reduced-motion` rule |
| Utilities | `touch-target` (44px hit area on phone or coarse pointers; element needs `relative`), `scrollbar-none`, `.scroll-fade-x` |
| Job card / table / sidebar | `--job-card-*`, `.job-card-*`, `--jobs-table-*`, `.jobs-table*`, `--sidebar-rail` 3.5rem, `--sidebar-panel` 14rem, `.sidebar-label` |
| Brand | `--linkedin*`, `.connections-*` (brand icons and small accents only), `--whatsapp` (icon only). `--tailor*` now alias the accent (no separate purple family) |

Theme: `lib/theme.tsx` + `.dark` on `<html>` (`jobwright-theme`). Dark neutrals are cool greys (hue 260, chroma 0.004); the accent stays indigo in dark (never a near-white primary).

Typography: system font stack (SF Pro on Apple). Board cards keep `text-sm` title, `text-caption` meta. Nothing below 12px: no `text-[10px]` / `text-[11px]`.

## Little things (keep these)

- **Sidebar:** hover open ~80ms / close ~180ms; click pins; Escape + outside click unpins; job drawer forces unpin; labels fade via `.sidebar-label`.
- **Stage labels** on sidebar and column headers: ALL CAPS `text-micro` in `.lane-label` (the only uppercase allowed), counts muted. Drawer `StagePicker` and table `StageBadge` stay Title Case.
- **No backdrop blur** except the md+ board header; phone and desktop render the same flat surfaces (WhatsApp / iOS scroll).
- **Closing `RunProgressDialog` does not stop the run;** Stop does.
- **Empty meta:** `MetaField` → `NA`; muted Chip for missing work model.
- **Focus:** global `:focus-visible` outline (2px `--ring`, offset 2px; text fields offset 0). Legacy `focus-visible:ring-*` classes still work; new code should not add them.
- **Header height:** `h-14` (`APP_SHELL_HEADER` on the board, `PageHeader` phone bar elsewhere), not a one-off.
- **Phone:** every page has the menu (`PageHeader` → `MobileNavTrigger`); dialogs are bottom sheets under 640px; sticky bars pad `--safe-bottom`; inputs use 16px text so iOS does not zoom.

## Do not reinvent (still missing as primitives)

Prefer extending the closest primitive. Do **not** promote these until they are reused in more than one place:

- Header search field in `App.tsx`
- Job drawer materials use `JobMaterialsPreview` (version dropdown + PDF/md); Profile keeps `ResumePreview`
- `StatusDot` lives in `components/admin/`; promote it only when Quality or Profile need it
- Confirm dialogs: `admin/ConfirmDialog` (also used by Quality) and `profile/ConfirmAction` overlap; merge before adding a third
- `Disclosure` / `DropZone` in `welcome/parts.tsx`, `CollapsibleSection` in `admin/`, the number-with-unit field local to `SearchTab`: promote to `components/` when a second page needs one

`ui/Card` (12px radius, hairline) is fine for grouped metrics. Settings and admin should prefer one `.surface` list with divided rows. `ui/ScrollArea` stays unused; overlays already scroll.

## Board and drawer (WP6, shipped 2026-09-28)

Board, table and drawer are on v2. Keep these when editing them:

- **Card:** `JobCardView` = `bg-surface` + hairline, 3px `--lane` bar on the left, `shadow-e1` on hover/drag (drag adds `rotate-1`), no lane fill. `JobSummary`: 2-line title, company, one place line (`placeLine`: location · work model), pay only when stated, at most 2 chips (`JobKeyChips`), listing link bottom-right. `showStage` adds the lane label (phone list with mixed stages).
- **Chips:** `jobChips(job, dealLabels)` in `JobMetaBadges.tsx` is the single priority list (alerts: posting closed, follow up, dealbreaker, location; then materials; then info). Cards show 2, the table title cell shows 1 alert/info, the Materials column shows materials only. Unknown work model and sponsorship are never shown as chips.
- **Score:** `ScoreBadge` pill = number + plain meaning (`label` `short` "8 Strong", `long` "8 · Strong match", `none`), tinted `--success` (7+), `--warning` (5–6), neutral (≤4, unscored). Levels and words live in `lib/scoreColor.ts` (`scoreLevel`, `SCORE_LABEL`, `SCORE_SHORT`).
- **Lanes:** `KanbanColumn` header = 8px `--lane` dot + uppercase `text-micro` label in `.lane-label` (the `tone-tint` 75% text mix) + muted count. Drop highlight uses `tone-tint` with `--tone: var(--lane)`. Empty lanes show a dashed box with the stage icon and per-stage copy (`EMPTY_COPY`); while dragging it says where the job will go.
- **Sidebar:** `NavItem` icons are neutral with a 6px `--lane` dot on the icon; lane labels uppercase in `.lane-label`, counts muted. First item is "All jobs".
- **Header:** desktop = title + count, `ViewModeTabs`, search, then Auto Search / WhatsApp (count `Badge`) / Add job, all `secondary`. Phone = one 56px row (menu, title + count, search icon that expands the field, Auto Search, WhatsApp with count dot, add). Board/Table toggle and sort/filters sit in a sticky toolbar under it (`JobsTable toolbarStart`). Sticky rows inside `main` use `-top-3` because `main` has `p-3`.
- **Table:** `.surface` container, `bg-surface-muted` head, rows focusable (Enter opens), filters via column popovers (desktop) or bottom `Sheet` (phone, `FiltersPanel` with autocomplete), active filters as `ValueChip`s, empty states via `EmptyState`.
- **Drawer:** top-down: header (title, company · place) → decision summary (`.surface`: `MatchExplanation` score pill, confidence, reasoning, dealbreakers/concerns/level as plain sentences; duplicate/closed line; `RateJob`) → follow-up callout → actions → Stage (`StagePicker`: Title Case pills with a lane dot, current = `tone-tint`) → Details (`DetailGrid`) → Job description (markdown, collapsed with "Show full description") → Resume / Cover letter → Who you know there → Notes (`SaveStatus`) → History. Actions: Prepare (`ai`) when no materials before applying, Open posting (`primary` once materials exist before applying, else `secondary`), I applied (`secondary`), Not for me / Close job (`ghost`). Phone: the same actions as a sticky bottom bar (icon over label, 56px, lead action keeps its variant, others ghost). `DrawerSection` wraps `SectionHeader as="h3"`.
- **Dialogs:** `DismissDialog` (radio cards, reasons via `ReasonChips`), `DailyBriefDialog` (Send now is `secondary` and asks "Send N jobs to <chat> now?" before posting).
