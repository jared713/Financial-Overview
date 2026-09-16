# Financial Overview

Two workspaces, sharing one saved library.

**Companies** — search UK companies at Companies House, pull their filed statutory
accounts as PDFs, and have Claude review and compare them.

**Industries** — upload the documents you already have about a market (a government
review, a regulator's report, a trade survey), say what you want out of them, and get a
write-up grounded in those documents alone.

Work one company at a time in the left-hand rail: add it, tick up to **4 years** of
accounts, and analyse it. Claude reads the actual filed PDFs and the write-up opens in its
own tab on the right. Repeat for up to **5 companies**, then hit **Compare** — with an
optional steer on what matters — for a side-by-side comparison in its own tab. Every
filing also links to the raw PDF.

Every review has three parts: the open web — what the company actually does, how it makes
money, and recent news — cross-checked against the filed figures; then **ownership and
investors**, from the PSC register and the shareholder lists inside confirmation
statements; then the accounts themselves. Because businesses are usually known online by something other than their
registered name, each company has a **Trades under a different name** box; fill it in and
the search keys off that instead.

Analysis and comparison are separate steps, because five companies' filings will not fit
in one request:

1. **Per company** — that company's selected filings go up together, so the review reads
   year on year within the company.
2. **Across companies** — the finished reviews (not the PDFs again) go up for the
   comparison, which keeps the request small and the figures consistent. It also means
   you can analyse as you go and only pay for a comparison when you want one.

Web research is a second call per company, made after its accounts review so it can be
grounded in the filed figures — but it reads first, because what the business does frames
every number that follows. It uses Claude's server-side `web_search` and `web_fetch`
tools, so there is no scraping to run or maintain.

Runs are asynchronous: the API returns a job id and the page renders each company's
review as it lands.

Everything you run is **kept until you delete it**. The **Saved** button opens the
library — every analysis and comparison, newest first, each with Open and Delete. Storage
is SQLite in `DATA_DIR`; mount a Railway volume there and it survives redeploys.

## Industry analysis

Upload up to 8 files (PDF or plain text, 20MB total), name the industry, and give an
instruction — "size the market and flag the policy risks" — or leave it blank for a
general summary. Claude is told to attribute every figure to the document it came from,
to label its own inferences as inferences rather than sourced claims, and to say what the
documents do not cover, including where a source's own interests colour what it reports.

Uploaded files are read into the request and then dropped. Only the filenames and the
write-up are stored.

## Stack

- **Backend** (`apps/api`): FastAPI, deployed to Railway. SQLite on a mounted volume for
  saved results; nothing else persisted.
- **Frontend** (`apps/web`): Next.js 14 (App Router) + Tailwind, deployed to Vercel.
- **Data sources**: Companies House public data API (search, filing history, PSC
  register) + document API (the filed PDFs). See [docs/SETUP.md](./docs/SETUP.md).
- **Review**: Anthropic Messages API — filing PDFs go up as `document` blocks, no OCR step.

## Layout

```
apps/
  api/         FastAPI service
    app/
      routers/       /companies, /analyses, /industry
      schemas/       Pydantic response models
      services/      Companies House client, Claude filing analysis,
                     web research, ownership, industry, run jobs, SQLite store
    tests/
  web/         Next.js app
    app/             / (companies) and /industry
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
| POST | `/industry` | Upload documents (multipart) and start an industry analysis |
| GET | `/industry/{id}` | Poll an industry analysis |
| DELETE | `/industry/{id}` | Delete a saved industry analysis |
| GET | `/analyses` | The saved library, newest first — companies and industries |
| DELETE | `/analyses/company/{id}` | Delete a saved analysis |
| DELETE | `/analyses/compare/{id}` | Delete a saved comparison |
| POST | `/companies/{number}/analyse` | Single company, synchronous → Markdown review |

Interactive docs at `/docs` when the API is running.

## Tests

```sh
cd apps/api && pytest
```

## Deploy

Railway (API) + Vercel (web). See [docs/DEPLOY.md](./docs/DEPLOY.md).
