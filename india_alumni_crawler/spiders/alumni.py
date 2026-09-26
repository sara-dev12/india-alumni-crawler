import re
from urllib.parse import urljoin, urlparse

import scrapy

from ..items import AlumniItem


# POC institutions. This list is intentionally small until extraction quality is
# manually validated. The production workflow should replace/extend this list
# from an authoritative institution dataset.
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

ALUMNI_TERMS = (
    "alumni", "alumnus", "alumna", "alumni association",
    "alumni directory", "distinguished alumni", "notable alumni",
    "alumni network", "former students", "awardees", "graduates",
)

YEAR_RE = re.compile(r"\b(200\d|201\d|202[0-5])\b")

# Explicit education-code forms are the highest-confidence source:
#   Dr. Name (BT/EE/2017)
#   Dr. Name (2017/DD/EE)
#   Dr. Name 2017/DD/EE
EDUCATION_CODE_RE = re.compile(
    r"(?P<name>(?:(?:Mr|Ms|Mrs|Dr|Prof|Shri|Smt)\.?\s+)"
    r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,6})"
    r"\s*(?:\((?P<paren>[^)]*?(?:200\d|201\d|202[0-5])[^)]*)\)"
    r"|(?P<plain>(?:200\d|201\d|202[0-5])(?:/[A-Za-z0-9.-]+){1,5}))",
    re.I,
)

# Degree tokens used when a site provides a human-readable record.
DEGREE_RE = re.compile(
    r"\b(B\.?\s*Tech\.?|B\.?\s*E\.?|M\.?\s*Tech\.?|M\.?\s*E\.?|"
    r"MBA|MCA|B\.?\s*Sc\.?|M\.?\s*Sc\.?|Ph\.?\s*D\.?)\b",
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

GENERIC_NAMES = {
    "awards & achievements", "view all", "learn more", "iit madras foundation",
    "duplicate degree", "upcoming events", "telephone directory",
    "our campus", "quick links", "general links", "giving back", "student aid",
    "academic initiatives", "student initiatives", "batch initiatives",
    "infrastructure initiatives", "community welfare", "associate deans",
    "partnership opportunities", "emergency fund", "what's new",
    "director's message", "dean's message", "institute services",
    "holiday list", "faculty forum", "digital photo archive", "press release",
    "academic calendar", "academic timetable", "academic rule books",
    "research internship", "find an expert", "research park", "central library",
    "computer centre", "transport service", "legal support", "human resource",
    "about us", "former principals", "former directors", "how to reach",
    "working hours", "organizational chart", "governing bodies",
    "board of governors", "finance committee", "research areas", "student life",
    "virtual tour", "staff webmail", "ug section", "pg section",
    "transcript section", "fees section", "computer applications",
    "central workshop", "webteam nit trichy",
}

JOB_WORDS = {
    "manager", "director", "dean", "professor", "engineer", "developer",
    "officer", "president", "chairman", "chairperson", "secretary",
    "founder", "ceo", "cto", "cfo", "administrator", "coordinator",
    "consultant", "analyst", "scientist", "architect", "researcher",
}

DEGREE_MAP = {
    "BT": "B.Tech",
    "BTECH": "B.Tech",
    "BE": "B.E.",
    "B.E": "B.E.",
    "MT": "M.Tech",
    "MTECH": "M.Tech",
    "ME": "M.E.",
    "M.E": "M.E.",
    "MBA": "MBA",
    "MCA": "MCA",
    "MSC": "M.Sc.",
    "MSC2": "M.Sc.",
    "M.SC": "M.Sc.",
    "MS": "M.S.",
    "PHD": "Ph.D.",
    "PH.D": "Ph.D.",
    "DD": "Dual Degree",
}

DEPARTMENT_ALIASES = {
    "EE": "Electrical Engineering",
    "ECE": "Electronics and Communication Engineering",
    "EEE": "Electrical and Electronics Engineering",
    "ME": "Mechanical Engineering",
    "CE": "Civil Engineering",
    "CSE": "Computer Science and Engineering",
    "CS": "Computer Science",
    "CHE": "Chemical Engineering",
    "CHM": "Chemistry",
    "PHY": "Physics",
    "BT": "Biotechnology",
    "BSBE": "Biological Sciences and Bioengineering",
    "IME": "Industrial and Management Engineering",
}


class AlumniSpider(scrapy.Spider):
    name = "alumni"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_records = set()

    async def start(self):
        for college_name, official_website in COLLEGES:
            yield scrapy.Request(
                official_website,
                callback=self.parse_home,
                errback=self.errback_log,
                meta={"college_name": college_name, "root": official_website},
            )

    def parse_home(self, response):
        college = response.meta["college_name"]
        root = response.meta["root"]

        # Discover alumni pages from visible navigation.
        for link in response.css("a[href]"):
            href = link.attrib.get("href", "")
            url = urljoin(response.url, href)
            if self.is_non_html_url(url) or not self.same_domain(url, root):
                continue

            label = self.normalize(" ".join(link.css("::text").getall()))
            combined = f"{label} {url}".lower()
            if any(term in combined for term in ALUMNI_TERMS):
                yield self.alumni_request(url, college, root)

        # Conservative fallbacks for common site structures.
        for suffix in (
            "/alumni", "/alumni/", "/alumni-association",
            "/alumni-directory", "/alumni-directory/",
        ):
            yield self.alumni_request(urljoin(root, suffix), college, root)

    def alumni_request(self, url, college, root):
        return scrapy.Request(
            url,
            callback=self.parse_alumni_page,
            errback=self.errback_log,
            meta={"college_name": college, "root": root},
        )

    def parse_alumni_page(self, response):
        if response.status != 200 or self.is_non_html_response(response):
            return

        college = response.meta["college_name"]
        title = self.normalize(response.css("title::text").get(""))
        body = self.normalize(" ".join(response.css("body ::text").getall()))

        if self.is_error_page(title, body):
            return

        # A page must identify itself as alumni-related. This prevents staff,
        # admissions and generic institutional pages from becoming alumni records.
        if not self.page_has_alumni_signal(response, title, body):
            return

        # PRIMARY EXTRACTION:
        # Only explicit name + education-code records are accepted here.
        # This eliminates page-level award/event years being mistaken for
        # graduation years.
        explicit = self.extract_explicit_records(body)
        if explicit:
            for candidate in explicit:
                yield from self.emit(candidate, college, response)
            return

        # SECONDARY EXTRACTION:
        # Used only when no explicit education-code records exist. Require a
        # strong person/profile container and a local education/batch signal.
        for node in response.xpath(
            "//article | //main//*[self::div or self::li or self::tr]"
        ):
            if self.is_navigation_node(node):
                continue

            text = self.node_text(node)
            if not self.strong_record_signal(text):
                continue

            name = self.find_name(node)
            if not name:
                continue

            # A generic page container is not enough; require a local year or
            # explicit degree/batch phrase near the person's name.
            year = self.extract_local_year(text)
            degree = self.extract_degree(text)
            if year is None and degree is None:
                continue

            profile_url = self.node_profile_url(node, response.url)
            evidence = text[:1500]

            yield from self.emit({
                "name": name,
                "degree": degree,
                "department": self.extract_department(text),
                "graduation_year": year,
                "profile_url": profile_url,
                "evidence": evidence,
                "confidence": "MEDIUM",
            }, college, response)

    def extract_explicit_records(self, text):
        results = []
        local_seen = set()

        for match in EDUCATION_CODE_RE.finditer(text):
            name = self.normalize(match.group("name"))
            code = self.normalize(match.group("paren") or match.group("plain"))

            if not self.looks_like_person_name(name):
                continue

            year = self.extract_year_from_code(code)
            if year is None or not 2000 <= year <= 2025:
                continue

            degree, department = self.parse_education_code(code)
            key = (name.casefold(), year, degree, department)
            if key in local_seen:
                continue
            local_seen.add(key)

            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 350)

            results.append({
                "name": name,
                "degree": degree,
                "department": department,
                "graduation_year": year,
                "profile_url": None,
                "evidence": self.normalize(text[start:end]),
                "confidence": "HIGH",
            })

        return results

    def parse_education_code(self, code):
        parts = [p.strip(" .").upper() for p in code.split("/") if p.strip()]
        year = next((int(p) for p in parts if re.fullmatch(r"20(?:0\d|1\d|2[0-5])", p)), None)
        non_year = [p for p in parts if not re.fullmatch(r"20(?:0\d|1\d|2[0-5])", p)]

        degree = None
        for part in non_year:
            if part in DEGREE_MAP:
                degree = DEGREE_MAP[part]
                break

        department = None
        for part in reversed(non_year):
            if re.fullmatch(r"[A-Z]{2,8}", part) and part not in DEGREE_MAP:
                department = DEPARTMENT_ALIASES.get(part, part)
                break

        return degree, department

    def extract_year_from_code(self, code):
        match = YEAR_RE.search(code)
        return int(match.group(1)) if match else None

    def strong_record_signal(self, text):
        lower = text.lower()
        return bool(
            YEAR_RE.search(text)
            and (
                re.search(r"\b(batch|class of|graduat(?:ed|ion)|passed out|year of)\b", lower)
                or DEGREE_RE.search(text)
                or any(word in lower for word in JOB_WORDS)
            )
        )

    def extract_local_year(self, text):
        # Do not accept arbitrary years from a large page container. Only use
        # the first year when the container itself is a strong record.
        match = YEAR_RE.search(text)
        return int(match.group(1)) if match else None

    def extract_degree(self, text):
        match = DEGREE_RE.search(text)
        return self.normalize(match.group(1)) if match else None

    def extract_department(self, text):
        match = re.search(
            r"(?:department|dept\.?|discipline|branch)\s*[:\-]?\s*"
            r"([A-Za-z][A-Za-z &/.-]{2,80})",
            text,
            re.I,
        )
        if not match:
            return None
        value = self.normalize(match.group(1))
        value = re.split(
            r"\b(?:batch|class|year|graduat|degree|currently|present)\b",
            value,
            flags=re.I,
        )[0].strip(" ,;:-")
        return value[:100] or None

    def find_name(self, node):
        for xpath in (
            ".//h1//text()", ".//h2//text()", ".//h3//text()", ".//h4//text()",
            ".//strong//text()", ".//b//text()",
        ):
            for raw in node.xpath(xpath).getall():
                candidate = self.normalize(raw)
                if self.looks_like_person_name(candidate):
                    return candidate

        for link in node.xpath(".//a[@href]"):
            candidate = self.normalize(" ".join(link.xpath(".//text()").getall()))
            if self.looks_like_person_name(candidate):
                return candidate

        return None

    def node_profile_url(self, node, base_url):
        for link in node.xpath(".//a[@href]"):
            href = link.attrib.get("href", "")
            if href:
                url = urljoin(base_url, href)
                if self.profile_url_signal(url):
                    return url
        return None

    def emit(self, candidate, college, response):
        name = self.normalize(candidate.get("name"))
        year = candidate.get("graduation_year")

        # Hard safety/data-quality gate.
        if not name or not self.looks_like_person_name(name):
            return
        if year is not None and not 2000 <= int(year) <= 2025:
            return

        key = (
            college.casefold(),
            name.casefold(),
            year,
            (candidate.get("degree") or "").casefold(),
            (candidate.get("department") or "").casefold(),
        )
        if key in self.seen_records:
            return
        self.seen_records.add(key)

        yield AlumniItem(
            college_name=college,
            alumni_name=name,
            degree=candidate.get("degree"),
            department=candidate.get("department"),
            graduation_year=year,
            alumni_profile_url=candidate.get("profile_url") or response.url,
            source_url=response.url,
            evidence_text=candidate.get("evidence", "")[:1500],
            extraction_status=candidate.get("confidence", "MEDIUM"),
            current_company="UNKNOWN",
            current_job_title="UNKNOWN",
            employment_source_url=None,
            employment_evidence_text="",
            employment_verification_status="NOT_VERIFIED",
        )

    def page_has_alumni_signal(self, response, title, body):
        haystack = f"{response.url} {title} {body[:12000]}".lower()
        return any(term in haystack for term in ALUMNI_TERMS)

    def looks_like_person_name(self, text):
        text = self.normalize(text)
        if not text or len(text) < 4 or len(text) > 100:
            return False

        lower = text.casefold()
        if lower in GENERIC_NAMES:
            return False
        if any(lower == p or lower.startswith(p + " ") for p in GENERIC_NAMES):
            return False
        if YEAR_RE.search(text):
            return False
        if any(term in lower for term in ALUMNI_TERMS):
            return False
        if any(word in lower.split() for word in JOB_WORDS):
            return False

        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
        if not 2 <= len(words) <= 7:
            return False

        honorifics = {"mr", "ms", "mrs", "dr", "prof", "shri", "smt"}
        significant = [w for w in words if w.casefold().strip(".") not in honorifics]
        return len(significant) >= 2 and all(w[0].isupper() for w in significant)

    def profile_url_signal(self, url):
        lower = url.lower()
        path = urlparse(url).path.lower()
        return (
            any(term in lower for term in ("alumni", "alumnus", "alumna", "awardee", "achiever"))
            and path.count("/") >= 2
        ) or any(term in lower for term in ("/profile/", "/person/", "alumni-profile"))

    def is_navigation_node(self, node):
        current = node
        for _ in range(5):
            if current is None:
                return False

            if current.root is not None and current.root.tag.lower() in NAV_TAGS:
                return True

            classes = current.attrib.get("class", "")
            node_id = current.attrib.get("id", "")
            if NAV_CLASS_RE.search(f"{classes} {node_id}"):
                return True

            parents = current.xpath("parent::*")
            current = parents[0] if parents else None

        return False

    def node_text(self, node):
        return self.normalize(" ".join(node.xpath(".//text()").getall()))

    def normalize(self, value):
        return re.sub(r"\s+", " ", str(value or "")).strip(" -,:;|")

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
            and not any(v in content_type for v in ("text/html", "application/xhtml+xml"))
        )

    def is_error_page(self, title, body):
        title_lower = title.lower()
        body_lower = body[:1500].lower()
        return (
            "404" in title_lower
            or "page not found" in title_lower
            or title_lower.strip() == "not found"
            or "404 not found" in body_lower
        )

    def errback_log(self, failure):
        self.logger.warning("Request failed: %s", failure.request.url)
