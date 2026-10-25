import time
import argparse
import json
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime, date

import pandas as pd
from bs4 import BeautifulSoup
import requests

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


START_URL = "https://chalkvenue.com/live"


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str) -> pd.Timestamp:
    """
    Try a few common venue date formats.
    """
    if not isinstance(date_str, str) or not date_str.strip():
        return pd.NaT

    raw = _clean_text(date_str)

    for fmt in [
        "%d/%m/%y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%y",
        "%a %d %b %Y",
        "%A %d %B %Y",
        "%d %b %Y",
        "%d %B %Y",
        ]:
        try:
            return pd.to_datetime(raw, format=fmt, errors="raise")
        except ValueError:
            pass

    return pd.to_datetime(raw, errors="coerce", dayfirst=True)


def _page_data(soup: BeautifulSoup) -> dict:
    """Read the public Inertia page data embedded in Chalk's HTML."""
    for script in soup.select('script[type="application/json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("props"), dict):
            return data["props"]
    return {}


def _event_schema(soup: BeautifulSoup) -> dict:
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "Event" in types or "MusicEvent" in types:
                yield value
            yield from walk(value.get("@graph", []))

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            event = next(walk(json.loads(script.string or script.get_text())), None)
        except (ValueError, TypeError):
            continue
        if event:
            return event
    return {}


def parse_listing_for_event_urls(html: str) -> list[str]:
    """Accept current /event/ links and the previous /live/ layout."""
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for anchor in soup.select("a[href]"):
        url = urljoin(START_URL, anchor["href"])
        parsed = urlparse(url)
        if parsed.netloc == urlparse(START_URL).netloc and re.match(
            r"^/(?:event|live)/[^/]+/?$", parsed.path
        ) and url not in urls:
            urls.append(url)
    return urls


def extract_name_from_detail_page(soup: BeautifulSoup) -> str:
    """
    Try common title selectors first, then fallback to first h1/h2.
    """
    selectors = [
        "h1",
        "main h1",
        "article h1",
        "section h1",
        "h2",
        "main h2",
    ]

    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = _clean_text(el.get_text(" ", strip=True))
            if text:
                return text

    return ""


def extract_date_and_price_from_detail_page(soup: BeautifulSoup) -> tuple[str, str]:
    date_value = ""
    cost_value = "Unknown"

    # -------------------------
    # 1. DATE (from <time>)
    # -------------------------
    time_el = soup.find("time")

    if time_el and time_el.has_attr("datetime"):
        raw_dt = time_el["datetime"]

        try:
            parsed = pd.to_datetime(raw_dt)
            date_value = parsed.strftime("%d/%m/%Y")
        except Exception:
            date_value = raw_dt

    # -------------------------
    # 2. PRICE
    # -------------------------
    full_text = _clean_text(soup.get_text(" ", strip=True))

    # Prefer amounts that are explicitly ticket prices, e.g.:
    # £35 adv
    # 35 adv
    # £27.50 door
    # 27.50 door
    m = re.search(
        r"(£\s?\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?)\s*(adv|door)\b",
        full_text,
        flags=re.IGNORECASE,
    )
    if m:
        amount = m.group(1).replace("£ ", "£").strip()
        label = m.group(2).lower()
        cost_value = f"{amount} {label}"
    else:
        # Fallback: plain £ price not tied to adv/door
        m = re.search(r"£\s?\d+(?:\.\d{1,2})?\b", full_text)
        if m:
            cost_value = m.group(0).replace("£ ", "£").strip()

    return date_value, cost_value


def parse_event_detail_html(html: str, event_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    event = _page_data(soup).get("event") or {}
    schema = _event_schema(soup)
    if event.get("cancelled") or str(schema.get("eventStatus", "")).endswith("EventCancelled"):
        return None

    event_name = event.get("name") or schema.get("name") or extract_name_from_detail_page(soup)
    date_value, cost_value = extract_date_and_price_from_detail_page(soup)
    raw_date = schema.get("startDate") or event.get("starts_at")
    if raw_date:
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if not pd.isna(parsed):
            if parsed.tzinfo is not None:
                parsed = parsed.tz_convert("Europe/London")
            date_value = parsed.strftime("%d/%m/%Y")
    price = event.get("price_description")
    if price:
        cost_value = _clean_text(str(price))
    elif cost_value == "Unknown":
        offers = schema.get("offers") or []
        if isinstance(offers, dict):
            offers = [offers]
        for offer in offers:
            price = offer.get("price")
            if price is not None and offer.get("priceCurrency") == "GBP":
                cost_value = f"\u00a3{price}"
                break

    if not event_name and not date_value and cost_value == "Unknown":
        return None

    return {
        "date": date_value,
        "event_name": event_name,
        "cost": cost_value,
        "event_url": event_url,
    }


def scrape_all_gig_events(start: date, end: date, polite_delay_s: float = 1.0) -> pd.DataFrame:
    rows = []
    with requests.Session() as session:
        def fetch(url):
            response = session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text

        listing_url = START_URL
        seen_pages = set()
        seen_events = set()
        while listing_url and listing_url not in seen_pages:
            seen_pages.add(listing_url)
            listing_html = fetch(listing_url)
            event_urls = parse_listing_for_event_urls(listing_html)
            if not event_urls:
                raise RuntimeError(f"No Chalk event links found on {listing_url}; listing layout may have changed.")
            props = _page_data(BeautifulSoup(listing_html, "html.parser"))
            listing_events = list(props.get("thisWeekEvents") or [])
            listing_events += (props.get("events") or {}).get("data", [])
            event_metadata = {item.get("link"): item for item in listing_events}
            for event_url in event_urls:
                if event_url in seen_events:
                    continue
                seen_events.add(event_url)
                metadata = event_metadata.get(event_url, {})
                if metadata.get("cancelled"):
                    continue
                listed_date = pd.to_datetime(metadata.get("starts_at"), errors="coerce", utc=True)
                if not pd.isna(listed_date):
                    listed_day = listed_date.tz_convert("Europe/London").date()
                    if not start <= listed_day <= end:
                        continue
                row = parse_event_detail_html(fetch(event_url), event_url)
                time.sleep(polite_delay_s)
                if row is None:
                    continue
                event_date = _parse_event_date(row["date"])
                if pd.isna(event_date):
                    raise RuntimeError(f"No valid Chalk event date found: {event_url}")
                if start <= event_date.date() <= end:
                    row["event_date"] = event_date
                    rows.append(row)
                    print("KEEPING:", event_url, row)

            next_url = (props.get("events") or {}).get("next_page_url")
            listing_url = urljoin(START_URL, next_url) if next_url else None
            if listing_url and urlparse(listing_url).netloc != urlparse(START_URL).netloc:
                raise RuntimeError(f"Unexpected Chalk pagination URL: {listing_url}")
            time.sleep(polite_delay_s)

    df = pd.DataFrame(
        rows,
        columns=["date", "event_name", "cost", "event_url", "event_date"]
    ).drop_duplicates()

    if df.empty:
        return pd.DataFrame(columns=["date", "event_name", "cost", "event_url", "event_date"])

    print("\nFILTERED SCRAPED DATA:")
    print(df[["date", "event_name", "cost", "event_date"]].head(20))

    return df.reset_index(drop=True)




def _parse_cli_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Scrape Chalk live listings into a CSV.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--out", default="chalk_gigs.csv", help="Output CSV filename.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds).")
    args = parser.parse_args()

    start_date = _parse_cli_date(args.start)
    end_date = _parse_cli_date(args.end)

    if end_date < start_date:
        raise ValueError("End date must be on/after start date.")

    df_filtered = scrape_all_gig_events(start=start_date, end=end_date, polite_delay_s=args.delay)

    output_df = df_filtered[["date", "event_name", "cost"]].copy()

    print("\nFINAL OUTPUT:")
    print(output_df)
    print(f"\nTotal events in range [{start_date} .. {end_date}]: {len(output_df)}")

    output_path = OUTPUT_DIR / args.out
    output_df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()