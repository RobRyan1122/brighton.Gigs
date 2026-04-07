from pathlib import Path
import subprocess
import sys

# Use the SAME Python interpreter (important for venv)
PYTHON = sys.executable

BASE_DIR = Path(__file__).resolve().parent

SCRIPTS = [
    "run_all_scrapers.py",
    "normalise_costs.py",
    "graphics.py",
    "emailer.py",
    "cleanup.py",
]


def run_script(script_name: str):
    script_path = BASE_DIR / script_name

    print(f"\n--- Running: {script_name} ---")

    result = subprocess.run(
        [PYTHON, str(script_path)],
        capture_output=True,
        text=True
    )

    # Print output for debugging/logging
    print(result.stdout)

    if result.returncode != 0:
        print(result.stderr)
        raise Exception(f"{script_name} failed with exit code {result.returncode}")


def main():
    for script in SCRIPTS:
        run_script(script)

    print("All scripts completed successfully")


if __name__ == "__main__":
    main()