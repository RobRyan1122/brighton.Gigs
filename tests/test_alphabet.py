import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch,MagicMock

spec=importlib.util.spec_from_file_location('alphabet',Path(__file__).resolve().parents[1]/'Venues/scrapeFiles/AlphabetScrape.py')
alphabet=importlib.util.module_from_spec(spec);spec.loader.exec_module(alphabet)

class AlphabetTests(unittest.TestCase):
    def test_all_months_are_accepted(self):
        for month in ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']:
            with self.subTest(month=month):
                items=alphabet.parse_listing_for_event_urls(f'<a href="/listings/band">{month} 12: Band</a>',date(2026,1,1))
                self.assertEqual(len(items),1)
                self.assertFalse(alphabet.pd.isna(items[0]['listing_date']))

    def test_year_inference_and_explicit_year(self):
        self.assertEqual(alphabet._parse_listing_date('JAN 23: Band',date(2026,11,8)).date(),date(2027,1,23))
        self.assertEqual(alphabet._parse_event_date('Nov 12',date(2027,11,8)).date(),date(2027,11,12))
        self.assertEqual(alphabet._parse_event_date('Jan 23 2028',date(2026,11,8)).date(),date(2028,1,23))
        self.assertTrue(alphabet.pd.isna(alphabet._parse_event_date('Feb 30',date(2026,11,8))))

    def test_detail_heading_and_compact_date(self):
        row=alphabet.parse_event_detail('<div class="sqs-html-content"><h1>Headroom presents: Alex Downey</h1><p>DATE: NOV14 TIME: 10:30 TICKETS: &#163;14.57</p></div>','url','NOV 14 (LATE): Alex Downey')
        self.assertEqual(row['event_name'],'Headroom presents: Alex Downey')
        self.assertEqual(alphabet._parse_event_date(row['date'],date(2026,11,8)).date(),date(2026,11,14))
        self.assertEqual(row['cost'],'\u00a314.57')

    def test_empty_output_keeps_csv_columns(self):
        with patch.object(alphabet,'make_driver',return_value=MagicMock()),patch.object(alphabet,'get_html',return_value='<html></html>'):
            df=alphabet.scrape_in_range(date(2026,11,8),date(2026,11,15),delay=0)
        self.assertTrue(df.empty)
        self.assertEqual(list(df[['date','event_name','cost']].columns),['date','event_name','cost'])

if __name__=='__main__': unittest.main()
