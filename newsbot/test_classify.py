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
        self.assertEqual(
            offer_status("Tata Steel to buy up to 26.38% in APL Apollo for Rs 15,511 crore, launch Rs 16,756-crore open offer"),
            "firm",
        )
        self.assertEqual(offer_status("Persistent Systems may soon launch up to $450 million QIP"), "firm")
        self.assertEqual(offer_status("IIFL Capital launches up to $250 million block deal in Sagility"), "firm")
        self.assertEqual(offer_status("Hogan Lovells advises on $375 million Aegis Logistics QIP"), "no")
        self.assertEqual(
            offer_status("Muthoot Finance shelves Belstar Microfinance IPO, not keen to list now"),
            "firm",
        )
        self.assertEqual(offer_status("Atomberg Technologies receives SEBI approval for Rs 450 crore IPO"), "firm")
        self.assertEqual(
            offer_status("Coal India's Mahanadi Coalfields IPO price band set at Rs 129-136 per share | Check GMP"),
            "firm",
        )
        self.assertEqual(
            offer_status("Foodlink F&B Holdings IPO GMP at 6% ahead of November 26 issue opening; check price band"),
            "no",
        )
        self.assertEqual(
            offer_status("Aegis Logistics announces Rs 3,500 crore fundraising plan through QIP; stock rises 3%"),
            "firm",
        )
        self.assertEqual(
            offer_status("Mahanadi Coalfields IPO: Coal India to divest up to 10% stake"),
            "firm",
        )
        self.assertEqual(offer_status("IIFCL IPO: Govt to part sale stake, company to issue fresh shares"), "firm")
        self.assertEqual(
            offer_status("Nvidia-backed Australian AI firm Firmus withdraws mega IPO, citing market volatility"),
            "no",
        )
        self.assertEqual(offer_status("Bonfiglioli Transmissions Ltd - IPO"), "firm")
        self.assertEqual(offer_status("Shell announces $5 billion buyback as oil refining booms"), "no")
        self.assertEqual(
            offer_status("IPO GMP: Bonfiglioli vs Tonbo vs Sahajanand Medical vs Zetwerk — Dates, price band, key details"),
            "no",
        )
        self.assertEqual(
            offer_status("IIFL Finance Block Deal: Trade Volume Crosses Two Times Its 30-Day Average; Stock Jumps Over 6%"),
            "no",
        )
        self.assertEqual(
            offer_status("Watrana Rentals SME IPO opens today; GMP at 25%, check key details"),
            "no",
        )
        self.assertEqual(
            offer_status("Crystal Crop Protection IPO opens: GMP signals 5% listing premium; should you subscribe?"),
            "no",
        )
        self.assertEqual(
            offer_status("InvIT IPO rush gathers pace; 4-5 private trusts likely to go public by Mar 2027"),
            "no",
        )
        self.assertIsNone(confirm_offer(
            "SEBI mulls 3rd-party monitoring of IPO fund use, shell firms pose market risk",
            "The chairman said the regulator is reviewing how IPO proceeds are monitored.",
        ))
        self.assertEqual(
            offer_status("SG Mart shares gain over 10% as board to meet this week to consider fund raising proposal"),
            "firm",
        )
        self.assertEqual(
            offer_status("Aegis Logistics board approves Rs 6,000 crore fund raising proposal"),
            "firm",
        )
        self.assertEqual(
            offer_status("Ather Energy allots shares, warrants in ₹1,200 crore fundraise"),
            "firm",
        )
        self.assertEqual(
            offer_status("Venus Pipes plans ₹372 crore share sale to 18 investors including Ashish Kacholia"),
            "firm",
        )
        self.assertEqual(
            offer_status("NSE IPO shrinks as SBI, Bank of Baroda, MS Strategic trim their OFS size"),
            "firm",
        )
        self.assertEqual(
            offer_status("SG Mart shares trade in red as company to mull raising funds on Nov 26"),
            "no",
        )
        self.assertEqual(
            offer_status("Multibagger stock: SG Mart surges 13% to record high on fundraise buzz"),
            "no",
        )
        self.assertEqual(
            offer_status("Japan-based Galilei Holdings to invest Rs 180 crore in Ice Make Refrigeration"),
            "no",
        )
        self.assertEqual(
            offer_status("US boosts long-term debt buybacks after yields hit highest levels in years"),
            "no",
        )
        self.assertEqual(
            offer_status("Centre announces ₹30,000 crore govt securities buyback via auction"),
            "no",
        )
        self.assertEqual(
            offer_status("CAM, Trilegal, Linklaters act on Piramal Finance's INR 2,100 crore QIP"),
            "no",
        )
        self.assertEqual(
            offer_status("NSE IPO opens today; should you apply? Check reviews, GMP"),
            "no",
        )
        self.assertEqual(
            offer_status("JM Financial's maiden pre-IPO fund raises ₹700 crore in first close"),
            "no",
        )
        self.assertEqual(
            offer_status("Dividend, bonus, split, buyback, spin off in October: TCS, NMDC, PTC India"),
            "no",
        )
        self.assertEqual(
            offer_status("Chinese AI firm Moonshot files confidentially for Hong Kong IPO"),
            "no",
        )
        self.assertEqual(
            offer_status("Airtel Money files for London IPO through offer for sale by shareholders"),
            "no",
        )
        self.assertEqual(
            offer_status("IPO: Share price band ₹300, GMP ₹313 - Check last date to apply"),
            "no",
        )
        self.assertEqual(
            offer_status("Pixxel raises $100 mn in Series C, India's largest spacetech fundraise"),
            "no",
        )
        self.assertEqual(
            offer_status("Ola shares crash 9% ahead of board meet to raise funds"),
            "no",
        )
        self.assertEqual(
            offer_status("Ola sheds 3.5%: Why is EV 2W stock down despite ₹1,000 cr fundraise plan?"),
            "no",
        )
        self.assertEqual(
            offer_status("Ionic Wealth announces Rs 117 crore fundraise from Angel One to ramp up growth"),
            "no",
        )
        self.assertEqual(
            offer_status("SpiceJet crisis: Why pilots' body wants govt to put ₹5,500-crore fundraise under lens"),
            "no",
        )
        self.assertEqual(
            offer_status("Adani Airports raises ₹2,790 crore from 360 ONE Asset, total fundraise hits $1.35 billion"),
            "firm",
        )
        self.assertEqual(
            offer_status("Cochin Shipyard OFS opens July 7; govt offers 2.52% stake at Rs 1,400 floor price"),
            "firm",
        )
        self.assertEqual(
            offer_status("Board of Brigade Enterprises approves issuance of convertible warrants"),
            "firm",
        )
        self.assertEqual(
            offer_status("SPML Infra allots 6.93 lakh equity shares and 95.39 lakh warrants"),
            "firm",
        )
        self.assertEqual(
            offer_status("Aditya Birla Capital invests Rs 485 crore in Aditya Birla Sun Life Insurance on rights basis"),
            "firm",
        )
        self.assertEqual(
            offer_status("Investors pull Oyo's valuation down further as IPO slips to early 2027"),
            "firm",
        )
        self.assertEqual(
            offer_status("RCF shares jump 3% after board approves Rs 1,500 crore FPO"),
            "firm",
        )
        self.assertEqual(
            offer_status("Nifty IPO index up 19.5% in 2026 as broad market slips, shows data"),
            "no",
        )
        self.assertEqual(
            offer_status("NSE Q1 Results: IPO-bound exchange posts 9% rise in profit as margin expands; revenue slips"),
            "maybe",
        )
        self.assertIsNone(confirm_offer(
            "NSE Q1 Results: IPO-bound exchange posts 9% rise in profit as margin expands; revenue slips"
        ))
        self.assertEqual(
            offer_status("Anthropic mulls mandatory employee stock trading plans after IPO"),
            "no",
        )
        self.assertEqual(
            offer_status("Sebi open market share buy-back norms explained: Eligibility, timeline and impact"),
            "no",
        )
        self.assertEqual(
            offer_status("US refiners ramp up buybacks as Iran war boosts fuel margins"),
            "no",
        )
        self.assertEqual(
            offer_status("Crystal Crop Protection IPO booked nearly 3x on Day 2"),
            "no",
        )
        self.assertEqual(
            offer_status("Upcoming IPOs: Shiprocket IPO, Dhoot Transmission IPO among new issues to open next week; full list here"),
            "no",
        )
        self.assertEqual(
            offer_status("IPO Rush: Over 50 firms file DRHPs ahead of Sebi deadline"),
            "no",
        )
        self.assertEqual(
            offer_status("Atomberg IPO decoded: Issue size, investor exits, financials and key risks"),
            "no",
        )
        self.assertEqual(
            offer_status("TeamLease Services announces ₹238 crore share buyback at ₹1,600 per share; posts 26% rise in Q4 net profit"),
            "firm",
        )
        self.assertEqual(
            offer_status("Vodafone Idea to raise Rs 4,730 crore from Aditya Birla Group entity via warrants issue"),
            "firm",
        )
        self.assertEqual(
            offer_status("SBI MF acquires stakes in Adani Enterprises and Adani Energy from GQG for Rs 5,748 crore"),
            "firm",
        )
        self.assertEqual(
            offer_status("Aditya Birla Capital raises ₹4,000 crore from promoters via preferential share allotment"),
            "firm",
        )
        self.assertEqual(
            offer_status("Zepto seals pre-IPO fundraise, defers listing to next year"),
            "firm",
        )
        self.assertEqual(
            offer_status("Reliance Jio IPO: 7 risk factors investors should know as firm gets Sebi nod for Rs 37,000-crore issue"),
            "firm",
        )
        self.assertEqual(
            offer_status("NHPC share price tanks around 6% after fundraise move through the OFS"),
            "no",
        )
        self.assertEqual(
            offer_status("Why India keeps selling stakes in PSUs instead of privatising them"),
            "no",
        )
        self.assertEqual(
            offer_status("Do you know what an Offer for Sale (OFS) is? Here's a complete guide"),
            "no",
        )
        self.assertEqual(
            offer_status("What income makes you middle class in India? Here’s what data from NSE DRHP shows"),
            "no",
        )
        self.assertEqual(
            offer_status("Anthropic IPO: 6 key takeaways from the Claude maker's filing"),
            "no",
        )
        self.assertEqual(
            offer_status("Why more companies are choosing SEBI's confidential IPO filing route"),
            "no",
        )
        self.assertEqual(
            offer_status("NSE IPO journey moves ahead: Top 10 things investors should know from DRHP"),
            "no",
        )
        self.assertEqual(
            offer_status("Steamhouse raises Rs 50 crore in pre-IPO funding from Madhusudhan Kela-backed funds"),
            "no",
        )
        self.assertEqual(
            offer_status("Bajaj Auto buyback record date nears. Should you participate in ₹5,633 crore share repurchase deal?"),
            "no",
        )
        self.assertEqual(
            offer_status("Govt's PSU stake sales via OFS at 11-year high so far in 2026"),
            "no",
        )
        self.assertEqual(
            offer_status("Sebi board brings back open-market share buybacks; eases debt listing"),
            "no",
        )
        self.assertEqual(
            offer_status("Sammaan Capital gets open offer from Avenir, IHC for 26% stake"),
            "firm",
        )
        self.assertEqual(
            offer_status("Give reasons before forcing the acquirer into an open offer, SAT tells SEBI"),
            "no",
        )
        self.assertEqual(
            offer_status("IHC becomes promoter of Sammaan Capital after completing open offer"),
            "no",
        )
        self.assertEqual(
            offer_status("38 companies file IPO papers in March; 64 await SEBI approval"),
            "no",
        )
        self.assertEqual(
            offer_status("Primary market action: Nearly a dozen companies file IPO papers with SEBI"),
            "no",
        )
        self.assertEqual(
            offer_status("IPO rush: 9 companies, including Trans ACNR Solutions, submit draft IPO papers to SEBI"),
            "firm",
        )
        self.assertEqual(
            offer_status("Wipro's buyback could give up to 14% returns to investors in the short-term"),
            "no",
        )
        self.assertEqual(
            offer_status("56% returns in six months! Ola Electric Mobility to raise ₹1,000 crore via rights issue"),
            "firm",
        )
        self.assertEqual(
            offer_status("Poonawalla Fincorp picks Jefferies, Kotak and JP Morgan for up to Rs 5,500 crore equity capital raise"),
            "firm",
        )
        self.assertEqual(
            classify("Poonawalla Fincorp picks Jefferies, Kotak and JP Morgan for up to Rs 5,500 crore equity capital raise"),
            "Fundraise",
        )
        self.assertEqual(
            offer_status("70% of ₹6,414 cr capital raise to fund fresh lending: IIFL Finance founder"),
            "no",
        )
        self.assertEqual(
            offer_status("Bajaj Finance shares fall 5% as company plans to seek approval for capital raise"),
            "no",
        )
        self.assertEqual(
            offer_status("SpiceJet to consider fresh capital raise through equity, preference shares; shares rise 5%"),
            "no",
        )
        self.assertEqual(
            offer_status("RIL says Jio Platforms receives SEBI observation letter for proposed IPO"),
            "firm",
        )
        self.assertEqual(
            offer_status("SEBI gives thumbs up to Bonbloc Technologies, Milestone Gears, Eastman Auto IPOs"),
            "maybe",
        )
        self.assertEqual(
            confirm_offer(
                "SEBI gives thumbs up to Bonbloc Technologies, Milestone Gears, Eastman Auto IPOs",
                "The SEBI has issued observations on the draft papers of Eastman Auto & Power on March 5.",
            ),
            "IPO",
        )
        self.assertEqual(
            offer_status("IPO pipeline robust with 245 DRHPs filed with Sebi, 175 receive observations: Equirus"),
            "no",
        )
        self.assertEqual(
            offer_status("Aurobindo Pharma shares fall 2% after USFDA issues one observation for Telangana facility"),
            "no",
        )
        self.assertEqual(
            offer_status("Razorpay moves closer to public market debut as Sebi gives green signal to IPO"),
            "no",
        )
        self.assertEqual(
            offer_status("Japan's Aica Kogyo to buy 40-53% of Stylam Industries for ₹1,500-2,000 crore"),
            "firm",
        )
        self.assertEqual(
            classify("Japan's Aica Kogyo to buy 40-53% of Stylam Industries for ₹1,500-2,000 crore"),
            "Stake",
        )
        self.assertEqual(
            offer_status("Tata Steel to buy 26.6% in APL Apollo Tubes for ₹15,511 crore"),
            "firm",
        )
        self.assertEqual(
            offer_status("Blackstone set to acquire 15% of IIFL for Rs 5,000 crore"),
            "firm",
        )
        self.assertEqual(
            offer_status("MUFG will not need RBI approval to acquire 20% in Shriram Finance"),
            "no",
        )
        self.assertEqual(
            offer_status("APL Apollo Tubes shares crash 20% after Tata Steel set to acquire controlling stake for Rs 15,511 crore"),
            "no",
        )
        self.assertEqual(
            offer_status("Your Rs 1 Lakh Buys 25% More Gold This Dhanteras Than In January"),
            "no",
        )
        self.assertEqual(
            offer_status("IndiGrid Infra Trust launches institutional share sale to raise up to ₹1,500 crore"),
            "firm",
        )
        self.assertEqual(
            classify("IndiGrid Infra Trust launches institutional share sale to raise up to ₹1,500 crore"),
            "Fundraise",
        )
        self.assertEqual(
            offer_status("JSW Energy to raise ₹4,000 crore via share sale — Check indicative issue price and other details"),
            "no",
        )
        self.assertEqual(
            offer_status("Aegis Logistics opens ₹6,000-crore share sale, sets floor price at ₹1,161.85"),
            "no",
        )
        self.assertEqual(
            offer_status("Swiggy to use nearly half of Rs 10,000 crore QIP proceeds for quick commerce expansion"),
            "firm",
        )

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
