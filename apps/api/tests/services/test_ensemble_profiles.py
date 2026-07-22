from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ensemble_profiles import (
    EnsembleProfileError,
    get_ensemble_profile,
    load_ensemble_profiles,
)


def test_paper_profiles_select_published_model_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Path(__file__).resolve().parents[2] / "config" / "ensemble.json"
    monkeypatch.setenv("ENSEMBLE_CONFIG_PATH", str(config))

    top1 = get_ensemble_profile("top1_2025")
    assert top1.model_ids_for("text") == (
        "beit3-large-coco-retrieval-384",
        "metaclip2-worldwide-huge",
        "perception-core-l14-336",
    )
    assert top1.model_ids_for("composed") == top1.model_ids_for("text")
    assert top1.rrf_k == 60

    top2 = get_ensemble_profile("top2_2025")
    assert top2.model_ids_for("text") == (
        "beit3-large-coco-retrieval-384",
        "bge-vl-large",
        "metaclip2-worldwide-huge",
        "perception-core-l14-336",
    )
    assert top2.model_ids_for("image") == top2.model_ids_for("text")
    assert top2.model_ids_for("composed") == ("bge-vl-large",)


def test_profile_loader_rejects_unknown_models_and_profiles(tmp_path: Path) -> None:
    config = tmp_path / "ensemble.json"
    config.write_text(
        json.dumps(
            {
                "models": [{"id": "known"}],
                "profiles": {
                    "broken": {
                        "text_model_ids": ["missing"],
                        "image_model_ids": ["known"],
                        "composed_model_ids": ["known"],
                        "rrf_k": 60,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(EnsembleProfileError, match="unknown model"):
        load_ensemble_profiles(config)
    config.write_text(
        json.dumps(
            {
                "models": [{"id": "known"}],
                "profiles": {
                    "valid": {
                        "text_model_ids": ["known"],
                        "image_model_ids": ["known"],
                        "composed_model_ids": ["known"],
                        "rrf_k": 60,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EnsembleProfileError, match="unknown ensemble profile"):
        get_ensemble_profile("missing", config_path=config)
