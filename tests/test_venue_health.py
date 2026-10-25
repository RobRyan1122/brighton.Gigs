import os
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

spec = importlib.util.spec_from_file_location('runner', Path(__file__).resolve().parents[1] / 'Venues/Orchastrators/run_all_scrapers.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VenueHealthTests(unittest.TestCase):
    def test_csv_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'venue.csv'
            with self.assertRaises(FileNotFoundError): runner.validate_output(path)
            for text in ['date,event_name,cost\n', 'wrong,columns\n1,2\n', 'date,event_name,cost\n,,10\n']:
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError): runner.validate_output(path)
            path.write_text('date,event_name,cost\n26/10/2026,Band,Unknown\n', encoding='utf-8')
            self.assertEqual(runner.validate_output(path), 1)

    def test_runner_checks_every_venue_and_rejects_stale_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); venues = root / 'Venues'; scripts = venues / 'scrapeFiles'
            scripts.mkdir(parents=True); (venues / 'csvs').mkdir()
            for name in ['Empty', 'Good', 'Stale', 'Crash']: (scripts / f'{name}.py').touch()
            from datetime import date, timedelta
            stale = venues / 'csvs' / runner.build_output_name(scripts / 'Stale.py', date.today(), date.today()+timedelta(days=7))
            stale.write_text('date,event_name,cost\n26/10/2026,Old band,10\n')
            def fake_run(cmd, **kwargs):
                name = Path(cmd[1]).stem
                output = venues / 'csvs' / cmd[-1]
                if name in ['Good', 'Empty']:
                    output.write_text('date,event_name,cost\n' + ('26/10/2026,Band,10\n' if name == 'Good' else ''))
                return subprocess.CompletedProcess(cmd, 1 if name == 'Crash' else 0, '', '')
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false', 'GITHUB_STEP_SUMMARY': ''}), patch.object(runner, 'SCRAPE_DIR', scripts), patch.object(runner, 'VENUES_DIR', venues), patch.object(runner.subprocess, 'run', side_effect=fake_run) as run:
                with self.assertRaises(RuntimeError) as error: runner.main()
            self.assertEqual(run.call_count, 4)
            for name in ['Empty', 'Stale', 'Crash']: self.assertIn(name, str(error.exception))
            self.assertIn('Good | 1 gigs', (root / 'scraper_health.md').read_text())


if __name__ == '__main__': unittest.main()
