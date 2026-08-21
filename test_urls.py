import unittest
from unittest.mock import patch

from ticketmaster import parse_event, pick_event_url
from urls import classify, marketplace_404, safe_public_url


Z7 = "https://www.ticketmaster.com/event/Z7r9jZ1A7-Ebw"
BOWL_INDEX = "https://www.hollywoodbowl.com/events/performances/"
BOWL_SHOW = (
    "https://www.hollywoodbowl.com/events/performances/4333/"
    "2026-09-04/maestro-of-the-movies-a-tribute-to-john-williams"
)
TM_SLUG = (
    "https://www.ticketmaster.com/harry-styles-together-together-"
    "new-york-new-york-08-28-2026/event/3B00643504538196"
)


class UrlRules(unittest.TestCase):
    def test_z7_marketplace_is_dead(self):
        self.assertTrue(marketplace_404(Z7, "Z7r9jZ1A7-Ebw"))
        self.assertEqual(classify(Z7, "Z7r9jZ1A7-Ebw"), "dead")
        self.assertIsNone(safe_public_url(Z7, "Z7r9jZ1A7-Ebw"))

    def test_bowl_calendar_index_is_not_a_show(self):
        self.assertEqual(classify(BOWL_INDEX), "index")
        self.assertIsNone(safe_public_url(BOWL_INDEX))

    def test_real_bowl_and_tm_slug_pass(self):
        self.assertEqual(classify(BOWL_SHOW), "ok")
        self.assertEqual(safe_public_url(BOWL_SHOW), BOWL_SHOW)
        self.assertEqual(classify(TM_SLUG), "ok")
        self.assertEqual(safe_public_url(TM_SLUG), TM_SLUG)

    def test_http_is_upgraded_javascript_is_dropped(self):
        self.assertEqual(
            safe_public_url("http://www.ticketweb.com/event/ichi-bons/14232324"),
            "https://www.ticketweb.com/event/ichi-bons/14232324",
        )
        self.assertIsNone(safe_public_url("javascript:alert(1)"))
        self.assertIsNone(safe_public_url("data:text/html,nope"))

    def test_homepage_is_weak_not_linked(self):
        self.assertEqual(classify("https://www.redrocksonline.com/"), "weak")
        self.assertIsNone(safe_public_url("https://www.redrocksonline.com/"))


class Picker(unittest.TestCase):
    def test_prefers_axs_outlet_over_z7(self):
        url = pick_event_url(
            {
                "id": "Z7r9jZ1A7OUZS",
                "name": "Reggae On The Rocks 2026",
                "url": Z7.replace("Z7r9jZ1A7-Ebw", "Z7r9jZ1A7OUZS"),
                "outlets": [
                    {
                        "url": "http://www.axs.com/events/1313694/reggae-on-the-rocks-2026-tickets",
                        "type": "venueBoxOffice",
                    },
                    {
                        "url": "https://www.ticketmaster.com/event/Z7r9jZ1A7OUZS",
                        "type": "tmMarketPlace",
                    },
                ],
            }
        )
        self.assertEqual(
            url, "https://www.axs.com/events/1313694/reggae-on-the-rocks-2026-tickets"
        )

    def test_z7_without_outlet_is_blank(self):
        self.assertIsNone(
            pick_event_url(
                {
                    "id": "Z7r9jZ1A7-Ebw",
                    "name": "Los Angeles Philharmonic",
                    "url": Z7,
                    "outlets": [],
                }
            )
        )

    @patch("ticketmaster.bowl_performance_url", return_value=BOWL_SHOW)
    def test_bowl_night_uses_official_page(self, _mock):
        url = pick_event_url(
            {
                "id": "Z7r9jZ1A7-Ebw",
                "name": "Los Angeles Philharmonic",
                "url": Z7,
                "dates": {"start": {"localDate": "2026-09-04"}},
                "_embedded": {"venues": [{"name": "Hollywood Bowl"}]},
                "outlets": [{"url": BOWL_INDEX, "type": "venueBoxOffice"}],
            }
        )
        self.assertEqual(url, BOWL_SHOW)

    @patch("ticketmaster.bowl_performance_url", return_value=BOWL_SHOW)
    def test_parse_event_does_not_store_z7(self, _mock):
        parsed = parse_event(
            {
                "id": "Z7r9jZ1A7-Ebw",
                "name": "Los Angeles Philharmonic",
                "url": Z7,
                "dates": {
                    "start": {"localDate": "2026-09-04", "localTime": "20:00:00"},
                    "status": {"code": "onsale"},
                },
                "_embedded": {"venues": [{"id": "Z6r9jZF7Fe", "name": "Hollywood Bowl"}]},
                "outlets": [{"url": BOWL_INDEX, "type": "venueBoxOffice"}],
            }
        )
        self.assertIsNotNone(parsed)
        self.assertNotEqual(parsed["url"], Z7)
        if parsed["url"]:
            self.assertFalse(marketplace_404(parsed["url"], parsed["id"]))
            self.assertNotEqual(parsed["url"].rstrip("/"), BOWL_INDEX.rstrip("/"))


if __name__ == "__main__":
    unittest.main()
