# Financial Overview

Search a UK company at Companies House, pull its filed statutory accounts as PDFs, and
have Claude summarise one filing or compare several.

Type a company name → pick from the search results → its accounts filings list out,
newest first → tick the ones you want → Claude reads the actual PDFs and returns a
summary (one filing) or a trend table plus trajectory read (several). Every filing also
links to the raw PDF.

## Stack

- **Backend** (`apps/api`): FastAPI, deployed to Railway. Stateless — no database.
- **Frontend** (`apps/web`): Next.js 14 (App Router) + Tailwind, deployed to Vercel.
- **Data source**: Companies House public data API + document API. See [docs/SETUP.md](./docs/SETUP.md).
- **Review**: Anthropic Messages API — filing PDFs go up as `document` blocks, no OCR step.

## Layout

```
apps/
  api/         FastAPI service
    app/
      routers/       /companies
      schemas/       Pydantic response models
      services/      Companies House client, Claude filing analysis
    tests/
  web/         Next.js app
    app/             the search + review page
    components/
    lib/
docs/          Setup and deploy guides
docker-compose.yml
```

## Quick start (local)

```sh
# 1. Get your keys — follow docs/SETUP.md, then:
cp apps/api/.env.example apps/api/.env
# edit COMPANIES_HOUSE_API_KEY and ANTHROPIC_API_KEY

# 2. Bring both services up
docker compose up --build

# 3. Open http://localhost:3000 and search a company
```

Without Docker:

```sh
cd apps/api && pip install -e ".[dev]" && uvicorn app.main:app --reload
cd apps/web && npm install && npm run dev
```

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Liveness |
| GET | `/companies/features` | Which keys are configured (drives the UI banners) |
| GET | `/companies/search?q=` | Company name/number search |
| GET | `/companies/{number}` | Company profile |
| GET | `/companies/{number}/filings` | Accounts filings, newest first |
| GET | `/companies/{number}/filings/{transaction_id}/pdf` | The filed PDF |
| POST | `/companies/{number}/analyse` | `{transaction_ids: [], question?}` → Markdown review |

Interactive docs at `/docs` when the API is running.

## Tests

```sh
cd apps/api && pytest
```

## Deploy

Railway (API) + Vercel (web). See [docs/DEPLOY.md](./docs/DEPLOY.md).
