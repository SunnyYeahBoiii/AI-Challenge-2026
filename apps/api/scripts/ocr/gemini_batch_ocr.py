"""Create a Gemini Batch inference JSONL file for OCRing Frame images from GCS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = """Extract all visible text from each video keyframe for keyword search.

Rules:

* Preserve the words and their original order.
* Vietnamese diacritics do not need to be exact.
* Ignore formatting, layout, colors, and HTML.
* Do not summarize, correct, or add text.
* If text is unclear, do not guess.

Return one plain-text string per keyframe."""

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BUCKET = "frameseeker-aic2026-assets"


def build_request(
    *, bucket: str, gcs_prefix: str, relative_path: Path, max_output_tokens: int
) -> dict[str, Any]:
    """Build one Batch inference request for a WebP Frame."""
    object_path = "/".join((gcs_prefix.strip("/"), relative_path.as_posix()))
    return {
        "request": {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": f"gs://{bucket}/{object_path}",
                                "mimeType": "image/webp",
                            }
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        }
    }


def write_requests(
    *,
    source_directory: Path,
    bucket: str,
    gcs_prefix: str,
    output_path: Path,
    max_output_tokens: int,
) -> int:
    """Write one JSONL Gemini request for each WebP Frame in a dataset directory."""
    if not source_directory.is_dir():
        raise ValueError(f"Source directory does not exist: {source_directory}")

    keyframes_root = source_directory.parent
    frames = sorted(source_directory.rglob("*.webp"))
    if not frames:
        raise ValueError(f"No .webp Frames found in: {source_directory}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for frame in frames:
            request = build_request(
                bucket=bucket,
                gcs_prefix=gcs_prefix,
                relative_path=frame.relative_to(keyframes_root),
                max_output_tokens=max_output_tokens,
            )
            output_file.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")))
            output_file.write("\n")

    return len(frames)


def parse_args() -> argparse.Namespace:
    """Parse script arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="L25", help="Dataset directory under data/keyframes.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="GCS bucket that contains keyframes.")
    parser.add_argument("--gcs-prefix", default="keyframes", help="GCS prefix for all keyframes.")
    parser.add_argument("--max-output-tokens", type=int, default=1024, help="Maximum number of output tokens for each request.")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    """Create the requested Batch inference JSONL file."""
    args = parse_args()
    if args.max_output_tokens < 1:
        raise ValueError("--max-output-tokens must be positive")

    source_directory = args.source_dir or PROJECT_ROOT / "data" / "keyframes" / args.dataset
    output_path = args.output or PROJECT_ROOT / "data" / "ocr" / args.dataset / "requests.jsonl"
    count = write_requests(
        source_directory=source_directory,
        bucket=args.bucket,
        gcs_prefix=args.gcs_prefix,
        output_path=output_path,
        max_output_tokens=args.max_output_tokens,
    )
    print(f"Wrote {count} requests to {output_path}")


if __name__ == "__main__":
    main()
