import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import scrapy

from ..items import AlumniItem

ALUMNI_TERMS = (
    "alumni", "alumnus", "alumna", "alumni association",
    "alumni directory", "distinguished alumni", "notable alumni",
    "alumni network", "former students", "graduates"
)

BATCH_RE = re.compile(r"\b(200(?:0|[1-9])|201\d|202[0-5])\b")

class AlumniSpider(scrapy.Spider):
    name = "alumni"
    allowed_http_codes = [200, 301, 302, 403, 404, 429, 500, 502, 503, 504]

    def __init__(self, college_csv="data/colleges.csv", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.college_csv = college_csv

    def start_requests(self):
        path = Path(self.college_csv)
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield scrapy.Request(
                    row["official_website"],
                    callback=self.parse_home,
                    errback=self.errback_log,
                    meta={"college_name": row["college_name"], "root": row["official_website"]},
                )

    def parse_home(self, response):
        college = response.meta["college_name"]
        root = response.meta["root"]

        for href in response.css("a::attr(href)").getall():
            url = urljoin(response.url, href)
            label = " ".join(response.css(f'a[href="{href}"] ::text').getall()).lower()
            if any(term in (label + " " + url.lower()) for term in ALUMNI_TERMS):
                if self.same_domain(url, root):
                    yield scrapy.Request(
                        url,
                        callback=self.parse_alumni_page,
                        errback=self.errback_log,
                        meta={"college_name": college, "root": root},
                    )

        for suffix in ("/alumni", "/alumni/", "/alumni-association", "/alumni-directory"):
            url = urljoin(root, suffix)
            yield scrapy.Request(
                url,
                callback=self.parse_alumni_page,
                errback=self.errback_log,
                meta={"college_name": college, "root": root},
                dont_filter=False,
            )

    def parse_alumni_page(self, response):
        if response.status != 200:
            return

        college = response.meta["college_name"]
        text = " ".join(response.css("body *::text").getall())
        text = re.sub(r"\s+", " ", text).strip()

        if not any(term in text.lower() for term in ALUMNI_TERMS):
            return

        for block in response.css("h1::text, h2::text, h3::text, h4::text, li::text, td::text").getall():
            clean = re.sub(r"\s+", " ", block).strip()
            if not self.looks_like_name(clean):
                continue

            year_match = BATCH_RE.search(clean)
            yield AlumniItem(
                college_name=college,
                alumni_name=self.clean_name(clean),
                degree=None,
                department=None,
                graduation_year=int(year_match.group(1)) if year_match else None,
                alumni_profile_url=response.url,
                source_url=response.url,
                evidence_text=clean[:1000],
                extraction_status="CANDIDATE",
            )

    def looks_like_name(self, text):
        if len(text) < 4 or len(text) > 100:
            return False
        lower = text.lower()
        if any(x in lower for x in ("alumni", "association", "department", "engineering", "college", "contact")):
            return False
        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
        return 2 <= len(words) <= 6 and sum(w[0].isupper() for w in words) >= 2

    def clean_name(self, text):
        return re.sub(r"\s+", " ", text).strip(" -,:;")

    def same_domain(self, url, root):
        return urlparse(url).netloc.lower().endswith(urlparse(root).netloc.lower())

    def errback_log(self, failure):
        self.logger.warning("Request failed: %s", failure.request.url)
