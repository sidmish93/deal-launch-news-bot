import unittest

from newsbot.feeds import _indian_issue, classify, classify_press, direct_url


class ClassifyTests(unittest.TestCase):
    def test_qip_filing(self):
        text = (
            "Urban Company Limited has informed the Exchange about Closure of "
            "Issue of qualified Institutional Placement |SUBJECT: Qualified Institutional Placement"
        )
        self.assertEqual(classify(text), "QIP")

    def test_preferential_and_rights(self):
        self.assertEqual(classify("allotment pursuant to Preferential Issue"), "Preferential")
        self.assertEqual(classify("closure of the Issue Period of the Rights Issue"), "Rights")

    def test_nav_is_not_a_deal(self):
        text = "Net Asset Value (per unit) of Motilal Oswal BSE Select IPO ETF is Rs. 47.93"
        self.assertIsNone(classify(text))

    def test_rhp_filing_day_wording(self):
        text = (
            "Filing of RHP of Mahanadi Coalfields Limited (MCL), "
            "a wholly owned Subsidiary of CIL, with SEBI"
        )
        self.assertEqual(classify(text), "RHP")
        self.assertEqual(classify("Filing of DRHP of South Eastern Coalfields Limited"), "DRHP")
        self.assertEqual(classify("Acme Limited has filled DP_RHP for its IPO"), "RHP")
        self.assertEqual(classify("Acme Limited has filled DP_DRHP for its IPO"), "DRHP")
        self.assertEqual(classify("Acme has filed a UDRHP with SEBI"), "UDRHP")
        self.assertEqual(classify("filed the Draft Red Herring Prospectus with SEBI"), "DRHP")

    def test_foreign_ipo_is_not_an_indian_issue(self):
        self.assertFalse(_indian_issue("Anthropic IPO debuts on Nasdaq", "IPO"))
        self.assertTrue(_indian_issue("NLC India Renewables files draft IPO papers", "IPO"))
        self.assertTrue(_indian_issue("Urban Company raises Rs 2,500 crore through QIP", "QIP"))

    def test_bing_tracker_url(self):
        link = (
            "http://www.bing.com/news/apiclick.aspx?ref=FexRss&url="
            "https%3a%2f%2fwww.cnbctv18.com%2fmarket%2fstory.htm&c=1"
        )
        self.assertEqual(direct_url(link), "https://www.cnbctv18.com/market/story.htm")

    def test_press_skips_grey_market(self):
        self.assertIsNone(classify_press("Acme IPO grey market premium rises"))
        self.assertEqual(classify_press("Acme launches Rs 2,000 crore QIP"), "QIP")


if __name__ == "__main__":
    unittest.main()
