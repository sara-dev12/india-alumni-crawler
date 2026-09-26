# India Engineering Alumni Crawler

Cloud-ready Scrapy POC for discovering public alumni pages on official Indian engineering-college websites.

## Scope
- POC target: 10 institutions supplied in `data/colleges.csv`
- Alumni batches: 2000-2025 when explicitly available
- Public pages only
- No login/CAPTCHA bypass
- No guessing current employment
- Every extracted record keeps its source URL

## Run locally for testing
```bash
pip install -r requirements.txt
scrapy crawl alumni -a college_csv=data/colleges.csv -O alumni.jsonl
```

## Zyte Scrapy Cloud
The repository root contains `scrapy.cfg`, so it can be connected directly to a Zyte Scrapy Cloud project using its GitHub deployment integration.

After connecting the repository, run the `alumni` spider. See Zyte's current GitHub deployment documentation for the dashboard steps.

## Next phase
Add an authoritative institution dataset, database pipeline, employment-verification service, and dashboard only after the 10-college extraction accuracy is manually checked.
