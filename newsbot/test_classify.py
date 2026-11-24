import datetime
import unittest

from newsbot.feeds import Deal, _indian_issue, classify, classify_press, confirm_offer, direct_url, offer_status


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
        self.assertEqual(
            kept("SEBI Approves Arohan Financial Services, Pristine Logistics To Float IPOs: Check Issue Details"),
            "IPO",
        )
        self.assertEqual(kept("Integris Medtech to launch Rs 3,000-crore IPO next week"), "IPO")
        self.assertEqual(kept("Mahindra Last Mile Mobility eyes IPO in 18 months"), "IPO")
        self.assertEqual(kept("Pernod Ricard weighs India IPO as market closes in on US"), "IPO")
        self.assertEqual(kept("Chandrasekaran to push Tata Sons IPO plan at board meet"), "IPO")
        self.assertEqual(kept("Oyo eyes IPO again as the offer slips to early 2027"), "IPO")
        self.assertEqual(
            kept("Yashoda Hospitals defers IPO; explores part stake sale targeting up to $3.2 bn"),
            "Stake",
        )
        self.assertEqual(
            kept("Tata Steel to acquire 26.38% stake in APL Apollo Tubes for Rs 15,510 crore"),
            "Stake",
        )
        self.assertEqual(
            kept("APL Apollo Tubes shares worth Rs 5,825 crore change hands in block deal"),
            "Block",
        )
        self.assertIsNone(kept("Anthropic's record IPO raises hopes for a charitable windfall"))
        self.assertIsNone(kept("Hogan Lovells advises on $375 million Aegis Logistics QIP"))
        self.assertIsNone(kept("Lenskart shares fall nearly 4% as Rs 921-crore block deal takes place"))
        self.assertIsNone(kept("Dalmia Bharat pares losses to trade flat after Rs 700-cr buyback announcement"))
        self.assertIsNone(kept("Upcoming dividend, split, rights issue record dates next week"))
        self.assertIsNone(kept("IDBI stake sale: employee forum announces December 3 strike"))
        self.assertIsNone(kept("InvIT IPO rush gathers pace; 4-5 private trusts likely to go public by Mar 2027"))
        self.assertIsNone(kept("After selling APL Apollo stake to Tata Steel, Sanjay Gupta family shifts focus to SG Mart"))
        self.assertIsNone(kept("J M Baxi Group buys 51% stake in San Maritime; enters shipbuilding"))
        self.assertIsNone(kept("Tata Steel share price in focus on announcement to acquire 26% stake in APL Apollo for Rs 15,511 crore"))

    def test_bing_tracker_url(self):
        link = (
            "http://www.bing.com/news/apiclick.aspx?ref=FexRss&url="
            "https%3a%2f%2fwww.cnbctv18.com%2fmarket%2fstory.htm&c=1"
        )
        self.assertEqual(direct_url(link), "https://www.cnbctv18.com/market/story.htm")

    def test_a_headline_that_only_names_the_offer_is_confirmed_from_the_verb_beside_it(self):
        headline = "Acme Industries mulls IPO next year"
        self.assertEqual(offer_status(headline), "maybe")
        self.assertEqual(confirm_offer(headline), "IPO")
        self.assertIsNone(confirm_offer("SEBI chairman bats for 2,000 more listings, pre-IPO framework"))
        self.assertEqual(
            confirm_offer(
                "Acme Industries board meets Thursday",
                "The company is considering an IPO to fund its expansion.",
            ),
            "IPO",
        )
        self.assertEqual(offer_status("Lenskart shares fall nearly 4% as Rs 921-crore block deal takes place"), "no")
        self.assertEqual(
            offer_status("Should you buy IDBI shares? Is it a good banking stock to bet on amid Fairfax stake sale deal"),
            "no",
        )
        self.assertEqual(
            offer_status("Dividend, Buyback, rights issue record date Nov 25: Zee, Vraj Iron, Bonlon, and more"),
            "no",
        )
        self.assertEqual(
            offer_status("Up to 5 InvITs expected to go public by March 2027 and launch IPOs"),
            "no",
        )
        self.assertIsNone(confirm_offer("Fintech WeRize posts Rs 44 crore profit, targets 10x growth ahead of IPO"))

    def test_a_late_listing_is_sent_after_the_first_run_has_remembered_the_lists(self):
        from newsbot.deal_bot import _choose

        now = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=datetime.timezone.utc)
        old = Deal(
            id="press:https://example.com/old",
            kind="IPO",
            company="Old Co files IPO papers",
            summary="",
            source="Mint",
            url="https://example.com/old",
            published=now - datetime.timedelta(hours=40),
        )
        fresh = Deal(
            id="press:https://example.com/new",
            kind="IPO",
            company="New Co files IPO papers",
            summary="",
            source="Mint",
            url="https://example.com/new",
            published=now - datetime.timedelta(hours=2),
        )
        state = {"seen": [], "held": {}, "watching": False}
        chosen = _choose([old, fresh], [], state, now)
        self.assertEqual([deal.company for deal in chosen], ["New Co files IPO papers"])
        self.assertEqual(state["held"][old.url], old.company)
        late = Deal(
            id="press:https://example.com/late",
            kind="IPO",
            company="Late Co files IPO papers",
            summary="",
            source="Mint",
            url="https://example.com/late",
            published=now - datetime.timedelta(hours=50),
        )
        chosen = _choose([old, late], [], state, now)
        self.assertEqual([deal.company for deal in chosen], ["Late Co files IPO papers"])
        state["seen"].append(late.id)
        self.assertEqual(_choose([late], [], state, now), [])

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
