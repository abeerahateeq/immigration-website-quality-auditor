# Immigration Consultancy Website Quality Auditor

An AI-assisted tool that audits authorized immigration-consultancy websites and
scores how professional, complete, and business-ready they are. Rule-based
scraping detects objective facts; an LLM (Google Gemini free tier, or
Anthropic Claude) turns those facts into a scored, structured judgment with
specific recommendations.

## How it works

```
sites.csv --> scraper.py --> raw facts (dict)
                                  |
                                  v
                          llm_judge.py --> score, problems,
                                  |         missing features,
                                  |         recommendations
                                  v
                     report_generator.py --> report.md / report.html
```

1. **`scraper.py`** fetches the homepage plus up to 4 internal pages found via
   `<nav>`/internal links, and extracts purely objective facts: HTTP status,
   load time, title/meta description, contact form presence, CTA button text,
   social links, FAQ section, image alt-text coverage, mobile viewport meta
   tag, phone/email visibility, and page count crawled.
2. **`llm_judge.py`** sends those facts (not the raw HTML) to an LLM with a
   system prompt that defines what a "professional immigration consultancy
   site" needs, and asks for a strict JSON response: score (0-100), problems,
   missing features, recommendations (each tagged high/medium/low priority),
   and an overall priority. It auto-detects which provider to use — Gemini if
   `GEMINI_API_KEY` is set, Claude if `ANTHROPIC_API_KEY` is set (see Setup).
3. **`report_generator.py`** builds a Markdown report and an HTML dashboard.
   **Every site's section is split into two clearly labeled blocks:**
   `🔍 Automatically Detected Facts` (script output, deterministic) and
   `🤖 AI-Generated Judgment` (the LLM's opinion, can be wrong).
4. **`main.py`** is the CLI that wires it all together, skips unauthorized
   rows, respects `robots.txt`, and never lets one bad site crash the batch.

## Setup

```bash
pip install -r requirements.txt

# Option A (recommended, free): Google Gemini
# Get a free key at https://aistudio.google.com/apikey
export GEMINI_API_KEY=AIza...

# Option B: Anthropic Claude (paid)
export ANTHROPIC_API_KEY=sk-ant-...

# Neither set? -- see "Running without an API key" below.
```

If both keys happen to be set, Gemini is used by default. Force a specific
provider with `export LLM_PROVIDER=gemini` or `export LLM_PROVIDER=anthropic`.
Change the Gemini model with `export GEMINI_MODEL=gemini-2.0-flash` (default)
or another free-tier model name.

## Usage

1. Copy `sites_template.csv` to `sites.csv` and fill in **only** websites you
   own, operate, or have explicit written permission to audit. Mark each row
   `authorized,yes` — anything else is skipped automatically and logged.

   ```csv
   url,authorized,notes
   https://your-consultancy.com,yes,own site
   https://client-site.com,yes,permission on file from client, dated 2026-08-01
   ```

2. Run the audit:

   ```bash
   python main.py --input sites.csv --outdir demo_output
   ```

3. Open `demo_output/report.html` (or `report.md`) for the results.

### Running without an API key

If neither `GEMINI_API_KEY` nor `ANTHROPIC_API_KEY` is set, `llm_judge.py`
falls back to a simple, clearly-labeled **heuristic mock judgment** so the
whole pipeline still runs end-to-end for testing/demo purposes. Every mock
result is tagged `⚠️ MOCK judgment` in the report so it's never confused with
a real AI opinion. This is how the included demo report was generated.

## Demo included in this repo

Since this environment has no open internet access, `demo_sites.csv` points
at two local mock immigration-consultancy pages under `sample_data/`
(`test_site/` — a reasonably complete site, `poor_site/` — a deliberately
incomplete one) plus one intentionally dead port, to prove out:

- successful multi-page crawl and fact extraction (`test_site`, 5 pages)
- correct detection of a poor site (no contact form, no meta description,
  no viewport tag, 0% alt-text coverage → score 0, 4 problems flagged)
- graceful handling of an unreachable site (`connection_error`, logged, no crash)
- the `authorized` column correctly skipping a non-authorized row

To reproduce locally:

```bash
cd sample_data/test_site && python3 -m http.server 8001 &
cd sample_data/poor_site && python3 -m http.server 8002 &
python main.py --input demo_sites.csv --outdir demo_output
```

For real sites, just point `sites.csv` at real URLs — the code doesn't change.

## What counts as "professional" (used in the LLM prompt)

- Contact info: phone **and** email, ideally a real contact form
- A clear, visible primary CTA (free consultation / eligibility check / book a call)
- Trust signals (licensing/registration info, testimonials — not auto-detected,
  flagged for human review instead)
- FAQ section
- Working social links
- Mobile responsiveness (viewport meta tag, used as a proxy signal)
- Basic SEO hygiene (title, meta description, image alt text)
- Reasonable page depth / content, not a single thin page
- Acceptable load time

## Ethics & scraping etiquette

- **Authorization gate**: `main.py` only audits rows marked `authorized,yes`
  in the input CSV — everything else is skipped and logged, never silently
  processed.
- **robots.txt respected**: `robots_check.py` checks `robots.txt` before
  fetching; disallowed URLs are recorded as blocked rather than fetched.
- **Low request volume**: shallow crawl (homepage + up to 4 internal pages),
  `0.5s` delay between pages on the same site, `1s` delay between different
  sites, single-threaded (no concurrent hammering).
- **Identifiable User-Agent**: requests are sent as
  `ImmigrationSiteAuditBot/1.0` with a contact placeholder, not spoofed as a
  browser.
- **No credential bypass, no CAPTCHA solving, no auth walls**: sites that
  block or challenge the bot are recorded as failures, not circumvented.

## Known limitations (read before trusting a score)

- **Static HTML only.** `requests` + BeautifulSoup don't execute JavaScript.
  A React/Vue single-page app that renders its content client-side will show
  up as "thin" or missing a contact form even if a human visitor sees a full
  site. Swap in Playwright if you need JS rendering — the `SiteFacts` schema
  and everything downstream stays the same.
- **CTA/social/FAQ detection is keyword-based**, not semantic. A site that
  says "Get a Free Case Review" instead of a listed keyword may be
  under-detected; a site that mentions "book" in an unrelated sentence could
  be a false positive. Recommend spot-checking flagged sites manually.
- **Alt-text coverage counts presence of the attribute, not quality.** An
  `alt="image"` counts as covered even though it's not descriptive.
- **Trust signals aren't auto-detected** (licensing numbers, professional
  body membership, testimonials, case results) — these matter a lot for an
  immigration consultancy specifically and currently require human review.
  The LLM is told this is out of scope for the automated facts, not asked to
  guess.
- **The LLM can hallucinate or misjudge**, especially score calibration
  between similar sites. Treat every score as a starting point, not a
  verdict — that's why facts and judgment are kept in separate report
  sections rather than blended into one narrative.
- **Legal/compliance content is not checked.** Whether an immigration
  consultancy's website makes accurate claims about services, credentials,
  or outcomes is a legal/regulatory question this tool does not and cannot
  assess.
- **Single-page contact info doesn't confirm a real business.** Presence of
  a phone number or form says nothing about response times, business
  legitimacy, or licensing status — those require actual due diligence.

## What a human should always double-check

- Every recommendation before implementing it (the LLM works from facts
  only, not business context or brand voice)
- Any site flagged `UNREACHABLE` — could be a real outage, a firewall/CAPTCHA,
  or a temporary blip; re-run before concluding the site is broken
- Trust/licensing signals (not automated at all)
- Whether a "missing" feature is actually missing vs. rendered by JavaScript
  this scraper can't see
- Legal accuracy of any claims on the audited site

## File structure

```
ia_audit_tool/
├── scraper.py            # rule-based fact extraction (requests + BeautifulSoup)
├── robots_check.py        # robots.txt politeness check
├── llm_judge.py           # Gemini/Claude API call + JSON parsing + mock fallback
├── report_generator.py    # Markdown + HTML report builder
├── main.py                 # CLI orchestrator
├── requirements.txt
├── sites_template.csv      # copy to sites.csv and fill in your own authorized URLs
├── demo_sites.csv          # local demo config (see "Demo included in this repo")
├── sample_data/             # local mock sites used for the demo run
│   ├── test_site/           # decent-quality mock consultancy site
│   └── poor_site/           # deliberately incomplete mock site
└── demo_output/
    ├── report.md
    └── report.html
```
