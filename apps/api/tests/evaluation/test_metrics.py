from __future__ import annotations

import pytest

from app.evaluation.metrics import _average_precision, _reciprocal_rank, evaluate_rankings


def test_evaluate_rankings_computes_recall_mrr_and_map() -> None:
    ground_truth = {
        "q1": {"f2"},
        "q2": {"f3", "f4"},
    }
    rankings = {
        "q1": ["f1", "f2", "f3"],
        "q2": ["f4", "f5", "f3"],
    }

    metrics = evaluate_rankings(ground_truth, rankings, recall_at=(1, 2, 5))

    assert metrics["queries"] == 2
    assert metrics["recall@1"] == pytest.approx(0.5)
    assert metrics["recall@2"] == pytest.approx(1.0)
    assert metrics["recall@5"] == pytest.approx(1.0)
    assert metrics["mrr"] == pytest.approx(0.75)
    assert metrics["map"] == pytest.approx((0.5 + ((1.0 + (2 / 3)) / 2)) / 2)


def test_metric_edge_cases_and_validation() -> None:
    assert _reciprocal_rank({"x"}, ["a", "b"]) == 0.0
    assert _average_precision(set(), ["x"]) == 0.0
    assert _average_precision({"x"}, ["x", "x"]) == 1.0
    with pytest.raises(ValueError, match="ground_truth"):
        evaluate_rankings({}, {})
    with pytest.raises(ValueError, match="positive"):
        evaluate_rankings({"q": {"x"}}, {"q": ["x"]}, recall_at=(0,))
