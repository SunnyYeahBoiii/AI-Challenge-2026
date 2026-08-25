"""Create resumable Qwen3-VL-Embedding artifacts for AI Challenge Batch-1.

This runner is designed for a Kaggle notebook with two attached input datasets:
keyframes and Batch-1 records.  It deliberately keeps every embedding shard aligned
with a byte-for-byte copy of its source ``records-xxxxx.jsonl`` file.
"""

from __future__ import annotations

import argparse
import importlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence, cast

import numpy as np

EMBEDDING_DIM = 2048
EMBEDDING_DTYPE = np.dtype(np.float16)
MANIFEST_VERSION = 1
PHASE_RANGES: dict[int, tuple[int, int]] = {
    1: (0, 48),
    2: (49, 97),
    3: (98, 145),
}
DEFAULT_INSTRUCTION = "Represent the user's input."


class EmbeddingRunError(RuntimeError):
    """Raised when an input or generated embedding artifact is invalid."""


@dataclass(frozen=True)
class ArtifactPaths:
    """Paths used by one Batch-1 embedding artifact."""

    root: Path
    embeddings: Path
    records: Path
    status: Path
    claims: Path
    logs: Path


def artifact_paths(output_root: Path, *, create: bool = True) -> ArtifactPaths:
    """Return artifact paths and optionally create the writable directories."""
    paths = ArtifactPaths(
        root=output_root,
        embeddings=output_root / "embeddings",
        records=output_root / "records",
        status=output_root / "status",
        claims=output_root / "claims",
        logs=output_root / "logs",
    )
    if create:
        for path in (
            paths.root,
            paths.embeddings,
            paths.records,
            paths.status,
            paths.claims,
            paths.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)
    return paths


def sha256_file(path: Path) -> str:
    """Calculate the SHA-256 hash of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted sessions never produce valid-looking state."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def atomic_copy(source: Path, destination: Path) -> None:
    """Copy a file atomically."""
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def atomic_save_npy(path: Path, values: np.ndarray) -> None:
    """Save an NPY array atomically."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, values, allow_pickle=False)
    temporary.replace(path)


def record_files(records_root: Path) -> list[Path]:
    """Return all Batch-1 record shards in their canonical lexical order."""
    files = sorted(records_root.glob("records-*.jsonl"))
    if not files:
        raise EmbeddingRunError(f"No records-*.jsonl files found in {records_root}")
    return files


def phase_record_files(records_root: Path, phase: int) -> list[Path]:
    """Return the record files owned by one primary Kaggle phase."""
    if phase not in PHASE_RANGES:
        raise EmbeddingRunError(f"Unknown phase {phase}; expected one of {sorted(PHASE_RANGES)}")
    files = record_files(records_root)
    start, end = PHASE_RANGES[phase]
    if len(files) <= end:
        raise EmbeddingRunError(
            f"Phase {phase} expects at least {end + 1} record shards, found {len(files)}"
        )
    return files[start : end + 1]


def record_output_name(record_file: Path) -> str:
    """Return the output embedding filename corresponding to one record filename."""
    return record_file.name.replace("records-", "embeddings-").replace(".jsonl", ".npy")


def status_output_name(record_file: Path) -> str:
    """Return the output status filename corresponding to one record filename."""
    return record_file.name.replace("records-", "status-").replace(".jsonl", ".json")


def resolve_frame_path(keyframes_root: Path, frame_path: str) -> Path:
    """Resolve a record's ``keyframes/...`` path safely against the Kaggle keyframe root."""
    normalized = frame_path.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if not relative.parts or relative.parts[0] != "keyframes":
        raise EmbeddingRunError(f"frame_path must start with 'keyframes/': {frame_path!r}")
    if ".." in relative.parts:
        raise EmbeddingRunError(f"frame_path may not contain '..': {frame_path!r}")
    resolved = keyframes_root.joinpath(*relative.parts[1:])
    if not resolved.is_file():
        raise EmbeddingRunError(f"Missing keyframe for record path {frame_path!r}: {resolved}")
    return resolved


def load_records(record_file: Path, keyframes_root: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    """Read records and their image paths while preserving record order exactly."""
    records: list[dict[str, Any]] = []
    image_paths: list[Path] = []
    with record_file.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise EmbeddingRunError(f"Invalid JSON in {record_file}:{line_number}") from error
            frame_uid = record.get("frame_uid")
            frame_path = record.get("frame_path")
            if not isinstance(frame_uid, str) or not frame_uid:
                raise EmbeddingRunError(f"Missing frame_uid in {record_file}:{line_number}")
            if not isinstance(frame_path, str) or not frame_path:
                raise EmbeddingRunError(f"Missing frame_path in {record_file}:{line_number} ({frame_uid})")
            records.append(record)
            image_paths.append(resolve_frame_path(keyframes_root, frame_path))
    if not records:
        raise EmbeddingRunError(f"Record shard is empty: {record_file}")
    return records, image_paths


def output_paths(paths: ArtifactPaths, record_file: Path) -> tuple[Path, Path, Path]:
    """Return embedding, record and status output paths for a source record shard."""
    return (
        paths.embeddings / record_output_name(record_file),
        paths.records / record_file.name,
        paths.status / status_output_name(record_file),
    )


def validate_completed_shard(
    paths: ArtifactPaths,
    record_file: Path,
    *,
    source_record: Path | None = None,
    check_norms: bool = False,
) -> bool:
    """Return whether a completed shard is structurally and cryptographically valid."""
    embedding_path, record_path, status_path = output_paths(paths, record_file)
    if not embedding_path.is_file() or not record_path.is_file() or not status_path.is_file():
        return False
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        values = np.load(embedding_path, allow_pickle=False, mmap_mode="r")
    except (json.JSONDecodeError, OSError, ValueError):
        return False
    if values.ndim != 2 or values.shape[1] != EMBEDDING_DIM or values.dtype != EMBEDDING_DTYPE:
        return False
    with record_path.open(encoding="utf-8") as handle:
        line_count = sum(1 for _ in handle)
    if line_count != values.shape[0] or int(status.get("record_count", -1)) != line_count:
        return False
    if status.get("record_sha256") != sha256_file(record_path):
        return False
    if status.get("embedding_sha256") != sha256_file(embedding_path):
        return False
    if source_record is not None and status.get("source_record_sha256") != sha256_file(source_record):
        return False
    if check_norms:
        sample = np.asarray(values[: min(len(values), 32)], dtype=np.float32)
        if not np.isfinite(sample).all():
            return False
        norms = np.linalg.norm(sample, axis=1)
        if not np.all((norms > 0.98) & (norms < 1.02)):
            return False
    return True


def write_completed_shard(
    paths: ArtifactPaths,
    record_file: Path,
    values: np.ndarray,
    *,
    model_path: str,
    model_revision: str,
    max_pixels: int,
    batch_size: int,
) -> None:
    """Write one verified embedding shard and its matching record copy atomically."""
    with record_file.open(encoding="utf-8") as handle:
        source_line_count = sum(1 for _ in handle)
    if values.shape != (source_line_count, EMBEDDING_DIM):
        raise EmbeddingRunError(
            f"Embedding shape {values.shape} does not match {record_file.name} ({source_line_count} rows)"
        )
    values = np.asarray(values, dtype=EMBEDDING_DTYPE)
    if not np.isfinite(values).all():
        raise EmbeddingRunError(f"Non-finite embeddings generated for {record_file.name}")
    embedding_path, output_record_path, status_path = output_paths(paths, record_file)
    atomic_save_npy(embedding_path, values)
    atomic_copy(record_file, output_record_path)
    status = {
        "schema_version": MANIFEST_VERSION,
        "status": "complete",
        "source_record": record_file.name,
        "record_file": output_record_path.name,
        "embedding_file": embedding_path.name,
        "record_count": source_line_count,
        "embedding_dim": EMBEDDING_DIM,
        "embedding_dtype": str(EMBEDDING_DTYPE),
        "normalized": True,
        "source_record_sha256": sha256_file(record_file),
        "record_sha256": sha256_file(output_record_path),
        "embedding_sha256": sha256_file(embedding_path),
        "model_path": model_path,
        "model_revision": model_revision,
        "max_pixels": max_pixels,
        "batch_size": batch_size,
        "completed_at_unix": time.time(),
    }
    atomic_write_json(status_path, status)
    if not validate_completed_shard(paths, record_file, source_record=record_file, check_norms=True):
        raise EmbeddingRunError(f"Generated artifact validation failed for {record_file.name}")


def try_claim(paths: ArtifactPaths, record_file: Path) -> bool:
    """Atomically claim a shard so exactly one GPU worker processes it."""
    claim_path = paths.claims / f"{record_file.stem}.claim"
    try:
        descriptor = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "claimed_at_unix": time.time()}, handle)
    return True


def reset_claims(paths: ArtifactPaths) -> None:
    """Remove stale claims left by a previously stopped Kaggle session."""
    for claim_path in paths.claims.glob("*.claim"):
        claim_path.unlink()


def import_qwen_embedder(qwen_repo: Path) -> type[Any]:
    """Load the official Qwen implementation only inside a GPU worker process."""
    repository = str(qwen_repo.resolve())
    if repository not in sys.path:
        sys.path.insert(0, repository)
    try:
        module = importlib.import_module("src.models.qwen3_vl_embedding")
    except ImportError as error:
        raise EmbeddingRunError(
            f"Could not import official Qwen code from {qwen_repo}; clone Qwen3-VL-Embedding first"
        ) from error
    return cast(type[Any], getattr(module, "Qwen3VLEmbedder"))


def build_embedder(
    qwen_repo: Path,
    model_path: Path,
    max_pixels: int,
    attention_implementation: str,
) -> Any:
    """Instantiate the official Qwen embedder on the CUDA device visible to this process."""
    import torch

    embedder_class = import_qwen_embedder(qwen_repo)
    return embedder_class(
        model_name_or_path=str(model_path),
        max_pixels=max_pixels,
        torch_dtype=torch.float16,
        attn_implementation=attention_implementation,
        local_files_only=True,
    )


def encode_images(embedder: Any, image_paths: Sequence[Path], batch_size: int) -> np.ndarray:
    """Encode image paths in order, retaining the input-to-output row mapping."""
    chunks: list[np.ndarray] = []
    for start in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[start : start + batch_size]
        inputs = [{"image": str(path)} for path in batch_paths]
        try:
            embeddings = embedder.process(inputs)
        except RuntimeError as error:
            if "out of memory" not in str(error).lower() or len(batch_paths) == 1:
                raise
            import torch

            torch.cuda.empty_cache()
            embeddings = embedder.process([{"image": str(path)} for path in batch_paths[:1]])
            remainder = encode_images(embedder, batch_paths[1:], batch_size=1)
            first = embeddings.detach().float().cpu().numpy()
            chunks.extend([first, remainder])
            continue
        values = embeddings.detach().float().cpu().numpy()
        if values.shape != (len(batch_paths), EMBEDDING_DIM):
            raise EmbeddingRunError(
                f"Qwen returned shape {values.shape}; expected ({len(batch_paths)}, {EMBEDDING_DIM})"
            )
        chunks.append(values)
    return np.concatenate(chunks, axis=0)


def choose_batch_size(embedder: Any, probe_paths: Sequence[Path], requested: str) -> int:
    """Use the requested batch size or safely probe two images for the automatic mode."""
    if requested in {"1", "2"}:
        return int(requested)
    if len(probe_paths) < 2:
        return 1
    try:
        probe = encode_images(embedder, probe_paths[:2], batch_size=2)
        if probe.shape == (2, EMBEDDING_DIM):
            return 2
    except RuntimeError as error:
        if "out of memory" not in str(error).lower():
            raise
        import torch

        torch.cuda.empty_cache()
    return 1


def worker(args: argparse.Namespace) -> int:
    """Run one GPU worker that claims and embeds pending shards for a phase."""
    keyframes_root = Path(args.keyframes_root)
    records_root = Path(args.records_root)
    paths = artifact_paths(Path(args.output_root))
    candidates = phase_record_files(records_root, args.phase)
    embedder: Any | None = None
    batch_size: int | None = None
    completed = 0
    for record_file in candidates:
        if time.time() >= args.deadline_unix:
            break
        if validate_completed_shard(paths, record_file, source_record=record_file):
            continue
        if not try_claim(paths, record_file):
            continue
        try:
            records, image_paths = load_records(record_file, keyframes_root)
            if embedder is None:
                embedder = build_embedder(
                    Path(args.qwen_repo),
                    Path(args.model_path),
                    args.max_pixels,
                    args.attention_implementation,
                )
                batch_size = choose_batch_size(embedder, image_paths, args.batch_size)
                print(f"Worker {args.worker_name}: using batch size {batch_size}", flush=True)
            if batch_size is None:
                raise EmbeddingRunError("Batch size was not initialized")
            values = encode_images(embedder, image_paths, batch_size)
            if len(records) != len(values):
                raise EmbeddingRunError(f"Input/output count mismatch for {record_file.name}")
            write_completed_shard(
                paths,
                record_file,
                values,
                model_path=args.model_path,
                model_revision=args.model_revision,
                max_pixels=args.max_pixels,
                batch_size=batch_size,
            )
            completed += 1
            print(f"Worker {args.worker_name}: completed {record_file.name}", flush=True)
        except Exception as error:
            error_path = paths.logs / f"{record_file.stem}.error.json"
            atomic_write_json(
                error_path,
                {
                    "record_file": record_file.name,
                    "worker": args.worker_name,
                    "error": repr(error),
                    "failed_at_unix": time.time(),
                },
            )
            raise
    print(f"Worker {args.worker_name}: completed {completed} shard(s)", flush=True)
    return 0


def partial_manifest(paths: ArtifactPaths, records_root: Path, phase: int) -> dict[str, Any]:
    """Build a manifest for completed artifacts without requiring every phase to be done."""
    entries: list[dict[str, Any]] = []
    for record_file in record_files(records_root):
        if validate_completed_shard(paths, record_file, source_record=record_file):
            status_path = output_paths(paths, record_file)[2]
            entries.append(json.loads(status_path.read_text(encoding="utf-8")))
    return {
        "schema_version": MANIFEST_VERSION,
        "kind": "qwen3-vl-embedding-batch1-partial",
        "phase": phase,
        "embedding_dim": EMBEDDING_DIM,
        "embedding_dtype": str(EMBEDDING_DTYPE),
        "normalized": True,
        "completed_shards": len(entries),
        "completed_frames": sum(int(entry["record_count"]) for entry in entries),
        "shards": entries,
        "generated_at_unix": time.time(),
    }


def orchestrate(args: argparse.Namespace) -> int:
    """Launch two single-GPU workers and persist a phase checkpoint after they exit."""
    paths = artifact_paths(Path(args.output_root))
    reset_claims(paths)
    deadline_unix = time.time() + args.deadline_minutes * 60
    worker_base = [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--keyframes-root",
        args.keyframes_root,
        "--records-root",
        args.records_root,
        "--output-root",
        args.output_root,
        "--qwen-repo",
        args.qwen_repo,
        "--model-path",
        args.model_path,
        "--phase",
        str(args.phase),
        "--deadline-unix",
        str(deadline_unix),
        "--batch-size",
        args.batch_size,
        "--max-pixels",
        str(args.max_pixels),
        "--attention-implementation",
        args.attention_implementation,
        "--model-revision",
        args.model_revision,
    ]
    processes: list[subprocess.Popen[bytes]] = []
    log_handles: list[Any] = []
    for gpu_index in (0, 1):
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        command = worker_base + ["--worker-name", f"gpu-{gpu_index}"]
        log_file = (paths.logs / f"phase-{args.phase}-gpu-{gpu_index}.log").open("w", encoding="utf-8")
        log_handles.append(log_file)
        processes.append(subprocess.Popen(command, env=environment, stdout=log_file, stderr=subprocess.STDOUT))
    failures = [process.wait() for process in processes]
    for log_handle in log_handles:
        log_handle.close()
    manifest = partial_manifest(paths, Path(args.records_root), args.phase)
    atomic_write_json(paths.root / "partial-manifest.json", manifest)
    if any(code != 0 for code in failures):
        raise EmbeddingRunError(f"At least one worker failed: exit codes {failures}")
    print(
        f"READY_TO_SAVE phase={args.phase} completed_shards={manifest['completed_shards']} "
        f"completed_frames={manifest['completed_frames']}",
        flush=True,
    )
    return 0


def bootstrap(args: argparse.Namespace) -> int:
    """Copy valid artifacts from a prior Notebook Output before a Kaggle resume run."""
    previous = artifact_paths(Path(args.previous_output_root), create=False)
    current = artifact_paths(Path(args.output_root))
    records_root = Path(args.records_root)
    copied = 0
    for record_file in record_files(records_root):
        if not validate_completed_shard(previous, record_file, source_record=record_file):
            continue
        if validate_completed_shard(current, record_file, source_record=record_file):
            continue
        for source, destination in zip(output_paths(previous, record_file), output_paths(current, record_file)):
            atomic_copy(source, destination)
        if not validate_completed_shard(current, record_file, source_record=record_file):
            raise EmbeddingRunError(f"Copied artifact did not validate for {record_file.name}")
        copied += 1
    print(f"Bootstrapped {copied} completed shard(s)", flush=True)
    return 0


def preflight(args: argparse.Namespace) -> int:
    """Validate the complete record-to-keyframe mapping before expensive inference."""
    keyframes_root = Path(args.keyframes_root)
    records_root = Path(args.records_root)
    if not keyframes_root.is_dir():
        raise EmbeddingRunError(f"Keyframe root does not exist: {keyframes_root}")
    if not records_root.is_dir():
        raise EmbeddingRunError(f"Records root does not exist: {records_root}")
    if args.sample_keyframe and not Path(args.sample_keyframe).is_file():
        raise EmbeddingRunError(f"Sample keyframe does not exist: {args.sample_keyframe}")
    total = 0
    for record_file in record_files(records_root):
        records, _ = load_records(record_file, keyframes_root)
        total += len(records)
    print(f"Preflight passed: {len(record_files(records_root))} shards, {total} frames", flush=True)
    return 0


def finalize(args: argparse.Namespace) -> int:
    """Validate all shards and create the final portable ZIP artifact."""
    output_root = Path(args.output_root)
    paths = artifact_paths(output_root)
    records_root = Path(args.records_root)
    statuses: list[dict[str, Any]] = []
    for record_file in record_files(records_root):
        if not validate_completed_shard(paths, record_file, source_record=record_file, check_norms=True):
            raise EmbeddingRunError(f"Incomplete or invalid output shard: {record_file.name}")
        statuses.append(json.loads(output_paths(paths, record_file)[2].read_text(encoding="utf-8")))
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "kind": "qwen3-vl-embedding-batch1",
        "model": {
            "id": "Qwen/Qwen3-VL-Embedding-2B",
            "revision": args.model_revision,
            "default_instruction": DEFAULT_INSTRUCTION,
        },
        "embedding_dim": EMBEDDING_DIM,
        "embedding_dtype": str(EMBEDDING_DTYPE),
        "normalized": True,
        "max_pixels": args.max_pixels,
        "total_frames": sum(int(status["record_count"]) for status in statuses),
        "total_shards": len(statuses),
        "shards": statuses,
        "generated_at_unix": time.time(),
    }
    manifest_path = output_root / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    zip_path = output_root.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for directory in (paths.embeddings, paths.records, paths.status):
            for file_path in sorted(directory.iterdir()):
                archive.write(file_path, file_path.relative_to(output_root))
        archive.write(manifest_path, manifest_path.name)
    print(f"Finalized {manifest['total_frames']} frames into {zip_path}", flush=True)
    return 0


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by the preflight and embedding commands."""
    parser.add_argument("--keyframes-root", required=True)
    parser.add_argument("--records-root", required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    add_common_arguments(preflight_parser)
    preflight_parser.add_argument("--sample-keyframe")
    preflight_parser.set_defaults(func=preflight)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--records-root", required=True)
    bootstrap_parser.add_argument("--previous-output-root", required=True)
    bootstrap_parser.add_argument("--output-root", required=True)
    bootstrap_parser.set_defaults(func=bootstrap)

    worker_parser = subparsers.add_parser("worker")
    add_common_arguments(worker_parser)
    worker_parser.add_argument("--output-root", required=True)
    worker_parser.add_argument("--qwen-repo", required=True)
    worker_parser.add_argument("--model-path", required=True)
    worker_parser.add_argument("--phase", required=True, type=int)
    worker_parser.add_argument("--deadline-unix", required=True, type=float)
    worker_parser.add_argument("--worker-name", required=True)
    worker_parser.add_argument("--batch-size", choices=("auto", "1", "2"), default="auto")
    worker_parser.add_argument("--max-pixels", type=int, default=921600)
    worker_parser.add_argument("--attention-implementation", default="sdpa")
    worker_parser.add_argument("--model-revision", default="main")
    worker_parser.set_defaults(func=worker)

    orchestrate_parser = subparsers.add_parser("orchestrate")
    add_common_arguments(orchestrate_parser)
    orchestrate_parser.add_argument("--output-root", required=True)
    orchestrate_parser.add_argument("--qwen-repo", required=True)
    orchestrate_parser.add_argument("--model-path", required=True)
    orchestrate_parser.add_argument("--phase", required=True, type=int)
    orchestrate_parser.add_argument("--deadline-minutes", type=int, default=630)
    orchestrate_parser.add_argument("--batch-size", choices=("auto", "1", "2"), default="auto")
    orchestrate_parser.add_argument("--max-pixels", type=int, default=921600)
    orchestrate_parser.add_argument("--attention-implementation", default="sdpa")
    orchestrate_parser.add_argument("--model-revision", default="main")
    orchestrate_parser.set_defaults(func=orchestrate)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--records-root", required=True)
    finalize_parser.add_argument("--output-root", required=True)
    finalize_parser.add_argument("--max-pixels", type=int, default=921600)
    finalize_parser.add_argument("--model-revision", default="main")
    finalize_parser.set_defaults(func=finalize)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested artifact-management command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except EmbeddingRunError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
