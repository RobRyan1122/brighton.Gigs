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

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_URL = "https://dustvenue.com/live"


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str) -> pd.Timestamp:
    """
    Dust detail page date format: 01-04-26
    """
    if not isinstance(date_str, str) or not date_str.strip():
        return pd.NaT

    raw = _clean_text(date_str)

    try:
        return pd.to_datetime(raw, format="%d-%m-%y", errors="raise")
    except ValueError:
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
    soup = BeautifulSoup(html, "html.parser")
    event_urls = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = _clean_text(a.get_text(" ", strip=True)).lower()

        if "tell me more" not in text:
            continue

        if not href.startswith("/live/"):
            continue

        full_url = urljoin(START_URL, href)

        if full_url not in seen:
            seen.add(full_url)
            event_urls.append(full_url)

    return event_urls


def parse_event_detail_html(html: str, event_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    name_el = soup.select_one("h1.mb-1.text-5xl.text-dustWhite.font-pwDusty")
    if name_el:
        event_name = _clean_text(name_el.get_text(" ", strip=True))
    else:
        h1 = soup.find("h1")
        event_name = _clean_text(h1.get_text(" ", strip=True)) if h1 else ""

    date_value = ""
    cost_value = "Unknown"

    h4s = soup.select("h4.pt-1.font-chalkDust.z-20")
    if not h4s:
        h4s = soup.find_all("h4")

    date_re = re.compile(r"^\d{2}-\d{2}-\d{2}$")
    cost_re = re.compile(r"^(?:£\s*)?\d+(?:\.\d{1,2})?\s*(adv|door)$", flags=re.IGNORECASE)

    for h4 in h4s:
        text = _clean_text(h4.get_text(" ", strip=True))

        if not date_value and date_re.fullmatch(text):
            date_value = text
            continue

        if cost_value == "Unknown" and cost_re.fullmatch(text):
            cost_value = text
            continue

    full_text = _clean_text(soup.get_text(" ", strip=True))

    if not date_value:
        m = re.search(r"\b\d{2}-\d{2}-\d{2}\b", full_text)
        if m:
            date_value = m.group(0)

    if cost_value == "Unknown":
        m = re.search(r"(?<![\d.])(?:£\s*)?\d+(?:\.\d{1,2})?\s*(adv|door)\b", full_text, flags=re.IGNORECASE)
        if m:
            cost_value = m.group(0)

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
    parser = argparse.ArgumentParser(description="Scrape Dust live listings into a CSV.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD), inclusive.")
    parser.add_argument("--out", default="dust_gigs.csv", help="Output CSV filename.")
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