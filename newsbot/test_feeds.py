import datetime
import unittest

from newsbot.feeds import _sitemap_entries, classify_press

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://auto.economictimes.indiatimes.com/news/zelio/136026637</loc>
    <news:news>
      <news:publication_date>2026-11-20T10:58:00+05:30</news:publication_date>
      <news:title>Zelio E-Mobility gets BSE nod for ₹168 crore preferential issue</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://economictimes.indiatimes.com/magazines/panache/gta.htm</loc>
    <news:news>
      <news:publication_date>2026-11-20T19:49:14+05:30</news:publication_date>
      <news:title>Woman creates GTA 6-themed gift basket</news:title>
    </news:news>
  </url>
</urlset>
"""


class SitemapTests(unittest.TestCase):
    def test_sitemap_keeps_the_publish_time_and_the_deal_headline(self):
        entries = _sitemap_entries(SITEMAP.encode())
        self.assertEqual(len(entries), 2)
        title, link, published = entries[0]
        self.assertEqual(title, "Zelio E-Mobility gets BSE nod for ₹168 crore preferential issue")
        self.assertIn("136026637", link)
        self.assertEqual(published, datetime.datetime.fromisoformat("2026-11-20T10:58:00+05:30"))
        self.assertEqual(classify_press(title), "Preferential")
        self.assertIsNone(classify_press(entries[1][0]))

    def test_ndtv_sitemap_uses_the_article_url_not_the_image(self):
        payload = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
                xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
          <url>
            <loc>https://www.ndtvprofit.com/business/urban-company-raises-rs-2-500-cr-via-qip-12353026</loc>
            <image:image><image:loc>https://c.ndtvimg.com/photo.jpg</image:loc></image:image>
            <lastmod><![CDATA[ 2026-11-20T05:10:00+05:30 ]]></lastmod>
          </url>
        </urlset>
        """
        from newsbot.feeds import _indian_issue, _listed_entries, _title_from_slug
        entries = _listed_entries(payload.encode())
        self.assertEqual(len(entries), 1)
        title, link, published = entries[0]
        self.assertEqual(title, _title_from_slug(link))
        self.assertTrue(link.endswith("12353026"))
        self.assertEqual(published, datetime.datetime.fromisoformat("2026-11-20T05:10:00+05:30"))
        kind = classify_press(title)
        self.assertEqual(kind, "QIP")
        self.assertTrue(_indian_issue(title, kind))


if __name__ == "__main__":
    unittest.main()
