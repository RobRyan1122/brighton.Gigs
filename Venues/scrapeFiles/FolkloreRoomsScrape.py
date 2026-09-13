import argparse
import time

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


START_URL = "https://www.thefolklorerooms.co.uk/listings"

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "csvs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# General helpers
# --------------------------------------------------

def _clean_text(value):
    if not value:
        return ""

    return " ".join(
        str(value).split()
    ).strip()


def make_driver():
    options = Options()

    # Required for GitHub Actions / non-GUI environments.
    options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(
        options=options
    )

    driver.set_page_load_timeout(30)

    return driver


def wait_for_page(driver, timeout=10):
    try:
        WebDriverWait(
            driver,
            timeout,
        ).until(
            lambda d: d.execute_script(
                "return document.readyState"
            ) == "complete"
        )
    except Exception:
        pass


def get_html(driver, url, wait=3):
    driver.get(url)

    wait_for_page(driver)

    time.sleep(wait)

    return driver.page_source


# --------------------------------------------------
# Folklore Rooms listing parsing
# --------------------------------------------------

import re


DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"\d{4}\b",
    re.IGNORECASE,
)


def parse_listings(html):
    """
    Extract:
        date
        event_name
        ticket_url

    from The Folklore Rooms listings page.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    rows = []

    headings = soup.find_all("h2")

    for heading in headings:
        event_name = _clean_text(
            heading.get_text(
                " ",
                strip=True,
            )
        )

        if not event_name:
            continue

        section_text = []
        ticket_url = ""

        for element in heading.next_elements:
            # Reaching another H2 means we've reached
            # the next event.
            if (
                isinstance(element, Tag)
                and element is not heading
                and element.name == "h2"
            ):
                break

            if isinstance(element, Tag):
                if element.name == "a":
                    link_text = _clean_text(
                        element.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    href = element.get("href")

                    if (
                        "BOOK TICKETS"
                        in link_text.upper()
                        and href
                    ):
                        ticket_url = href

            elif isinstance(element, str):
                text = _clean_text(
                    element
                )

                if text:
                    section_text.append(
                        text
                    )

        combined_text = " ".join(
            section_text
        )

        date_match = DATE_RE.search(
            combined_text
        )

        if not date_match:
            continue

        date_text = _clean_text(
            date_match.group(0)
        )

        try:
            event_date = datetime.strptime(
                date_text,
                "%A, %d %B %Y",
            )
        except ValueError:
            continue

        rows.append(
            {
                "date": date_text,
                "event_date": pd.Timestamp(
                    event_date.date()
                ),
                "event_name": event_name,
                "ticket_url": ticket_url,
            }
        )

    df = pd.DataFrame(
        rows
    )

    if not df.empty:
        df = (
            df.drop_duplicates(
                subset=[
                    "event_date",
                    "event_name",
                ]
            )
            .reset_index(drop=True)
        )

    return df


# --------------------------------------------------
# Ticket provider detection
# --------------------------------------------------

def get_hostname(url):
    if not url:
        return ""

    try:
        return (
            urlparse(url)
            .hostname
            or ""
        ).lower()

    except Exception:
        return ""


def is_dice_url(url):
    """
    Accepts:
        dice.fm
        www.dice.fm
        link.dice.fm
        other *.dice.fm hosts
    """

    host = get_hostname(
        url
    )

    return (
        host == "dice.fm"
        or host.endswith(".dice.fm")
    )


# --------------------------------------------------
# DICE price extraction
# --------------------------------------------------

def extract_dice_price(driver):
    """
    DICE exposes its displayed ticket price in:

    <div data-testid="event-details-cta-price">
        <span>Free</span>
        ...
    </div>

    or:

    <div data-testid="event-details-cta-price">
        <span>£12.50</span>
        ...
    </div>
    """

    try:
        html = driver.page_source

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        price_container = soup.select_one(
            '[data-testid="event-details-cta-price"]'
        )

        if not price_container:
            print(
                "    DICE price element not found"
            )

            return ""

        price_span = price_container.find(
            "span"
        )

        if not price_span:
            print(
                "    DICE price span not found"
            )

            return ""

        price = _clean_text(
            price_span.get_text(
                " ",
                strip=True,
            )
        )

        return price

    except Exception as exc:
        print(
            f"    DICE price extraction failed: "
            f"{exc}"
        )

        return ""


def extract_dice_ticket_price(
    driver,
    ticket_url,
):
    """
    Only called for URLs that are already known to
    belong to DICE.

    link.dice.fm redirects to the full DICE event page,
    after which the actual price element is read.
    """

    try:
        print(
            f"    Opening DICE: {ticket_url}"
        )

        driver.get(
            ticket_url
        )

        wait_for_page(
            driver,
            timeout=10,
        )

        # Allow DICE's client-side UI to render.
        time.sleep(4)

        final_url = driver.current_url

        print(
            f"    Final URL: {final_url}"
        )

        if not is_dice_url(
            final_url
        ):
            print(
                "    DICE link redirected to "
                "another provider -> leaving blank"
            )

            return ""

        price = extract_dice_price(
            driver
        )

        print(
            f"    Price: "
            f"{price or 'not found'}"
        )

        return price

    except Exception as exc:
        print(
            f"    DICE page failed: "
            f"{exc}"
        )

        return ""


# --------------------------------------------------
# Main scrape
# --------------------------------------------------

def scrape_in_range(
    start,
    end,
):
    driver = make_driver()

    try:
        print(
            "Loading Folklore Rooms listings..."
        )

        listings_html = get_html(
            driver,
            START_URL,
            wait=4,
        )

        df = parse_listings(
            listings_html
        )

        if df.empty:
            print(
                "No Folklore Rooms events found."
            )

            return pd.DataFrame(
                columns=[
                    "date",
                    "event_name",
                    "cost",
                ]
            )

        # Only process events inside the requested range.
        df = df[
            (
                df["event_date"].dt.date
                >= start
            )
            & (
                df["event_date"].dt.date
                <= end
            )
        ].copy()

        df = (
            df.sort_values(
                "event_date"
            )
            .reset_index(drop=True)
        )

        if df.empty:
            print(
                "No Folklore Rooms events "
                "in requested date range."
            )

            return pd.DataFrame(
                columns=[
                    "date",
                    "event_name",
                    "cost",
                ]
            )

        costs = []

        for _, row in df.iterrows():
            print()

            print(
                f"Checking: "
                f"{row['event_name']}"
            )

            ticket_url = row[
                "ticket_url"
            ]

            if not ticket_url:
                print(
                    "    No ticket link "
                    "-> leaving price blank"
                )

                costs.append(
                    ""
                )

                continue

            # --------------------------------------------------
            # ONLY DICE gets visited.
            #
            # See Tickets, Eventbrite, Skiddle, TicketTailor,
            # Ticketmaster, etc. are intentionally left blank.
            # --------------------------------------------------

            if not is_dice_url(
                ticket_url
            ):
                host = get_hostname(
                    ticket_url
                )

                print(
                    f"    Non-DICE provider "
                    f"({host or 'unknown'}) "
                    "-> leaving price blank"
                )

                costs.append(
                    ""
                )

                continue

            cost = extract_dice_ticket_price(
                driver,
                ticket_url,
            )

            costs.append(
                cost
            )

        df["cost"] = costs

        return df

    finally:
        driver.quit()


# --------------------------------------------------
# CLI
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Scrape gigs from "
            "The Folklore Rooms."
        )
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date YYYY-MM-DD",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date YYYY-MM-DD",
    )

    parser.add_argument(
        "--out",
        default="FolkloreRoomsScrape.csv",
        help="Output CSV filename",
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
            "End date must be "
            "on or after start date."
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
        OUTPUT_DIR
        / args.out
    )

    output.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    print()
    print(
        "Final results:"
    )

    print(
        output.to_string(
            index=False
        )
    )

    print()

    print(
        f"Saved: {output_path}"
    )


if __name__ == "__main__":
    main()