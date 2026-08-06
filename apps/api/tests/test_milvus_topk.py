from app.services.milvus_client import MILVUS_MAX_TOPK, clamp_milvus_topk


def test_clamp_milvus_topk_keeps_valid_values() -> None:
    assert clamp_milvus_topk(20) == 20
    assert clamp_milvus_topk(MILVUS_MAX_TOPK) == MILVUS_MAX_TOPK


def test_clamp_milvus_topk_caps_overfetch_above_ceiling() -> None:
    # Parallel mode asks for topk*2; without clamping, topk=10000 → 20000 → 500.
    assert clamp_milvus_topk(20_000) == MILVUS_MAX_TOPK


def test_clamp_milvus_topk_floors_at_one() -> None:
    assert clamp_milvus_topk(0) == 1
    assert clamp_milvus_topk(-5) == 1
