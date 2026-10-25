from __future__ import annotations

import json
import csv
import os
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


def validate_output(path: Path) -> int:
    """Reject missing, malformed, or empty output from this run."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"date", "event_name", "cost"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")
        rows = list(reader)
    if not rows:
        raise ValueError("No gigs returned; check the venue website for changes or a quiet week")
    if any(not row.get("date", "").strip() or not row.get("event_name", "").strip() for row in rows):
        raise ValueError("CSV contains gigs without a date or event name")
    return len(rows)


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
        raise RuntimeError("No venue scraper scripts found")

    print(f"Found {len(py_files)} scraper file(s)")
    print(f"Start date: {start_str}")
    print(f"End date:   {end_str}")
    print("-" * 50)

    failures = []
    successful_files = []
    summary = ["## Venue scraper results", f"Date range: {start_str} to {end_str}", "", "| Venue | Result |", "| --- | --- |"]

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
            output_path = VENUES_DIR / "csvs" / out_name
            # An old CSV must never conceal a scraper that failed to write output.
            output_path.unlink(missing_ok=True)
            result = subprocess.run(
                cmd,
                cwd=str(SCRAPE_DIR),
                capture_output=True,
                text=True,
                check=False,
                timeout=900,
            )

            if result.stdout:
                print("STDOUT:")
                print(result.stdout.strip())

            if result.stderr:
                print("STDERR:")
                print(result.stderr.strip())

            if result.returncode != 0:
                raise RuntimeError(f"Scraper exited with code {result.returncode}; see logs above")
            count = validate_output(output_path)
            successful_files.append(out_name)
            print(f"Finished successfully: {script_path.name}: {count} gigs")
            summary.append(f"| {script_path.stem} | {count} gigs |")

        except Exception as e:
            message = f"{script_path.stem}: {e}"
            failures.append(message)
            print(f"WARNING: {message}")
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::warning file=Venues/scrapeFiles/{script_path.name}::{message}")
            summary.append(f"| {script_path.stem} | FAILED: {e} |")

        print("-" * 50)

    report = "\n".join(summary) + "\n"
    (VENUES_DIR.parent / "scraper_health.md").write_text(report, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(report)
    (VENUES_DIR.parent / "scraper_health.json").write_text(
        json.dumps({"failures": failures, "successful_files": successful_files}), encoding="utf-8")
    if not successful_files:
        raise RuntimeError("No venues returned usable gigs:\n" + "\n".join(failures))
    if failures:
        print("Continuing with successful venues; failed venues will be omitted.")


if __name__ == "__main__":
    main()