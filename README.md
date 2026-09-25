# LawDiver API Tester

A **local web console** for exercising the [LawDiver Caselaw API](https://lawdiver.com/products/api) end to end — search, cite-check, retrieve, statutes, PDFs, usage, and more — with results shown in plain language on the left and the exact machine request/response on the right.

This repository is a **standalone tester app**. It is not the official API itself and not a published SDK. It talks only to LawDiver’s public REST surface at `https://lawdiver.com/api/v1`. It keeps optional request history in a **local SQLite file on your machine**. It never connects to any LawDiver production database.

| | |
| --- | --- |
| **Product** | [lawdiver.com/products/api](https://lawdiver.com/products/api) |
| **API docs** | [lawdiver.com/docs/api](https://lawdiver.com/docs/api) |
| **Get an API key** | [lawdiver.com/account/api-keys](https://lawdiver.com/account/api-keys) |
| **Official examples pack** | [dumpsticks/LawDiver_api](https://github.com/dumpsticks/LawDiver_api) |
| **This tester (local UI)** | Open **http://127.0.0.1:8765/** after starting the app (see below) |
| **Base URL** | `https://lawdiver.com/api/v1` |

---

## What this is

LawDiver’s caselaw API lets you programmatically:

- Search ~10M+ U.S. opinions with jurisdiction-scoped engines (citation, case name, keyword, semantic, hybrid, or auto)
- Cite-check one citation, a batch, or an entire PDF/DOCX brief
- Resolve citations, retrieve cases and statute section text, pull good-law / cited-by graphs and opinion PDFs
- Inspect your usage ledger and rate limits

Building against that surface usually means reading JSON and wiring `curl` or a client by hand. **This app is the opposite of that friction:**

1. Pick a function from the left-hand menu  
2. Fill only the inputs that jurisdiction/type actually require (dynamic forms)  
3. Run the call  
4. Read a **human view** (cards, verdicts, snippets) and a **machine view** (method, URL, redacted headers, JSON body in / JSON body out)

It is useful if you are:

- Evaluating LawDiver before integrating it into a product or agent  
- Debugging a bad payload (compare what you *meant* to send with what the wire panel shows)  
- Learning the API without living in Postman or raw logs  
- Smoke-testing a new key after signup  

---

## What this is not

- **Not** hosted SaaS — you run it on localhost  
- **Not** a substitute for the [canonical API reference](https://lawdiver.com/docs/api)  
- **Not** permission to hit LawDiver internal databases — only the public HTTPS API  
- **Not** a place to commit secrets — your live `ld_live_…` key stays in a gitignored `.env`

---

## Prerequisites

- Python **3.10+**
- A LawDiver account with a verified email  
- An API key from [Account → API keys](https://lawdiver.com/account/api-keys)

### Create a LawDiver API key (about five minutes)

1. Sign up at [https://lawdiver.com](https://lawdiver.com) and **verify your email**.  
2. Open **[Account → API keys](https://lawdiver.com/account/api-keys)**.  
3. **Create a key**. It is shown **exactly once**. Only a hash is stored server-side; if you lose it, revoke and create another.  
4. Keys look like: `ld_live_xxxxxxxxxxxxxxxxxxxx`.  
5. Treat the key as a **server-side secret**. Never put it in frontend bundles, screenshots, issues, or this git repo.

More detail: [Authentication](https://github.com/dumpsticks/LawDiver_api/blob/main/docs/authentication.md) in the official examples pack, and the live docs at [lawdiver.com/docs/api](https://lawdiver.com/docs/api).

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/dumpsticks/LawDiver_API_Tester.git
cd LawDiver_API_Tester
```

### 2. Create a virtualenv and install dependencies

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
cp .env.example .env
```

Edit `.env` and set **either** (or both) of:

```env
LAWDIVER_API_KEY=ld_live_your_real_key_here
# optional alias also accepted by the client:
LAWDIVER_AGENT_API_KEY=ld_live_your_real_key_here

# leave this alone unless LawDiver gives you a different base:
LAWDIVER_API_BASE=https://lawdiver.com/api/v1
```

`.env` is listed in `.gitignore`. Do not commit it.

### 4. Start the app

```bash
python run.py
```

Or:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

### 5. Open the tester

**http://127.0.0.1:8765/**

You should see a status pill like `Key configured · https://lawdiver.com/api/v1`. Pick **Case search** (or any menu item), fill the form, and click **Run**.

---

## How to use the UI

### Menu (left)

Functions are grouped:

| Group | Functions |
| --- | --- |
| Reference | API discovery, Jurisdictions |
| Search & retrieve | Case search, Citation resolve, Case retrieve, Statute retrieve |
| Cite check | Citations, Document upload, Document job status |
| Case details | Metadata, Batch, Good-law, Cited by, Case PDF |
| Account | Usage ledger |

### Dynamic inputs

For **Case search**, companion fields appear only when the API requires them:

- `one_state` / `one_state_plus_federal` → **State** dropdown (USPS codes from `GET /jurisdictions`)  
- `federal_circuit` → **Circuit**  
- `federal_district` → **District state**  
- Broad types (`all_federal`, `us_supreme_court`, …) → no companion field  

That mirrors the real API contract: sending an empty `jurisdiction.state` produces `invalid_request`.

### Results (split panel)

- **Human view** — readable cards (case names, verdicts, good-law labels, statute text, download links).  
- **Machine view** — what was sent (method, URL, headers with `Authorization: Bearer <redacted>`, body) and what came back (JSON). Use **Copy JSON** to paste into tickets or agents.

### Pace requests / rate limits

Authenticated calls share an account rate limit (commonly **60 requests per minute**; see your `GET /usage` / docs). The tester includes:

- **Pace requests (1s)** — soft spacing between Runs (on by default)  
- A **countdown banner** if LawDiver returns `rate_limited` / HTTP 429  

Prefer scoped searches over national semantic blasts when you are iterating quickly.

### History

**History** stores recent runs in local SQLite (`data/history.db`), including human + machine payloads when available. **Open I/O** restores both panels. This file is gitignored and never sent to LawDiver’s databases.

### Did-you-mean retrieve

Famous case-name retrieves often return `status: "did_you_mean"` with candidates (HTTP 200). Use **Retrieve this case** on a candidate to follow up with `caseId`.

### Document cite-check

Upload a PDF or Word brief. The app starts `POST /citecheck/document`, polls the job, and can download the report PDF into `downloads/`. Optional email fields request LawDiver’s email-link delivery.

---

## Endpoints covered

| Menu item | LawDiver API |
| --- | --- |
| API discovery | `GET /api/v1` |
| Jurisdictions | `GET /jurisdictions` |
| Case search | `POST /search` |
| Cite check (citations) | `POST /citecheck/cite` |
| Cite check (document) | `POST /citecheck/document` + job poll |
| Document job status | `GET /citecheck/jobs/:id` |
| Citation resolve | `POST /citations/resolve` |
| Case retrieve | `POST /cases/retrieve` |
| Statute retrieve | `POST /statutes/retrieve` |
| Case metadata | `GET /cases/:id` |
| Case batch | `POST /cases/batch` |
| Good-law detail | `GET /cases/:id/good-law` |
| Cited by | `GET /cases/:id/cited-by` |
| Case PDF | `GET /cases/:id/pdf` |
| Usage ledger | `GET /usage` |

Field-level reference: [lawdiver.com/docs/api](https://lawdiver.com/docs/api) · Catalog notes: [LawDiver_api docs/endpoints.md](https://github.com/dumpsticks/LawDiver_api/blob/main/docs/endpoints.md).

---

## Project layout

```text
LawDiver_API_Tester/
  app/
    main.py              # FastAPI app — menu metadata, /api/run proxies
    lawdiver_client.py   # Thin REST client (clone-and-copy style)
    formatters.py        # JSON → human view models
    db.py                # Local SQLite history only
  static/                # Single-page UI (HTML/CSS/JS)
  scripts/               # Optional smoke / stress helpers
  .env.example           # Placeholder keys — copy to .env
  run.py                 # uvicorn launcher on 127.0.0.1:8765
  requirements.txt
```

Stack: **Python + FastAPI + httpx** serving a small static UI. No React build step.

---

## Security notes

1. **Never commit `.env`.** Rotate any key that was pasted into chat, screenshots, or a public gist.  
2. The machine panel deliberately shows `Bearer <redacted>`.  
3. Call LawDiver from **this local backend** (or your own server). Do not embed keys in browser-only apps.  
4. Prefer `https://lawdiver.com` (apex). Cross-host redirects can strip `Authorization` on some clients.

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Status: “No API key in .env” | Missing/empty `LAWDIVER_API_KEY` / `LAWDIVER_AGENT_API_KEY` |
| `invalid_api_key` | Wrong/revoked key — create a new one at [/account/api-keys](https://lawdiver.com/account/api-keys) |
| `invalid_request` on search + state | Empty or non-USPS state for `one_state*` — use the dropdown |
| `rate_limited` | Over ~60/min — wait for the banner countdown |
| `Non-JSON … HTTP 504` | Transient gateway timeout — retry (client auto-retries once) |
| Document upload errors with emails | Fixed multipart encoding in this client; update to latest `main` |
| UI stuck on “Checking key…” | Hard-refresh (Ctrl+F5); ensure `static/app.js` loads without console errors |

Sanity checks without the UI:

```bash
# No key required
curl https://lawdiver.com/api/v1

# Key required
curl "https://lawdiver.com/api/v1/usage?days=7" \
  -H "Authorization: Bearer $LAWDIVER_API_KEY"
```

---

## Related links

- **LawDiver home:** [https://lawdiver.com](https://lawdiver.com)  
- **Caselaw / CaseDiver search (product):** [https://lawdiver.com/casediver](https://lawdiver.com/casediver)  
- **CiteDiver:** [https://lawdiver.com/products/citediver](https://lawdiver.com/products/citediver)  
- **API product page:** [https://lawdiver.com/products/api](https://lawdiver.com/products/api)  
- **API documentation:** [https://lawdiver.com/docs/api](https://lawdiver.com/docs/api)  
- **Create / revoke API keys:** [https://lawdiver.com/account/api-keys](https://lawdiver.com/account/api-keys)  
- **Official examples (TS / Python / cURL):** [https://github.com/dumpsticks/LawDiver_api](https://github.com/dumpsticks/LawDiver_api)  
- **MCP (same key):** [https://lawdiver.com/mcp](https://lawdiver.com/mcp)

---

## License

MIT — same spirit as the LawDiver examples pack. LawDiver the product and its data remain subject to LawDiver’s own terms; this repo only ships a local HTTP client UI.
