import time
import argparse
import re
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


START_URL = "https://princealbertbrighton.co.uk/"

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str) -> pd.Timestamp:
    if not date_str:
        return pd.NaT

    raw = _clean_text(date_str)

    raw = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)

    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return pd.to_datetime(f"{raw} 2026", format=fmt, errors="raise")
        except Exception:
            pass

    return pd.to_datetime(raw, errors="coerce", dayfirst=True)


def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,3000")
    return webdriver.Chrome(options=options)


def get_html(driver, url, wait=5):
    driver.get(url)
    time.sleep(wait)
    return driver.page_source





def normalise_price(text: str) -> str:
    if not text:
        return ""

    cleaned = _clean_text(text)

    m = re.search(r"£\s*\d+(?:\.\d{1,2})?", cleaned)
    if m:
        return m.group(0).replace(" ", "")

    return cleaned


def parse_homepage(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    name_nodes = soup.select('div[data-id="154e459"] .jet-listing-dynamic-field__content')
    date_nodes = soup.select('div[data-id="27af3ce"] .jet-listing-dynamic-field__content')
    price_nodes = soup.select('div[data-id="af29adb"] .jet-listing-dynamic-field__content')

    count = min(len(name_nodes), len(date_nodes), len(price_nodes))

    for i in range(count):
        event_name = _clean_text(name_nodes[i].get_text(" ", strip=True))
        date_value = _clean_text(date_nodes[i].get_text(" ", strip=True))
        price_value = _clean_text(price_nodes[i].get_text(" ", strip=True))

        if not event_name or not date_value:
            continue

        rows.append({
            "date": date_value,
            "event_name": event_name,
            "cost": normalise_price(price_value) if price_value else "Unknown",
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates(subset=["date", "event_name", "cost"]).reset_index(drop=True)

    return df


def scrape_in_range(start, end):
    driver = make_driver()

    try:
        html = get_html(driver, START_URL, wait=5)
        df = parse_homepage(html)
    finally:
        driver.quit()

    if df.empty:
        df["event_date"] = pd.Series(dtype="datetime64[ns]")
        return df

    df["event_date"] = df["date"].apply(_parse_event_date)
    df = df.dropna(subset=["event_date"]).copy()

    df = df[
        (df["event_date"].dt.date >= start) &
        (df["event_date"].dt.date <= end)
    ].copy()

    return df.sort_values("event_date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default="PrinceAlbertScrape.csv")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    if end < start:
        raise ValueError("End date must be on or after start date.")

    df = scrape_in_range(start, end)
    output = df[["date", "event_name", "cost"]].copy()

    output_path = OUTPUT_DIR / args.out
    output.to_csv(output_path, index=False, encoding="utf-8")

    print(output)
    print("Saved:", output_path)


if __name__ == "__main__":
    main()