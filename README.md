# Financial Overview

Search UK companies at Companies House, pull their filed statutory accounts as PDFs,
and have Claude review and compare them.

Work one company at a time in the left-hand rail: add it, tick up to **4 years** of
accounts, and analyse it. Claude reads the actual filed PDFs and the write-up opens in its
own tab on the right. Repeat for up to **5 companies**, then hit **Compare** — with an
optional steer on what matters — for a side-by-side comparison in its own tab. Every
filing also links to the raw PDF.

Tick **Research online** and each company gets a second pass over the open web —
what it actually does, how it makes money, and recent news — cross-checked against the
filed figures. Because businesses are usually known online by something other than their
registered name, each company has a **Trades under a different name** box; fill it in and
the search keys off that instead.

Analysis and comparison are separate steps, because five companies' filings will not fit
in one request:

1. **Per company** — that company's selected filings go up together, so the review reads
   year on year within the company.
2. **Across companies** — the finished reviews (not the PDFs again) go up for the
   comparison, which keeps the request small and the figures consistent. It also means
   you can analyse as you go and only pay for a comparison when you want one.

Web research, when enabled, is a third call per company, made after its accounts review
so it can be grounded in the filed figures. It uses Claude's server-side `web_search` and
`web_fetch` tools — no scraping to run or maintain.

Runs are asynchronous: the API returns a job id and the page renders each company's
review as it lands.

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
      routers/       /companies, /analyses
      schemas/       Pydantic response models
      services/      Companies House client, Claude filing analysis,
                     web research, multi-company run jobs
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
| POST | `/analyses/company` | Start one company: `{company_number, transaction_ids, trading_name?, research?}` |
| GET | `/analyses/company/{id}` | Poll that company's review |
| POST | `/analyses/compare` | Compare finished analyses: `{analysis_ids: [], guidance?}` |
| GET | `/analyses/compare/{id}` | Poll the comparison |
| POST | `/companies/{number}/analyse` | Single company, synchronous → Markdown review |

Interactive docs at `/docs` when the API is running.

## Tests

```sh
cd apps/api && pytest
```

## Deploy

Railway (API) + Vercel (web). See [docs/DEPLOY.md](./docs/DEPLOY.md).
