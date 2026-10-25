import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'Venues/Orchastrators' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

class PartialVenueTests(unittest.TestCase):
    def test_graphics_excludes_stale_and_failed_venue_files(self):
        graphics = load('graphics')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); csvs = root / 'csvs'; csvs.mkdir()
            (csvs / 'ChalkScrape.csv').write_text('date,event_name,cost\n25/10/2026,Good band,10\n')
            (csvs / 'PrinceAlbertScrape.csv').write_text('date,event_name,cost\n25/10/2026,Stale band,10\n')
            (root / 'scraper_health.json').write_text(json.dumps({'successful_files': ['ChalkScrape.csv'], 'failures': ['PrinceAlbert']}))
            with patch.object(graphics, 'PROJECT_ROOT', root):
                df = graphics.load_all_csvs(csvs)
            self.assertEqual(list(df.event_name), ['Good band'])

    def test_warning_email_explains_delivery_continued(self):
        alert = load('alert_failure')
        with patch.dict(os.environ, {'SENDER_EMAIL':'test@example.com','RECIPIENT_EMAIL':'test@example.com'}):
            msg = alert.build_alert(venue_warning=True)
        self.assertIn('venues missing', msg['Subject'])
        self.assertIn('Posters were generated and emailed', msg.get_content())
        self.assertNotIn('pipeline failed', msg.get_content())

    def test_main_continues_through_poster_delivery(self):
        main = load('main')
        with patch.object(main, 'run_script') as run:
            main.main()
        self.assertEqual([c.args[0] for c in run.call_args_list], ['run_all_scrapers.py','normalise_costs.py','graphics.py','emailer.py','cleanup.py'])

if __name__ == '__main__': unittest.main()
