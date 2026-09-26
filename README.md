# India Engineering Alumni Crawler

Cloud-ready Scrapy pipeline for discovering **public alumni education records** from official Indian engineering-institution websites.

## Data scope

- Target graduation years: **2000–2025**
- Public web pages only
- Official institution domains are the primary discovery source
- No login, CAPTCHA bypass, paywall bypass, or access-control circumvention
- No private addresses, phone numbers, personal email addresses, family data, or sensitive personal data
- Current employment is **never inferred** from an alumni record
- When employment cannot be independently verified, the value remains `UNKNOWN`

## Current architecture

```
Institution seed list
        |
        v
Official college website
        |
        v
Robots.txt + polite crawling
        |
        v
Alumni-page discovery
        |
        v
Explicit alumni education-code extraction
        |
        +----> Name
        +----> Graduation year
        +----> Degree
        +----> Department
        +----> Source URL
        +----> Evidence
        |
        v
Normalization + hard validation
        |
        v
Deduplication
        |
        v
Alumni dataset
        |
        v
Employment verification queue
        |
        +----> Current company/title only when public evidence supports it
        +----> Otherwise UNKNOWN
```

## Why the extractor is structured this way

Many institutional pages contain navigation labels, event years, award years, staff profiles, and unrelated links. A generic "find a name + find any year on the page" strategy creates false positives.

The crawler therefore uses this priority:

1. **HIGH confidence:** explicit records such as `Dr. Name (PhD/EE/2022)` or `Name 2017/DD/EE`.
2. **MEDIUM confidence:** a person-like name inside a strong alumni/person container with a local education or graduation signal.
3. Page-level years such as award/event years are **not** used as graduation years when an explicit education code exists.
4. Staff/administrative pages are not treated as alumni merely because they mention alumni.
5. Generic labels such as `View All`, `Learn More`, and `Awards & Achievements` are rejected.
6. Records are deduplicated by institution + person + education attributes.

## POC institutions

The current proof of concept contains 10 institutions:

- IIT Madras
- IIT Delhi
- IIT Bombay
- IIT Kanpur
- IIT Kharagpur
- IIT Roorkee
- IIT Guwahati
- NIT Trichy
- NIT Surathkal
- NIT Warangal

Do **not** scale to hundreds/thousands of institutions until the 10-institution POC passes manual quality checks.

## Zyte Scrapy Cloud

The repository contains `scrapy.cfg` and `scrapinghub.yml`. GitHub-to-Zyte deployment can therefore be used without running the crawler locally.

After deployment:

1. Deploy the `main` branch.
2. Run the `alumni` spider.
3. Download `alumni.jsonl`.
4. Inspect unique alumni records and evidence.
5. Only after the discovery dataset is clean, run the employment-verification stage.

## Employment verification

The discovery spider intentionally outputs:

- `current_company = UNKNOWN`
- `current_job_title = UNKNOWN`
- `employment_verification_status = NOT_VERIFIED`

These fields must only be populated by a later verification process using a public source that explicitly supports the current employment claim.

Examples of acceptable evidence include a current official employer biography, institutional profile, or other public professional source. A stale alumni page, search-result snippet, or an unrelated name match is not sufficient by itself.

## Production roadmap

### Phase 1 — Institution discovery
Build a maintained institution registry containing:
- institution name
- official domain
- institution type
- state
- source/provenance
- active status

### Phase 2 — Alumni discovery
Extract:
- name
- graduation year
- degree
- department
- alumni/profile URL
- source URL
- evidence
- confidence

### Phase 3 — Verification
For each alumni:
- search public professional sources
- require explicit identity/context match
- capture current company and title only when supported
- retain verification source and evidence
- otherwise mark `UNKNOWN`

### Phase 4 — Deduplication/entity resolution
Merge records using:
- institution
- normalized name
- education information
- profile URL
- additional public evidence

Never merge two people solely because their names are similar.

### Phase 5 — Storage and analytics
Move validated records into a cloud database and expose:
- institution
- batch
- degree
- department
- current company
- current title
- evidence URL
- verification date
- confidence/status

### Phase 6 — Scale
Scale in controlled stages:
10 institutions → 100 → 500 → full registry.

At every stage, sample records and measure:
- precision
- false-positive rate
- duplicate rate
- missing-year rate
- verification coverage

## Local smoke test

```bash
pip install -r requirements.txt
scrapy crawl alumni -O alumni.jsonl
```

For the cloud workflow, use Zyte Scrapy Cloud rather than relying on local processing.
