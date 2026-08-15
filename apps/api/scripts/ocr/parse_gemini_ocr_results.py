"""Convert Gemini Batch OCR JSONL output into Frame-to-text JSON records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def find_image_uri(request: dict[str, Any]) -> str:
    """Return the sole GCS image URI from a Gemini request."""
    for content in request.get("contents", []):
        for part in content.get("parts", []):
            file_data = part.get("fileData")
            if file_data and file_data.get("mimeType") == "image/webp":
                return str(file_data["fileUri"])
    raise ValueError("Request does not contain an image/webp fileData URI")


def image_path_from_uri(uri: str) -> str:
    """Convert a GCS URI to the project-relative Frame path."""
    marker = "/keyframes/"
    if not uri.startswith("gs://") or marker not in uri:
        raise ValueError(f"Expected a keyframes GCS URI, received: {uri}")
    return f"keyframes/{uri.split(marker, maxsplit=1)[1]}"


def extract_ocr_text(response: dict[str, Any]) -> str:
    """Combine text parts from the first non-thought Gemini candidate."""
    candidates = response.get("candidates", [])
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [
        str(part["text"])
        for part in parts
        if "text" in part and not part.get("thought", False)
    ]
    return "\n".join(text_parts)


def parse_results(input_path: Path) -> tuple[list[dict[str, str]], int]:
    """Parse Batch JSONL and return records plus the number of non-success rows."""
    records: list[dict[str, str]] = []
    non_success_count = 0

    with input_path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                result = json.loads(line)
                image_uri = find_image_uri(result["request"])
                ocr_text = extract_ocr_text(result.get("response", {}))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid result at line {line_number}: {error}") from error

            if result.get("status"):
                non_success_count += 1
            records.append({"image": image_path_from_uri(image_uri), "ocr_text": ocr_text})

    records.sort(key=lambda record: record["image"])
    return records, non_success_count


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "ocr" / "L25" / "results.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "ocr" / "L25" / "results.json",
    )
    return parser.parse_args()


def main() -> None:
    """Convert a Gemini Batch OCR output file to JSON."""
    args = parse_args()
    records, non_success_count = parse_results(args.input)
    with args.output.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(f"Wrote {len(records)} records to {args.output}")
    print(f"Rows with non-empty status: {non_success_count}")


if __name__ == "__main__":
    main()
