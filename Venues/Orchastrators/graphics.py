from __future__ import annotations

from pathlib import Path
from typing import Optional
import random

import pandas as pd
from dateutil import parser as dtparser
from PIL import Image, ImageDraw, ImageFont


# ----------------------------
# Config
# ----------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
VENUES_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = VENUES_DIR.parent

CSV_DIR = VENUES_DIR / "csvs"
BG_DIR = VENUES_DIR / "imageassets"
OUT_DIR = PROJECT_ROOT / "output_daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Canvas settings
WIDTH = 1080
HEIGHT = 1350
PADDING = 60

# Typography
FONT_REGULAR_PATHS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

FONT_BOLD_PATHS = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in paths:
        try:
            return ImageFont.truetype(p, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_DATE = _load_font(FONT_BOLD_PATHS, 64)
FONT_VENUE = _load_font(FONT_BOLD_PATHS, 42)
FONT_EVENT = _load_font(FONT_REGULAR_PATHS, 34)
FONT_COST = _load_font(FONT_REGULAR_PATHS, 30)
FONT_FOOT = _load_font(FONT_REGULAR_PATHS, 26)


# ----------------------------
# Venue name mapping
# ----------------------------

def venue_name_from_filename(path: Path) -> str:
    """
    Convert CSV filename to nice venue name.
    """
    stem = path.stem.lower()

    cleaned = stem
    cleaned = cleaned.replace("scrape", "")
    cleaned = cleaned.replace("-", "_")
    cleaned = cleaned.split("_")[0].strip()

    mapping = {
        "gds": "Green Door Store",
        "greendoorstore": "Green Door Store",
        "hope": "Hope & Ruin",
        "hopeandruin": "Hope & Ruin",
        "rossi": "Rossi Bar",
        "rossibar": "Rossi Bar",
        "chalk": "Chalk",
        "alphabet": "Alphabet",
        "dust": "Dust",
        "folklore": "The Folklore Rooms",
        "folklorerooms": "The Folklore Rooms",
    }

    if cleaned in mapping:
        return mapping[cleaned]

    return cleaned.replace("_", " ").title()


# ----------------------------
# Date normalisation
# ----------------------------

def normalise_date_str(s: str) -> Optional[pd.Timestamp]:
    """
    Convert various date strings to a normalized date (midnight) Timestamp.
    """
    if not isinstance(s, str) or not s.strip():
        return None

    raw = s.strip()

    raw = raw.split("–")[0].strip()
    raw = raw.split("-")[0].strip() if " - " in raw else raw

    raw = (
        raw.replace("st ", " ")
           .replace("nd ", " ")
           .replace("rd ", " ")
           .replace("th ", " ")
    )

    raw = raw.split(" at ")[0].strip()

    try:
        dt = dtparser.parse(raw, dayfirst=True, fuzzy=True, default=dtparser.parse("2026-01-01"))
        return pd.Timestamp(dt.date())
    except Exception:
        return None


# ----------------------------
# Background helpers
# ----------------------------

def get_background_files(bg_dir: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return [p for p in bg_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]


def resize_and_crop_to_fill(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_width / target_height

    if src_ratio > target_ratio:
        # Image is wider than target: fit height, crop width
        new_h = target_height
        new_w = int(new_h * src_ratio)
    else:
        # Image is taller/narrower than target: fit width, crop height
        new_w = target_width
        new_h = int(new_w / src_ratio)

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2
    right = left + target_width
    bottom = top + target_height

    return img.crop((left, top, right, bottom))


def make_background() -> Image.Image:
    bg_files = get_background_files(BG_DIR)

    if not bg_files:
        # fallback if folder is empty
        return Image.new("RGB", (WIDTH, HEIGHT), "white")

    chosen = random.choice(bg_files)

    with Image.open(chosen) as bg:
        bg = bg.convert("RGB")
        bg = resize_and_crop_to_fill(bg, WIDTH, HEIGHT)
        return bg.copy()


# ----------------------------
# Text layout helpers
# ----------------------------

def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current: list[str] = []

    for w in words:
        test = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]

    if current:
        lines.append(" ".join(current))

    return lines


def draw_section(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    venue_name: str,
    rows: list[tuple[str, str]],
) -> int:
    draw.text((x, y), venue_name, font=FONT_VENUE, fill="black")
    y += 54

    if not rows:
        draw.text((x, y), "No events", font=FONT_EVENT, fill="black")
        return y + 46

    for event_name, cost in rows:
        cost_text = "" if pd.isna(cost) else str(cost)

        cost_bbox = draw.textbbox((0, 0), cost_text, font=FONT_COST)
        cost_w = cost_bbox[2] - cost_bbox[0]

        name_max_w = w - cost_w - 30
        lines = wrap_text(draw, str(event_name), FONT_EVENT, name_max_w)

        for line in lines:
            draw.text((x, y), line, font=FONT_EVENT, fill="black")
            y += 40

        if cost_text:
            draw.text((x + w - cost_w, y - 40), cost_text, font=FONT_COST, fill="black")

        y += 18

    return y


# ----------------------------
# Main: load, merge, render
# ----------------------------

def load_csv_with_venue(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required_cols = {"date", "event_name", "cost"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")

    df = df[["date", "event_name", "cost"]].copy()
    df["venue"] = venue_name_from_filename(path)
    df["event_day"] = df["date"].apply(normalise_date_str)

    df = df.dropna(subset=["event_day"]).copy()
    df["event_day"] = pd.to_datetime(df["event_day"])
    return df


def load_all_csvs(csv_dir: Path) -> pd.DataFrame:
    csv_paths = sorted(csv_dir.glob("*.csv"))

    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")

    frames = []

    for path in csv_paths:
        try:
            df = load_csv_with_venue(path)
            frames.append(df)
            print(f"Loaded {path.name} -> {df['venue'].iloc[0]} ({len(df)} rows)")
        except Exception as e:
            print(f"Skipping {path.name}: {e}")

    if not frames:
        raise ValueError("No valid CSV files could be loaded.")

    return pd.concat(frames, ignore_index=True)


def render_day_poster(day: pd.Timestamp, df_day: pd.DataFrame) -> Path:
    img = make_background()
    draw = ImageDraw.Draw(img)

    

    day_str = day.strftime("%a %d %b %Y")
    draw.text((PADDING, PADDING), day_str, font=FONT_DATE, fill="black")

    y = PADDING + 90

    df_day = df_day.sort_values(["venue", "event_name"])
    venues = df_day["venue"].unique().tolist()

    section_w = WIDTH - 2 * PADDING

    for v in venues:
        rows = df_day[df_day["venue"] == v][["event_name", "cost"]].fillna("").values.tolist()
        rows = [(r[0], r[1]) for r in rows]

        y = draw_section(img, draw, PADDING, y, section_w, v, rows)
        y += 30

        if y > HEIGHT - PADDING - 80:
            draw.text((PADDING, HEIGHT - PADDING - 60), "…more events not shown", font=FONT_FOOT, fill="black")
            break

    footer = "brighton.localgigs"
    footer_bbox = draw.textbbox((0, 0), footer, font=FONT_FOOT)
    footer_w = footer_bbox[2] - footer_bbox[0]
    draw.text((WIDTH - PADDING - footer_w, HEIGHT - PADDING - 40), footer, font=FONT_FOOT, fill="black")

    safe_day = day.strftime("%Y-%m-%d")
    out_path = OUT_DIR / f"{safe_day}.png"
    img.save(out_path, "PNG")
    return out_path


def main():
    all_events = load_all_csvs(CSV_DIR)

    days = sorted(all_events["event_day"].unique())
    print(f"Found {len(days)} unique days")

    for d in days:
        day_ts = pd.Timestamp(d)
        df_day = all_events[all_events["event_day"] == day_ts]
        out = render_day_poster(day_ts, df_day)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()