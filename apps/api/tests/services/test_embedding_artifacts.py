from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from app.services.embedding_artifacts import (
    EmbeddingArtifactWriter,
    FrameRecord,
    iter_artifact_shards,
    iter_input_records,
)
from app.services.model_registry import ModelSpec


def test_frame_record_preserves_original_frame_mapping() -> None:
    raw = {
        "file_path": "keyframes/L21/L21_V001/0007.webp",
        "video_path": "keyframes/L21/L21_V001",
        "keyframe_info": {
            "frame_idx": 180,
            "shot_idx": 3,
            "start_time": 5.0,
            "end_time": 7.0,
            "pts_time": 6.0,
            "fps": 30.0,
        },
        "OD_tags": ["person"],
        "RAM_tags": ["person", "street"],
        "watch_url": "https://example.test/watch?v=V1",
    }

    record = FrameRecord.from_mapping(raw)

    assert record.frame_uid == "L21_V001:00000007"
    assert record.frame_index == 7
    assert record.original_frame_idx == 180
    assert record.pts_time == 6.0
    assert record.tags == ("person", "street")
    assert record.youtube_url == "https://example.test/watch?v=V1"
    assert record.as_metadata()["youtube_url"] == "https://example.test/watch?v=V1"


def test_iter_input_records_supports_json_and_jsonl(tmp_path: Path) -> None:
    record = {"file_path": "keyframes/L01/L01_V001/0001.webp"}
    json_path = tmp_path / "frames.json"
    json_path.write_text(json.dumps([record]), encoding="utf-8")
    jsonl_path = tmp_path / "frames.jsonl"
    jsonl_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    assert list(iter_input_records(json_path)) == [record]
    assert list(iter_input_records(jsonl_path)) == [record]


def test_artifact_writer_creates_shards_checksums_and_manifest(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path, spec, shard_size=2)
    records = [
        FrameRecord.from_mapping({"file_path": "keyframes/L01/V1/0001.webp"}),
        FrameRecord.from_mapping({"file_path": "keyframes/L01/V1/0002.webp"}),
        FrameRecord.from_mapping({"file_path": "keyframes/L01/V1/0003.webp"}),
    ]

    writer.append(records[:2], np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    writer.append(records[2:], np.asarray([[0.5, 0.5]], dtype=np.float32))
    manifest_path = writer.finalize()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["total_frames"] == 3
    assert [shard["count"] for shard in manifest["shards"]] == [2, 1]
    assert all(len(shard["embeddings_sha256"]) == 64 for shard in manifest["shards"])
    assert np.load(tmp_path / "fake" / "embeddings-00000.npy").shape == (2, 2)

    shards = list(iter_artifact_shards(manifest_path, verify_checksums=True))
    assert [embeddings.shape for embeddings, _ in shards] == [(2, 2), (1, 2)]
    assert shards[0][1][0]["frame_uid"] == "V1:00000001"


def test_frame_record_explicit_fields_and_validation() -> None:
    record = FrameRecord.from_mapping(
        {
            "frame_uid": "V1:00000002",
            "frame_path": "root/V1/0002.webp",
            "video_id": "V1",
            "frame_index": 2,
            "frame_idx": 60,
            "timestamp": 2.0,
            "fps": 30,
            "tags": ["a", "a", ""],
        }
    )
    assert record.as_metadata()["frame_idx"] == 60
    assert record.as_metadata()["timestamp"] == 2.0
    assert record.tags == ("a",)

    with pytest.raises(ValueError, match="required"):
        FrameRecord.from_mapping({})
    with pytest.raises(ValueError, match="numeric"):
        FrameRecord.from_mapping({"frame_path": "root/V1/not-a-number.webp"})
    with pytest.raises(ValueError, match="keyframe_info"):
        FrameRecord.from_mapping(
            {"frame_path": "root/V1/0001.webp", "keyframe_info": "invalid"}
        )
    with pytest.raises(ValueError, match="tags"):
        FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp", "tags": "person"})
    with pytest.raises(ValueError, match="canonical"):
        FrameRecord.from_mapping(
            {"frame_path": "root/V1/0001.webp", "frame_uid": "wrong"}
        )
    with pytest.raises(ValueError, match="finite"):
        FrameRecord.from_mapping(
            {"frame_path": "root/V1/0001.webp", "pts_time": float("nan")}
        )
    with pytest.raises(ValueError, match="non-negative"):
        FrameRecord.from_mapping(
            {"frame_path": "root/V1/0001.webp", "frame_idx": -1}
        )


def test_input_record_validation(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "bad.jsonl"
    jsonl_path.write_text("\n[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        list(iter_input_records(jsonl_path))

    object_path = tmp_path / "object.json"
    object_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="array"):
        list(iter_input_records(object_path))

    item_path = tmp_path / "items.json"
    item_path.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError, match="objects"):
        list(iter_input_records(item_path))


def test_artifact_writer_guards_output_resume_and_shapes(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    with pytest.raises(ValueError, match="shard_size"):
        EmbeddingArtifactWriter(tmp_path, spec, shard_size=0)

    output_dir = tmp_path / "fake"
    output_dir.mkdir()
    (output_dir / "orphan.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not empty"):
        EmbeddingArtifactWriter(tmp_path, spec)
    with pytest.raises(FileNotFoundError, match="without manifest"):
        EmbeddingArtifactWriter(tmp_path, spec, resume=True)

    (output_dir / "orphan.txt").unlink()
    writer = EmbeddingArtifactWriter(tmp_path, spec)
    record = FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})
    with pytest.raises(ValueError, match="shape"):
        writer.append([record], np.ones((1, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="finite"):
        writer.append([record], np.full((1, 2), np.nan, dtype=np.float32))
    with pytest.raises(ValueError, match="duplicate frame_uid"):
        writer.append(
            [record, record],
            np.ones((2, 2), dtype=np.float32),
        )
    manifest_path = writer.finalize()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["complete"] is True


def test_resume_tracks_processed_ids_and_validates_model(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path, spec, shard_size=1)
    record = FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})
    writer.append([record], np.ones((1, 2), dtype=np.float32))
    writer.finalize()

    resumed = EmbeddingArtifactWriter(tmp_path, spec, resume=True)
    assert resumed.processed_frame_uids == {"V1:00000001"}
    resumed.finalize()

    wrong_id = ModelSpec("other", "fake", "fake/model", 2, "frames_fake")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "manifest.json").write_text(
        (tmp_path / "fake" / "manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different model"):
        EmbeddingArtifactWriter(tmp_path, wrong_id, resume=True)

    manifest = json.loads((tmp_path / "fake" / "manifest.json").read_text(encoding="utf-8"))
    manifest["model"]["dimension"] = 3
    (tmp_path / "fake" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="different embedding"):
        EmbeddingArtifactWriter(tmp_path, spec, resume=True)


def test_resume_rejects_corrupted_existing_shard(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path, spec, shard_size=1)
    record = FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})
    writer.append([record], np.ones((1, 2), dtype=np.float32))
    manifest_path = writer.finalize()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    embeddings_path = manifest_path.parent / manifest["shards"][0]["embeddings_file"]
    embeddings_path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="checksum"):
        EmbeddingArtifactWriter(tmp_path, spec, resume=True)


def test_resume_rejects_different_checkpoint_identity(tmp_path: Path) -> None:
    spec = ModelSpec(
        "fake",
        "fake",
        "fake/model",
        2,
        "frames_fake",
        revision="original",
    )
    writer = EmbeddingArtifactWriter(tmp_path, spec, shard_size=1)
    writer.append(
        [FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})],
        np.ones((1, spec.dimension), dtype=np.float32),
    )
    writer.finalize()

    with pytest.raises(ValueError, match="revision"):
        EmbeddingArtifactWriter(
            tmp_path,
            replace(spec, revision="different"),
            resume=True,
        )


def test_artifact_reader_rejects_manifest_checksum_and_shape_corruption(tmp_path: Path) -> None:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")
    writer = EmbeddingArtifactWriter(tmp_path, spec, shard_size=1)
    record = FrameRecord.from_mapping({"frame_path": "root/V1/0001.webp"})
    writer.append([record], np.ones((1, 2), dtype=np.float32))
    manifest_path = writer.finalize()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    invalid_version = tmp_path / "invalid-version.json"
    invalid_version.write_text(json.dumps({**manifest, "artifact_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        list(iter_artifact_shards(invalid_version))

    invalid_dimension = tmp_path / "invalid-dimension.json"
    bad_dimension = json.loads(json.dumps(manifest))
    bad_dimension["model"]["dimension"] = 0
    invalid_dimension.write_text(json.dumps(bad_dimension), encoding="utf-8")
    with pytest.raises(ValueError, match="dimension"):
        list(iter_artifact_shards(invalid_dimension))

    embeddings_path = manifest_path.parent / manifest["shards"][0]["embeddings_file"]
    embeddings_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="embedding checksum"):
        list(iter_artifact_shards(manifest_path))

    np.save(embeddings_path, np.ones((2, 2), dtype=np.float32), allow_pickle=False)
    with pytest.raises(ValueError, match="shape"):
        list(iter_artifact_shards(manifest_path, verify_checksums=False))
