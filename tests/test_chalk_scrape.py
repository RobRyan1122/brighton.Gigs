import importlib.util
import json
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "chalk", Path(__file__).resolve().parents[1] / "Venues/scrapeFiles/ChalkScrape.py"
)
chalk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chalk)


def page(props, body=""):
    return body + '<script type="application/json">' + json.dumps({"props": props}) + '</script>'


class ChalkTests(unittest.TestCase):
    def test_links_do_not_depend_on_css_classes(self):
        html = '<a href="/event/band">Band</a><a href="/event/band">Image</a><a href="/live/old">Old</a><a href="/live">Live</a><a href="https://elsewhere.com/event/no">No</a>'
        self.assertEqual(chalk.parse_listing_for_event_urls(html), [
            'https://chalkvenue.com/event/band', 'https://chalkvenue.com/live/old'])

    def test_current_detail_data_and_cancelled_event(self):
        event = {"name": "Band", "starts_at": "2026-07-01T23:30:00Z", "price_description": "15 adv"}
        row = chalk.parse_event_detail_html(page({"event": event}), 'url')
        self.assertEqual((row['event_name'], row['date'], row['cost']), ('Band', '02/07/2026', '15 adv'))
        event['cancelled'] = True
        self.assertIsNone(chalk.parse_event_detail_html(page({"event": event}), 'url'))

    def test_schema_and_old_time_fallback(self):
        html = '<script type="application/ld+json">' + json.dumps({"@graph": [{"@type": "MusicEvent", "name": "Band", "startDate": "2026-10-26T19:00:00Z", "offers": {"price": 12, "priceCurrency": "GBP"}}]}) + '</script>'
        row = chalk.parse_event_detail_html(html, 'url')
        self.assertEqual((row['date'], row['cost']), ('26/10/2026', '\u00a312'))
        row = chalk.parse_event_detail_html('<h1>Old band</h1><time datetime="2026-10-27"></time><p>15 adv</p>', 'url')
        self.assertEqual((row['date'], row['cost']), ('27/10/2026', '15 adv'))

    def test_pagination_range_and_duplicate_links(self):
        first = 'https://chalkvenue.com/event/first'
        second = 'https://chalkvenue.com/event/second'
        def listing(url, dt, next_url=None):
            return page({"events": {"data": [{"link": url, "starts_at": dt}], "next_page_url": next_url}}, f'<a href="{url}">Gig</a>')
        pages = {
            chalk.START_URL: listing(first, '2026-11-01', '/live?events=2'),
            'https://chalkvenue.com/live?events=2': listing(second, '2026-10-26'),
            second: page({"event": {"name": "Second", "starts_at": "2026-10-26", "price_description": "10 adv"}}),
        }
        class Response:
            def __init__(self, text): self.text = text
            def raise_for_status(self): pass
        with patch.object(chalk.requests.Session, 'get', side_effect=lambda url, **kw: Response(pages[url])):
            df = chalk.scrape_all_gig_events(date(2026,10,26), date(2026,10,26), 0)
        self.assertEqual(list(df.event_name), ['Second'])


if __name__ == '__main__':
    unittest.main()
