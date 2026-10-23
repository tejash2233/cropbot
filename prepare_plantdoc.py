"""Safely extract the PlantDoc train/test image folders on Windows and Linux."""
import argparse
from pathlib import Path
import re
from zipfile import ZipFile

from shutil import copyfileobj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", default="work/PlantDoc-Dataset.zip",
                        help="Path to the PlantDoc-Dataset ZIP archive")
    parser.add_argument("--output", default="datasets/PlantDoc",
                        help="Output folder used by train_model.py")
    args = parser.parse_args()
    archive = Path(args.archive)
    output = Path(args.output)
    if not archive.is_file():
        raise SystemExit(f"PlantDoc archive not found: {archive}\nDownload it from the PlantDoc-Dataset GitHub repository first.")

    invalid = re.compile(r'[<>:"/\\|?*]')
    count = 0
    with ZipFile(archive) as dataset:
        for item in dataset.infolist():
            if item.is_dir():
                continue
            parts = item.filename.split("/")
            if len(parts) != 4 or parts[1] not in {"train", "test"}:
                continue
            extension = Path(parts[-1]).suffix.lower()
            if extension not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                continue
            split = parts[1]
            label = invalid.sub("_", parts[2]).strip(" .")
            folder = output / split / label
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / f"{count:05d}{extension}"
            with dataset.open(item) as source, destination.open("wb") as target:
                copyfileobj(source, target)
            count += 1

    train_classes = {path.name for path in (output / "train").iterdir() if path.is_dir()}
    test_root = output / "test"
    test_classes = {path.name for path in test_root.iterdir() if path.is_dir()}
    for label in train_classes - test_classes:
        (test_root / label).mkdir(parents=True, exist_ok=True)
    print(f"Prepared {count} image files in {output.resolve()}")
    print(f"Classes: {len(train_classes)} train labels; test split kept separate.")


if __name__ == "__main__":
    main()
