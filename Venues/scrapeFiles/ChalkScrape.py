import time
import argparse
import re
from urllib.parse import urljoin
from datetime import datetime, date

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from pathlib import Path

OUTPUT_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\Venues\csvs")
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
        "%d-%m-%y",
        "%d/%m/%y",
        "%d/%m/%Y",
        "%Y-%m-%d",
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


def make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2200")
    return webdriver.Chrome(options=options)


def get_rendered_html(driver: webdriver.Chrome, url: str, wait_s: float = 3.0) -> str:
    driver.get(url)
    time.sleep(wait_s)
    return driver.page_source


def parse_listing_for_event_urls(html: str) -> list[str]:
    """
    Extract Chalk event URLs directly from the clickable anchor:
    <a class="col-span-2 text-center" href="...">
        <h2>Event Name</h2>
    </a>
    """
    soup = BeautifulSoup(html, "html.parser")
    event_urls = []
    seen = set()

    for a in soup.select("a.col-span-2.text-center[href]"):
        href = a.get("href", "").strip()

        if not href:
            continue

        if "/live/" not in href:
            continue

        # extract name (just for debug visibility)
        h2 = a.find("h2")
        title = _clean_text(h2.get_text(" ", strip=True)) if h2 else "UNKNOWN"

        if href not in seen:
            seen.add(href)
            event_urls.append(href)

            print(f"FOUND EVENT: {title} -> {href}")

    return event_urls


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
            date_value = parsed.strftime("%Y-%m-%d")
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

    event_name = extract_name_from_detail_page(soup)
    date_value, cost_value = extract_date_and_price_from_detail_page(soup)

    if not event_name and not date_value and cost_value == "Unknown":
        return None

    return {
        "date": date_value,
        "event_name": event_name,
        "cost": cost_value,
        "event_url": event_url,
    }


def scrape_all_gig_events(start: date, end: date, polite_delay_s: float = 1.0) -> pd.DataFrame:
    driver = make_driver()

    try:
        listing_html = get_rendered_html(driver, START_URL, wait_s=5)
        event_urls = parse_listing_for_event_urls(listing_html)

        print("EVENT URLS FOUND:", len(event_urls))
        for url in event_urls[:10]:
            print(url)

        rows = []

        for event_url in event_urls:
            try:
                detail_html = get_rendered_html(driver, event_url, wait_s=2.5)
                row = parse_event_detail_html(detail_html, event_url)

                if not row:
                    print("SKIPPING (no row):", event_url)
                    time.sleep(polite_delay_s)
                    continue

                event_date = _parse_event_date(row["date"])

                if pd.isna(event_date):
                    print("SKIPPING (bad date):", event_url, row["date"])
                    time.sleep(polite_delay_s)
                    continue

                event_day = event_date.date()

                if event_day < start:
                    print("BEFORE RANGE:", event_url, row["date"])
                    time.sleep(polite_delay_s)
                    continue

                if event_day > end:
                    print("OUT OF RANGE:", event_url, row["date"])
                    print("Reached first event after end date, stopping scrape.")
                    break

                row["event_date"] = event_date
                rows.append(row)
                print("KEEPING:", event_url, row)

                time.sleep(polite_delay_s)

            except Exception as e:
                print(f"FAILED: {event_url} -> {e}")
                continue

    finally:
        driver.quit()

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