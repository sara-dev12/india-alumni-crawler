import re
import unicodedata

class NormalizeItemPipeline:
    def process_item(self, item, spider):
        name = item.get("alumni_name", "")
        name = unicodedata.normalize("NFKC", name)
        name = re.sub(r"\s+", " ", name).strip(" -,:;")
        item["alumni_name"] = name
        item["graduation_year"] = self._year(item.get("graduation_year"))
        return item

    def _year(self, value):
        if not value:
            return None
        match = re.search(r"\b(20(?:0\d|1\d|2[0-5]))\b", str(value))
        return int(match.group(1)) if match else None
