"""Encode canonical keyframes with one or more configured embedding models.

The output is a resumable, checksummed artifact directory per model. Indexing into
Milvus is intentionally a separate step so inference can run on a GPU machine while
the database runs elsewhere.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.services.embedding_artifacts import (
    EmbeddingArtifactWriter,
    FrameRecord,
    iter_input_records,
)
from app.services.model_registry import ModelRegistry, load_model_specs

LOGGER = logging.getLogger("frameseeker.embed_keyframes")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load_image(images_root: Path, record: FrameRecord) -> Image.Image:
    image_path = Path(record.frame_path)
    if not image_path.is_absolute():
        image_path = images_root / image_path
    with Image.open(image_path) as image:
        return image.convert("RGB").copy()


def embed_model(
    *,
    registry: ModelRegistry,
    model_id: str,
    input_path: Path,
    images_root: Path,
    output_root: Path,
    batch_size: int,
    shard_size: int,
    resume: bool,
    limit: int | None,
    skip_errors: bool,
) -> Path:
    """Run offline image inference for one model and return its artifact manifest."""
    spec = registry.spec(model_id)
    model = registry.get(model_id)
    writer = EmbeddingArtifactWriter(
        output_root,
        spec,
        shard_size=shard_size,
        resume=resume,
    )
    pending_records: list[FrameRecord] = []
    pending_images: list[Image.Image] = []
    accepted = 0

    def flush_batch() -> None:
        if not pending_records:
            return
        embeddings = model.encode_images(list(pending_images))
        writer.append(list(pending_records), embeddings)
        pending_records.clear()
        pending_images.clear()

    for raw_record in iter_input_records(input_path):
        if limit is not None and accepted >= limit:
            break
        try:
            record = FrameRecord.from_mapping(raw_record)
            if record.frame_uid in writer.processed_frame_uids:
                continue
            image = _load_image(images_root, record)
        except (OSError, ValueError, UnidentifiedImageError) as error:
            if not skip_errors:
                raise
            LOGGER.warning("Skipping invalid frame: %s", error)
            continue
        pending_records.append(record)
        pending_images.append(image)
        accepted += 1
        if len(pending_records) >= batch_size:
            flush_batch()
            if accepted % 1_000 == 0:
                LOGGER.info("%s: encoded %d Frames", model_id, accepted)
    flush_batch()
    return writer.finalize()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON/JSONL Frame manifest")
    parser.add_argument(
        "--images-root",
        type=Path,
        default=REPOSITORY_ROOT / "data",
        help="Root used to resolve relative frame_path values",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "ensemble-embeddings",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "ensemble.json",
    )
    parser.add_argument("--model", action="append", dest="models", help="Model id; repeatable")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--shard-size", type=int, default=10_000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-errors", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.shard_size < 1:
        raise ValueError("batch-size and shard-size must be positive")
    specs = load_model_specs(args.config)
    registry = ModelRegistry(specs)
    model_ids = args.models or [spec.model_id for spec in registry.enabled_specs()]
    for model_id in model_ids:
        try:
            manifest = embed_model(
                registry=registry,
                model_id=model_id,
                input_path=args.input,
                images_root=args.images_root,
                output_root=args.output,
                batch_size=args.batch_size,
                shard_size=args.shard_size,
                resume=args.resume,
                limit=args.limit,
                skip_errors=args.skip_errors,
            )
            LOGGER.info("Wrote %s", manifest)
        finally:
            registry.unload(model_id)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
