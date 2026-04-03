from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from datetime import date, timedelta




SCRIPT_DIR = Path(__file__).resolve().parent
VENUES_DIR = SCRIPT_DIR.parent
SCRAPE_DIR = VENUES_DIR / "scrapeFiles"

def build_output_name(script_path: Path, start_date: date, end_date: date) -> str:
    """
    Create output CSV name based on the scrape file name and date range.
    Example:
        AlphabetScrape.py -> AlphabetScrape_2026-04-01_to_2026-04-07.csv
    """
    base_name = script_path.stem

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    return f"{base_name}_{start_str}_to_{end_str}.csv"


def main() -> None:
    if not SCRAPE_DIR.exists():
        print(f"Scrape directory does not exist: {SCRAPE_DIR}")
        sys.exit(1)

    today = date.today()
    end_date = today + timedelta(days=7)

    start_str = today.isoformat()
    end_str = end_date.isoformat()

    py_files = sorted(SCRAPE_DIR.glob("*.py"))

    if not py_files:
        print(f"No .py files found in: {SCRAPE_DIR}")
        return

    print(f"Found {len(py_files)} scraper file(s)")
    print(f"Start date: {start_str}")
    print(f"End date:   {end_str}")
    print("-" * 50)

    for script_path in py_files:
        out_name = build_output_name(script_path, today, end_date)

        cmd = [
            sys.executable,
            str(script_path),
            "--start",
            start_str,
            "--end",
            end_str,
            "--out",
            out_name,
        ]

        print(f"Running: {script_path.name}")
        print(f"Output:  {out_name}")
        print("Command:", " ".join(f'"{c}"' if " " in c else c for c in cmd))

        try:
            result = subprocess.run(
                cmd,
                cwd=str(SCRAPE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.stdout:
                print("STDOUT:")
                print(result.stdout.strip())

            if result.stderr:
                print("STDERR:")
                print(result.stderr.strip())

            if result.returncode == 0:
                print(f"Finished successfully: {script_path.name}")
            else:
                print(f"Failed with return code {result.returncode}: {script_path.name}")

        except Exception as e:
            print(f"Error running {script_path.name}: {e}")

        print("-" * 50)


if __name__ == "__main__":
    main()