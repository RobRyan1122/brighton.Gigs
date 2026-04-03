import time
import argparse
import re
from urllib.parse import urljoin
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup
import pandas as pd

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


START_URL = "https://www.hope.pub/events/"


# ----------------------------
# Small utilities
# ----------------------------

def _clean_text(s: str) -> str:
    """Collapse repeated whitespace/newlines to a single space."""
    return " ".join(s.split()).strip()


# ----------------------------
# Date parsing for Hope
# Example: "Tue 3rd Mar at 7:30 pm"
# ----------------------------

_ORDINAL_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)", flags=re.IGNORECASE)

def _infer_year(month: int, today: date) -> int:
    """
    Hope listing dates do not include a year.
    We infer:
      - same year if month >= current month
      - next year if month < current month (handles Dec->Jan rollover)
    """
    return today.year if month >= today.month else today.year + 1


def _parse_hope_date(date_str: str, today: date | None = None) -> pd.Timestamp:
    """
    Convert Hope date string like "Tue 3rd Mar at 7:30 pm" into a pandas Timestamp.

    We parse day + month, infer year, and ignore time.
    Returns NaT if parsing fails.
    """
    if today is None:
        today = date.today()

    try:
        s = _clean_text(date_str)

        # Remove ordinal suffixes: 3rd -> 3, 21st -> 21, etc.
        s = _ORDINAL_RE.sub(r"\1", s)

        # Keep only the start date if a range is shown
        # e.g. "Tue 3rd Mar at 7:30 pm – Tue 3rd Mar at 11:00 pm"
        s = s.split("–")[0].strip()

        # Remove time portion: "Tue 3 Mar at 7:30 pm" -> "Tue 3 Mar"
        s = s.split(" at ")[0].strip()

        # Expected tokens now: ["Tue", "3", "Mar"]
        parts = s.split()
        if len(parts) < 3:
            return pd.NaT

        day = int(parts[1])
        mon_str = parts[2][:3]  # take "Mar" from "March" safely
        month = datetime.strptime(mon_str, "%b").month

        year = _infer_year(month, today)
        return pd.Timestamp(datetime(year, month, day))
    except Exception:
        return pd.NaT


# ----------------------------
# Scrape listing page for events
# ----------------------------

def parse_events_from_listing_html(html: str) -> list[dict]:
    """
    Parse /events/ listing HTML and return a list of dicts:
      - date (raw string)
      - event_name
      - event_url (absolute)
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    # Each card represents an event in the list view
    for card in soup.select(".events-list-alternate__card"):
        date_el = card.select_one(".meta--date")
        title_el = card.select_one("h3.card__heading a.heading-link")

        if not date_el or not title_el:
            continue

        raw_date = _clean_text(date_el.get_text(" ", strip=True))
        event_name = _clean_text(title_el.get_text(" ", strip=True))
        event_url = title_el.get("href")

        if event_url:
            event_url = urljoin(START_URL, event_url)

        events.append(
            {
                "date": raw_date,
                "event_name": event_name,
                "event_url": event_url,
            }
        )

    return events


def scrape_hope_listing(session: requests.Session, start_url: str = START_URL, polite_delay_s: float = 0.3) -> pd.DataFrame:
    """
    Scrape all listing pages (if pagination exists) and return a DataFrame with:
      - date, event_name, event_url, event_date
    """
    all_events: list[dict] = []
    seen_urls: set[str] = set()
    url = start_url

    while url and url not in seen_urls:
        seen_urls.add(url)

        resp = session.get(url, timeout=20)
        resp.raise_for_status()

        all_events.extend(parse_events_from_listing_html(resp.text))

        # Hope currently tends not to paginate, but this is defensive
        soup = BeautifulSoup(resp.text, "html.parser")
        next_link = soup.select_one("a[rel='next']")
        url = urljoin(url, next_link["href"]) if next_link and next_link.get("href") else None

        if url:
            time.sleep(polite_delay_s)

    df = pd.DataFrame(all_events, columns=["date", "event_name", "event_url"]).drop_duplicates()

    # Add parsed date column for filtering
    today = date.today()
    df["event_date"] = df["date"].apply(lambda s: _parse_hope_date(s, today=today))

    return df


# ----------------------------
# Date-range filter
# ----------------------------

def filter_events_by_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Keep only events within [start, end] inclusive. Drops unparseable dates."""
    df = df.dropna(subset=["event_date"]).copy()
    d = df["event_date"].dt.date
    return df.loc[(d >= start) & (d <= end)].reset_index(drop=True)


# ----------------------------
# Price scraping (event page -> fatsoma page)
# ----------------------------

_PRICE_RE = re.compile(r"£\s?\d+(?:\.\d{2})?(?:\s*\+)?", flags=re.IGNORECASE)

def extract_ticket_url_from_event_page(html: str) -> str | None:
    """
    From a Hope event page, extract the main outbound ticket URL.
    In your HTML, this is:
      <a class="event-single__heading-link" href="https://www.fatsoma.com/e/...">
    """
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("a.event-single__heading-link")
    if a and a.get("href"):
        return a["href"].strip()
    return None


def extract_price_from_fatsoma_html(html: str) -> str | None:
    """
    Try to find a ticket price on a Fatsoma event page.
    This is heuristic but usually works because prices appear in either:
      - JSON-LD
      - visible text near ticket options
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) Look in JSON-LD blocks (often include price/currency)
    for script in soup.select("script[type='application/ld+json']"):
        txt = script.get_text(" ", strip=True)
        m = _PRICE_RE.search(txt)
        if m:
            return _clean_text(m.group(0))

    # 2) Fallback: search full page text for £...
    txt = soup.get_text(" ", strip=True)
    m = _PRICE_RE.search(txt)
    if m:
        return _clean_text(m.group(0))

    return None


def enrich_costs_for_filtered_events(
    df: pd.DataFrame,
    session: requests.Session,
    polite_delay_s: float = 0.25
) -> pd.DataFrame:
    """
    For each row in df (already date-filtered), visit the Hope event page,
    extract the ticket URL (Fatsoma), then fetch that and extract price.

    Adds/sets:
      - ticket_url
      - cost
    """
    df = df.copy()
    df["ticket_url"] = None
    df["cost"] = "Unknown"

    for i, row in df.iterrows():
        event_url = row.get("event_url")
        if not event_url:
            continue

        # --- Fetch Hope event page ---
        try:
            resp = session.get(event_url, timeout=20)
            resp.raise_for_status()
        except Exception:
            continue

        ticket_url = extract_ticket_url_from_event_page(resp.text)
        df.at[i, "ticket_url"] = ticket_url

        # If there's no ticket URL, we can't fetch a price reliably
        if not ticket_url:
            continue

        time.sleep(polite_delay_s)

        # --- Fetch ticket provider page (Fatsoma) ---
        try:
            resp2 = session.get(ticket_url, timeout=20)
            resp2.raise_for_status()
        except Exception:
            continue

        price = extract_price_from_fatsoma_html(resp2.text)
        if price:
            df.at[i, "cost"] = price

        time.sleep(polite_delay_s)

    return df


# ----------------------------
# CLI / main
# ----------------------------

def _parse_cli_date(s: str) -> date:
    """Parse YYYY-MM-DD to datetime.date."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Scrape Hope & Ruin events within a date range (and fetch ticket prices).")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--out", default="hope_events.csv", help="Output CSV filename.")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between requests (seconds).")
    args = parser.parse_args()

    start_date = _parse_cli_date(args.start)
    end_date = _parse_cli_date(args.end)
    if end_date < start_date:
        raise ValueError("End date must be on/after start date.")

    # Create one session for all requests (cookies + keep-alive)
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

    # 1) Scrape listing once
    df = scrape_hope_listing(session=session)

    # 2) Filter by date range (so we don't hit every event page)
    df = filter_events_by_date_range(df, start_date, end_date)

    # 3) Only now, enrich prices for the filtered set
    df = enrich_costs_for_filtered_events(df, session=session, polite_delay_s=args.delay)

    # 4) Keep the columns you asked for (plus you can keep extra if you want)
    output_df = df[["date", "event_name", "cost"]].copy()

    print(output_df)
    print(f"\nTotal events in range [{start_date} .. {end_date}]: {len(output_df)}")

    output_path = OUTPUT_DIR / args.out
    output_df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()