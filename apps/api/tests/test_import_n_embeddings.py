import json
from pathlib import Path

import numpy as np
import pytest

from scripts.import_n_embeddings import (
    canonical_frame_path,
    iter_embedding_shards,
    validate_artifacts,
)


def _write_shard(
    records_dir: Path,
    embeddings_dir: Path,
    stem: str,
    records: list[dict[str, object]],
    embeddings: np.ndarray,
) -> None:
    records_dir.mkdir(parents=True, exist_ok=True)
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"{stem}-records-00000.jsonl"
    record_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    np.save(embeddings_dir / f"{stem}-embeddings-00000.npy", embeddings)


def test_canonical_frame_path_keeps_full_n_level() -> None:
    assert canonical_frame_path("N021-V001", 25) == "keyframes/N021/N021-V001/25.webp"


def test_iter_embedding_shards_pairs_every_n_artifact(tmp_path: Path) -> None:
    records_dir = tmp_path / "records"
    embeddings_dir = tmp_path / "embeddings"
    _write_shard(
        records_dir,
        embeddings_dir,
        "n-part1",
        [{"video_id": "N001-V001", "frame_index": 0}],
        np.zeros((1, 1024), dtype=np.float32),
    )

    shards = list(iter_embedding_shards(records_dir, embeddings_dir))

    assert [(records.name, embeddings.name) for records, embeddings in shards] == [
        ("n-part1-records-00000.jsonl", "n-part1-embeddings-00000.npy")
    ]


def test_validate_artifacts_checks_rows_vectors_and_keyframes(tmp_path: Path) -> None:
    records_dir = tmp_path / "records"
    embeddings_dir = tmp_path / "embeddings"
    keyframes_dir = tmp_path / "keyframes"
    records = [
        {"video_id": "N001-V001", "frame_index": 0},
        {"video_id": "N001-V001", "frame_index": 25},
    ]
    _write_shard(
        records_dir,
        embeddings_dir,
        "n-part1",
        records,
        np.zeros((2, 1024), dtype=np.float32),
    )
    for frame_index in (0, 25):
        path = keyframes_dir / "N001" / "N001-V001" / f"{frame_index}.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert validate_artifacts(records_dir, embeddings_dir, keyframes_dir) == 2

    (keyframes_dir / "N001/N001-V001/25.webp").unlink()
    with pytest.raises(FileNotFoundError, match="Missing keyframe"):
        validate_artifacts(records_dir, embeddings_dir, keyframes_dir)
