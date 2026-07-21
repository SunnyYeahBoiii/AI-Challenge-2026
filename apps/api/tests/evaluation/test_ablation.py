from __future__ import annotations

import pytest

from app.evaluation.ablation import evaluate_source_ablation, fuse_query_rankings


def test_fuse_query_rankings_applies_source_weights() -> None:
    ranking = fuse_query_rankings(
        {
            "a": ["f1", "f2"],
            "b": ["f2", "f3"],
        },
        source_weights={"a": 1.0, "b": 2.0},
        rrf_k=60,
    )

    assert ranking == ["f2", "f3", "f1"]


def test_source_ablation_evaluates_each_subset() -> None:
    ground_truth = {"q1": {"target"}}
    runs = {
        "q1": {
            "a": ["wrong", "target"],
            "b": ["target", "wrong"],
        }
    }

    report = evaluate_source_ablation(ground_truth, runs, rrf_k=60, recall_at=(1, 2))

    assert set(report) == {"a", "b", "a+b"}
    assert report["a"]["recall@1"] == 0.0
    assert report["b"]["recall@1"] == 1.0
    assert report["a+b"]["recall@2"] == 1.0


def test_fusion_rejects_invalid_weights_and_skips_zero_weight_sources() -> None:
    assert fuse_query_rankings(
        {"a": ["arbitrary"], "b": ["target"]},
        source_weights={"a": 0.0, "b": 1.0},
    ) == ["target"]
    with pytest.raises(ValueError, match="finite"):
        fuse_query_rankings({"a": ["x"]}, source_weights={"a": float("nan")})
    with pytest.raises(ValueError, match="unknown"):
        evaluate_source_ablation(
            {"q": {"x"}},
            {"q": {"a": ["x"]}},
            source_weights={"typo": 1.0},
        )
