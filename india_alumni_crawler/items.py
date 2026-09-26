import scrapy

class AlumniItem(scrapy.Item):
    college_name = scrapy.Field()
    alumni_name = scrapy.Field()
    degree = scrapy.Field()
    department = scrapy.Field()
    graduation_year = scrapy.Field()
    alumni_profile_url = scrapy.Field()
    source_url = scrapy.Field()
    evidence_text = scrapy.Field()
    extraction_status = scrapy.Field()
