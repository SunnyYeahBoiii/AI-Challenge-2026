import json
from pathlib import Path

import numpy as np
import pytest

from scripts.embed_qwen_batch1 import (
    EMBEDDING_DIM,
    EmbeddingRunError,
    artifact_paths,
    phase_record_files,
    resolve_frame_path,
    validate_completed_shard,
    write_completed_shard,
)


def write_record(path: Path, frame_paths: list[str]) -> None:
    records = [
        {
            "frame_uid": f"L21_V001:{index:08d}",
            "frame_path": frame_path,
            "video_id": "L21_V001",
        }
        for index, frame_path in enumerate(frame_paths)
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_resolve_frame_path_uses_the_keyframes_prefix(tmp_path: Path) -> None:
    keyframes_root = tmp_path / "keyframes"
    target = keyframes_root / "L21" / "L21_V001" / "10018.webp"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"frame")

    assert resolve_frame_path(keyframes_root, "keyframes/L21/L21_V001/10018.webp") == target

    with pytest.raises(EmbeddingRunError, match="must start"):
        resolve_frame_path(keyframes_root, "L21/L21_V001/10018.webp")


def test_phase_record_files_use_three_primary_ranges(tmp_path: Path) -> None:
    for index in range(146):
        (tmp_path / f"records-{index:05d}.jsonl").write_text("{}\n", encoding="utf-8")

    assert [path.name for path in phase_record_files(tmp_path, 1)] == [
        f"records-{index:05d}.jsonl" for index in range(49)
    ]
    assert [path.name for path in phase_record_files(tmp_path, 3)] == [
        f"records-{index:05d}.jsonl" for index in range(98, 146)
    ]


def test_completed_shard_keeps_record_and_embedding_rows_aligned(tmp_path: Path) -> None:
    records_root = tmp_path / "source-records"
    records_root.mkdir()
    record_file = records_root / "records-00000.jsonl"
    write_record(
        record_file,
        [
            "keyframes/L21/L21_V001/10018.webp",
            "keyframes/L21/L21_V001/10079.webp",
        ],
    )
    values = np.full((2, EMBEDDING_DIM), 1 / np.sqrt(EMBEDDING_DIM), dtype=np.float32)
    output = artifact_paths(tmp_path / "artifact")

    write_completed_shard(
        output,
        record_file,
        values,
        model_path="/models/qwen",
        model_revision="test-revision",
        max_pixels=921600,
        batch_size=1,
    )

    output_record = output.records / record_file.name
    output_embeddings = output.embeddings / "embeddings-00000.npy"
    assert output_record.read_bytes() == record_file.read_bytes()
    assert np.load(output_embeddings, allow_pickle=False).shape == (2, EMBEDDING_DIM)
    assert validate_completed_shard(output, record_file, source_record=record_file, check_norms=True)

    output_record.write_text("{}\n", encoding="utf-8")
    assert not validate_completed_shard(output, record_file, source_record=record_file)
