import unittest

from india_alumni_crawler.spiders.alumni import AlumniSpider


class AlumniExtractionTests(unittest.TestCase):
    def setUp(self):
        self.spider = AlumniSpider()

    def test_explicit_parenthesized_record(self):
        rows = self.spider.extract_explicit_records(
            "Dr. Nilesh Pandey (PhD/EE/2022) received an award."
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Dr. Nilesh Pandey")
        self.assertEqual(rows[0]["graduation_year"], 2022)
        self.assertEqual(rows[0]["degree"], "Ph.D.")
        self.assertEqual(rows[0]["department"], "Electrical Engineering")

    def test_explicit_slash_record(self):
        rows = self.spider.extract_explicit_records(
            "Dr. Aravind Srinivas 2017/DD/EE"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["graduation_year"], 2017)
        self.assertEqual(rows[0]["degree"], "Dual Degree")
        self.assertEqual(rows[0]["department"], "Electrical Engineering")

    def test_page_award_year_is_not_graduation_year(self):
        rows = self.spider.extract_explicit_records(
            "2026 Dr. Aravind Srinivas 2017/DD/EE"
        )
        self.assertEqual(rows[0]["graduation_year"], 2017)

    def test_navigation_labels_are_rejected(self):
        self.assertFalse(self.spider.looks_like_person_name("Awards & Achievements"))
        self.assertFalse(self.spider.looks_like_person_name("View All"))
        self.assertFalse(self.spider.looks_like_person_name("Learn More"))

    def test_target_year_range(self):
        rows = self.spider.extract_explicit_records(
            "Dr. Old Person (BT/EE/1999) Dr. New Person (BT/EE/2000)"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Dr. New Person")


if __name__ == "__main__":
    unittest.main()
