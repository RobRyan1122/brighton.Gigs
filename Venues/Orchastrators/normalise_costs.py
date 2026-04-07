from pathlib import Path
import re
import pandas as pd

# This file lives in: Venues/Orchastrators
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_DIR = SCRIPT_DIR.parent / "csvs"


def normalise_cost(value):
    if pd.isna(value):
        return ""

    text = str(value).strip()

    # Find first integer or decimal number
    match = re.search(r"\d+(?:\.\d+)?", text)

    if not match:
        return ""

    number = float(match.group())
    return f"£{number:.2f}"


def process_csv(csv_path: Path):
    try:
        df = pd.read_csv(csv_path)

        if "cost" not in df.columns:
            print(f"Skipping {csv_path.name} - no cost column")
            return

        df["cost"] = df["cost"].apply(normalise_cost)
        df.to_csv(csv_path, index=False)

        print(f"Updated: {csv_path.name}")

    except Exception as e:
        print(f"Failed: {csv_path.name} - {e}")


def main():
    if not CSV_DIR.exists():
        raise FileNotFoundError(f"CSV directory not found: {CSV_DIR}")

    csv_files = list(CSV_DIR.glob("*.csv"))

    if not csv_files:
        print("No CSV files found")
        return

    for csv_file in csv_files:
        process_csv(csv_file)

    print("Cost normalisation complete")


if __name__ == "__main__":
    main()