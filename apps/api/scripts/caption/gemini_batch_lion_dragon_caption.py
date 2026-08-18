"""Create Gemini Batch caption requests for lion and dragon dance videos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gemini_batch_cycling_caption import (
    DEFAULT_BUCKET,
    PROJECT_ROOT,
    WINDOW_SIZE,
    create_requests,
    write_jsonl,
)


SYSTEM_PROMPT_PATH = Path(__file__).parent / "lion_dragon_system_prompt.txt"
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
DEFAULT_WINDOW_STRIDE = 4
DEFAULT_MAX_OUTPUT_TOKENS = 3096


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="L24", help="Dataset directory under data/keyframes.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="GCS bucket containing keyframes.")
    parser.add_argument("--gcs-prefix", default="keyframes", help="GCS prefix containing keyframes.")
    parser.add_argument(
        "--window-stride",
        type=int,
        default=DEFAULT_WINDOW_STRIDE,
        help="Start each five-frame window every N source keyframes (default: 4).",
    )
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--thinking-level",
        choices=["MINIMAL", "LOW", "MEDIUM", "HIGH"],
        default="MINIMAL",
    )
    parser.add_argument("--output", type=Path, help="Destination Batch JSONL file.")
    parser.add_argument("--manifest", type=Path, help="Destination window manifest JSON file.")
    return parser.parse_args()


def main() -> None:
    """Create five-frame lion and dragon dance caption requests."""
    args = parse_args()
    if args.window_stride < 1:
        raise ValueError("--window-stride must be positive")
    if args.max_output_tokens < 1:
        raise ValueError("--max-output-tokens must be positive")

    keyframes_root = PROJECT_ROOT / "data" / "keyframes"
    dataset_directory = keyframes_root / args.dataset
    if not dataset_directory.is_dir():
        raise ValueError(f"Dataset directory does not exist: {dataset_directory}")

    output_directory = PROJECT_ROOT / "data" / "captions" / args.dataset
    output_path = args.output or output_directory / "requests.jsonl"
    manifest_path = args.manifest or output_directory / "windows.json"
    requests, manifest, skipped_videos = create_requests(
        dataset_directory=dataset_directory,
        keyframes_root=keyframes_root,
        bucket=args.bucket,
        gcs_prefix=args.gcs_prefix,
        window_stride=args.window_stride,
        max_output_tokens=args.max_output_tokens,
        thinking_level=args.thinking_level,
        system_prompt=SYSTEM_PROMPT,
    )
    if not requests:
        raise ValueError("No five-frame windows could be created")

    write_jsonl(output_path, requests)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"window_size": WINDOW_SIZE, "window_stride": args.window_stride, "windows": manifest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(requests)} Batch requests to {output_path}")
    print(f"Wrote frame-window manifest to {manifest_path}")
    if skipped_videos:
        print(f"Skipped {len(skipped_videos)} videos with fewer than five frames")


if __name__ == "__main__":
    main()
