"""Create search-normalized OCR fields without changing the source OCR output."""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "ocr" / "results.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ocr" / "results.search.json"


def normalize_for_search(text: str) -> str:
    """Normalize OCR text while retaining letters and digits for lexical search."""
    normalized = unicodedata.normalize("NFC", text).casefold()
    if normalized.strip() == "none":
        return ""

    characters = [
        " "
        if character.isspace()
        or unicodedata.category(character).startswith(("P", "C"))
        else character
        for character in normalized
    ]
    return " ".join("".join(characters).split())


def fold_vietnamese(text: str) -> str:
    """Return a lowercase Vietnamese string without diacritics."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    without_marks = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return without_marks.replace("đ", "d")


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(arguments)


def load_records(input_path: Path) -> list[dict[str, Any]]:
    """Load and validate OCR records from a JSON array."""
    loaded = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError(f"Expected a JSON array in {input_path}")
    if any(not isinstance(record, dict) for record in loaded):
        raise ValueError(f"Every record in {input_path} must be a JSON object")
    if any(not isinstance(record.get("ocr_text"), str) for record in loaded):
        raise ValueError(f"Every record in {input_path} must have string field 'ocr_text'")
    return loaded


def enrich_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add non-destructive OCR search fields to each record."""
    enriched_records: list[dict[str, Any]] = []
    for record in records:
        enriched = record.copy()
        search_text = normalize_for_search(record["ocr_text"])
        enriched["ocr_text_search"] = search_text
        enriched["ocr_text_folded"] = fold_vietnamese(search_text)
        enriched_records.append(enriched)
    return enriched_records


def main(arguments: Sequence[str] | None = None) -> None:
    """Generate a separate OCR JSON file with search-normalized fields."""
    args = parse_arguments(arguments)
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if input_path == output_path:
        raise ValueError("--output must differ from --input to preserve source OCR")

    records = load_records(input_path)
    enriched_records = enrich_records(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(enriched_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(enriched_records):,} records to {output_path}")


if __name__ == "__main__":
    main()
