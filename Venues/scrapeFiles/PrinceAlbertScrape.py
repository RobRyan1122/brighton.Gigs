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


def _parse_event_date(date_str: str, reference_date: date) -> pd.Timestamp:
    if not date_str:
        return pd.NaT

    raw = _clean_text(date_str)

    # Convert "September 3rd" -> "September 3"
    raw = re.sub(
        r"(\d{1,2})(st|nd|rd|th)\b",
        r"\1",
        raw,
        flags=re.IGNORECASE,
    )

    # Handle the site adding a weekday, e.g.
    # "Thursday September 3rd"
    raw = re.sub(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    # If the website starts providing a full year,
    # use that rather than trying to infer one.
    if re.search(r"\b20\d{2}\b", raw):
        return pd.to_datetime(
            raw,
            errors="coerce",
            dayfirst=True,
        )

    # Otherwise the Prince Albert date is expected to be
    # something like "September 3" or "Sep 3".
    parsed_date = None

    for fmt in ("%B %d", "%b %d"):
        try:
            parsed_date = datetime.strptime(raw, fmt)
            break
        except ValueError:
            pass

    if parsed_date is None:
        return pd.NaT

    candidate = pd.Timestamp(
        year=reference_date.year,
        month=parsed_date.month,
        day=parsed_date.day,
    )

    # Handle events crossing into the next calendar year.
    #
    # Example:
    # scrape date = 30 August 2026
    # event date = January 15
    #
    # That should mean January 15 2027, not January 15 2026.
    if candidate.date() < reference_date:
        days_in_past = (reference_date - candidate.date()).days

        if days_in_past > 60:
            candidate = candidate.replace(
                year=reference_date.year + 1
            )

    return candidate


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

    m = re.search(
        r"£\s*\d+(?:\.\d{1,2})?",
        cleaned,
    )

    if m:
        return m.group(0).replace(" ", "")

    return cleaned


def parse_homepage(html):
    soup = BeautifulSoup(html, "html.parser")

    rows = []

    name_nodes = soup.select(
        'div[data-id="154e459"] '
        ".jet-listing-dynamic-field__content"
    )

    date_nodes = soup.select(
        'div[data-id="27af3ce"] '
        ".jet-listing-dynamic-field__content"
    )

    price_nodes = soup.select(
        'div[data-id="af29adb"] '
        ".jet-listing-dynamic-field__content"
    )

    count = min(
        len(name_nodes),
        len(date_nodes),
        len(price_nodes),
    )

    for i in range(count):

        event_name = _clean_text(
            name_nodes[i].get_text(
                " ",
                strip=True,
            )
        )

        date_value = _clean_text(
            date_nodes[i].get_text(
                " ",
                strip=True,
            )
        )

        price_value = _clean_text(
            price_nodes[i].get_text(
                " ",
                strip=True,
            )
        )

        if not event_name or not date_value:
            continue

        rows.append(
            {
                "date": date_value,
                "event_name": event_name,
                "cost": (
                    normalise_price(price_value)
                    if price_value
                    else "Unknown"
                ),
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df = (
            df.drop_duplicates(
                subset=[
                    "date",
                    "event_name",
                    "cost",
                ]
            )
            .reset_index(drop=True)
        )

    return df


def scrape_in_range(start, end):
    driver = make_driver()

    try:
        html = get_html(
            driver,
            START_URL,
            wait=5,
        )

        df = parse_homepage(html)

    finally:
        driver.quit()

    if df.empty:
        df["event_date"] = pd.Series(
            dtype="datetime64[ns]"
        )

        return df

    # Use the requested scrape start date when inferring
    # which year an event belongs to.
    df["event_date"] = df["date"].apply(
        lambda value: _parse_event_date(
            value,
            start,
        )
    )

    df = df.dropna(
        subset=["event_date"]
    ).copy()

    df = df[
        (df["event_date"].dt.date >= start)
        & (df["event_date"].dt.date <= end)
    ].copy()

    return (
        df.sort_values("event_date")
        .reset_index(drop=True)
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        required=True,
    )

    parser.add_argument(
        "--end",
        required=True,
    )

    parser.add_argument(
        "--out",
        default="PrinceAlbertScrape.csv",
    )

    args = parser.parse_args()

    start = datetime.strptime(
        args.start,
        "%Y-%m-%d",
    ).date()

    end = datetime.strptime(
        args.end,
        "%Y-%m-%d",
    ).date()

    if end < start:
        raise ValueError(
            "End date must be on or after start date."
        )

    df = scrape_in_range(
        start,
        end,
    )

    output = df[
        [
            "date",
            "event_name",
            "cost",
        ]
    ].copy()

    output_path = (
        OUTPUT_DIR / args.out
    )

    output.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    print(output)

    print(
        "Saved:",
        output_path,
    )


if __name__ == "__main__":
    main()