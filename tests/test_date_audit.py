import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
def load(name, folder='scrapeFiles'):
    spec=importlib.util.spec_from_file_location(name,ROOT/'Venues'/folder/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class DateAuditTests(unittest.TestCase):
    def test_yearless_venues_all_months_and_future_year(self):
        alphabet=load('AlphabetScrape');prince=load('PrinceAlbertScrape');hope=load('HopeScrape')
        for month in range(1,13):
            ref=date(2032,month,1);end=date(2032,month,28);mon=ref.strftime('%b');full=ref.strftime('%B')
            for name,parse,text in [('Alphabet',alphabet._parse_event_date,f'{mon} 12'),('Prince Albert',prince._parse_event_date,f'{full} 12th'),('Hope',hope._parse_hope_date,f'Mon 12th {mon} at 7:30 pm')]:
                with self.subTest(venue=name,month=month):
                    self.assertEqual(parse(text,ref,end).date(),date(2032,month,12))

    def test_new_year_and_stale_previous_month(self):
        alphabet=load('AlphabetScrape');prince=load('PrinceAlbertScrape');hope=load('HopeScrape')
        for parse,text in [(alphabet._parse_event_date,'Jan 2'),(prince._parse_event_date,'January 2nd'),(hope._parse_hope_date,'Sat 2nd Jan at 7:30 pm')]:
            self.assertEqual(parse(text,date(2031,12,28),date(2032,1,4)).date(),date(2032,1,2))
        self.assertEqual(hope._parse_hope_date('Fri 31st Dec at 7:30 pm',date(2032,1,1),date(2032,1,7)).date(),date(2031,12,31))

    def test_leap_days_and_explicit_years(self):
        alphabet=load('AlphabetScrape');prince=load('PrinceAlbertScrape');hope=load('HopeScrape')
        for parse,text in [(alphabet._parse_event_date,'Feb 29'),(prince._parse_event_date,'February 29th'),(hope._parse_hope_date,'Sun 29th Feb at 7:30 pm')]:
            self.assertEqual(parse(text,date(2032,2,25),date(2032,3,2)).date(),date(2032,2,29))
        self.assertEqual(hope._parse_hope_date('Sat 2nd Jan 2033 at 7:30 pm',date(2031,12,28)).date(),date(2033,1,2))

    def test_existing_full_year_venues(self):
        cases=[('ChalkScrape','_parse_event_date','02/01/2032'),('DustScrape','_parse_event_date','02-01-32'),('GDSscrape','_parse_event_date','Fri, 2 Jan 2032'),('RossiScrape','_parse_gds_style_date','Fri, 2 Jan 2032')]
        for module,func,text in cases:
            with self.subTest(venue=module): self.assertEqual(getattr(load(module),func)(text).date(),date(2032,1,2))
        folklore=load('FolkloreRoomsScrape')
        df=folklore.parse_listings('<h2>Test Band</h2><p>Friday, 2 January 2032</p>')
        self.assertEqual(df.iloc[0].event_date.date(),date(2032,1,2))

    def test_rossi_month_iteration_crosses_year(self):
        rossi=load('RossiScrape')
        self.assertEqual(rossi._month_year_iter(date(2031,12,28),date(2032,2,2)),[(2031,12),(2032,1),(2032,2)])
        self.assertIn('yr=2032',rossi._build_month_url(2032,2))

    def test_graphics_retains_year_and_uses_range(self):
        graphics=load('graphics','Orchastrators')
        self.assertEqual(graphics.normalise_date_str('02/01/2032').date(),date(2032,1,2))
        self.assertEqual(graphics.normalise_date_str('2032-01-02').date(),date(2032,1,2))
        self.assertEqual(graphics.normalise_date_str('Jan 2',date(2031,12,28),date(2032,1,4)).date(),date(2032,1,2))
        self.assertEqual(graphics.normalise_date_str('Feb 29',date(2032,2,25),date(2032,3,2)).date(),date(2032,2,29))

    def test_dust_does_not_assume_listing_order(self):
        dust=load('DustScrape')
        rows=[{'date':'10-01-32','event_name':'Later','cost':'10','event_url':'later'}, {'date':'02-01-32','event_name':'In range','cost':'10','event_url':'in-range'}]
        with patch.object(dust,'make_driver',return_value=MagicMock()),patch.object(dust,'get_rendered_html',return_value=''),patch.object(dust,'parse_listing_for_event_urls',return_value=['later','in-range']),patch.object(dust,'parse_event_detail_html',side_effect=rows):
            df=dust.scrape_all_gig_events(date(2032,1,1),date(2032,1,7),0)
        self.assertEqual(list(df.event_name),['In range'])

if __name__=='__main__': unittest.main()
