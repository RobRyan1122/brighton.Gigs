import time
import argparse
from urllib.parse import urljoin
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path


START_URL = "https://thegreendoorstore.co.uk/events/?event-type=gig&mon=&yr="


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def _clean_text(s: str) -> str:
    """Normalises whitespace in extracted text."""
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str) -> pd.Timestamp:
    """
    Converts the site's date string (e.g. 'Sun, 1 Mar 2026') into a pandas Timestamp.

    If parsing fails, returns NaT (so you can drop/handle it safely later).
    """
    try:
        # Example site format: "Sun, 1 Mar 2026"
        return pd.to_datetime(date_str, format="%a, %d %b %Y", errors="raise")
    except ValueError:
        # Some sites sometimes omit leading zero or vary spacing; fallback to pandas parser.
        return pd.to_datetime(date_str, errors="coerce")


def parse_events_from_html(html: str) -> list[dict]:
    """
    Extracts event data from a single page of HTML.

    Returns a list of dicts with:
      - date (raw string)
      - event_name
      - cost
    """
    soup = BeautifulSoup(html, "html.parser")
    events = []

    for card in soup.select("article.event-card"):
        title_el = card.select_one("h3.event-card__title")
        date_el = card.select_one("span.event-card__date")
        price_el = card.select_one(".event-card__price span")

        if not title_el or not date_el or not price_el:
            continue

        events.append(
            {
                "date": _clean_text(date_el.get_text(" ", strip=True)),
                "event_name": _clean_text(title_el.get_text(" ", strip=True)),
                "cost": _clean_text(price_el.get_text(" ", strip=True)),
            }
        )

    return events


def get_next_page_url(html: str, current_url: str) -> str | None:
    """Finds the next page URL from pagination, or returns None if there isn't one."""
    soup = BeautifulSoup(html, "html.parser")

    next_link = soup.select_one(".events-pagination a[title='Next page']")
    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    next_link = soup.select_one(".events-pagination .pagination__item--next a")
    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    return None


def scrape_all_gig_events(start_url: str = START_URL, polite_delay_s: float = 0.5) -> pd.DataFrame:
    """
    Scrapes all pages of gig events and returns a DataFrame with columns:
      - date (raw string from site)
      - event_name
      - cost
      - event_date (parsed datetime)
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )

    all_events: list[dict] = []
    seen_urls: set[str] = set()
    url = start_url

    while url and url not in seen_urls:
        seen_urls.add(url)

        resp = session.get(url, timeout=20)
        resp.raise_for_status()

        html = resp.text
        all_events.extend(parse_events_from_html(html))

        url = get_next_page_url(html, current_url=url)
        if url:
            time.sleep(polite_delay_s)

    df = pd.DataFrame(all_events, columns=["date", "event_name", "cost"]).drop_duplicates()

    # Add a parsed datetime column (keeps original 'date' string too)
    df["event_date"] = df["date"].apply(_parse_event_date)

    return df


def filter_events_by_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """
    Drops any events not within [start, end] inclusive.

    Assumes df contains an 'event_date' column (datetime-like).
    - Rows with unparseable dates (NaT) are dropped.
    """
    # Ensure we have the parsed date column
    if "event_date" not in df.columns:
        raise ValueError("DataFrame must contain an 'event_date' column. Call scrape_all_gig_events() first.")

    # Drop rows with invalid dates
    df = df.dropna(subset=["event_date"]).copy()

    # Convert to date-only for inclusive filtering
    event_dates = df["event_date"].dt.date

    # Keep only rows where event_date is within range (inclusive)
    mask = (event_dates >= start) & (event_dates <= end)
    return df.loc[mask].reset_index(drop=True)


def _parse_cli_date(s: str) -> date:
    """Parses CLI date in YYYY-MM-DD format into a datetime.date."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    """
    Entry point:
    - Accepts --start and --end
    - Scrapes events
    - Filters by date range
    - Prints and saves CSV
    """
    parser = argparse.ArgumentParser(description="Scrape Green Door Store gig listings into a CSV.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--out", default="greendoor_gigs.csv", help="Output CSV filename.")
    args = parser.parse_args()

    start_date = _parse_cli_date(args.start)
    end_date = _parse_cli_date(args.end)

    if end_date < start_date:
        raise ValueError("End date must be on/after start date.")

    df = scrape_all_gig_events()
    df_filtered = filter_events_by_date_range(df, start_date, end_date)

    # Optional: drop the helper parsed column before saving (or keep it)
    # Keeping it is often useful, so I'll keep it by default.
    print(df_filtered)
    print(f"\nTotal events in range [{start_date} .. {end_date}]: {len(df_filtered)}")

    output_path = OUTPUT_DIR / args.out
    df_filtered.to_csv(output_path, index=False, encoding="utf-8")

    print(f"Saved: {output_path}")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()