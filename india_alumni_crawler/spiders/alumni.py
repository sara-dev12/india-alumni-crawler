import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import scrapy

from ..items import AlumniItem

ALUMNI_TERMS = (
    "alumni", "alumnus", "alumna", "alumni association",
    "alumni directory", "distinguished alumni", "notable alumni",
    "alumni network", "former students", "graduates", "awardees",
)

PROFILE_PATH_TERMS = (
    "alumni", "alumnus", "alumna", "profile", "person",
    "awardee", "achiever", "distinguished", "notable",
)

YEAR_RE = re.compile(r"\b(200\d|201\d|202[0-5])\b")
BATCH_CONTEXT_RE = re.compile(
    r"(?:batch|class\s+of|graduat(?:ed|ion)|passed\s+out|year\s+of|"
    r"b\.?tech|b\.e\.?|m\.?tech|m\.e\.?|degree)",
    re.I,
)

NON_HTML_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3", ".avi", ".mov",
)

NAV_TAGS = {"nav", "header", "footer", "aside", "form"}
NAV_CLASS_RE = re.compile(
    r"(nav|menu|header|footer|sidebar|breadcrumb|search|cookie|social|"
    r"language|login|account|pagination)",
    re.I,
)
PERSON_CLASS_RE = re.compile(
    r"(alumni|alumnus|alumna|profile|person|member|awardee|achiever|"
    r"distinguished|notable|graduate)",
    re.I,
)
JOB_WORDS = {
    "manager", "director", "dean", "professor", "engineer", "developer",
    "officer", "president", "chairman", "chairperson", "secretary",
    "founder", "ceo", "cto", "cfo", "administrator", "coordinator",
    "consultant", "analyst", "scientist", "architect", "researcher",
}
DEGREE_WORDS = {
    "b.tech", "btech", "b.e.", "be", "m.tech", "mtech", "m.e.",
    "me", "mba", "mca", "b.sc", "bsc", "m.sc", "msc", "ph.d", "phd",
}
GENERIC_NAMES = {
    "our campus", "quick links", "general links", "giving back",
    "student aid", "academic initiatives", "student initiatives",
    "batch initiatives", "infrastructure initiatives", "community welfare",
    "associate deans", "partnership opportunities", "emergency fund",
    "what's new", "director's message", "dean's message", "institute services",
    "holiday list", "faculty forum", "digital photo archive", "press release",
    "academic calendar", "academic timetable", "academic rule books",
    "research internship", "find an expert", "research park",
    "central library", "computer centre", "transport service", "legal support",
    "human resource", "about us", "former principals", "former directors",
    "how to reach", "working hours", "organizational chart", "governing bodies",
    "board of governors", "finance committee", "research areas", "student life",
    "virtual tour", "staff webmail", "ug section", "pg section",
    "transcript section", "fees section", "computer applications",
    "central workshop", "webteam nit trichy",
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
        colleges = self.COLLEGES
        if self.college_csv:
            path = Path(self.college_csv)
            with path.open(newline="", encoding="utf-8") as f:
                colleges = [
                    (row["college_name"], row["official_website"])
                    for row in csv.DictReader(f)
                ]

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

        links = response.css("a[href]")
        for link in links:
            href = link.attrib.get("href", "")
            url = urljoin(response.url, href)
            if self.is_non_html_url(url) or not self.same_domain(url, root):
                continue

            label = self.normalize_text(" ".join(link.css("::text").getall()))
            combined = f"{label} {url}".lower()

            if any(term in combined for term in ALUMNI_TERMS):
                yield scrapy.Request(
                    url,
                    callback=self.parse_alumni_page,
                    errback=self.errback_log,
                    meta={"college_name": college, "root": root},
                )

        for suffix in (
            "/alumni", "/alumni/", "/alumni-association",
            "/alumni-directory", "/alumni-directory/",
        ):
            url = urljoin(root, suffix)
            yield scrapy.Request(
                url,
                callback=self.parse_alumni_page,
                errback=self.errback_log,
                meta={"college_name": college, "root": root},
            )

    def parse_alumni_page(self, response):
        if response.status != 200 or self.is_non_html_response(response):
            return

        college = response.meta["college_name"]
        title = self.normalize_text(response.css("title::text").get(""))
        body_text = self.normalize_text(" ".join(response.css("body ::text").getall()))

        if self.is_error_page(title, body_text):
            return

        page_signal = self.page_has_alumni_signal(response, body_text)
        if not page_signal:
            return

        seen = set()

        # 1. Prefer semantic/content containers that look like person cards or records.
        for node in response.xpath(
            "//article | //main//*[self::div or self::li or self::tr]"
        ):
            if self.is_navigation_node(node):
                continue

            text = self.node_text(node)
            if not self.is_person_record_text(text):
                continue

            candidate = self.extract_record(node, text)
            if candidate:
                yield from self.emit_candidate(candidate, college, response, seen)

        # 2. Tables: require a year/batch/degree signal in the same row.
        for row in response.xpath("//tr"):
            if self.is_navigation_node(row):
                continue
            text = self.node_text(row)
            if not self.has_record_signal(text):
                continue
            candidate = self.extract_record(row, text)
            if candidate:
                yield from self.emit_candidate(candidate, college, response, seen)

        # 3. Profile-like links. Only follow links whose URL strongly resembles
        # an alumni/person profile; this avoids treating every menu link as a person.
        for link in response.xpath("//a[@href]"):
            if self.is_navigation_node(link):
                continue

            href = link.attrib.get("href", "")
            url = urljoin(response.url, href)
            label = self.normalize_text(" ".join(link.xpath(".//text()").getall()))

            if not label or not self.looks_like_person_name(label):
                continue
            if not self.profile_url_signal(url):
                continue

            context = self.nearby_context(link)
            if not self.has_record_signal(context) and not self.profile_url_signal(response.url):
                continue

            candidate = {
                "name": label,
                "year": self.extract_year(context),
                "degree": self.extract_degree(context),
                "department": self.extract_department(context),
                "profile_url": url,
                "evidence": self.normalize_text(f"{label} | {context}")[:1500],
            }
            yield from self.emit_candidate(candidate, college, response, seen)

    def emit_candidate(self, candidate, college, response, seen):
        name = self.normalize_text(candidate.get("name", ""))
        key = (name.casefold(), candidate.get("profile_url") or response.url)
        if key in seen:
            return
        seen.add(key)

        yield AlumniItem(
            college_name=college,
            alumni_name=name,
            degree=candidate.get("degree"),
            department=candidate.get("department"),
            graduation_year=candidate.get("year"),
            alumni_profile_url=candidate.get("profile_url") or response.url,
            source_url=response.url,
            evidence_text=candidate.get("evidence", "")[:1500],
            extraction_status="STRUCTURED_CANDIDATE",
        )

    def extract_record(self, node, text):
        if not self.has_record_signal(text):
            return None

        name = self.find_name_in_node(node)
        if not name:
            return None

        return {
            "name": name,
            "year": self.extract_year(text),
            "degree": self.extract_degree(text),
            "department": self.extract_department(text),
            "profile_url": self.node_profile_url(node),
            "evidence": text[:1500],
        }

    def find_name_in_node(self, node):
        # Headings and strong/emphasized labels are preferred over arbitrary links.
        for xpath in (
            ".//h1//text()", ".//h2//text()", ".//h3//text()", ".//h4//text()",
            ".//strong//text()", ".//b//text()",
        ):
            for raw in node.xpath(xpath).getall():
                text = self.normalize_text(raw)
                if self.looks_like_person_name(text):
                    return text

        # Then inspect links, but only if the link itself looks like a person name.
        for link in node.xpath(".//a[@href]"):
            text = self.normalize_text(" ".join(link.xpath(".//text()").getall()))
            if self.looks_like_person_name(text):
                return text

        return None

    def node_profile_url(self, node):
        for link in node.xpath(".//a[@href]"):
            href = link.attrib.get("href", "")
            if href and self.profile_url_signal(href):
                return href
        return None

    def nearby_context(self, node):
        parent = node.xpath("ancestor::*[self::article or self::li or self::div or self::td][1]")
        if parent:
            return self.node_text(parent[0])[:2000]
        return self.node_text(node)[:2000]

    def page_has_alumni_signal(self, response, body_text):
        url_lower = response.url.lower()
        title_lower = self.normalize_text(
            response.css("title::text").get("")
        ).lower()
        return (
            any(term in url_lower for term in ALUMNI_TERMS)
            or any(term in title_lower for term in ALUMNI_TERMS)
            or any(term in body_text.lower() for term in ALUMNI_TERMS)
        )

    def has_record_signal(self, text):
        lower = text.lower()
        return bool(
            YEAR_RE.search(text)
            or BATCH_CONTEXT_RE.search(text)
            or any(word in lower for word in JOB_WORDS)
            or any(word in lower for word in DEGREE_WORDS)
        )

    def is_person_record_text(self, text):
        if not text or len(text) < 12 or len(text) > 2500:
            return False
        if not self.has_record_signal(text):
            return False
        return bool(
            re.search(r"[A-Z][A-Za-z.'-]+\s+[A-Z][A-Za-z.'-]+", text)
        )

    def looks_like_person_name(self, text):
        text = self.normalize_text(text)
        if not text or len(text) < 4 or len(text) > 100:
            return False

        lower = text.casefold()
        if lower in GENERIC_NAMES:
            return False
        if any(term in lower for term in ALUMNI_TERMS):
            return False
        if any(word in lower.split() for word in JOB_WORDS):
            return False
        if YEAR_RE.search(text):
            return False

        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
        if not 2 <= len(words) <= 6:
            return False

        # Require conventional person-name capitalization.
        return all(
            word[0].isupper()
            for word in words
            if word.lower() not in {"mr", "ms", "mrs", "dr", "prof", "shri", "smt"}
        )

    def extract_year(self, text):
        matches = YEAR_RE.findall(text)
        return int(matches[0]) if matches else None

    def extract_degree(self, text):
        lower = text.lower()
        patterns = (
            r"\bB\.?\s*Tech\.?\b",
            r"\bB\.?\s*E\.?\b",
            r"\bM\.?\s*Tech\.?\b",
            r"\bM\.?\s*E\.?\b",
            r"\bMBA\b", r"\bMCA\b", r"\bB\.?Sc\.?\b",
            r"\bM\.?Sc\.?\b", r"\bPh\.?D\.?\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return self.normalize_text(match.group(0))
        return None

    def extract_department(self, text):
        patterns = (
            r"(?:department|dept\.?|discipline|branch)\s*[:\-]?\s*"
            r"([A-Za-z][A-Za-z &/.-]{2,80})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = self.normalize_text(match.group(1))
                value = re.split(
                    r"\b(?:batch|class|year|graduat|degree|currently|present)\b",
                    value,
                    flags=re.I,
                )[0].strip(" ,;:-")
                if value:
                    return value[:100]
        return None

    def profile_url_signal(self, url):
        lower = url.lower()
        path = urlparse(url).path.lower()
        return any(term in lower for term in PROFILE_PATH_TERMS) and (
            path.count("/") >= 2 or any(term in lower for term in ("profile", "person", "awardee", "achiever"))
        )

    def is_navigation_node(self, node):
        current = node
        for _ in range(4):
            if current is None:
                break
            if current.root is not None and current.root.tag.lower() in NAV_TAGS:
                return True
            classes = " ".join(current.attrib.get("class", "").split())
            node_id = current.attrib.get("id", "")
            if NAV_CLASS_RE.search(f"{classes} {node_id}"):
                return True
            current = current.xpath("parent::*")[0] if current.xpath("parent::*") else None
        return False

    def normalize_text(self, text):
        return re.sub(r"\s+", " ", str(text or "")).strip(" -,:;|")

    def node_text(self, node):
        return self.normalize_text(" ".join(node.xpath(".//text()").getall()))

    def is_error_page(self, title, body_text):
        lower_title = title.lower()
        lower_body = body_text.lower()
        return (
            "404" in lower_title
            or "page not found" in lower_title
            or "not found" == lower_title.strip()
            or "404 not found" in lower_body[:1200]
        )

    def same_domain(self, url, root):
        url_host = (urlparse(url).hostname or "").lower()
        root_host = (urlparse(root).hostname or "").lower()
        return url_host == root_host or url_host.endswith("." + root_host)

    def is_non_html_url(self, url):
        path = (urlparse(url).path or "").lower()
        return any(path.endswith(ext) for ext in NON_HTML_EXTENSIONS)

    def is_non_html_response(self, response):
        if self.is_non_html_url(response.url):
            return True
        content_type = response.headers.get(b"Content-Type", b"").decode(
            "latin-1", errors="ignore"
        ).lower()
        return bool(
            content_type
            and not any(
                value in content_type
                for value in ("text/html", "application/xhtml+xml")
            )
        )

    def errback_log(self, failure):
        self.logger.warning("Request failed: %s", failure.request.url)
