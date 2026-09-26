import scrapy


class AlumniItem(scrapy.Item):
    # Institution / education
    college_name = scrapy.Field()
    alumni_name = scrapy.Field()
    degree = scrapy.Field()
    department = scrapy.Field()
    graduation_year = scrapy.Field()

    # Discovery evidence
    alumni_profile_url = scrapy.Field()
    source_url = scrapy.Field()
    evidence_text = scrapy.Field()
    extraction_status = scrapy.Field()

    # Employment verification stage.
    # The discovery spider never guesses these values.
    current_company = scrapy.Field()
    current_job_title = scrapy.Field()
    employment_source_url = scrapy.Field()
    employment_evidence_text = scrapy.Field()
    employment_verification_status = scrapy.Field()
