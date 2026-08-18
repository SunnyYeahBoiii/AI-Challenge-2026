"""Create Gemini Batch caption requests for cycling videos using five-frame windows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SYSTEM_PROMPT_PATH = Path(__file__).parent / "cycling_system_prompt.txt"
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BUCKET = "frameseeker-aic2026-assets"
WINDOW_SIZE = 10
DEFAULT_WINDOW_STRIDE = 8
DEFAULT_MAX_OUTPUT_TOKENS = 4096


def natural_path_key(path: Path) -> list[int | str]:
    """Return a numeric-aware sort key for a keyframe path."""
    return [int(part) if part.isdecimal() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def build_windows(frames: list[Path], window_stride: int) -> list[list[Path]]:
    """Group consecutive frames into overlapping five-frame windows."""
    if len(frames) < WINDOW_SIZE:
        return []

    windows = [
        frames[start : start + WINDOW_SIZE]
        for start in range(0, len(frames) - WINDOW_SIZE + 1, window_stride)
    ]
    final_window = frames[-WINDOW_SIZE:]
    if windows[-1] != final_window:
        windows.append(final_window)
    return windows


def build_request(
    *,
    bucket: str,
    gcs_prefix: str,
    frame_paths: list[Path],
    keyframes_root: Path,
    max_output_tokens: int,
    thinking_level: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> dict[str, Any]:
    """Build one Gemini request containing five GCS WebP frames."""
    if len(frame_paths) != WINDOW_SIZE:
        raise ValueError(f"Expected {WINDOW_SIZE} frames, received {len(frame_paths)}")

    image_parts: list[dict[str, dict[str, str]]] = []
    for frame_path in frame_paths:
        relative_path = frame_path.relative_to(keyframes_root).as_posix()
        object_path = f"{gcs_prefix.strip('/')}/{relative_path}"
        image_parts.append(
            {
                "fileData": {
                    "fileUri": f"gs://{bucket}/{object_path}",
                    "mimeType": "image/webp",
                }
            }
        )

    return {
        "request": {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": image_parts}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": thinking_level},
            },
        }
    }


def create_requests(
    *,
    dataset_directory: Path,
    keyframes_root: Path,
    bucket: str,
    gcs_prefix: str,
    window_stride: int,
    max_output_tokens: int,
    thinking_level: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Create batch requests and a local frame-to-window manifest for one dataset."""
    requests: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    skipped_videos: list[str] = []

    for video_directory in sorted(dataset_directory.iterdir(), key=natural_path_key):
        if not video_directory.is_dir():
            continue
        frames = sorted(video_directory.glob("*.webp"), key=natural_path_key)
        windows = build_windows(frames, window_stride)
        if not windows:
            skipped_videos.append(video_directory.name)
            continue

        for window in windows:
            request_index = len(requests)
            requests.append(
                build_request(
                    bucket=bucket,
                    gcs_prefix=gcs_prefix,
                    frame_paths=window,
                    keyframes_root=keyframes_root,
                    max_output_tokens=max_output_tokens,
                    thinking_level=thinking_level,
                    system_prompt=system_prompt,
                )
            )
            manifest.append(
                {
                    "request_index": request_index,
                    "video": video_directory.name,
                    "frames": [path.relative_to(keyframes_root).as_posix() for path in window],
                }
            )

    return requests, manifest, skipped_videos


def write_jsonl(output_path: Path, requests: list[dict[str, Any]]) -> None:
    """Write Batch request instances as UTF-8 JSON Lines."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for request in requests:
            output_file.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")))
            output_file.write("\n")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="L23", help="Dataset directory under data/keyframes.")
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
    """Create five-frame caption requests for the requested dataset."""
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
        print(f"Skipped {len(skipped_videos)} videos with fewer than five sampled frames")


if __name__ == "__main__":
    main()

