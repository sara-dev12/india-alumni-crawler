import re
import unicodedata


TARGET_MIN_YEAR = 2000
TARGET_MAX_YEAR = 2025


class NormalizeItemPipeline:
    """Normalize and hard-filter records before they reach the feed."""

    def process_item(self, item, spider):
        item["alumni_name"] = self._clean(item.get("alumni_name"))
        item["degree"] = self._clean(item.get("degree"))
        item["department"] = self._clean(item.get("department"))
        item["college_name"] = self._clean(item.get("college_name"))

        year = self._year(item.get("graduation_year"))
        item["graduation_year"] = year

        # Discovery is not employment verification.
        item["current_company"] = item.get("current_company") or "UNKNOWN"
        item["current_job_title"] = item.get("current_job_title") or "UNKNOWN"
        item["employment_verification_status"] = (
            item.get("employment_verification_status") or "NOT_VERIFIED"
        )
        item["employment_source_url"] = item.get("employment_source_url") or None
        item["employment_evidence_text"] = item.get("employment_evidence_text") or ""

        if year is not None and not TARGET_MIN_YEAR <= year <= TARGET_MAX_YEAR:
            item["graduation_year"] = None

        return item

    def _clean(self, value):
        if value is None:
            return None
        value = unicodedata.normalize("NFKC", str(value))
        value = re.sub(r"\s+", " ", value).strip(" -,:;|")
        return value or None

    def _year(self, value):
        if value is None:
            return None
        match = re.search(r"\b(20(?:0\d|1\d|2[0-5]))\b", str(value))
        return int(match.group(1)) if match else None
