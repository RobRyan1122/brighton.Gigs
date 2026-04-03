import time
import argparse
import re
from urllib.parse import urljoin
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


START_URL = "https://www.alphabetbrighton.com/listings"

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------
# UTILS
# -------------------------
def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str) -> pd.Timestamp:
    if not date_str:
        return pd.NaT

    raw = _clean_text(date_str)

    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return pd.to_datetime(f"{raw} 2026", format=fmt, errors="raise")
        except Exception:
            pass

    return pd.to_datetime(raw, errors="coerce", dayfirst=True)


def _parse_listing_date(listing_text: str) -> pd.Timestamp:
    """
    Parse dates from listing text like:
    'APR 30: SISTER RAY DAVIES'
    """
    if not listing_text:
        return pd.NaT

    m = re.match(r"^(APR|MAY|JUN|SEP|OCT)\s+(\d{1,2})", listing_text, flags=re.IGNORECASE)
    if not m:
        return pd.NaT

    month_map = {
        "APR": "Apr",
        "MAY": "May",
        "JUN": "Jun",
        "SEP": "Sep",
        "OCT": "Oct",
    }

    mon = month_map[m.group(1).upper()]
    day = m.group(2)

    return _parse_event_date(f"{mon} {day}")


def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2200")
    return webdriver.Chrome(options=options)


def get_html(driver, url, wait=3):
    driver.get(url)
    time.sleep(wait)
    return driver.page_source


# -------------------------
# LISTING PAGE
# -------------------------
def parse_listing_for_event_urls(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = _clean_text(a.get_text(" ", strip=True))

        if "/listings/" not in href:
            continue
        if not text.startswith(("APR", "MAY", "JUN", "SEP", "OCT", "POSTPONED")):
            continue

        url = urljoin(START_URL, href)
        if url in seen:
            continue
        seen.add(url)

        listing_date = _parse_listing_date(text)

        items.append({
            "url": url,
            "listing_text": text,
            "listing_date": listing_date,
        })

    return items


def filter_listing_items_by_range(items, start, end):
    filtered = []

    for item in items:
        listing_date = item.get("listing_date")

        if pd.isna(listing_date):
            continue

        if start <= listing_date.date() <= end:
            filtered.append(item)

    return filtered


# -------------------------
# DETAIL PAGE
# -------------------------
def parse_event_detail(html, url, listing_text=""):
    soup = BeautifulSoup(html, "html.parser")

    # -------- NAME --------
    event_name = ""
    h3_candidates = soup.find_all("h3")
    for h3 in h3_candidates:
        text = _clean_text(h3.get_text(" ", strip=True))
        if text:
            event_name = text
            break

    # -------- DATE + PRICE --------
    date_value = ""
    cost_value = "Unknown"

    for block in soup.select(".sqs-html-content"):
        text = _clean_text(block.get_text(" ", strip=True))

        if not text:
            continue

        m = re.search(r"DATE:\s*([A-Z]+\s+\d{1,2})", text, flags=re.IGNORECASE)
        if m and not date_value:
            date_value = m.group(1).title()

        m = re.search(r"TICKETS:\s*(£\d+(?:\.\d{2})?)", text, flags=re.IGNORECASE)
        if m and cost_value == "Unknown":
            cost_value = m.group(1)

        if date_value and cost_value != "Unknown":
            break

    # -------- FALLBACK DATE FROM LISTING TEXT --------
    if not date_value and listing_text:
        m = re.match(r"^(APR|MAY|JUN|SEP|OCT)\s+(\d{1,2})", listing_text, flags=re.IGNORECASE)
        if m:
            month_map = {
                "APR": "Apr",
                "MAY": "May",
                "JUN": "Jun",
                "SEP": "Sep",
                "OCT": "Oct",
            }
            mon = month_map[m.group(1).upper()]
            day = m.group(2)
            date_value = f"{mon} {day}"

    print("SCRAPED:", event_name, date_value, cost_value)

    return {
        "date": date_value,
        "event_name": event_name,
        "cost": cost_value,
        "event_url": url,
    }


# -------------------------
# MAIN SCRAPER
# -------------------------
def scrape_in_range(start, end, delay=1):
    driver = make_driver()

    try:
        listing_html = get_html(driver, START_URL, 5)
        items = parse_listing_for_event_urls(listing_html)

        print(f"ALL LISTING ITEMS FOUND: {len(items)}")

        items = filter_listing_items_by_range(items, start, end)

        print(f"ITEMS IN RANGE [{start} .. {end}]: {len(items)}")
        for item in items[:10]:
            print(item["listing_text"], "->", item["url"])

        rows = []

        for item in items:
            try:
                url = item["url"]
                listing_text = item.get("listing_text", "")

                html = get_html(driver, url, 2)
                row = parse_event_detail(html, url, listing_text)

                if row:
                    rows.append(row)

                time.sleep(delay)

            except Exception as e:
                print("FAILED:", item, e)

    finally:
        driver.quit()

    df = pd.DataFrame(rows)

    if df.empty:
        df["event_date"] = pd.Series(dtype="datetime64[ns]")
        return df

    df["event_date"] = df["date"].apply(_parse_event_date)

    print("\nRAW DATA:")
    print(df.head(10))

    return df


# -------------------------
# CLI
# -------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default="alphabet.csv")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    if end < start:
        raise ValueError("End date must be on or after start date.")

    df = scrape_in_range(start, end, delay=args.delay)

    output = df[["date", "event_name", "cost"]].copy()

    print("\nFILTERED:")
    print(output)

    output_path = OUTPUT_DIR / args.out
    output.to_csv(output_path, index=False, encoding="utf-8")
    print("Saved:", output_path)


if __name__ == "__main__":
    main()