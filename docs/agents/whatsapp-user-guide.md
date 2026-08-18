# WhatsApp user guide (jobwright via Hermes)

Plain-language guide for humans. Share this with anyone using job search help over WhatsApp.

## What this is

**Hermes** is the AI assistant on the Mac mini. **jobwright** is the job-search tool behind it: find roles, score fit, tailor resumes, write cover letters, and optionally submit applications (with your approval).

You talk to Hermes on WhatsApp. Hermes runs jobwright on the server.

## Getting started

1. Ask the admin to register you (name, resume, target roles, WhatsApp chat).
2. Once registered, you receive **job digests** on a weekday schedule (typically every few hours).
3. Each digest lists top matching jobs with scores and links.

No app to install. Just message Hermes in WhatsApp.

## Messages you can send

| You send | What happens |
|----------|----------------|
| `job status` or `how are my jobs?` | Hermes shows pipeline stats (discovered, scored, tailored, applied). |
| `find jobs now` | Hermes runs a fresh search (may take several minutes). |
| `CONFIRM APPLY` | **Only if apply is enabled for you.** Starts live applications for jobs in today's digest. One batch per day. |
| `help jobs` | Hermes explains what you can do and whether apply is on or off. |
| Resume or preferences in plain text | Hermes can update your profile (admin may need to approve). |

Hermes understands normal language too. Examples: "Any new PM roles in the Bay Area?" or "Pause applications for me."

## Daily digest flow

```
Morning / periodic prep  →  Digest on WhatsApp  →  You review
                                                      ↓
                                            (optional) CONFIRM APPLY
                                                      ↓
                                            Live apply (if enabled)
```

**Find-only mode (default for new users):** You get digests and tailored materials. Nothing is submitted until you explicitly opt in and send `CONFIRM APPLY`.

**Apply enabled:** Digest includes a line asking you to reply `CONFIRM APPLY` to submit up to a few top jobs from that digest. Reply exactly that phrase (case insensitive is fine).

## Safety rules (for you)

1. **Nothing submits without `CONFIRM APPLY`** (and only if apply is enabled on your profile).
2. **One apply batch per day** after you confirm.
3. **LinkedIn applications are never automated** (blocked by design).
4. **Dry-run first:** Admin enables live apply only after test runs look good.

## What you will not get on WhatsApp

- Full PDF resumes inline (links or summaries instead).
- Instant apply to a random URL you paste (admin/agent workflow required).
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
| No digest today | Ask Hermes: "Did the job pipeline run?" |
| `CONFIRM APPLY` did nothing | Apply may be disabled, digest may be find-only, or you already applied today. Ask Hermes to check. |
| Wrong jobs showing up | Tell Hermes your updated titles, locations, or salary floor. |
| Want to stop applying | Say "turn off auto apply" or "find only mode." |

## Example conversation

```
You:  job status
Bot:  42 discovered, 8 scored 7+, 3 tailored, 0 applied today.

You:  find jobs now
Bot:  Running discover → score → tailor. I'll message when done (~10 min).

You:  (later, digest arrives with 5 jobs)
You:  CONFIRM APPLY
Bot:  Confirmed. Submitting up to 5 jobs from today's list...
      Applied 3/5. 2 need manual follow-up (captcha).
```

## Privacy

- Resume and profile data stay on the Mac mini under your user folder.
- API keys are global and never sent in WhatsApp messages.
- Do not paste passwords or SSNs in chat.

## Admin / power users

See `docs/agents/whatsapp-routing.md` (Hermes agent) and `docs/agents/hermes-setup.md` (cron install).
