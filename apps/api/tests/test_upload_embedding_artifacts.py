"""Tests for the Milvus-only embedding artifact loader."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def load_module():
    path = Path(__file__).parents[1] / "scripts" / "upload_embedding_artifacts.py"
    spec = importlib.util.spec_from_file_location("upload_embedding_artifacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_artifact(tmp_path: Path) -> tuple[object, Path]:
    module = load_module()
    root = tmp_path / "artifact"
    for directory in ("records", "embeddings", "status"):
        (root / directory).mkdir(parents=True)
    records = [
        {"video_id": "L21_V001", "frame_idx": 17, "frame_path": "keyframes/L21/L21_V001/17.webp"},
        {"video_id": "L21_V001", "frame_index": 18, "frame_path": "keyframes/L21/L21_V001/18.webp"},
    ]
    record_path = root / "records" / "records-00000.jsonl"
    record_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    np.save(root / "embeddings" / "embeddings-00000.npy", np.ones((2, 3), dtype=np.float16))
    (root / "status" / "status-00000.json").write_text(
        json.dumps({"normalized": True, "embedding_dim": 3, "rows": 2}), encoding="utf-8"
    )
    (root / "manifest.json").write_text(
        json.dumps({"embedding_dim": 3, "normalized": True, "total_frames": 2}), encoding="utf-8"
    )
    return module.ArtifactConfig("test", root, "test_collection", 3), record_path


def test_load_validated_shard_reads_aligned_records_and_embeddings(tmp_path: Path) -> None:
    module = load_module()
    config, record_path = build_artifact(tmp_path)

    records, embeddings = module.load_validated_shard(config, record_path)

    assert len(records) == 2
    assert embeddings.shape == (2, 3)
    assert embeddings.dtype == np.float16


def test_milvus_rows_preserves_metadata_and_casts_embedding_to_float32(tmp_path: Path) -> None:
    module = load_module()
    config, record_path = build_artifact(tmp_path)
    records, embeddings = module.load_validated_shard(config, record_path)

    rows = module.milvus_rows(records, embeddings)

    assert rows[0] == ["L21_V001", "L21_V001"]
    assert rows[3] == [17, 18]
    assert rows[13][0] == [1.0, 1.0, 1.0]


def test_load_validated_shard_rejects_dimension_mismatch(tmp_path: Path) -> None:
    module = load_module()
    config, record_path = build_artifact(tmp_path)
    np.save(config.root / "embeddings" / "embeddings-00000.npy", np.ones((2, 2), dtype=np.float16))

    try:
        module.load_validated_shard(config, record_path)
    except ValueError as error:
        assert "expected (2, 3)" in str(error)
    else:
        raise AssertionError("Expected dimension validation to fail")


def test_append_rows_combines_shards_by_column(tmp_path: Path) -> None:
    module = load_module()
    config, record_path = build_artifact(tmp_path)
    records, embeddings = module.load_validated_shard(config, record_path)
    first = module.milvus_rows(records[:1], embeddings[:1])
    second = module.milvus_rows(records[1:], embeddings[1:])

    module.append_rows(first, second)

    assert len(first[0]) == 2
    assert first[3] == [17, 18]
    assert len(first[13]) == 2
