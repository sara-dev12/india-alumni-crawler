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
BATCH_CODE_RE = re.compile(r"^\d{4}\s*/", re.I)
NAME_RE = re.compile(
    r"^(?:(?:mr|ms|mrs|dr|prof|shri|smt)\.\s+)?"
    r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,5}$"
)
NON_HTML_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3", ".avi", ".mov"
)

GENERIC_PHRASES = {
    "404 not found", "page not found", "awards & achievements",
    "iit guwahati by the numbers", "welcome to acir", "degree/certificate",
    "make a gift", "opportunities for faculty", "national institute of technology",
    "tamil nadu, india", "working with other offices regarding mous",
    "our campus", "quick links", "general links", "giving back",
    "joy of giving", "iit madras foundation", "distinguished alumnus awards",
    "duplicate degree", "upcoming events", "the institute", "student cell",
    "academic initiatives", "student initiatives", "batch initiatives",
    "infrastructure initiatives", "community welfare", "associate deans",
    "partnership opportunities", "philanthropist society", "student aid",
    "emergency fund", "what's new", "director's message", "dean's message",
    "institute services", "guest house", "no dues", "acir campaign",
    "institute development"
}

JOB_TITLE_WORDS = {
    "manager", "director", "dean", "professor", "associate", "engineer",
    "developer", "officer", "president", "chairman", "chairperson",
    "secretary", "founder", "ceo", "cto", "cfo", "administrator",
    "coordinator", "consultant", "analyst", "scientist"
}


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
            return

        if self.is_non_html_url(response.url):
            return

        college = response.meta["college_name"]
        page_title = self.clean_name(response.css("title::text").get() or "")

        # Custom 404 pages often return HTTP 200. Do not extract their labels
        # as people.
        page_text = " ".join(response.css("body *::text").getall())
        page_text = re.sub(r"\s+", " ", page_text).strip()
        page_lower = page_text.lower()
        if self.is_error_page(page_title, page_lower):
            return

        if not any(term in page_lower for term in ALUMNI_TERMS):
            return

        selectors = (
            "h1::text, h2::text, h3::text, h4::text, "
            "a::text, td::text, li::text"
        )

        seen = set()
        for block in response.css(selectors).getall():
            clean = self.clean_name(block)
            key = clean.casefold()
            if key in seen or not self.looks_like_name(clean):
                continue
            seen.add(key)

            year_match = BATCH_RE.search(clean)
            year = int(year_match.group(1)) if year_match else None

            yield AlumniItem(
                college_name=college,
                alumni_name=clean,
                degree=None,
                department=None,
                graduation_year=year,
                alumni_profile_url=response.url,
                source_url=response.url,
                evidence_text=clean[:1000],
                extraction_status="CANDIDATE",
            )

    def is_error_page(self, title, page_lower):
        title_lower = title.lower()
        if "404" in title_lower or "not found" in title_lower:
            return True
        if "404 not found" in page_lower[:1000]:
            return True
        return False

    def looks_like_name(self, text):
        text = self.clean_name(text)
        if len(text) < 4 or len(text) > 100:
            return False

        lower = text.lower()
        if lower in GENERIC_PHRASES:
            return False

        if BATCH_CODE_RE.match(text):
            return False

        if any(
            x in lower
            for x in (
                "alumni", "association", "department", "engineering",
                "college", "contact", "foundation", "campaign",
                "initiative", "events", "links", "fund", "programme",
                "program", "students", "campus", "opportunities",
                "technology", "institute", "working with", "office"
            )
        ):
            return False

        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
        if not 2 <= len(words) <= 6:
            return False

        core_words = [
            w.lower().rstrip(".")
            for w in words
            if w.lower().rstrip(".") not in {"mr", "ms", "mrs", "dr", "prof", "shri", "smt"}
        ]
        if len(core_words) < 2:
            return False

        if any(w in JOB_TITLE_WORDS for w in core_words):
            return False

        # Person-name candidates should have normal name capitalization.
        if not NAME_RE.match(text):
            return False

        return True

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
