# WhatsApp user guide (jobwright via Hermes)

Plain-language guide for humans. Share this with anyone using job search help over WhatsApp.

## What this is

**Hermes** is the AI assistant on the Mac mini. **jobwright** is the job-search tool behind it: find roles, score fit, tailor resumes, write cover letters, and optionally submit applications (with your approval).

You talk to Hermes on WhatsApp. Hermes runs jobwright on the server.

## Getting started

1. Ask the admin to register you (name, resume, target roles, WhatsApp chat).
2. Once registered, you get **one WhatsApp message each morning** listing new jobs that are ready to review.
3. Each line has a link. Tap it to open that job in your dashboard, where the tailored resume, cover letter, and networking suggestions live.

No app to install. Just message Hermes in WhatsApp, and open the links you receive in a browser.

## Messages you can send

| You send | What happens |
|----------|----------------|
| `job status` or `how are my jobs?` | Hermes shows pipeline stats (discovered, scored, tailored, applied). |
| `find jobs now` | Hermes runs a fresh search (may take several minutes), then sends the new-jobs list. |
| `notify` or `resend my jobs` | Hermes resends the current list of new jobs with dashboard links. |
| `help jobs` | Hermes explains what you can do and whether apply is on or off. |
| Resume or preferences in plain text | Hermes can update your profile (admin may need to approve). |

Hermes understands normal language too. Examples: "Any new PM roles in the Bay Area?" or "Pause applications for me."

## Daily flow

```
Morning search (pipeline runs)  ->  One WhatsApp list of new jobs
                                          |
                                    Tap a job link
                                          |
                              Review + apply in the dashboard
```

**Find-only mode (default for new users):** You get the daily list and tailored materials in the dashboard. Nothing is submitted for you.

**Apply enabled:** You can submit an application from the dashboard apply button (it asks you to confirm first). Applying never happens automatically.

## Safety rules (for you)

1. **Nothing submits automatically.** Applying only happens when you press apply in the dashboard and confirm.
2. **LinkedIn applications are never automated** (blocked by design). LinkedIn jobs still appear with tailored materials; you apply manually via the LinkedIn link.
3. **Dry-run first:** Admin enables live apply only after test runs look good.

## What you will not get on WhatsApp

- Full PDF or DOCX resumes inline (open the dashboard link instead).
- Instant apply to a random URL you paste (use the dashboard).
- LinkedIn connection scraping (export a Connections CSV if you want networking suggestions).

## Networking and company targets

Ask Hermes:

- "Who in my network works at these companies?"
- "Build a target company list for fintech in SF."

Requires a LinkedIn **Connections.csv** export at `users/<id>/connections.csv` (admin helps upload once; dummy OK for testing).

Cover letter examples go in `cover-letter/examples/`. Resume source: `resume/base.txt`.

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| No list today | Ask Hermes: "Did the job pipeline run?" (the list is only sent when new jobs are ready). |
| A job link will not open | Ask Hermes to check the dashboard is up, or resend with `notify`. |
| Wrong jobs showing up | Tell Hermes your updated titles, locations, or salary floor. |
| Want to stop applying | Say "turn off auto apply" or "find only mode." |

## Example conversation

```
You:  job status
Bot:  42 discovered, 8 scored 7+, 3 tailored, 0 applied today.

You:  find jobs now
Bot:  Running discover -> score -> tailor. I'll message when done (~10 min).

Bot:  (later) 3 new jobs ready to review:
      * Chief of Staff @ Acme - jobwright.parthchandak.info/jobs/ab12cd
      ...
You:  (tap a link, review and apply in the dashboard)
```

## Privacy

- Resume and profile data stay on the Mac mini under your user folder.
- API keys are global and never sent in WhatsApp messages.
- Do not paste passwords or SSNs in chat.

## Admin / power users

See `docs/agents/whatsapp-routing.md` (Hermes agent) and `docs/agents/hermes-setup.md` (cron install).
