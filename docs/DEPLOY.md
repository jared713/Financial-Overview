# Deploy: Railway + Vercel

```
GitHub (main)
   │
   ├─> Vercel ─── apps/web      (Next.js)
   │
   └─> Railway ── apps/api      (FastAPI, Dockerfile)
```

No database, no background jobs — the API is stateless, so both sides are a plain
build-and-serve.

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

- Companies House API is free (600 requests / 5 minutes).
- Anthropic is the only per-use cost: roughly $0.30–$1.50 for two sets of full accounts,
  a few cents for small-company filings. `ANTHROPIC_MAX_TOKENS` caps the response.
- Analysing five or six large filings can take a couple of minutes in one request. If
  you hit a gateway timeout, analyse fewer at a time.

## Before making the API public

The API has **no authentication**. Anyone who finds the Railway URL can spend your
Anthropic credit through `/companies/{no}/analyse`. Options, cheapest first:

1. Keep the URL private and unshared (fine for personal use, but it is not a secret —
   Railway URLs are guessable and the Vercel app exposes it to the browser).
2. Put a shared bearer token in front of the API and send it from the web app.
3. Front it with an auth proxy (Cloudflare Access, Vercel middleware + a session).
