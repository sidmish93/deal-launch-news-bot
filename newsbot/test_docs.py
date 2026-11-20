import io
import unittest
import zipfile

from newsbot.docs import unzip
from newsbot.feeds import Deal


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class UnzipTests(unittest.TestCase):
    def test_returns_the_pdfs_and_skips_junk(self):
        blob = _zip({
            "Offer/UDRHP.pdf": b"%PDF-1.4 prospectus",
            "Offer/Abridged.pdf": b"%PDF-1.4 short",
            "Offer/": b"",
            "__MACOSX/Offer/UDRHP.pdf": b"junk",
            "../secret.pdf": b"nope",
        })
        opened = unzip(blob)
        names = [name for name, _ in opened.files]
        self.assertEqual(names, ["UDRHP.pdf", "Abridged.pdf"])
        self.assertEqual(opened.files[0][1], b"%PDF-1.4 prospectus")
        self.assertEqual(opened.skipped, 0)

    def test_rejects_a_file_that_is_not_a_zip(self):
        with self.assertRaises(ValueError):
            unzip(b"%PDF-1.4 already a pdf")

    def test_message_can_omit_the_zip_link(self):
        deal = Deal("1", "UDRHP", "Acme", "Filed a UDRHP", "NSE offer document", "https://nse.example/Acme.zip", None)
        self.assertNotIn(".zip", deal.format(include_url=False))
        self.assertIn("Acme.zip", deal.format())


if __name__ == "__main__":
    unittest.main()
