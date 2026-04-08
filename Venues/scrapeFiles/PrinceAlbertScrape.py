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


def looks_like_date(text: str) -> bool:
    if not text:
        return False
    return bool(re.match(r"^[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?$", text.strip(), flags=re.IGNORECASE))


def looks_like_price(text: str) -> bool:
    if not text:
        return False
    return (
        "free" in text.lower()
        or "ticket" in text.lower()
        or bool(re.search(r"£\s*\d", text))
    )


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

    content_nodes = soup.select(".jet-listing-dynamic-field__content")
    texts = [_clean_text(node.get_text(" ", strip=True)) for node in content_nodes]
    texts = [t for t in texts if t]

    i = 0
    while i < len(texts):
        text = texts[i]

        if looks_like_date(text):
            date_value = text

            event_name = ""
            price_value = ""

            # walk backwards to find the event name
            j = i - 1
            while j >= 0:
                candidate = texts[j]
                if not looks_like_date(candidate) and not looks_like_price(candidate):
                    event_name = candidate
                    break
                j -= 1

            # walk forwards to find the price
            k = i + 1
            while k < len(texts):
                candidate = texts[k]
                if looks_like_price(candidate):
                    price_value = normalise_price(candidate)
                    break
                if looks_like_date(candidate):
                    break
                k += 1

            if event_name:
                rows.append({
                    "date": date_value,
                    "event_name": event_name,
                    "cost": price_value if price_value else "Unknown",
                })

        i += 1

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