import datetime
import unittest

from newsbot.feeds import Deal, _indian_issue, classify, classify_press, direct_url


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

    def test_whole_paper_headlines_that_only_mention_a_deal(self):
        def kept(title: str) -> str | None:
            kind = classify_press(title)
            if not kind or not _indian_issue(title, kind):
                return None
            return kind

        self.assertIsNone(kept(
            "GIFT Nifty down, signals cautious start for Sensex, Nifty despite Anthropic IPO boost"
        ))
        self.assertIsNone(kept(
            "Anthropic IPO windfall: More than 400 employees could be worth over ₹935 crore each"
        ))
        self.assertIsNone(kept("Anthropic IPO raises $107.3 billion, surpassing SpaceX's record debut"))
        self.assertIsNone(kept(
            "Anthropic IPO document filed with US Securities and Exchange Commission warns of AI risk"
        ))
        self.assertIsNone(kept(
            "India to have preferential trade access to global GDP, says Piyush Goyal"
        ))
        self.assertIsNone(kept(
            "SEBI chairman bats for 2,000 more listings, pre-IPO framework"
        ))
        self.assertEqual(kept("Mahanadi Coalfields ₹8,981 cr IPO opens today: Price, lot size, dates"), "IPO")
        self.assertEqual(
            kept("Zelio E-Mobility gets BSE nod for ₹168 crore preferential issue, warrants"),
            "Preferential",
        )
        self.assertEqual(kept("Integris Medtech to launch Rs 3,000-crore IPO next week"), "IPO")

    def test_bing_tracker_url(self):
        link = (
            "http://www.bing.com/news/apiclick.aspx?ref=FexRss&url="
            "https%3a%2f%2fwww.cnbctv18.com%2fmarket%2fstory.htm&c=1"
        )
        self.assertEqual(direct_url(link), "https://www.cnbctv18.com/market/story.htm")

    def test_message_is_headline_source_time_and_link(self):
        published = datetime.datetime(2026, 11, 19, 18, 15, tzinfo=datetime.timezone.utc)
        deal = Deal(
            id="press:https://www.moneycontrol.com/news/story",
            kind="IPO",
            company="SEBI chairman bats for 2,000 more listings, pre-IPO framework",
            summary="SEBI is separately reviewing the ICDR framework",
            source="Moneycontrol",
            url="https://www.moneycontrol.com/news/story",
            published=published,
        )
        self.assertEqual(
            deal.format(),
            "SEBI chairman bats for 2,000 more listings, pre-IPO framework\n"
            "Moneycontrol | 19 Nov 2026, 11:45 PM IST\n"
            "https://www.moneycontrol.com/news/story",
        )

    def test_press_skips_grey_market(self):
        self.assertIsNone(classify_press("Acme IPO grey market premium rises"))
        self.assertEqual(classify_press("Acme launches Rs 2,000 crore QIP"), "QIP")


if __name__ == "__main__":
    unittest.main()
