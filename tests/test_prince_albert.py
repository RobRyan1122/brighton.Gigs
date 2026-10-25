import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prince', Path(__file__).resolve().parents[1] / 'Venues/scrapeFiles/PrinceAlbertScrape.py')
prince = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prince)


class PrinceAlbertTests(unittest.TestCase):
    def test_empty_listing_preserves_output_columns(self):
        with patch.object(prince, 'get_html', return_value='<html>No listings</html>'):
            df = prince.scrape_in_range(date(2026,10,25), date(2026,11,1))
        self.assertTrue(df.empty)
        self.assertEqual(list(df[['date','event_name','cost']].columns), ['date','event_name','cost'])

    def test_server_rendered_listing_and_date_range(self):
        html = '''<div data-id="154e459"><div class="jet-listing-dynamic-field__content">Test Band</div></div>
        <div data-id="27af3ce"><div class="jet-listing-dynamic-field__content">October 27th</div></div>
        <div data-id="af29adb"><div class="jet-listing-dynamic-field__content">&#163;7.00 + booking fee</div></div>'''
        with patch.object(prince, 'get_html', return_value=html):
            df = prince.scrape_in_range(date(2026,10,25), date(2026,11,1))
            self.assertEqual(list(df.event_name), ['Test Band'])
            self.assertEqual(df.iloc[0].cost, '\u00a37.00')
            self.assertEqual(df.iloc[0].event_date.date(), date(2026,10,27))
            self.assertTrue(prince.scrape_in_range(date(2026,11,1),date(2026,11,7)).empty)


if __name__ == '__main__': unittest.main()
