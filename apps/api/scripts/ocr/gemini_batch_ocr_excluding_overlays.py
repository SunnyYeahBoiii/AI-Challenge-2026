"""Create Gemini Batch OCR requests that exclude video overlays for selected datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = """Extract all visible text from each video keyframe for keyword search.
Rules:
Preserve the words and their original order.
Vietnamese diacritics do not need to be exact.
Ignore formatting, layout, colors, and HTML.
Do not summarize, correct, or add text.
If text is unclear, do not guess.
EXCLUDE the scrolling news ticker text at the very bottom of the screen.
EXCLUDE channel names, logos, and on-screen clocks/timestamps (typically located in the top corners).
If no relevant text remains after applying the exclusions, output exactly "None".
Return one plain-text string per keyframe."""

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BUCKET = "frameseeker-aic2026-assets"
DEFAULT_DATASETS = ["L21", "L22"]


def build_request(
    *,
    bucket: str,
    gcs_prefix: str,
    relative_path: Path,
    max_output_tokens: int,
    thinking_level: str,
) -> dict[str, Any]:
    """Build one Gemini Batch inference request for a WebP Frame."""
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
                "thinkingConfig": {"thinkingLevel": thinking_level},
            },
        }
    }


def write_requests(
    *,
    source_directories: list[Path],
    keyframes_root: Path,
    bucket: str,
    gcs_prefix: str,
    output_path: Path,
    max_output_tokens: int,
    thinking_level: str,
) -> int:
    """Write one JSONL Gemini request for every WebP Frame in selected datasets."""
    frames: list[Path] = []
    for source_directory in source_directories:
        if not source_directory.is_dir():
            raise ValueError(f"Source directory does not exist: {source_directory}")
        frames.extend(source_directory.rglob("*.webp"))

    frames.sort()
    if not frames:
        raise ValueError("No .webp Frames found in the selected source directories")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for frame in frames:
            request = build_request(
                bucket=bucket,
                gcs_prefix=gcs_prefix,
                relative_path=frame.relative_to(keyframes_root),
                max_output_tokens=max_output_tokens,
                thinking_level=thinking_level,
            )
            output_file.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")))
            output_file.write("\n")

    return len(frames)


def parse_args() -> argparse.Namespace:
    """Parse script arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=DEFAULT_DATASETS,
        help="Dataset directories under data/keyframes (default: L21 L22).",
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="GCS bucket containing keyframes.")
    parser.add_argument("--gcs-prefix", default="keyframes", help="GCS prefix for all keyframes.")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=1024,
        help="Maximum output tokens per image.",
    )
    parser.add_argument(
        "--thinking-level",
        default="MINIMAL",
        choices=["MINIMAL", "LOW", "MEDIUM", "HIGH"],
        help="Gemini thinking level per image.",
    )
    parser.add_argument("--output", type=Path, help="Local JSONL destination.")
    return parser.parse_args()


def main() -> None:
    """Create Batch requests for the selected datasets."""
    args = parse_args()
    if args.max_output_tokens < 1:
        raise ValueError("--max-output-tokens must be positive")

    keyframes_root = PROJECT_ROOT / "data" / "keyframes"
    source_directories = [keyframes_root / dataset for dataset in args.datasets]
    dataset_label = "-".join(args.datasets)
    output_path = args.output or PROJECT_ROOT / "data" / "ocr" / dataset_label / "requests.jsonl"
    count = write_requests(
        source_directories=source_directories,
        keyframes_root=keyframes_root,
        bucket=args.bucket,
        gcs_prefix=args.gcs_prefix,
        output_path=output_path,
        max_output_tokens=args.max_output_tokens,
        thinking_level=args.thinking_level,
    )
    print(f"Wrote {count} requests to {output_path}")


if __name__ == "__main__":
    main()
