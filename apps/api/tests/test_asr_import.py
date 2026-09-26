import json
from pathlib import Path

import pytest

from scripts.import_asr_dataset import (
    AsrRecord,
    asr_document,
    build_es_bulk_body,
    canonical_frame_path,
    embedding_path_for_record,
    load_asr_records,
    validate_keyframes,
)


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def test_load_asr_records_keeps_repeated_text_per_frame_and_skips_n(tmp_path: Path) -> None:
    repeated = "đây là context được lặp lại"
    _write_records(
        tmp_path / "M01" / "M01_V001.json",
        [
            {"video_id": "M01_V001", "frame_idx": 383, "audio_text": repeated},
            {"video_id": "M01_V001", "frame_idx": 415, "audio_text": repeated},
        ],
    )
    _write_records(
        tmp_path / "S01" / "S01-V001.json",
        [{"video_id": "S01-V001", "frame_idx": 1074, "audio_text": "đua xe"}],
    )
    _write_records(
        tmp_path / "N021" / "N021-V001.json",
        [{"video_id": "N021-V001", "frame_idx": 1, "audio_text": ""}],
    )

    records = load_asr_records(tmp_path)

    assert set(records) == {
        ("M01_V001", 383),
        ("M01_V001", 415),
        ("S01-V001", 1074),
    }
    assert records[("M01_V001", 383)].audio_text == repeated
    assert records[("M01_V001", 415)].audio_text == repeated


def test_load_asr_records_rejects_file_video_id_mismatch(tmp_path: Path) -> None:
    _write_records(
        tmp_path / "M01" / "M01_V001.json",
        [{"video_id": "M01_V002", "frame_idx": 1, "audio_text": "text"}],
    )

    with pytest.raises(ValueError, match="does not match file"):
        load_asr_records(tmp_path)


def test_load_asr_records_rejects_duplicate_frame_key(tmp_path: Path) -> None:
    duplicate = {"video_id": "M01_V001", "frame_idx": 383, "audio_text": "text"}
    _write_records(tmp_path / "M01" / "M01_V001.json", [duplicate, duplicate])

    with pytest.raises(ValueError, match="Duplicate ASR frame"):
        load_asr_records(tmp_path)


def test_asr_document_uses_frame_identity_and_preserves_vietnamese() -> None:
    record = AsrRecord(
        video_id="M01_V001",
        frame_idx=383,
        audio_text="  Chương   Trình Sáu Mươi Giây  ",
    )

    assert asr_document(record) == {
        "frame_key": "M01_V001:383",
        "video_id": "M01_V001",
        "video_path": "keyframes/M01/M01_V001",
        "frame_id": 383,
        "frame_idx": 383,
        "frame_path": "keyframes/M01/M01_V001/383.webp",
        "asr_text": "chương trình sáu mươi giây",
    }


def test_es_bulk_uses_partial_update_without_touching_ocr() -> None:
    record = AsrRecord("S01-V001", 1074, "ghiền mì gõ")

    body = build_es_bulk_body([record], "video_texts_v1")

    assert body == [
        {
            "update": {
                "_index": "video_texts_v1",
                "_id": "S01-V001:1074",
            }
        },
        {
            "doc": asr_document(record),
            "doc_as_upsert": True,
        },
    ]
    assert "ocr_text" not in body[1]["doc"]


def test_canonical_frame_path_uses_video_level() -> None:
    assert canonical_frame_path("S01-V001", 1074) == "keyframes/S01/S01-V001/1074.webp"


def test_embedding_path_matches_record_shard_name(tmp_path: Path) -> None:
    record_path = tmp_path / "media" / "ms-s01-records-00056.jsonl"

    assert embedding_path_for_record(record_path, tmp_path / "embeddings") == (
        tmp_path / "embeddings" / "ms-s01-embeddings-00056.npy"
    )
def test_validate_keyframes_requires_every_asr_frame(tmp_path: Path) -> None:
    records = {
        ("M01_V001", 383): AsrRecord("M01_V001", 383, "text"),
        ("S01-V001", 1074): AsrRecord("S01-V001", 1074, "text"),
    }
    for video_id, frame_idx in records:
        path = tmp_path / video_id[:3] / video_id / f"{frame_idx}.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    validate_keyframes(records, tmp_path)

    (tmp_path / "S01/S01-V001/1074.webp").unlink()

    with pytest.raises(FileNotFoundError, match="Missing keyframes"):
        validate_keyframes(records, tmp_path)
