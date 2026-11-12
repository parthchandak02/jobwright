# jobwright design rules

Read before any dashboard change. The UI skill ([frontend-tasteful](../.cursor/skills/frontend-tasteful/SKILL.md))
has the tokens and primitives; this file has the principles and what we learned. Add a dated line to
Lessons whenever a change teaches something (a correction from Parth always counts), and edit a rule
that stops holding instead of arguing with it further down.

Grounded in Don Norman's *The Design of Everyday Things*, Steve Krug's *Don't Make Me Think* and
progressive disclosure, the same principles Tandem and Wedding Looks follow (adopted here 8 Nov 2026).
jobwright keeps its own look (design v2, "calm & refined", system type); only the principles are shared.

## Who it's for

Job seekers who aren't technical, on a phone between other things and on a laptop when applying. Most
visits are one of three jobs: see what's new and decide (Review), act on one job (open it, prepare,
apply), or fix a setting. Every screen should make its one job obvious.

## Principles

1. **Show it, don't write it.** An icon, colour, position or number beats a sentence. Cards show the
   score as a number in its colour, pay as `$165k-190k`, materials as icons in the table.
2. **One obvious next step per screen.** One solid (primary) button: Review on the board, the stage's
   next step in a job, Interested in Review. Everything else is secondary, ghost or an icon.
3. **Short words.** Labels 1 to 3 words ("Good match?", "Why not?", "Where", "Visa"). Page and section
   titles are enough; no subtitle that restates the title.
4. **Help behind an ⓘ.** Explanations go in `help` (`PageHeader`, `SectionHeader`, `FormField`), which
   renders the ⓘ popover (`FieldHint`). Only what's needed to act stays on screen. What stays visible
   no matter what: anything about what gets sent or submitted for the person (Claude stops before
   Submit, a real WhatsApp message goes out), and confirm dialogs.
5. **One meaning per signal, everywhere.** Green / amber / grey = strong / partial / weak fit, and
   nothing else on a card is coloured except a real problem (red) or a follow-up. Stage colour is a
   dot, never a fill or stripe. A new colour or icon needs a key (the board's ⓘ is the score key).
6. **Feedback for every action.** Toast with Undo for moves and ratings, `SaveStatus` for autosave,
   progress in the button while a search runs. Never a silent button.
7. **Signifiers.** Tappable things look tappable; 44px targets on phones; nothing important only on
   hover or only by swipe (Review's swipe has buttons too).
8. **Nothing covers content.** No floating buttons over lists; toasts sit above the tab bar; phone
   headers carry the title, so nothing repeats it below.
9. **Honest data.** Never show a guess as fact: scores say how sure they are, empty facts are left
   out rather than filled with "Not mentioned", pay we can't read is shown as written.
10. **Progressive disclosure.** Long text folds (the match reason shows 3 lines, then More); rarely
    used controls go one level down (the stage is a menu, not six chips).

## Before shipping a screen change

- Screenshot phone (390) and wide (1440), light and dark, before and after (`readme_images.py`
  fixtures drive the dashboard with fake data). Look at them; don't trust a passing build.
- Ask: what can be removed? Could a sentence be an icon or go behind an ⓘ? Is there exactly one
  primary button? Does every colour mean the one thing it means everywhere else?
- `cd frontend && pnpm build && pnpm lint && pnpm test`.

## Lessons (newest first)

- 2026-11-12: ⌘F / Ctrl+F opens a global search (jobs incl. closed, pages, settings tabs) instead of the
  browser's find; pressing it again hands over to the browser. Single-letter matches are not highlighted
  (they marked half of every row).
- 2026-11-09: Lane headers must stay visible while a lane scrolls (Parth). A sticky header only sticks to
  its nearest scroll container, and the board row's own `overflow-x-auto` swallowed it. On desktop the
  page (`main`) now scrolls both ways and the headers are `sticky` with a background.
- 2026-11-08: Parth said the site still read as a wall of text. Measure it: count visible words per
  screen on a phone before and after (About you went 468 → 138, Claude 305 → 215). Application
  details became short names ("Need visa sponsorship"; the full form wording sits behind ⓘ only
  when there's a hint), Yes / No questions became one row each with the answer on the right, an
  amber dot replaced nine "Needed" badges (the section title counts them), where an answer came
  from is an icon, and empty optional fields wait behind "More (5)". A cleanup isn't done until the
  live site shows it: say clearly when changes are only on a branch.
- 2026-11-08: Applied Tandem's principles across the dashboard. Board header: Review is the one
  primary button; Auto Search, WhatsApp and Add job became icons with tooltips. Cards lost the
  repeated per-card link icon (the job panel has Open posting), the "Strong" word (colour + key
  carry it) and "Resume + letter" outside Prepare (it only matters before applying). The job panel's
  six stage chips became one Stage menu inside Details, and empty rows ("Sponsorship: Not
  mentioned") are left out. Page and section explanations moved behind ⓘ; removing a description
  must not leave an empty gap on phones (`PageHeader` drops its top padding then).
- 2026-11-08: Card style B (Parth's pick): no stage stripe on cards; the lane header carries the
  stage, and the score is the only colour on a card.
- 2026-11-08: Repeated per-row buttons are a smell (from Wedding Looks): a list of prompts gets icon
  Copy buttons, not a column of "Copy" pills.
