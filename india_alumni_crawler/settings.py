BOT_NAME = "india_alumni_crawler"

SPIDER_MODULES = ["india_alumni_crawler.spiders"]
NEWSPIDER_MODULE = "india_alumni_crawler.spiders"

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.5
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "IndiaAlumniResearchCrawler/0.1 (+public-research; respect robots.txt)"
}

FEEDS = {
    "alumni.jsonl": {
        "format": "jsonlines",
        "encoding": "utf8",
        "overwrite": False,
    }
}

ITEM_PIPELINES = {
    "india_alumni_crawler.pipelines.NormalizeItemPipeline": 300,
}

LOG_LEVEL = "INFO"
