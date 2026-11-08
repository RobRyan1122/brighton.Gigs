import argparse
import re

from datetime import datetime, date
from pathlib import Path

import pandas as pd

from bs4 import BeautifulSoup

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


START_URL = "https://princealbertbrighton.co.uk/"

SCRIPT_DIR = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(SCRIPT_DIR.parent))
from date_utils import resolve_month_day

OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_event_date(date_str: str, reference_date: date, end_date: date | None = None) -> pd.Timestamp:
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
    if re.search(r"\b\d{4}\b", raw):
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
            parsed_date = datetime.strptime(f"{raw} 2000", fmt + " %Y")
            break
        except ValueError:
            pass

    if parsed_date is None:
        return pd.NaT

    try:
        return pd.Timestamp(resolve_month_day(parsed_date.month, parsed_date.day, reference_date, end_date))
    except ValueError:
        return pd.NaT


def get_html(url):
    # Listings are server-rendered; Chrome is unnecessary and can return an
    # incomplete page on the hosted runner. Retry transient network failures.
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"])
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retries))
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.content


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

    df = pd.DataFrame(rows, columns=["date", "event_name", "cost"])

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
    df = parse_homepage(get_html(START_URL))

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
            end,
        )
    )

    df = df.dropna(
        subset=["event_date"]
    ).copy()

    df = df[
        (df["event_date"].dt.date >= start)
        & (df["event_date"].dt.date <= end)
    ].copy()

    df["date"] = df["event_date"].dt.strftime("%d/%m/%Y")

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