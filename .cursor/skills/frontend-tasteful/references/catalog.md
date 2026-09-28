# jobwright dashboard catalog (curated)

Source of truth for **what to reuse**. Paths under `frontend/src/`. Orient with graphify (`explain "Chip"`, `explain "laneTone"`, `query "JobSummary"`) then read the file.

Do not dump every component or every CSS value here. If a pattern is missing, read peers + `index.css`, then promote when it becomes shared. Design direction and spec: `docs/agents/design-v2-audit.md` section 2 ("calm & refined").

## Layers

| Layer | Where | Role |
|-------|-------|------|
| Tokens | `index.css` (`@theme`, `@theme inline`, `:root`, `.dark`, `@utility`, `@layer components`) | Colour, type scale, spacing, radius, elevation, motion, stage, job-card, sidebar, table, drawer |
| shadcn / Radix | `components/ui/` | Button, Input, Textarea, Select, Checkbox, Switch, Segmented, Tabs, Dialog, Sheet, Popover, DropdownMenu, Tooltip, Badge, Skeleton, … |
| Domain | `components/` (not `ui/`) | Product layout |
| Pages | `App.tsx`, `ProfilePage`, `JobDrawer`, `pages/` (`WelcomePage`, `QualityPage`, `AdminPage`) | Composition only |
| Data / identity | `lib/api.ts` (typed API), `lib/me.tsx` (`MeProvider` / `useMe`: login, admin, profiles), `lib/reasons.ts`, `lib/useRunStream.ts` | Shared hooks; no page-local fetch wrappers |

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
| Phone menu (stages, Match quality, Admin, Profile, theme) | `MobileNavProvider` + `MobileNav` (rendered once in `App.tsx`) + `MobileNavTrigger` / `useMobileNav()` |
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
| Work model / sponsorship / materials / WhatsApp | `WorkModelBadge`, `SponsorshipBadge`, `JobMetaBadges` |
| Meta rows (`Label: NA`) | `MetaField` |
| Fit score | `ScoreBadge` / `ScoreEditor` (`lib/scoreColor.ts`) |
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
| Gated dialogs | `DismissDialog` (close with outcome; "Not for me" asks why), `ManualAddModal`, `DailyBriefDialog` (pending count, next send, Send now; links to Profile → WhatsApp) |
| WhatsApp chat selection + test send | `WhatsAppChatPicker` (Profile Daily list tab, onboarding, Admin; `hideTest` when the caller owns test-send; `onChange(target, chat?)`; `chatDisplayName` shows "Unnamed group · …4902" for raw ids) |

### Profile / forms

| Use | Primitive |
|-----|-----------|
| Labeled field + help | `FormField` (visible `hint`, `help` popover), `FieldHint`, `SectionHeader` |
| Auto Search editors | `ChipInput`, `QueryChipInput` (`mode` `auto`/`chips`/`list`: above 12 titles a divided list with a Daily/Weekly `Segmented` per row; chips mode moves via a chip menu), `LocationChipInput` (neutral, Enter only so "City, ST" stays one chip), `BoardToggles` (empty value = `DEFAULT_BOARDS` shown on) |
| Profile tabs (one save model: autosave + `SaveStatus`; Match rules uses `ActionBar`) | `components/profile/*Tab.tsx`, `useAutosave` (debounced save with state/savedAt/retry, flushes on unmount), `ConfirmAction` |
| Read-only pairs in dialogs | `DetailRow` / `DetailGrid` |
| Match rules (fit, dealbreakers, locations, level, pay) | `CriteriaEditor` (`compact` in onboarding; grouped with h3 subheadings otherwise; dealbreakers and pluses are divided lists with inline fields; Radix `Select` for the cutoff) |

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

### Buttons

Hierarchy: one `primary` per view; `secondary` for ordinary actions; `ghost` for tertiary and navigation; `destructive` only inside confirm dialogs; list-level Remove is `destructive-ghost` (or a destructive `DropdownMenuItem`) inside a "⋯" menu; `ai` (accent tint + `Sparkles`) for AI actions. Real-world side effects (send WhatsApp, run search) are `secondary` with an icon and always confirm. `xs` is desktop-dense only (admin rows, status strip). `RunProgressButton variant="prepare"` is a lane-tinted secondary. Nav rows and list rows may use raw `<button>` (existing exception) but must add `touch-target` or a 44px min height on phone.

**Chip vs Badge:** `Chip` = job/domain status (`size="sm"`, dense) or a removable form value (`ValueChip`). `Badge` = generic counts / run-stage chips in progress UI. Do not restyle `Badge` as a job chip. A chip is either a status or a removable value: no embedded secondary buttons or labels; use `trailing` with a `DropdownMenu` trigger, or a `Segmented` per row.

## Token families (extend these; do not re-hardcode)

| Family | Tokens / classes |
|--------|------------------|
| Neutrals | `--background`, `--surface`, `--surface-muted`, `--foreground`, `--muted-foreground`, `--subtle-foreground` (placeholder/disabled only), `--border`, `--border-strong` (= `--input`); `--card` / `--popover` / `--secondary` / `--muted` alias them |
| Accent + semantic | `--primary` (indigo, hue 262), `--accent` / `--accent-foreground` (selected tint), `--ring`, `--destructive`, `--success`, `--warning`, `--overlay`, `--pill-active` |
| Tints | `tone-tint` utility + `--tone` (10% fill, 22% border, 75% text mix); used by `Chip tone` and `Badge` |
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

Typography: system font stack (SF Pro on Apple). Board cards keep `text-sm` title, `text-xs` meta. Nothing below 12px: no `text-[10px]` / `text-[11px]`.

## Little things (keep these)

- **Sidebar:** hover open ~80ms / close ~180ms; click pins; Escape + outside click unpins; job drawer forces unpin; labels fade via `.sidebar-label`.
- **Stage labels** on sidebar, column headers, and drawer current stage: ALL CAPS + `laneTone` on label and count (the only uppercase allowed). Table `StageBadge` stays Title Case inside Chip.
- **No backdrop blur** except the md+ board header; phone and desktop render the same flat surfaces (WhatsApp / iOS scroll).
- **Closing `RunProgressDialog` does not stop the run;** Stop does.
- **Empty meta:** `MetaField` → `NA`; muted Chip for missing work model.
- **Focus:** global `:focus-visible` outline (2px `--ring`, offset 2px; text fields offset 0). Legacy `focus-visible:ring-*` classes still work; new code should not add them.
- **Header height:** `h-14` (`APP_SHELL_HEADER` on the board, `PageHeader` phone bar elsewhere), not a one-off.
- **Phone:** every page has the menu (`PageHeader` → `MobileNavTrigger`); dialogs are bottom sheets under 640px; sticky bars pad `--safe-bottom`; inputs use 16px text so iOS does not zoom.

## Do not reinvent (still missing as primitives)

Prefer extending the closest primitive. Do **not** promote these until they are reused in more than one place:

- Header search field in `App.tsx`
- `JobsTable` local `FilterChip` (not `Chip`)
- Job drawer materials use `JobMaterialsPreview` (version dropdown + PDF/md); Profile keeps `ResumePreview`
- `StatusDot` lives in `components/admin/`; promote it only when Quality or Profile need it

`ui/Card` (12px radius, hairline) is fine for grouped metrics. Settings and admin should prefer one `.surface` list with divided rows. `ui/ScrollArea` stays unused; overlays already scroll.
