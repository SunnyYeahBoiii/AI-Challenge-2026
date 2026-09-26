"""Unit tests for canonical video id parsing."""

import pytest

from app.services.video_id import level_of, name_variants


@pytest.mark.parametrize(
    ("video_id", "expected"),
    [
        ("L21_V001", "L21"),
        ("M10_V031", "M10"),
        ("S01-V001", "S01"),
        ("N001-V001", "N001"),
        ("N100-V012", "N100"),
        ("V001", "V001"),
    ],
)
def test_level_of_parses_full_level(video_id: str, expected: str) -> None:
    assert level_of(video_id) == expected


@pytest.mark.parametrize("video_id", ["", "1234", "L", "_V001", "-V001"])
def test_level_of_is_total_for_unparsable_ids(video_id: str) -> None:
    assert level_of(video_id) == ""


@pytest.mark.parametrize(
    ("video_id", "expected"),
    [
        ("N001-V001", ("N001-V001", "N001_V001")),
        ("N001_V001", ("N001_V001", "N001-V001")),
        ("L21_V001", ("L21_V001", "L21-V001")),
        ("S01-V001", ("S01-V001", "S01_V001")),
        ("L21", ("L21",)),
        ("", ("",)),
    ],
)
def test_name_variants_tolerates_both_separators(
    video_id: str, expected: tuple[str, ...]
) -> None:
    assert name_variants(video_id) == expected


def test_name_variants_never_duplicates_the_requested_spelling() -> None:
    for video_id in ("L21_V001", "M01_V002", "S01-V003", "N001-V004"):
        variants = name_variants(video_id)
        assert variants[0] == video_id
        assert len(set(variants)) == len(variants)
