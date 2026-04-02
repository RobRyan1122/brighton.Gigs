from pathlib import Path
import shutil

CSV_SOURCE_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\Venues\csvs")
IMG_SOURCE_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\output_daily")

CSV_ARCHIVE_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\archive\csv")
IMG_ARCHIVE_DIR = Path(r"C:\Users\PC\OneDrive\Documents\BrightonLocalGigs\archive\img")

CSV_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
IMG_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def move_files(source_dir: Path, archive_dir: Path, allowed_exts: set[str]):
    if not source_dir.exists():
        print(f"Source folder does not exist: {source_dir}")
        return

    for file in source_dir.iterdir():
        if not file.is_file():
            continue

        if file.suffix.lower() not in allowed_exts:
            continue

        destination = archive_dir / file.name

        if destination.exists():
            print(f"Overwriting existing file: {destination}")
            destination.unlink()

        shutil.move(str(file), str(destination))
        print(f"Moved {file.name} -> {destination}")


def main():
    # Move csvs
    move_files(
        source_dir=CSV_SOURCE_DIR,
        archive_dir=CSV_ARCHIVE_DIR,
        allowed_exts={".csv"}
    )

    # Move images
    move_files(
        source_dir=IMG_SOURCE_DIR,
        archive_dir=IMG_ARCHIVE_DIR,
        allowed_exts={".png", ".jpg", ".jpeg", ".webp"}
    )

    print("Cleanup complete")


if __name__ == "__main__":
    main()