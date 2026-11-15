# Shot list: jobwright cook

Data: `scripts/cook_demo_server.py` (Alex Rivera fixtures). Theme: set `localStorage jobwright-theme` via shoot `--dark` when needed.

| Shot | Refs | Shows | Route | Viewport | State | Take from refs | Watch for |
|---|---|---|---|---|---|---|---|
| S01 | R01,R02,R03 | Board kanban | `/` | 390, 1440 | light/dark, board tab | card density, calm neutrals, one primary CTA | lane scroll, sticky headers, overflow |
| S02 | R04 | Job drawer | `/jobs/HERO_ID` | 390, 1440 | light/dark | section rhythm, score color discipline | wall of text, duplicate titles |
| S03 | R01 | Quick review | `/review` | 390 | light/dark | focused single-task layout | one primary, swipe + buttons |
| S04 | R05 | Settings About | `/profile?tab=about` | 390, 1440 | light/dark | open whitespace, form rows | field spacing, help behind i |
| S05 | R06 | Match quality | `/quality` | 1440 | light/dark | chart + numbers polish | tabular nums, admin calm |

HERO_ID: first backlog job with score 9 from fixtures (discover at runtime from board JSON or readme_images HERO_JOB).