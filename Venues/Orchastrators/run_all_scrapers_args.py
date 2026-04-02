from __future__ import annotations

import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime, date


SCRAPE_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\Venues\scrapeFiles")


def build_output_name(script_path: Path, start_date: date, end_date: date) -> str:
    base_name = script_path.stem

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    return f"{base_name}_{start_str}_to_{end_str}.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Run all scrapers with a date range")

    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)

    if start_date > end_date:
        print("Start date must be before or equal to end date")
        sys.exit(1)

    if not SCRAPE_DIR.exists():
        print(f"Scrape directory does not exist: {SCRAPE_DIR}")
        sys.exit(1)

    start_str = start_date.isoformat()
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
        out_name = build_output_name(script_path, start_date, end_date)

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