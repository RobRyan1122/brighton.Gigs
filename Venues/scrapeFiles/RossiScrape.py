import time
import argparse
from dataclasses import dataclass
from datetime import datetime, date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://therossibar.co.uk"
BASE_EVENTS_URL = "https://therossibar.co.uk/events/"


# ----------------------------
# Helpers
# ----------------------------

def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_gds_style_date(date_str: str) -> pd.Timestamp:
    """
    Rossi uses the same date format you showed:
      "Wed, 4 Mar 2026"
    """
    # Strict parse first, then fallback
    ts = pd.to_datetime(date_str, format="%a, %d %b %Y", errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(date_str, errors="coerce")
    return ts


def _month_year_iter(start: date, end: date) -> list[tuple[int, int]]:
    """
    Return a list of (year, month) tuples covering the range, inclusive.
    Example: 2026-03-01 .. 2026-04-10 -> [(2026,3), (2026,4)]
    """
    months = []
    y, m = start.year, start.month

    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        # increment month
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1

    return months


def _build_month_url(year: int, month: int) -> str:
    """
    Build the Rossi monthly listing URL:
      https://therossibar.co.uk/events/?mon=03&yr=2026
    """
    return f"{BASE_EVENTS_URL}?mon={month:02d}&yr={year}"


# ----------------------------
# HTML parsing
# ----------------------------

def parse_events_from_html(html: str) -> list[dict]:
    """
    Extract events from a single Rossi listing page.
    Pulls:
      - date (string)
      - event_name
      - cost
      - event_url
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    for card in soup.select("article.event-card"):
        title_el = card.select_one("h3.event-card__title")
        date_el = card.select_one("span.event-card__date")
        price_el = card.select_one(".event-card__price span")
        link_el = card.select_one("a.event-card__link")

        if not title_el or not date_el or not price_el:
            continue

        event_url = link_el.get("href").strip() if link_el and link_el.get("href") else None
        if event_url:
            event_url = urljoin(BASE_URL, event_url)

        events.append(
            {
                "date": _clean_text(date_el.get_text(" ", strip=True)),
                "event_name": _clean_text(title_el.get_text(" ", strip=True)),
                "cost": _clean_text(price_el.get_text(" ", strip=True)),
                "event_url": event_url,
            }
        )

    return events


def get_next_page_url(html: str, current_url: str) -> str | None:
    """
    Get the 'Next page' URL from Rossi pagination.
    """
    soup = BeautifulSoup(html, "html.parser")

    next_link = soup.select_one(".events-pagination a[title='Next page']")
    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    next_link = soup.select_one(".events-pagination .pagination__item--next a")
    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    return None


# ----------------------------
# Scraping logic
# ----------------------------

def scrape_month(session: requests.Session, year: int, month: int, polite_delay_s: float = 0.3) -> pd.DataFrame:
    """
    Scrape all pages for a specific year+month (Rossi's URL is month-scoped).
    """
    url = _build_month_url(year, month)
    seen: set[str] = set()
    rows: list[dict] = []

    while url and url not in seen:
        seen.add(url)

        resp = session.get(url, timeout=20)
        resp.raise_for_status()

        html = resp.text
        rows.extend(parse_events_from_html(html))

        url = get_next_page_url(html, current_url=url)
        if url:
            time.sleep(polite_delay_s)

    df = pd.DataFrame(rows, columns=["date", "event_name", "cost", "event_url"]).drop_duplicates()
    if df.empty:
        return df

    df["event_date"] = df["date"].apply(_parse_gds_style_date)
    return df


def filter_events_by_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """
    Keep only events within [start, end] inclusive.
    Drops rows where date couldn't be parsed.
    """
    if df.empty:
        return df

    df = df.dropna(subset=["event_date"]).copy()
    d = df["event_date"].dt.date
    return df.loc[(d >= start) & (d <= end)].reset_index(drop=True)


def scrape_rossi_in_range(start: date, end: date, polite_delay_s: float = 0.3) -> pd.DataFrame:
    """
    Scrape Rossi events across all months spanned by the date range.
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

    dfs: list[pd.DataFrame] = []

    for (y, m) in _month_year_iter(start, end):
        df_month = scrape_month(session, y, m, polite_delay_s=polite_delay_s)
        if not df_month.empty:
            dfs.append(df_month)

    if not dfs:
        return pd.DataFrame(columns=["date", "event_name", "cost", "event_url", "event_date"])

    df_all = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["date", "event_name", "event_url"])
    df_all = filter_events_by_date_range(df_all, start, end)
    return df_all


# ----------------------------
# Optional: Standard plugin entrypoint for your run_all runner
# ----------------------------

def scrape(start: date, end: date) -> pd.DataFrame:
    """
    Standardised entrypoint (so your run_all.py can import this and call scrape()).
    Returns the core columns plus venue.
    """
    df = scrape_rossi_in_range(start, end)
    df = df.copy()
    df["venue"] = "Rossi Bar"
    return df[["date", "event_name", "cost", "venue", "event_url"]]


# ----------------------------
# CLI
# ----------------------------

def _parse_cli_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Scrape Rossi Bar events for a date range.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--out", default="rossi_events.csv", help="Output CSV filename.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between requests (seconds).")
    args = parser.parse_args()

    start = _parse_cli_date(args.start)
    end = _parse_cli_date(args.end)
    if end < start:
        raise ValueError("End date must be on/after start date.")

    df = scrape_rossi_in_range(start, end, polite_delay_s=args.delay)

    # Save with the same 3 columns you’ve been using
    out_df = df[["date", "event_name", "cost"]].copy()
    output_path = OUTPUT_DIR / args.out
    out_df.to_csv(output_path, index=False, encoding="utf-8")

    print(out_df)
    print(f"\nSaved: {output_path}")
    print(f"Total events: {len(out_df)}")


if __name__ == "__main__":
    main()