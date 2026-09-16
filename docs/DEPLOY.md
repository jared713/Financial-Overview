# Deploy: Railway + Vercel

```
GitHub (main)
   │
   ├─> Vercel ─── apps/web      (Next.js)
   │
   └─> Railway ── apps/api      (FastAPI, Dockerfile)
```

Results are saved to SQLite in `DATA_DIR` and kept until deleted. **Run the API as a
single replica** — one process owns that file, and in-flight runs are tracked in memory,
so a second instance would not see the first one's work.

## Railway — API

1. **New project** → "Deploy from GitHub repo" → pick this repo.
2. Set the service root to `apps/api`. Railway picks up `apps/api/Dockerfile` and
   `apps/api/railway.json`.
3. Set environment variables on the service:
   - `COMPANIES_HOUSE_API_KEY` (required — see [SETUP.md](./SETUP.md))
   - `ANTHROPIC_API_KEY` (optional; without it the review button is disabled)
   - `ANTHROPIC_MODEL` (optional, defaults to `claude-opus-5`)
   - `CORS_ORIGINS` → your Vercel URL, comma-separated, **no brackets or quotes**:
     `https://financial-overview.vercel.app`
4. Deploy, then check:
   - `https://<your-api>.up.railway.app/healthz` → `{"status":"ok"}`
   - `https://<your-api>.up.railway.app/companies/features` →
     `{"companies_house":true,"claude_review":true,…}`

The startup log prints which variables are set (names only, never values).

## Railway — storage volume

Without a volume the SQLite file sits on the container's filesystem and is wiped on
every deploy. The app still runs and still saves; it just forgets. The page shows an
amber banner when that is the case, and `/companies/features` reports
`saving_is_durable: false`.

To keep saved work:

1. On the `api` service → **Settings** → **Volumes** → **Add volume**.
2. Mount path: `/data` (matching `DATA_DIR`).
3. Redeploy. The startup log prints the store path and whether it is durable.

A few MB covers thousands of analyses — the rows are Markdown, and filing PDFs are not
kept. To back it up, or move it, copy `/data/financial-overview.sqlite3` (and the `-wal`
file alongside it) via a Railway shell.

## Vercel — Web

1. **Add new project** → import this repo.
2. Set **Root Directory** to `apps/web`.
3. Framework preset: Next.js (auto-detected).
4. Environment variable: `NEXT_PUBLIC_API_URL=https://<your-api>.up.railway.app`.
5. Deploy. Vercel auto-deploys on push to `main`.

Set `CORS_ORIGINS` on Railway to the Vercel URL you end up with, including any custom
domain. A mismatch shows up as a CORS error in the browser console with the API itself
returning 200.

## Costs and timeouts

- Companies House API is free (600 requests / 5 minutes), and the Industries workspace
  does not use it at all.
- Anthropic is the only per-use cost: roughly $0.30–$1.50 for two sets of full accounts,
  a few cents for small-company filings. `ANTHROPIC_MAX_TOKENS` caps the response.
- Each company takes a minute or two, and the comparison another. That is why both are
  asynchronous — the POST returns an id and the page polls — so there is no gateway
  timeout to tune.
- Cost scales with pages, not companies. Five small companies cost pennies; five sets of
  full plc accounts with four years each can run to $20+. The page shows an estimate
  from the filings' page counts before you start.
- **Web research** runs for every company, adding server-side web search and fetch on top
  of the token cost, billed per search. The per-company estimate on the page covers the
  filings only and marks the rest as "+ web".
- Outbound network access for research is Anthropic's, not your Railway service's — the
  search and fetch run on Anthropic's infrastructure, so nothing extra is needed on the
  container.

## Before making the API public

The API has **no authentication**. Anyone who finds the Railway URL can spend your
Anthropic credit, **read every saved analysis, and delete them**. That matters more now
that results persist — the library is the whole history of what you have researched.
Options, cheapest first:

1. Keep the URL private and unshared (fine for personal use, but it is not a secret —
   Railway URLs are guessable and the Vercel app exposes it to the browser).
2. Put a shared bearer token in front of the API and send it from the web app.
3. Front it with an auth proxy (Cloudflare Access, Vercel middleware + a session).
