# Design v2 audit: "calm & refined"

Date: 2026-09-27. Branch `dev`. Scope: `/welcome`, `/profile` (search, rules, documents, whatsapp, about), `/admin`, `/quality`, with a consistency pass over the board and job drawer.

Method: sandbox copy of one real profile plus an empty profile (`JOBWRIGHT_USERS_ROOT=/tmp/...`, Hermes dry run, dev auth), SPA built from `frontend/`, Playwright screenshots at 1440x900 and 390x844, light and dark, including scrolled `main`, the expanded admin person row, the status popover, collapsible sections, the Add person dialog, and every Welcome step. The Welcome review step and the Quality accuracy state used mocked API responses, so no LLM calls were made. Every write endpoint that sends WhatsApp, runs a search or calls an LLM was blocked at the network layer. No screenshots are committed.

Sandbox caveats (not UI bugs): the "Access error" and "Group instructions error" chips come from the disabled Cloudflare token and missing Hermes config. "No daily list yet" appears because `logs/` was not copied. The PDF iframe on Documents renders blank in headless Chromium.

Owner direction: calm and refined (Linear/Notion-like), generous whitespace, soft neutrals, one accent, crisp type, subtle depth. Users are non-technical job seekers. Desktop and phone (390px) have equal priority.

> Note on `.cursor/skills/frontend-tasteful`: that skill says "do not swap fonts, add heroes, or open up whitespace". v2 changes this on purpose for the pages in scope. WP1 must update `SKILL.md` and `references/catalog.md` so later agents don't revert the new tokens. The board and drawer keep their density; only their tokens change.

---

## 0. Top 10 problems (ranked)

1. **Phone users have no navigation outside the board.** The hamburger `Sheet` exists only in the board header in `App.tsx`. `ProfilePage`, `QualityPage` and `AdminPage` render their own headers with no menu (Profile has only a back arrow), and `AppSidebar` is `hidden md:flex`. On a phone, Admin and Quality are dead ends.
2. **Too many colours.** The profile Search tab shows green (daily), grey-green (weekly), red (blocked), blue (locations) and yellow (good-fit) chips at once. The sidebar has six coloured icons, and lane cards are 30% tinted. The only neutral surface is the page background, and nothing reads as "the accent".
3. **Chips double as editors.** `QueryChipInput` puts a 10px "Weekly" button inside every daily chip and a "Daily" button inside every weekly chip (a move action that reads as a label). It uses the only `text-[10px]` in forms. `ChipInput` placeholders look like real values ("social impact program manager", and "San Francisco, CA" right under a San Francisco chip).
4. **Four save models on one page.** Search autosaves with a tiny "Saving…/Saved" label. Match rules has an explicit Save at the top-right, which is off screen after scrolling a 2-screen form. WhatsApp and About have Save at the bottom. Admin autosaves. Users can't tell what is saved.
5. **Header hierarchy is weak and differs per page.** Every page header is `text-xs font-bold uppercase tracking-wider` (e.g. "Example Person 2", "ADMIN", "MATCH QUALITY"), smaller than the body text. Profile centres it, while Admin and Quality left-align it with an icon. There is no real page title (h1 at 20–24px), and section labels (`SectionLabel`) are also uppercase xs muted. Titles, labels and tabs all compete at about 12–14px.
6. **Welcome review is one long form.** On a phone it runs about 2,200px: 14 fields, three chip colours, a nested bordered "HOW JOBS ARE SCORED" box with 8 more fields, and the only CTA at the very bottom. Phone number sits under "What to look for". Dealbreaker rows stack label, description and trash on three lines at 390px.
7. **Form controls are inconsistent.** Inputs are h-9 (`ui/input`) in Welcome but `h-8` in About, CriteriaEditor and Admin. Native `<select>` in `CriteriaEditor` sits next to Radix `Select` in `PersonSettings`. There is a raw `<textarea>` in `AboutTab` and native checkboxes in WhatsApp and PersonSettings. `BoardToggles` shows every board as off when `boards` is empty, even though discovery then uses the default boards.
8. **Jargon and admin data leak to job seekers.** Quality shows "score:t1: 3,439,201", raw token totals, "scorer v2.3", Precision/Recall tables and a "Rescore my open jobs" button. The WhatsApp chat picker (admin) lists raw group IDs ("120363409468483759"). Search tab labels include "Results per site" and "Posted within (hours)", which are empty inputs with no defaults shown.
9. **Admin rows have no labels.** The person row shows "6:00 AM · 6+ · top 10 · 30 new this week · 3.5M tok" with no column headers. The status dot is grey for both "fine" and "unknown". On mobile the collapsed label says "No daily list yet" while the expanded panel says "Last list: Today 6:28 AM · 4 sent". The row's actions ("Run search now", "Send test" next to Change) sit in the same outline style as navigation ("Open board").
10. **Tabs and primary actions are hard to find on a phone.** The profile `TabsList` scrolls horizontally with no affordance, so "About you" is cut off at 390px. Primary buttons are not sticky. The Letters step makes "Skip for now" the primary button and "Upload PDFs" secondary. In dark mode `--primary` is near-white, so the accent disappears completely.

Also worth fixing (lower priority): the IBM Plex Sans Google Fonts request (external CDN, blocks first paint on WhatsApp in-app browser); glass/backdrop blur on every surface (already disabled on mobile, so desktop and phone look different); `rounded-md/lg/xl` used interchangeably (58 occurrences); 11 ad-hoc `uppercase` labels; duplicate "Send test" inside `ConnectedChat` for non-admins on Welcome (a real message to a real group during onboarding).

---

## 1. Page-by-page critique

### 1.1 Welcome (`pages/WelcomePage.tsx`)

**Desktop 1440**
- Hierarchy: brand block ("JOBWRIGHT" 14px tracked caps plus the email) is heavier than the step title (h1 `text-lg`, 18px). The step title should be the loudest thing on screen.
- Progress (`Progress`): six 20px numbered circles with 12px labels in one line. Fine on desktop, but it reads as a checklist, not "you're on step 2 of 5". The active and future states differ only by a thin border.
- Layout: `max-w-3xl` (768px) column, left aligned in a 1440 viewport, with about 600px of empty canvas under short steps (Name, WhatsApp, Letters, Done). There's no card or surface, so the page feels unfinished rather than calm.
- Resume step: the dashed upload zone is good. The four optional hint inputs in a 2x2 grid compete with the upload for attention. Only one label ("Roles you want") has a `FieldHint` "?", so baselines misalign by 3px (label height changes with the hint icon).
- Review step: see Top 10 #6. It also stacks three chip colour systems (QueryChipInput green, LocationChipInput blue, avoid-roles red, must-haves yellow). "Search keywords" splits into "Daily"/"Weekly" sub-labels at 12px bold with no explanation inline (it's hidden in a "?" tooltip, which is unreachable by touch on iOS).
- WhatsApp step (non-admin): `ConnectedChat` includes a "Send test" button. For a first-time user this sends a real message to a group, which is a surprising side effect during setup. The time input is `w-40` with no timezone shown (Profile shows "(PDT)").
- Letters: primary/secondary are inverted (Skip is primary). There's no drop zone, unlike the resume step.
- Done: two buttons and no summary of what was set up (keywords count, time, chat). This is a missed moment to reassure the user.
- Loading: "Reading your resume… (up to a minute)" appears only inside the button. There's no progress or skeleton for a 30–60s wait, and the page looks frozen.
- Back navigation exists only on Review.

**Phone 390**
- Progress wraps to two lines with orphan "5 Cover letters / 6 Start". Replace it with a compact "Step 2 of 5" and a thin bar.
- Review: dealbreaker grid collapses to three rows per item with the trash icon alone on a line. The nested bordered box costs 32px of width. The CTA sits about 2,100px down, and the Back and Save buttons are 36px tall (just under a 44px touch target).
- `FieldHint` "?" is 20px (below a 44px touch target) and tooltips need hover.

**Dark**: primary becomes `oklch(0.9 0 0)` (white button, black text), so completed step checks turn white and the accent is lost.

### 1.2 Profile (`components/ProfilePage.tsx`, `CriteriaEditor`, `ProfileMaterials`, `WhatsAppChatPicker`, `ConnectedChat`)

**Shared shell**
- Header: back arrow, centred `Example Person 2` in 12px caps and, for admins, `ProfileSwitcher` at the right. There's no page title ("Settings") and no description. The name reads as a label, not a heading.
- Width: `Tabs` is `max-w-6xl` (1152px), but WhatsApp and About content is `max-w-2xl`, Search and Rules are full 1152px, and Documents is full-bleed. Line length on Rules textareas reaches about 150 characters.
- Tabs: shadcn pill `TabsList` (muted grey tray). OK on desktop. At 390px "About you" is clipped with no scroll hint (Top 10 #10).
- Section headers: `SectionLabel` is 12px uppercase muted plus a "?" icon ("AUTO SEARCH", "HOW JOBS ARE SCORED", "DAILY WHATSAPP LIST", "WEEKLY SUMMARY"). These are weaker than the field labels (14px medium) below them, which inverts the hierarchy.
- Help text lives only in tooltips. Non-technical users won't hover "?" and phones can't. Short hints should be visible under the label.

**Search tab**
- About 50 chips across Daily/Weekly/Block titles make a wall of colour. Every chip carries an embedded move button plus an x. Consider a list or table view when there are more than 12 items, or collapse after 2 rows with "Show all 27".
- Weekly chips are desaturated green (`--query-weekly`) and read as disabled.
- Placeholder-as-example problem (Top 10 #3).
- `BoardToggles`: selected is `default` (filled primary) and unselected is `outline`. With `boards: []` all five look unselected, which is the wrong state (Top 10 #7). It should be a checkbox-chip group that shows "All boards (default)".
- Number inputs ("Drop below (USD)", "Posted within (hours)", "Results per site") are empty with no placeholder or default and span a third of 1152px each (about 370px wide for a 3-digit number).
- The autosave indicator is a 12px muted "Saved" at the far right of the section label row, easy to miss.

**Match rules tab**
- Actions ("Suggest from my ratings" in the purple `ai` variant, "Save rules" primary) sit top-right at the section-label baseline. At 390px they wrap under the label. After scrolling, Save is off screen (Top 10 #4).
- The "derived" notice is a grey bordered box in 12px, the same visual weight as an input. It should be an inline info callout.
- The "What you're looking for" textarea is fixed at 4 rows and holds about 900 characters of real content, so it's clipped with an internal scrollbar. It should auto-grow.
- Good-fit chips use `--stage-prepare` (yellow at 0.72 L) with yellow text on a pale yellow fill, the lowest-contrast chip in the app (about 3:1).
- Dealbreakers: the name input (`12rem`) truncates labels mid-word ("Fundraising / development"), and name and description often duplicate each other. Each row is a bordered box containing bordered inputs (double borders).
- "Pluses" chips hold paragraph-length text that truncates with an ellipsis. Chips are the wrong control for sentences.
- The native `<select>` for "Send me jobs scored at least" looks different from Radix `Select` elsewhere.

**Documents tab**
- Left rail list of letters in a muted tray, PDF/Markdown pill tabs, "Replace PDF" top-right. There are three segmented/tray styles on one screen (profile tabs, file list, PDF/Markdown).
- File names truncate ("Example Person 2 Cover Lette…") with no tooltip or wrap.
- Phone: the file list stacks above a `90vh` iframe, so the user scrolls past a blank frame (iOS in-app browsers often can't render PDF iframes). Default to the Markdown view on mobile or show a "Open PDF" link card.
- "Add cover PDFs" is outline-small under the list; no drag and drop.
- Hint copy is technical ("amalgamated when Auto Search writes materials").

**WhatsApp tab**
- Non-admin: `ConnectedChat` is a muted box with "Send test". This is good, but the same box pattern is used for notices (derived rules) and chat, so it lacks meaning.
- Admin: the full `WhatsAppChatPicker` list is embedded, with raw numeric group names and "Enter a chat id instead" as a 12px link. On a phone the picker pushes Time and Save below the fold.
- "Weekly summary" is a section header for a single checkbox. The native checkbox is 13px.
- "Remind me to follow up after (days with no reply)" is a long label for a `w-24` input. Use inline "Remind me after [10] days".
- There are two buttons of equal size: "Save" (primary) and "Send today's list now" (outline). The second sends WhatsApp and should be visually separated as a secondary/danger-adjacent action.

**About tab**
- Inputs are `h-8` here versus `h-9` elsewhere. `Target role` is a raw `<textarea>` that duplicates Match rules → "What you're looking for" and Welcome → "Target role" (same concept in three places with three labels).
- The 2-column grid on desktop puts City/State on separate rows at full half-width.

### 1.3 Admin (`pages/AdminPage.tsx`, `components/admin/*`)

**Desktop**
- Header: shield icon plus `ADMIN` 12px caps and a refresh icon. Content `max-w-5xl`. The header text is left-aligned at the sidebar edge while content is centred with a large left gutter, so the two don't line up.
- `SystemStrip`: four tinted pill chips (green/red/red/orange) plus an outline "Sync" button between chips. The chips and buttons share a line and height, so it's hard to see what's clickable (chips with popovers look identical to chips without). Error copy in popovers uses environment variable names (fine for admins).
- People list: glass container, 44px rows. Columns (chat, time, cutoff, top N, new this week, cost) are unlabeled (Top 10 #9). Token cost "3.5M tok" is right-aligned and competes with the chevron.
- Expanded `PersonSettings`: two-column form in the row plus an action row. Actions mix navigation (Open board/Open profile), a dangerous real-world action (Run search now, sends WhatsApp), and destructive Remove (ghost red, far right). All are `xs` outline, the same weight. "Send test" also sits beside "Change". The `SaveIndicator` is inline in the action row, away from the fields that changed.
- `CollapsibleSection` ("Admins and alerts", "AI usage") are 14px semibold with a chevron. They are fine, but visually unrelated to the People section header (which has a count and an outline button).
- AI usage table: good tabular numbers. The footnote exposes the environment variable `JOBWRIGHT_LLM_PRICES`.

**Phone**
- No navigation (Top 10 #1).
- SystemStrip wraps to two lines with Sync orphaned.
- Collapsed row: name, status, then two lines of meta ("Richa - Job Applications 6:00 AM 6+ top 10 / 30 new this week 3.5M tok") separated only by spaces.
- Expanded: good stacking, but "Run search now" and "Remove" sit on the same line at 28px height (`size="xs"`), below touch target size, and adjacent.
- `AddPersonDialog`: centred modal; "Pick their WhatsApp chat now (optional)" is plain text that looks like a disabled label. The primary disabled button looks washed out (opacity 50% on navy).

### 1.4 Match quality (`pages/QualityPage.tsx`)
- A local `Card` with glass and an uppercase 12px title duplicates the Admin section pattern with different styling. The metric component `Big` (24px) is the only large type in the app, so the page's hierarchy is metrics above everything, including the explanation.
- Copy is for engineers: token counts by `purpose` (`score:t1`), "scorer v2.3", "Old scorer (P / R)", and Precision/Recall defined in a paragraph. Job seekers need: "Of the jobs we sent you, 71% were a fit" and "Rate 20 more jobs to improve".
- Accuracy and Rescore buttons are shown to every user. They trigger LLM work and cost, and belong behind admin or at least an explanatory confirm.
- Empty state "No accuracy check yet." is 14px body with no guidance.
- Phone: the 4-column metric table fits but "Precision Recall" headers collide. The three `Big` metrics wrap into a 2+1 layout with an odd gap.
- AI usage card should be admin-only (it's already in Admin).

### 1.5 Board and drawer (consistency only)
- Board: lane cards tinted at 30% of the lane colour, each with 3–5 chips (work model, Sponsorship "?", materials, WhatsApp green) plus a score badge. With the v2 tokens the tint should drop to about 8% or a 3px top/left lane accent. Density stays.
- The "Sponsorship" chip with a "?" icon appears on nearly every card and carries no information when unknown. Hide unknown values.
- Drawer: title 16px semibold and score badge; the action row has four different button styles (outline, `ai` purple, outline, ghost). Stage picker uses ALL CAPS coloured text links. The job description shows raw markdown (`**Job Title**`). The back button has a visible focus ring on open (focus lands there, which is correct, but the ring is heavy).
- Mobile table view: the "Board / Table" toggle, Auto Search, WhatsApp, + and search wrap into three rows of header (about 140px) before content.

---

## 2. "Calm & refined" design system spec

All tokens live in `frontend/src/index.css` (`:root`, `.dark`, `@theme inline`). Names keep shadcn semantics so existing components inherit the change.

### 2.1 Color (OKLCH)

One accent: a calm indigo-blue (hue 262). Neutrals are a very low chroma warm grey (hue 80, chroma ≤ 0.006) in light and neutral in dark. Stage colours are kept but lowered in chroma and used mainly as small dots, 3px bars and text, not fills.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--background` | `oklch(0.985 0.002 80)` | `oklch(0.16 0.004 260)` | App canvas |
| `--surface` (new) | `oklch(1 0 0)` | `oklch(0.195 0.004 260)` | Cards, rows, inputs |
| `--surface-muted` (new) | `oklch(0.97 0.003 80)` | `oklch(0.22 0.004 260)` | Tab tray, callouts, hover |
| `--card` / `--popover` | = `--surface` | = `--surface` (popover `0.23`) | |
| `--foreground` | `oklch(0.22 0.01 260)` | `oklch(0.95 0.003 260)` | Body, titles |
| `--muted-foreground` | `oklch(0.50 0.01 260)` (≥ 4.6:1 on bg) | `oklch(0.70 0.005 260)` | Hints, meta |
| `--subtle-foreground` (new) | `oklch(0.62 0.008 260)` | `oklch(0.58 0.005 260)` | Placeholder, disabled text only |
| `--border` | `oklch(0.915 0.004 80)` | `oklch(0.28 0.004 260)` | Hairlines |
| `--border-strong` (new) | `oklch(0.86 0.005 80)` | `oklch(0.34 0.004 260)` | Inputs, focused rows |
| `--input` | = `--border-strong` | = `--border-strong` | |
| `--primary` (accent) | `oklch(0.52 0.15 262)` | `oklch(0.70 0.13 262)` | Primary buttons, links, active tab indicator, checks |
| `--primary-foreground` | `oklch(0.99 0 0)` | `oklch(0.16 0.02 262)` | |
| `--accent` (tint) | `oklch(0.96 0.02 262)` | `oklch(0.26 0.04 262)` | Selected row, active nav, selected chip |
| `--accent-foreground` | `oklch(0.40 0.12 262)` | `oklch(0.86 0.06 262)` | |
| `--ring` | `oklch(0.52 0.15 262 / 0.45)` | `oklch(0.70 0.13 262 / 0.5)` | Focus ring |
| `--destructive` | `oklch(0.55 0.17 25)` | `oklch(0.68 0.15 25)` | Remove, errors |
| `--success` (new) | `oklch(0.55 0.11 155)` | `oklch(0.74 0.11 155)` | Saved, connected |
| `--warning` (new) | `oklch(0.62 0.12 70)` | `oklch(0.78 0.11 70)` | Needs attention |

Stage colours (soften chroma about 35%, keep hues so users' mental map holds):

| Stage | Light | Dark |
|---|---|---|
| `--stage-backlog` | `oklch(0.60 0.02 260)` | `oklch(0.72 0.02 260)` |
| `--stage-prepare` | `oklch(0.66 0.10 85)` (was yellow 100, too low contrast) | `oklch(0.80 0.10 85)` |
| `--stage-applied` | `oklch(0.56 0.11 255)` | `oklch(0.74 0.10 255)` |
| `--stage-in-progress` | `oklch(0.62 0.12 50)` | `oklch(0.76 0.11 50)` |
| `--stage-offer` | `oklch(0.58 0.11 155)` | `oklch(0.76 0.10 155)` |
| `--stage-closed` | `oklch(0.56 0.10 330)` | `oklch(0.74 0.09 330)` |

Rules:
- Stage colour appears as a dot (8px), a lane header text colour, or a 3px left bar. Lane card fill at most `color-mix(var(--lane) 7%, var(--surface))` (was 30%).
- Tinted chip recipe: `bg: color-mix(tone 10%, surface)`, `border: color-mix(tone 22%, surface)`, `text: color-mix(tone 75%, foreground)`. This gives at least 4.5:1 text contrast for every tone.
- Form chips (keywords, locations, role types) are neutral (`--surface-muted`, `--foreground`). Only semantic negatives (Block titles, dealbreakers, "Locations that don't") get the destructive tint. This removes the green/blue/yellow keyword colours.
- `--tailor` (purple) stays only for the AI action, and `--linkedin`/`--whatsapp` only for brand icons, never large fills.
- Drop `--glass*`, `--mesh-*` and background gradients. Replace them with flat `--background` plus `--surface` cards. Keep `.glass` as an alias to the new `.surface` during migration.

### 2.2 Typography

- Font: prefer the system stack, self-hosted if we want Plex: `font-family: "Inter var", "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`. Only use Inter if it's self-hosted (e.g. `@fontsource-variable/inter` bundled by Vite, no CDN). Otherwise the system stack alone (SF Pro on iPhone and Mac) meets "crisp" best and removes the Google Fonts request in `frontend/index.html`. Decision for WP1: system stack by default, with an optional self-hosted Inter behind one CSS variable `--font-sans`.
- Numerals: `font-variant-numeric: tabular-nums` on metrics, tables, times, scores.
- Scale (rem at 16px root). Tailwind theme tokens `--text-*` in `@theme inline`:

| Token | Size / line-height | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | 28/34 | 600 | -0.015em | Welcome step title (desktop), big metrics |
| `title` | 22/28 | 600 | -0.01em | Page title (h1) |
| `heading` | 17/24 | 600 | -0.005em | Section header (h2) |
| `subheading` | 15/22 | 600 | 0 | Card title, row name |
| `body` | 15/24 (phone), 14/22 (desktop dense) | 400 | 0 | Body, inputs |
| `label` | 14/20 | 500 | 0 | Field labels, buttons |
| `caption` | 13/18 | 400 | 0 | Hints, meta, table secondary |
| `micro` | 12/16 | 500 | 0.01em | Chip text, counts. Floor: nothing smaller than 12px |

- Uppercase is allowed only for lane headers on the board (existing convention). Remove it from page headers, `SectionLabel`, Quality card titles, brand text.
- Inputs use 16px on phones (prevents iOS zoom): `text-base md:text-sm`.

### 2.3 Spacing, radius, elevation

- Spacing scale (4px base): 4, 8, 12, 16, 20, 24, 32, 40, 56, 72. Rhythm tokens:
  - `--space-field` 20px between fields; 8px label → control; 6px control → hint.
  - `--space-section` 40px desktop, 32px phone between sections.
  - `--page-pad-x` 32px desktop, 16px phone; `--page-pad-top` 40px desktop, 20px phone.
- Radius: `--radius` 10px. Inputs and buttons 8px (`radius-md`), cards and dialogs 12px (`radius-lg`), chips 999px, popovers 10px. Remove ad-hoc `rounded-xl` on list containers (use `radius-lg`).
- Elevation: three levels only.
  - `e0`: hairline border `--border`, no shadow (lists, inputs, cards on pages).
  - `e1`: `0 1px 2px oklch(0.2 0.01 260 / 0.05), 0 2px 8px -2px oklch(0.2 0.01 260 / 0.06)` (popovers, sticky action bar, hovered card).
  - `e2`: `0 8px 32px -8px oklch(0.2 0.01 260 / 0.18)` (dialogs, sheets).
  - Dark mode shadows at 3x alpha, and prefer a lighter surface over a shadow.
- No backdrop blur except the sticky page header (and only on md+).

### 2.4 Focus, motion, touch

- Focus ring: `outline: 2px solid var(--ring); outline-offset: 2px` on `:focus-visible` for every interactive element (replaces `ring-[3px] ring-ring/50`, which was heavy on the drawer back button).
- Motion: `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)` (keep), durations `--dur-1: 120ms` (hover/colour), `--dur-2: 180ms` (expand, tabs), `--dur-3: 240ms` (sheet/dialog). No translateY hover lift on cards (remove `.glass-interactive` transform). Respect `prefers-reduced-motion`.
- Touch targets: at least 44x44px on phone for every button, row, chip remove (use a hit-area pseudo element for 16px x icons), checkbox row and `FieldHint`. Button `sm` becomes 36px desktop / 44px phone; `xs` is desktop-only (never in phone layouts).

### 2.5 Component rules

- **Page header (`PageHeader`, new, `components/PageHeader.tsx`)**: sticky 56px bar with a menu button (phone) or nothing (desktop, sidebar present), then in content: `title` h1 + one-line `caption` description + right-aligned actions (max 2). Left edge aligns with the content column. Replaces the ad-hoc headers in `ProfilePage`, `QualityPage`, `AdminPage`.
- **Section header (`SectionHeader`, replaces `SectionLabel`)**: `heading` 17/600, optional `caption` description underneath (visible text, not a tooltip), optional right slot (status like "Saved", or one action). 40px above, 16px below.
- **Form field (`FormField` v2)**: label (`label` 14/500) → control → visible hint (`caption`, muted) → error (`caption`, destructive, with `aria-describedby`). `FieldHint` tooltip only for long explanations, and it must also open on tap (use Popover, not Tooltip). Optional "(optional)" suffix in muted text instead of in the label string.
- **Controls**: one height (40px desktop, 44px phone), one radius, `--input` border, `--surface` fill. Use Radix `Select` everywhere (replace native `<select>` in `CriteriaEditor`). Add `ui/checkbox` and `ui/switch` (Radix) to replace native checkboxes. `Textarea` auto-grows (`field-sizing: content` with min rows, JS fallback).
- **Chips**: 28px tall (desktop), 32px (phone), `micro` text, neutral by default; tone only for semantic status. A chip is either a status (read-only `Chip`) or a removable value (`ValueChip` with a 16px x in a 32px hit area). No embedded secondary buttons; move actions (Daily ↔ Weekly) go into a small menu on the chip or a segmented control per keyword row.
- **Lists vs cards**: settings and admin use lists (one surface, divided rows). Cards are only for the board and for grouped metrics. No bordered box inside a bordered box: nested groups use `--surface-muted` background, no border.
- **Buttons (hierarchy)**: one `primary` per view (filled accent). `secondary` (surface + border) for ordinary actions. `ghost` for tertiary and navigation. `destructive` only in confirm dialogs; list-level Remove is a ghost with destructive text inside a "More" menu. `ai` becomes accent-tinted with a sparkle icon (no separate purple family, or keep purple only on board and drawer tailor). Actions with real-world side effects (Send test, Send now, Run search) are `secondary` with an icon and always confirm.
- **Tabs**: underline tabs (text 14/500, 2px accent indicator, 44px tall) instead of the grey pill tray, for page-level navigation (Profile). The pill `TabsList` stays for small toggles (Board/Table, PDF/Markdown). On phone: underline tabs in a horizontal scroller with fade masks at edges, auto-scroll the active tab into view; or a `Select` "Section: Search ▾" under 360px.
- **Save model**: settings autosave per field with a single `SaveStatus` in the section header ("Saved · just now" / "Saving…" / "Couldn't save · Retry"). Where explicit save is required (Match rules, because it changes scoring), use a sticky bottom `ActionBar` that appears when dirty: "You have unsaved changes [Discard] [Save rules]".
- **Dialogs**: max-width 480px (forms), 640px (pickers). Title `heading`, description `caption`, footer right-aligned (primary right). On phone they become bottom sheets (full width, 16px radius top, drag handle, safe-area padding).
- **Empty states (`EmptyState`, new)**: 40px muted icon, `subheading` title, one `body` muted sentence, one primary action. Used for: board no jobs, Quality no eval, Admin no people, Documents no letters, Connections none.
- **Loading**: skeletons that match final layout (rows, fields). Long runs (resume draft 30–60s) show a staged progress list ("Reading your resume → Picking keywords → Writing your rules") with elapsed time.
- **Status**: `StatusDot` has 3 semantic states (success, warning, destructive) plus neutral "unknown" with a hollow ring, always with a text label next to it on phone.

### 2.6 Layout grids

- **Desktop (≥ 1024px)**: sidebar rail 56px (existing hover/pin kept), content area centred with `max-width`:
  - Settings/forms (Profile, Welcome): 720px content column. Profile adds an optional 200px left sub-nav at ≥ 1280px instead of top tabs (see blueprint).
  - Admin, Quality: 960px.
  - Board: full width (unchanged).
  - Page padding 32px sides, 40px top. Header left edge = content left edge.
- **Tablet (768–1023px)**: rail stays; content max 720px; two-column form grids collapse to one.
- **Phone (< 768px)**: 16px side padding, single column. Every page gets the same top bar: menu button (opens the existing `Sheet` nav, extracted to `MobileNav`) + page title + at most one icon action. Optional bottom tab bar (Board, Profile, Quality, and Admin for admins) is a stretch goal; the minimum is the menu on every page. Sticky bottom action bar for primary CTAs, with bottom safe-area inset padding (CSS `safe-area-inset-bottom`).
- Welcome uses its own shell: no sidebar, centred 560px column (desktop) with a surface card, `display` title, and a step indicator at the top.

---

## 3. Redesign blueprints

### 3.1 Welcome

Changes:
- 5 steps shown to the user: **About you → Resume → Your search → Daily list → Finish**. Cover letters becomes an optional block inside Finish (with drop zone), not a separate step. The internal `Step` type can stay and only the progress mapping changes.
- Split the Review step into two screens: **Your search** (target role, keywords, where) and **How we judge fit** (good-fit roles, dealbreakers, locations ok/not, seniority, pay floor, cutoff). Each has visible hints, neutral chips, and a sticky footer [Back] [Continue].
- Move Phone to "About you" (with name) or to Daily list, where it's used.
- Resume draft waiting state: full-panel progress with 3 stages and "This usually takes under a minute".
- Remove "Send test" from `ConnectedChat` in onboarding (pass `hideTest`), or put it behind a confirm.
- Finish: summary list (keywords count, locations, send time, chat name) with "Edit" links, then primary "Find my first jobs" and ghost "Go to my board".
- Letters: primary "Upload letters" (drop zone); "Skip" is a ghost link.

Desktop:
```
┌──────────────────────────────────────────────────────────────────────────┐
│                         ○ jobwright                                      │
│                                                                          │
│            Step 3 of 5 · Your search                                     │
│            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░░              │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │  Here's what we'll search for            (display 28/600)        │   │
│   │  Edit anything that's off. You can change it later.  (caption)   │   │
│   │                                                                  │   │
│   │  Target role                                                     │   │
│   │  ┌────────────────────────────────────────────────────────────┐  │   │
│   │  │ Program manager at an education nonprofit…                 │  │   │
│   │  └────────────────────────────────────────────────────────────┘  │   │
│   │  One or two sentences, in your own words.                        │   │
│   │                                                                  │   │
│   │  Job titles to search every day                                  │   │
│   │  (program manager ×) (program officer ×) [+ Add title      ]     │   │
│   │  Searched each morning.                                          │   │
│   │  ▸ Also search weekly (2)                                        │   │
│   │                                                                  │   │
│   │  Where                                                           │   │
│   │  (San Francisco, CA ×) (Remote ×)        [+ Add place      ]     │   │
│   ├──────────────────────────────────────────────────────────────────┤   │
│   │  ← Back                                         [ Continue → ]   │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                         signed in as new@example.com                     │
└──────────────────────────────────────────────────────────────────────────┘
card max-width 560–640px, surface e0, 40px padding; footer sticky within viewport
```

Phone:
```
┌──────────────────────────────┐
│ ○ jobwright        Step 3/5  │
│ ━━━━━━━━━━━━━━━━░░░░░░░░░░░  │
│                              │
│ Here's what we'll            │
│ search for     (title 22)    │
│ Edit anything that's off.    │
│                              │
│ Target role                  │
│ ┌──────────────────────────┐ │
│ │ Program manager at…      │ │
│ └──────────────────────────┘ │
│ Job titles, every day        │
│ (program manager ×)          │
│ (program officer ×)          │
│ [+ Add title             ]   │
│ ▸ Also search weekly (2)     │
│ Where                        │
│ (San Francisco ×) (Remote ×) │
│ [+ Add place             ]   │
│                              │
├──────────────────────────────┤  sticky, safe-area padded
│ ← Back        [ Continue → ] │  44px buttons
└──────────────────────────────┘
```

Dealbreaker row (phone): one card per rule, with name as bold text + description textarea, and a "⋯" menu for Remove. There's no separate name input: the label is derived from the first words, and the backend `id` is kept via `slugify`.

### 3.2 Profile

Changes:
- `PageHeader`: "Settings" (title) + caption "What we search for, how we judge fit, and your daily list." Admin profile switcher moves into the header's right slot as a compact "Viewing: Richa ▾" select.
- Navigation: desktop ≥ 1280px has a left sub-nav (Search, Match rules, Documents, Daily list, About you). Below that, underline tabs; phone uses scrollable underline tabs with edge fade.
- Rename "WhatsApp" tab to "Daily list" (it includes weekly summary and follow-ups).
- Every tab: `SectionHeader` + visible hints, 720px column, one save model (autosave with `SaveStatus`, except Match rules with sticky `ActionBar`).
- Search: keywords as a list when more than 12 (`KeywordList`: row per keyword with a Daily/Weekly segmented control and remove), else neutral chips. Blocked titles use destructive-tinted chips and collapse after 2 rows ("Show all 27"). Boards become a checkbox chip group with an "All boards" default state. Advanced numbers (Drop below, Posted within, Results per site) go into a collapsed "Advanced" section with placeholders showing defaults.
- Match rules: "Suggest from my ratings" in the section header right slot (secondary with sparkle); Save in the sticky bar; auto-grow textareas; good-fit chips neutral; dealbreakers as a divided list with an inline editable label + description.
- Documents: resume card (file name, updated date, [Replace] [Open PDF]) + "Cover letter examples" list with drop zone. The preview opens on demand (desktop inline, phone opens a new tab), no default 90vh iframe.
- Daily list: chat (read-only row, or picker behind "Change" for admins, reusing `ChatField`), time with timezone, `Switch` "Weekly summary on Sunday", inline "Remind me to follow up after [10] days". "Send today's list now" moves to a separate "Send now" row with a confirm dialog.
- About you: single column; target role removed here (edited in Match rules "What you're looking for", linked).

Desktop (Search tab):
```
┌────┬─────────────────────────────────────────────────────────────────────┐
│rail│ Settings                                   Viewing: Richa ▾         │
│    │ What we search for, how we judge fit, and your daily list.         │
│    │ ─────────────────────────────────────────────────────────────────── │
│    │ Search   Match rules   Documents   Daily list   About you           │
│    │ ━━━━━━                                                              │
│    │                                                                     │
│    │ Job titles                                          ✓ Saved         │
│    │ We search these on job boards each morning.                         │
│    │ ┌───────────────────────────────────────────────────────────────┐   │
│    │ │ social impact program manager         [Daily|Weekly]    ×     │   │
│    │ │ corporate social responsibility       [Daily|Weekly]    ×     │   │
│    │ │ …  Show all 27                                                │   │
│    │ │ [+ Add a job title                                          ] │   │
│    │ └───────────────────────────────────────────────────────────────┘   │
│    │                                                                     │
│    │ Never show titles containing                                        │
│    │ (fundraising ×) (philanthropy ×) (advancement ×) … Show all 27      │
│    │ [+ Add phrase                    ]                                  │
│    │                                                                     │
│    │ Where                                                               │
│    │ (San Francisco, CA ×) (Remote ×)  [+ Add place ]                    │
│    │                                                                     │
│    │ Job boards                                                          │
│    │ [✓ Indeed] [✓ LinkedIn] [✓ Google] [✓ Glassdoor] [✓ ZipRecruiter]   │
│    │ Using all boards (default).                                         │
│    │                                                                     │
│    │ ▸ Advanced: pay floor, posting age, results per board               │
└────┴─────────────────────────────────────────────────────────────────────┘
content column 720px, centred in the area to the right of the rail
```

Phone (Match rules with unsaved changes):
```
┌──────────────────────────────┐
│ ☰  Settings                  │
├──────────────────────────────┤
│ Search  Match rules  Docu›   │ underline tabs, edge fade
│         ━━━━━━━━━━━          │
│ How we judge fit             │
│ Every new job is compared    │
│ with these rules and your    │
│ ratings.  [✦ Suggest]        │
│                              │
│ What you're looking for      │
│ ┌──────────────────────────┐ │
│ │ auto-growing textarea…   │ │
│ └──────────────────────────┘ │
│ Good-fit roles               │
│ (Social impact program…  ×)  │
│ Dealbreakers                 │
│ ┌──────────────────────────┐ │
│ │ Fundraising          ⋯   │ │
│ │ Fundraising / advance…   │ │
│ ├──────────────────────────┤ │
│ │ Grant writing        ⋯   │ │
│ └──────────────────────────┘ │
├──────────────────────────────┤ sticky ActionBar (only when dirty)
│ Unsaved changes  [Discard][Save] │
└──────────────────────────────┘
```

### 3.3 Admin

Changes:
- `PageHeader`: "Admin" + caption "People, their daily lists, and system health." Right slot: [Add person] (primary) and a refresh icon.
- System health becomes a compact **status list** card instead of pills: rows "WhatsApp bridge · Connected", "Login access · Error · [Sync]", "Group instructions · 1 needs update · [Apply]", "Alerts chat · Not set · [Pick]". Each row has a dot, label, state text and action on the right; details open inline (disclosure), not in a popover. It collapses to one line "All systems OK" when healthy.
- People: a table-like list with a header row on desktop (Person · Chat · Sends at · Cutoff · List · New (7d) · AI cost). Status dot plus text for non-OK states only.
- Expanded person: grouped into "Login", "Daily list" and "Actions". Actions: [Open board] [Open profile] as ghost links; "Send test" and "Run search now" as secondary with a WhatsApp icon (confirm dialogs kept); Remove moves into a "⋯" menu. `SaveStatus` sits at the top of the expanded panel.
- Collapsible sections share `SectionHeader` styling with a chevron.
- Phone: each person is a card-row with two lines ("Example Person 2 · ● OK" / "Richa - Job Applications · 6:00 AM · top 10"). Expanded settings become a full-screen sheet (`Sheet side="bottom"` at 92vh) with sticky close, not an inline 700px expansion.

Desktop:
```
┌────┬───────────────────────────────────────────────────────────────────────┐
│rail│ Admin                                        [+ Add person]  ⟳        │
│    │ People, their daily lists, and system health.                        │
│    │                                                                      │
│    │ System                                                               │
│    │ ┌──────────────────────────────────────────────────────────────────┐ │
│    │ │ ● WhatsApp bridge        Connected                               │ │
│    │ │ ● Login access           Couldn't sync: token rejected   [Sync]  │ │
│    │ │ ● Group instructions     1 needs update                 [Apply]  │ │
│    │ │ ○ Alerts chat            Not set                         [Pick]  │ │
│    │ └──────────────────────────────────────────────────────────────────┘ │
│    │                                                                      │
│    │ People · 2 (1 setting up)                                            │
│    │ ┌──────────────────────────────────────────────────────────────────┐ │
│    │ │ Person        Chat                 Sends  Cutoff List  New  Cost │ │
│    │ ├──────────────────────────────────────────────────────────────────┤ │
│    │ │ ● Example Person 2 Richa - Job Appl…    6:00   6+     10    30   3.5M▾│ │
│    │ │ ┌ Login ───────────────┐ ┌ Daily list ─────────────┐   ✓ Saved   │ │
│    │ │ │ emails chips         │ │ time · cutoff · size    │             │ │
│    │ │ │ chat  [Change]       │ │ ☐ Review first ☐ Weekly │             │ │
│    │ │ └──────────────────────┘ └─────────────────────────┘             │ │
│    │ │ Open board · Open profile     [Send test] [Run search now]  ⋯    │ │
│    │ ├──────────────────────────────────────────────────────────────────┤ │
│    │ │ ○ New Person  Muskaan - Job…       Setup pending  [Do setup]   ▾ │ │
│    │ └──────────────────────────────────────────────────────────────────┘ │
│    │ ▸ Admins and alerts   1 admin · alerts to nobody                     │
│    │ ▸ AI usage            Last 30 days                                   │
└────┴───────────────────────────────────────────────────────────────────────┘
```

Phone:
```
┌──────────────────────────────┐
│ ☰  Admin               ⟳  +  │
├──────────────────────────────┤
│ System       ⚠ 2 need action │ tap → expands list
│                              │
│ People · 2                   │
│ ┌──────────────────────────┐ │
│ │ ● Example Person 2          › │ │ 56px row → bottom sheet
│ │   Job Applications · 6:00│ │
│ ├──────────────────────────┤ │
│ │ ○ New Person           › │ │
│ │   Setup pending          │ │
│ └──────────────────────────┘ │
│ ▸ Admins and alerts          │
│ ▸ AI usage                   │
└──────────────────────────────┘
```

### 3.4 Match quality

Changes:
- Reframe the page for job seekers as **"How well we match you"**. Hero metric: "Of the jobs we sent you in the last 30 days, **11%** moved forward" plus a plain-language "Your ratings" block with a progress nudge ("154 ratings. Rate a few jobs each day to keep your list sharp.").
- Accuracy check becomes "Match accuracy" with one sentence: "When we send you a job scored 7+, it's a fit about **7 in 10** times." The detailed Precision/Recall table goes behind a "Details" disclosure (admins by default open).
- The suggested cutoff becomes a callout with a direct action button [Use 6+] (writes `notify_threshold` via criteria save) instead of "go to Profile → Match rules".
- AI usage card: admin-only (hide for non-admins; it's in Admin already).
- "Run accuracy check" / "Rescore my open jobs": admin-only or behind a confirm explaining time and cost. Rescore should also warn that it replaces current scores.
- `EmptyState` when there's no eval: "We'll check accuracy after you rate 20 jobs" with a progress bar (labels_total / 20).

Desktop:
```
┌────┬──────────────────────────────────────────────────────────────────┐
│rail│ How well we match you                                            │
│    │ Your ratings teach jobwright what fits.                          │
│    │                                                                  │
│    │ ┌────────────────────┐ ┌────────────────────┐ ┌────────────────┐ │
│    │ │ 189                │ │ 11%                │ │ 154            │ │
│    │ │ jobs sent (30 d)   │ │ you moved forward  │ │ ratings so far │ │
│    │ └────────────────────┘ └────────────────────┘ └────────────────┘ │
│    │                                                                  │
│    │ Match accuracy                                                   │
│    │ When we send a job scored 7+, it's a fit about 7 in 10 times.    │
│    │ ┌─────────────────────────────────────────────────────────────┐  │
│    │ │ ℹ Suggested: send jobs scored 6+ (you use 7+).   [Use 6+]   │  │
│    │ │   You'd get more jobs, and about 7 in 10 would still fit.   │  │
│    │ └─────────────────────────────────────────────────────────────┘  │
│    │ ▸ Details (precision and recall by cutoff)                       │
│    │                                                                  │
│    │ Admin: [Run accuracy check] [Rescore open jobs]   AI usage ▸     │
└────┴──────────────────────────────────────────────────────────────────┘
```

Phone: the same content in a single column; metric cards as a 3-up row of compact tiles (number 22px, caption 12px), or stacked if the width is under 360px.

---

## 4. Implementation plan (parallel work packages)

Order: WP1 lands first (small, mechanical, 1–2 days). WP2–WP5 then run in parallel with no shared files beyond the WP1 primitives, which are frozen once WP1 merges. Each WP runs `pnpm run build`, does a visual check at 1440 and 390, light and dark, and updates `references/catalog.md` only for primitives it owns.

### WP1: Tokens, typography, primitives (blocking, one engineer)
Files:
- `frontend/src/index.css`: new color tokens (section 2.1), `--font-sans` system stack, type scale `--text-*`, spacing and radius tokens, elevation `--shadow-e1/e2`, focus outline, motion durations; soften stage tokens; `.surface` class; `.glass`/`.glass-strong` aliased to `.surface` (no blur); lane card tint to 7%.
- `frontend/index.html`: remove the Google Fonts links (or self-host via `@fontsource-variable/inter` in `package.json` + `main.tsx`).
- `components/ui/button.tsx`: sizes (`sm` 36/44 phone), variants `primary|secondary|ghost|destructive|link|ai`; keep the old names as aliases (`default`→primary, `outline`→secondary) so pages compile unchanged.
- `components/ui/input.tsx`, `textarea.tsx` (auto-grow), `select.tsx`, `tabs.tsx` (add `variant="underline"`), `dialog.tsx` (bottom-sheet on phone), `popover.tsx`.
- New: `components/ui/checkbox.tsx`, `components/ui/switch.tsx` (radix-ui already a dependency).
- New domain primitives: `components/PageHeader.tsx`, `components/SectionHeader.tsx` (keep `SectionLabel` re-exporting it), `components/SaveStatus.tsx`, `components/ActionBar.tsx`, `components/EmptyState.tsx`, `components/MobileNav.tsx` (extract the `Sheet` from `App.tsx`; App keeps using it).
- `components/FormField.tsx` (visible `hint`, `optional`, `error` props; `FieldHint` becomes a Popover in `FieldHint.tsx`).
- `components/Chip.tsx` + `ChipInput.tsx` (neutral default, `tone` recipe, 32px hit area on remove, placeholder "Add…" copy).
- `.cursor/skills/frontend-tasteful/SKILL.md`, `references/catalog.md`: record v2 direction and new primitives.
- Acceptance: the app builds with no page changes and looks calmer everywhere. No `text-[10px]`/`text-[11px]` left in `ui/` or the new primitives.

### WP1 implementation notes

Landed on branch `design-wp1`. Where the spec left a choice, the calm option was taken:

- **Font:** system stack only (`--font-sans` → `--app-font-sans`). No Inter, no font package, no CDN. To self-host later, prepend the family to `--app-font-sans`.
- **Radius:** `--radius` 10px; `rounded-md` 8px, `rounded-lg` 12px, `rounded-popover` 10px. `rounded-xl` is also 12px so the existing `rounded-xl` cards and lists match the card radius without page edits. Sheet and phone-dialog tops use `rounded-2xl` (16px).
- **Body text:** `text-body` is 15/24 on phone and 14/22 from 768px (CSS variables `--fs-body` / `--lh-body`). `body` uses it.
- **Chip size:** status chips keep the dense board size (`Chip size="sm"`, default) so the board keeps its density. The 28px / 32px phone size in 2.5 applies to removable form values (`ValueChip`, used by `ChipInput`). Chip text is `micro` (12px).
- **Chip tint:** the 2.1 recipe is the `tone-tint` utility driven by `--tone`. `Chip tone` and the tinted `Badge` variants use it. `--query-daily` and `--query-weekly` now alias a neutral grey, so keyword chips read neutral before WP3 lands. Good-fit (`--stage-prepare`) and location (`--stage-applied`) chips are still set by their callers; WP3 should make them neutral.
- **AI accent:** `Button variant="ai"` is accent-tinted (indigo) with no purple. `--tailor*` alias the accent, so no purple is left.
- **Buttons:** added `primary` and `secondary`; `default` and `outline` are aliases. Added `destructive-ghost` for list-level Remove. Sizes: `default` 40/44, `sm` 36/44, `lg` 44/48, `icon` 40/44, `icon-sm` 32/36, `xs` 28 (32 on phone). `xs` and `icon-sm` keep their small look but get a 44px `touch-target` hit area on phones and coarse pointers.
- **Focus ring:** a global `:focus-visible` outline (2px `--ring`, offset 2px). Text fields and select triggers use offset 0 plus an accent border, so the ring hugs the field. Legacy `focus-visible:ring-*` classes in pages still render; WP pages drop them as they migrate.
- **Dialog → bottom sheet:** below 640px (Tailwind `sm`) rather than 768px, so existing `sm:max-w-*` page overrides keep working. Every phone is under 640px. Default desktop width is 480px (`size="form"`), with `picker` at 640px and `wide`.
- **Safe area:** padding uses `env(safe-area-inset-bottom)` through `--safe-bottom`. `viewport-fit=cover` was not added to `index.html`. Without it iOS Safari reports 0 in normal browsing, which avoids content going under the notch in landscape. Add it only together with top and side insets.
- **PageHeader on phone:** the sticky bar shows the menu, the title (`heading` size) and actions; the description stays visible under the bar as a caption. On desktop the header is not sticky (no bar), and the title is `title` 22px.
- **MobileNav:** `MobileNavProvider` holds the open state in `App.tsx`. `MobileNav` (one sheet) renders there, and any page opens it through `PageHeader` / `MobileNavTrigger`. Welcome sits outside the provider, so the trigger renders nothing there. The phone menu theme row now shows its label, like the rail.
- **Dark mode:** pill tabs and `Segmented` use `--pill-active` (lighter than the tray in dark). Dialogs and sheets use `--popover` (0.23 L) so they lift by lightness, not shadow.
- **Glass:** `.glass`, `.glass-strong` and `.glass-interactive` are flat aliases (surface, hairline border, e1 on hover, no blur, no lift). The phone-only glass override was removed, so lane cards show the 7% tint on phones too.
- **Extra primitives:** `ui/dropdown-menu` (for "⋯" menus and chip move actions), `ui/segmented` (Daily/Weekly per row), `ui/skeleton` and `PageColumn` / `Page` (a page shell composing `PageHeader`). These were added because WP2-WP5 can't edit `ui/*`.
- **FormField:** `hint` is now visible text under the control. Existing callers' tooltip hints (all under 120 characters) become visible without page edits. `help` is the new popover prop. `label` accepts any node.
- **Textarea:** auto-grows by default (`field-sizing: content`, with a JS fallback where unsupported). `rows` sets the minimum height, capped at 60vh. `autoGrow={false}` restores a fixed, resizable textarea.
- **Not done in WP1 (owned elsewhere):** the sidebar stage icon colours and the board header control heights (WP6), the `QueryChipInput` embedded move button and its `text-[10px]` (WP3), the `ScoreBadge`/`ScoreEditor`/`JobsTable` `text-[10px]`/`[11px]` and the connections panel's 10-11px sizes (WP6).

### WP2: Welcome (one engineer)
Files: `pages/WelcomePage.tsx` (split into `pages/welcome/` step components if it passes about 400 lines: `WelcomeShell.tsx`, `StepAbout.tsx`, `StepResume.tsx`, `StepSearch.tsx`, `StepFit.tsx`, `StepDailyList.tsx`, `StepFinish.tsx`), `components/ConnectedChat.tsx` (add `hideTest` prop only).
- Uses `CriteriaEditor` read-only as-is, or passes `compact`; if a phone layout change to dealbreakers is needed, coordinate with WP3 (WP3 owns `CriteriaEditor`). WP2 may render its own simplified fit form to avoid conflict.
- Does not touch API contracts (`draftSetup`, `confirmSetup`, `updateProfile`, `startRun` unchanged).

### WP3: Profile (one engineer)
Files: `components/ProfilePage.tsx` (split tabs into `components/profile/SearchTab.tsx`, `RulesTab.tsx`, `DocumentsTab.tsx`, `DailyListTab.tsx`, `AboutTab.tsx`), `components/CriteriaEditor.tsx`, `components/QueryChipInput.tsx` (new `KeywordList` mode), `components/LocationChipInput.tsx`, `components/BoardToggles.tsx` (empty = all default state), `components/ProfileMaterials.tsx`, `components/ResumePreview.tsx`, `components/WhatsAppChatPicker.tsx` (show a friendly fallback for unnamed groups: "Unnamed group · …4902").
- Keeps autosave debounce and endpoints; adds `SaveStatus` and `ActionBar`.
- Adds `MobileNav` trigger via `PageHeader`.

### WP4: Admin (one engineer)
Files: `pages/AdminPage.tsx`, `components/admin/SystemStrip.tsx` (becomes status list; keep the file name), `PersonRow.tsx` (header row, labels, status text), `PersonSettings.tsx` (grouping, actions menu, `Switch`), `CollapsibleSection.tsx`, `AddPersonDialog.tsx`, `AdminsAlertsSection.tsx`, `AiUsageSection.tsx`, `ConfirmDialog.tsx`, `adminFormat.ts` (status labels: never "No daily list yet" when `brief_today` shows a send).
- Phone: person detail in a bottom `Sheet` (new local component `components/admin/PersonSheet.tsx`).
- Keep optimistic patch and rollback logic in `AdminPage` untouched.

### WP5: Match quality (one engineer, small; can pair with WP4)
Files: `pages/QualityPage.tsx` only (+ optional `components/quality/*`). Uses `useMe().me.is_admin` to gate AI usage and run buttons. The "Use 6+" action calls the existing `saveCriteria` with `notify_threshold` after `getCriteria` (no API change).

### WP6: Board and drawer token alignment (after WP1; optional; one engineer)
Files: `components/KanbanColumn.tsx`, `JobCardView.tsx`, `JobCardLayout.tsx`, `JobMetaBadges.tsx`, `SponsorshipBadge.tsx` (hide unknown), `JobDrawer.tsx` (action row hierarchy, render JD markdown), `StagePicker.tsx`, `App.tsx` header (mobile header condensed to one row plus a search icon). Density stays.

Conflict map: WP1 owns `ui/*`, `index.css`, and the new shared primitives. WP2 owns `pages/WelcomePage*` + the `ConnectedChat` prop. WP3 owns `ProfilePage`, `CriteriaEditor`, chip inputs, materials and picker. WP4 owns `components/admin/*` + `AdminPage`. WP5 owns `QualityPage`. WP6 owns the board, drawer and `App.tsx`. The only cross-WP edit is `App.tsx` adopting `MobileNav` (WP1 extracts it; WP6 later restyles the board header).

Suggested order after WP1: WP3 and WP2 first (highest user impact), WP4 and WP5 in parallel, WP6 last.

Quality gate per WP: `cd frontend && pnpm run build`; no new hardcoded colours (`rg "#[0-9a-f]{3,6}|oklch\(" frontend/src --glob '!index.css'` returns nothing new); keyboard pass (Tab through every control, visible focus); 390px pass (no horizontal scroll, 44px targets); dark mode pass.

---

## 5. Mobbin reference queries (generic, no app data)

- "onboarding multi-step form progress bar web"
- "resume upload onboarding"
- "settings page left navigation web app"
- "settings mobile tabs"
- "autosave indicator settings"
- "unsaved changes sticky bar"
- "tag input chips form"
- "notification schedule settings time picker"
- "admin users table expandable row"
- "system status list health check"
- "empty state dashboard first run"
- "metrics summary cards analytics simple"
- "bottom sheet form mobile web"
- "Linear settings" / "Notion settings" (for rhythm and type scale)
