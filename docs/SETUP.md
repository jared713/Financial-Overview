# Setup: Companies House + Claude

Two API keys. The Companies House one is required; the Anthropic one is optional and
only enables the review.

## 1. Get a Companies House API key

1. Register at <https://developer.company-information.service.gov.uk/> (free).
2. **Manage applications** → **Create an application** → environment **Live**.
3. Inside the application, **Create new key** → key type **REST**.
4. Copy the key into `COMPANIES_HOUSE_API_KEY`.

Notes:

- The key is used as the HTTP Basic *username*, with an empty password. The API
  client handles that; you only ever paste the raw key.
- Rate limit is **600 requests per 5 minutes** per key. The app caches downloaded
  PDFs in memory for 30 minutes so downloading and then analysing the same filing
  costs one fetch.
- Live keys can be restricted to an IP allowlist. If you set one, add your Railway
  service's egress IP or requests will 401.
- Keep the key server-side only. It lives on the API service; the browser never sees
  it, which is why filing PDFs are proxied through `/companies/{no}/filings/{txn}/pdf`
  rather than linked directly to Companies House.

## 2. Get an Anthropic API key (optional)

<https://console.anthropic.com/settings/keys> → `ANTHROPIC_API_KEY`.

Without it the app still searches companies and downloads filing PDFs — the
"Review with Claude" button is disabled and the UI says why.

`ANTHROPIC_MODEL` defaults to `claude-opus-5`.

## 3. How it works

```
name ──> GET /companies/search           search/companies
     ──> GET /companies/{no}/filings     filing-history?category=accounts
     ──> GET …/filings/{txn}/pdf         document-api /document/{id}/content
     ──> POST …/analyse                  PDFs -> Claude Messages API
```

Downloading a filing is a two-hop dance: the document API answers `302` to a
signed AWS URL, and the Companies House `Authorization` header must **not** be
replayed to AWS (S3 rejects two auth mechanisms). `fetch_document_pdf` follows
that redirect by hand with a clean client.

The PDFs go to Claude as `document` content blocks — no OCR step, which matters
because many small-company filings are scanned images. All selected filings go up
in one message, oldest first, so the model compares them against each other rather
than summarising each in isolation.

## 4. What you get back

**Per company.** One year selected → filing details, a table of the disclosed figures,
what stands out, and watch-outs. Two or more years → an overview, a trend table with one
column per period, a trajectory read, comparability flags, and watch-outs.

**Across companies** (two or more selected) → a side-by-side table using each company's
most recent period, how they compare, standouts, comparability caveats, and watch-outs.

**Web research** (optional, per run). A second pass per company using Claude's
server-side `web_search` and `web_fetch` tools:

- *What they do* — the business in plain terms, and how confident Claude is that it found
  the right company. UK trading names collide constantly, so it is told to confirm the
  site against the company number, registered office or filed name, and to say so when it
  cannot.
- *Revenue model* — the revenue streams it can evidence, each marked as from the filings
  or from the web, and whether the accounts support the picture the website paints.
- *Recent news* — roughly the last 18 months, dated and attributed.
- *Sources* — title and URL for each.

Most businesses are known online by something other than their registered name, so each
company has a **Trades under a different name** field; it is passed to the research pass
as the name to search for. With research on, the comparison also gains a *How they make
money* section.

Limits: **5 companies per comparison**, **4 years each**, and 20MB of PDF per company.
The comparison takes an optional steer ("focus on cash generation and debt"), answered in
an extra section.

Companies are analysed one at a time, so you can read the first while the second runs, and
a company only needs analysing again if you change which years it covers.

## 5. Limits worth knowing

- **Filleted and micro-entity accounts have no profit and loss account.** Most small
  UK companies file these, so turnover and profit are simply not there. The prompt
  tells Claude to say "not disclosed" rather than infer — if you need revenue for a
  small company, Companies House does not have it.
- Scanned paper filings are flagged `scanned` in the filings table. Claude reads them
  visually, but figures from a poor scan deserve a check against the source PDF.
- Accounts are filed up to 9 months after period end, so the most recent filing is
  usually 9–21 months behind today.
- A long analysis run (5–6 filings) can take a couple of minutes; the page shows progress
  per company while it works.
- Web research adds time and cost per company: a handful of searches and page fetches,
  billed on top of the tokens. It is off by default for that reason.
- Research quality varies wildly by company. A listed plc is well covered; a small private
  company may have no website and no coverage at all, and Claude will say so rather than
  invent something.

## 6. API reference

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/companies/features` | Which keys are configured (drives the UI banners) |
| GET | `/companies/search?q=` | Company name/number search |
| GET | `/companies/{number}` | Company profile |
| GET | `/companies/{number}/filings` | Accounts filings, newest first |
| GET | `/companies/{number}/filings/{transaction_id}/pdf` | The filed PDF |
| POST | `/companies/{number}/analyse` | `{transaction_ids: [], question?}` → Markdown review |

Filing documents are fetched by transaction id and re-checked against that company's
filing history, so the document proxy can only reach filings that belong to the
company in the path.
