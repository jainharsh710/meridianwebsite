# Meridian content engine

Writes, checks and publishes one Insights article every Monday at 02:00 IST, then reports results by email.
Runs entirely on GitHub Actions; nothing runs on anyone's laptop.

## What runs when
- `.github/workflows/seo-weekly.yml`: Monday 02:00 IST. Learns from Search Console, emails last week's
  results, picks a topic, researches, writes, edits, runs the compliance gate, builds the page, pushes to
  `main` (Cloudflare deploys it), confirms it is live, pings IndexNow, resubmits the sitemap, emails the article.
- `.github/workflows/seo-daily-index.yml`: daily 09:00 IST. Records which posts Google has indexed.

## Controls
- **Pause:** add an empty file named `PAUSE` at the repo root. Delete it to resume.
- **Stop completely:** GitHub → Actions → the workflow → "..." → Disable workflow.
- **Try it without publishing:** Actions → "SEO engine (weekly article)" → Run workflow → tick "Dry run".
- **Undo a post:** revert its commit ("Publish: <title>").
- **Spend cap:** repository variable `MAX_RUN_USD` (default 12). Set a monthly limit in the Anthropic Console too.

## Secrets (Settings → Secrets and variables → Actions)
`ANTHROPIC_API_KEY`, `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, `GSC_SA_JSON`, `RESEND_API_KEY`, `REPORT_EMAIL`.
Optional variables: `MAIL_FROM` (default `Meridian SEO Engine <seo@meridiancapital.in>`), `MAX_RUN_USD`.

## Where things live
- `prompts/`: the instructions for each agent (shared context, topic map and compliance rules in `00_shared.md`).
- `engine/`: the code. `pipeline.py` is the weekly flow; `site.py` builds pages from an existing article as the template.
- `data/`: posts, strategy, topic ledger, experiments, perspective bank, Search Console snapshots, and every
  agent's input and output per run in `data/runs/<date>/`.

`automation/` and `.github/` are excluded from the public site by `.assetsignore` and `_redirects`.

## Test offline
`python automation/tests/offline_test.py` runs the full pipeline on a temporary copy of the site with
simulated AI and API replies.
