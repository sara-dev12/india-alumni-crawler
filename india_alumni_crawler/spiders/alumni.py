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
NON_HTML_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3", ".avi", ".mov"
)


class AlumniSpider(scrapy.Spider):
    name = "alumni"
    allowed_http_codes = [200, 301, 302, 403, 404, 429, 500, 502, 503, 504]

    COLLEGES = [
        ("IIT Madras", "https://www.iitm.ac.in/"),
        ("IIT Delhi", "https://home.iitd.ac.in/"),
        ("IIT Bombay", "https://www.iitb.ac.in/"),
        ("IIT Kanpur", "https://www.iitk.ac.in/"),
        ("IIT Kharagpur", "https://www.iitkgp.ac.in/"),
        ("IIT Roorkee", "https://www.iitr.ac.in/"),
        ("IIT Guwahati", "https://www.iitg.ac.in/"),
        ("NIT Trichy", "https://www.nitt.edu/"),
        ("NIT Surathkal", "https://www.nitk.ac.in/"),
        ("NIT Warangal", "https://www.nitw.ac.in/"),
    ]

    def __init__(self, college_csv=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.college_csv = college_csv

    async def start(self):
        if self.college_csv:
            path = Path(self.college_csv)
            with path.open(newline="", encoding="utf-8") as f:
                colleges = [
                    (row["college_name"], row["official_website"])
                    for row in csv.DictReader(f)
                ]
        else:
            colleges = self.COLLEGES

        for college_name, official_website in colleges:
            yield scrapy.Request(
                official_website,
                callback=self.parse_home,
                errback=self.errback_log,
                meta={"college_name": college_name, "root": official_website},
            )

    def parse_home(self, response):
        college = response.meta["college_name"]
        root = response.meta["root"]

        for href in response.css("a::attr(href)").getall():
            url = urljoin(response.url, href)
            if self.is_non_html_url(url):
                continue

            label = " ".join(
                response.css(f'a[href="{href}"] ::text').getall()
            ).lower()

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

        content_type = response.headers.get(b"Content-Type", b"").decode(
            "latin-1", errors="ignore"
        ).lower()
        if content_type and not any(
            x in content_type for x in ("text/html", "application/xhtml+xml")
        ):
            self.logger.info(
                "Skipping non-HTML alumni URL: %s (%s)",
                response.url,
                content_type,
            )
            return

        if self.is_non_html_url(response.url):
            return

        college = response.meta["college_name"]
        text = " ".join(response.css("body *::text").getall())
        text = re.sub(r"\s+", " ", text).strip()

        if not any(term in text.lower() for term in ALUMNI_TERMS):
            return

        for block in response.css(
            "h1::text, h2::text, h3::text, h4::text, li::text, td::text"
        ).getall():
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
        if any(
            x in lower
            for x in ("alumni", "association", "department", "engineering", "college", "contact")
        ):
            return False
        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
        return 2 <= len(words) <= 6 and sum(w[0].isupper() for w in words) >= 2

    def clean_name(self, text):
        return re.sub(r"\s+", " ", text).strip(" -,:;")

    def same_domain(self, url, root):
        url_host = (urlparse(url).hostname or "").lower()
        root_host = (urlparse(root).hostname or "").lower()
        return url_host == root_host or url_host.endswith("." + root_host)

    def is_non_html_url(self, url):
        path = (urlparse(url).path or "").lower()
        return any(path.endswith(ext) for ext in NON_HTML_EXTENSIONS)

    def errback_log(self, failure):
        self.logger.warning("Request failed: %s", failure.request.url)
