import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile


from tools import DOIST_CATALOG as CATALOG, ROOT
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def capture_paths(directory):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    ids = {item["id"] for item in catalog["itens"] if item["estado"] == "elegível"}
    captures = {}
    for path in (directory / "capturas").iterdir():
        if path.stem in ids and path.suffix.lower() in IMAGE_TYPES and path.is_file():
            if path.stem in captures:
                raise ValueError(f'More than one image matches {path.stem}.')
            captures[path.stem] = path
    return sorted(captures.values()), sorted(ids - captures.keys())


def recognise(executable, image_path):
    row = {"id": image_path.stem, "texto": ""}
    try:
        process = subprocess.run(
            [executable, str(image_path), "stdout", "-l", "eng", "--psm", "11"],
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {**row, "estado": "erro", "erro": str(error)}
    if process.returncode:
        error = process.stderr.strip() or f"Tesseract retornou código {process.returncode}."
        return {**row, "estado": "erro", "erro": error}
    text = process.stdout.strip()
    return {**row, "texto": text, "estado": "extraido" if text else "vazio"}


def write_index(destination, rows):
    counts = Counter()
    temporary = NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            for row in rows:
                temporary.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[row["estado"]] += 1
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description='Read text from local Doist images with Tesseract.')
    parser.add_argument("--tesseract", default="tesseract", help="Tesseract command or executable path.")
    args = parser.parse_args()
    executable = shutil.which(args.tesseract)
    if executable is None:
        parser.error("Tesseract unavailable. Use --tesseract to set the executable path.")

    directory = ROOT / "dados" / "doist"
    try:
        captures, missing = capture_paths(directory)
    except (OSError, ValueError) as error:
        parser.error(f'Cannot read the local Doist collection. {error}')
    if not captures:
        parser.error("Local images missing. Run python -m tools.collection.download_doist.")

    destination = directory / "wiki-ocr.jsonl"
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as workers:
        rows = workers.map(lambda image: recognise(executable, image), captures)
        counts = write_index(destination, rows)
    print(f"{destination}: {counts['extraido']} transcripts, {counts['vazio']} empty images, {counts['erro']} errors.")
    if missing:
        print(f"Missing eligible images: {', '.join(missing)}.")
    return int(bool(counts["erro"] or missing))


if __name__ == "__main__":
    raise SystemExit(main())
