from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.services.embedding_artifacts import EmbeddingArtifactWriter, FrameRecord
from app.services.model_registry import ModelSpec
from scripts import load_ensemble_embeddings as loader
from scripts.load_ensemble_embeddings import _columns, load_artifact, load_artifacts


def _config(path: Path, spec: ModelSpec) -> Path:
    config_path = path / "ensemble.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": spec.model_id,
                        "adapter": spec.adapter,
                        "model_name": spec.model_name,
                        "pretrained": spec.pretrained,
                        "revision": spec.revision,
                        "dtype": spec.dtype,
                        "dimension": spec.dimension,
                        "collection": spec.collection,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _multi_config(path: Path, specs: list[ModelSpec]) -> Path:
    config_path = path / "ensemble.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": spec.model_id,
                        "adapter": spec.adapter,
                        "model_name": spec.model_name,
                        "dimension": spec.dimension,
                        "collection": spec.collection,
                        "enabled": True,
                    }
                    for spec in specs
                ]
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _artifact(path: Path, spec: ModelSpec, frame_indices: list[int]) -> Path:
    writer = EmbeddingArtifactWriter(path, spec, shard_size=1)
    records = [
        FrameRecord.from_mapping(
            {
                "frame_path": f"root/V1/{frame_index:04d}.webp",
                "frame_index": frame_index,
            }
        )
        for frame_index in frame_indices
    ]
    writer.append(
        records,
        np.ones((len(records), spec.dimension), dtype=np.float32),
    )
    return writer.finalize()


def test_artifact_loader_dry_run_validates_real_shards_end_to_end(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path / "artifacts", spec, shard_size=1)
    records = [
        FrameRecord.from_mapping(
            {
                "frame_path": "keyframes/L01/V1/0001.webp",
                "frame_idx": 30,
                "fps": 30.0,
                "pts_time": 1.0,
            }
        ),
        FrameRecord.from_mapping(
            {
                "frame_path": "keyframes/L01/V1/0002.webp",
                "frame_idx": 60,
                "fps": 30.0,
                "pts_time": 2.0,
            }
        ),
    ]
    writer.append(records, np.eye(2, dtype=np.float32))
    manifest_path = writer.finalize()

    loaded = load_artifact(
        manifest_path=manifest_path,
        config_path=_config(tmp_path, spec),
        insert_batch_size=1,
        verify_checksums=True,
        recreate=False,
        dry_run=True,
    )

    assert loaded == 2


def test_multi_model_loader_rejects_mismatched_galleries_before_database_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = [
        ModelSpec("a", "fake", "a", 2, "frames_a"),
        ModelSpec("b", "fake", "b", 2, "frames_b"),
    ]
    manifests = [
        _artifact(tmp_path / "artifacts-a", specs[0], [1, 2]),
        _artifact(tmp_path / "artifacts-b", specs[1], [1, 3]),
    ]
    database_calls: list[object] = []
    monkeypatch.setattr(
        loader,
        "ensure_model_collection",
        lambda *args, **kwargs: database_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="gallery Frame set"):
        load_artifacts(
            manifest_paths=manifests,
            config_path=_multi_config(tmp_path, specs),
            insert_batch_size=1,
            verify_checksums=True,
            recreate=False,
            dry_run=False,
        )

    assert database_calls == []


def test_loader_rejects_stale_collection_rows_before_upsert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    manifest_path = _artifact(tmp_path / "artifacts", spec, [1])

    class StaleCollection:
        num_entities = 1
        upsert_calls: list[object] = []

        def load(self) -> None:
            return None

        def query_iterator(self, **kwargs: object) -> object:
            del kwargs
            batches = [[{"frame_uid": "V1:00000099"}]]

            class Iterator:
                def next(self) -> list[dict[str, str]]:
                    return batches.pop(0) if batches else []

                def close(self) -> None:
                    return None

            return Iterator()

        def upsert(self, columns: object) -> None:
            self.upsert_calls.append(columns)

    collection = StaleCollection()
    monkeypatch.setattr(loader, "ensure_model_collection", lambda *args, **kwargs: collection)

    with pytest.raises(ValueError, match="stale Frames"):
        load_artifact(
            manifest_path=manifest_path,
            config_path=_config(tmp_path, spec),
            insert_batch_size=1,
            verify_checksums=True,
            recreate=False,
            dry_run=False,
        )

    assert collection.upsert_calls == []


def test_loader_columns_reject_duplicate_ids_and_validate_batch_size(tmp_path: Path) -> None:
    records = [
        {
            "frame_uid": "V1:00000001",
            "video_id": "V1",
            "frame_path": "root/V1/0001.webp",
            "frame_index": 1,
            "tags": ["x" * 100],
        },
        {
            "frame_uid": "V1:00000001",
            "video_id": "V1",
            "frame_path": "root/V1/0001.webp",
            "frame_index": 1,
            "tags": [],
        },
    ]
    with pytest.raises(ValueError, match="duplicate"):
        _columns(records, np.ones((2, 2), dtype=np.float32))

    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path / "artifacts", spec)
    manifest_path = writer.finalize()
    with pytest.raises(ValueError, match="insert_batch_size"):
        load_artifact(
            manifest_path=manifest_path,
            config_path=_config(tmp_path, spec),
            insert_batch_size=0,
            verify_checksums=True,
            recreate=False,
            dry_run=True,
        )


def test_loader_columns_reject_data_that_milvus_cannot_insert() -> None:
    record = {
        "frame_uid": "V1:00000001",
        "video_id": "V1",
        "video_path": "root/V1",
        "frame_path": "root/V1/0001.webp",
        "frame_index": 1,
    }
    with pytest.raises(ValueError, match="counts"):
        _columns([record], np.ones((0, 2), dtype=np.float32))
    with pytest.raises(ValueError, match="finite"):
        _columns([record], np.full((1, 2), np.nan, dtype=np.float32))
    with pytest.raises(ValueError, match="video_path"):
        _columns(
            [{**record, "video_path": "x" * 501}],
            np.ones((1, 2), dtype=np.float32),
        )


def test_loader_preflights_complete_compatible_artifact_before_database_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake", revision="rev-a")
    writer = EmbeddingArtifactWriter(tmp_path / "artifacts", spec, shard_size=1)
    record = FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})
    writer.append([record], np.ones((1, 2), dtype=np.float32))
    manifest_path = writer.finalize()
    config_path = _config(tmp_path, spec)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["models"][0]["revision"] = "rev-a"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["complete"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    database_calls: list[object] = []
    monkeypatch.setattr(
        loader,
        "ensure_model_collection",
        lambda *args, **kwargs: database_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="incomplete"):
        load_artifact(
            manifest_path=manifest_path,
            config_path=config_path,
            insert_batch_size=1,
            verify_checksums=True,
            recreate=True,
            dry_run=False,
        )

    assert database_calls == []


def test_loader_rejects_checkpoint_revision_mismatch(tmp_path: Path) -> None:
    artifact_spec = ModelSpec(
        "fake", "fake", "fake/model", 2, "frames_fake", revision="artifact-revision"
    )
    writer = EmbeddingArtifactWriter(tmp_path / "artifacts", artifact_spec)
    manifest_path = writer.finalize()
    configured_spec = ModelSpec(
        "fake", "fake", "fake/model", 2, "frames_fake", revision="configured-revision"
    )

    with pytest.raises(ValueError, match="revision"):
        load_artifact(
            manifest_path=manifest_path,
            config_path=_config(tmp_path, configured_spec),
            insert_batch_size=1,
            verify_checksums=True,
            recreate=False,
            dry_run=True,
        )
