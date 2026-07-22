from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services.model_registry import DEFAULT_CONFIG_PATH

RetrievalMode = Literal["text", "image", "composed"]


class EnsembleProfileError(ValueError):
    """Raised when a named paper-reproduction profile is invalid."""


@dataclass(frozen=True)
class EnsembleProfile:
    """Published model selection for one retrieval system."""

    profile_id: str
    text_model_ids: tuple[str, ...]
    image_model_ids: tuple[str, ...]
    composed_model_ids: tuple[str, ...]
    rrf_k: int

    def model_ids_for(self, mode: RetrievalMode) -> tuple[str, ...]:
        if mode == "text":
            return self.text_model_ids
        if mode == "image":
            return self.image_model_ids
        return self.composed_model_ids


def _model_ids(
    raw_profile: dict[str, object],
    field: str,
    *,
    known_models: set[str],
) -> tuple[str, ...]:
    raw_ids = raw_profile.get(field)
    if not isinstance(raw_ids, list) or not raw_ids:
        raise EnsembleProfileError(f"profile {field} must be a non-empty list")
    if any(not isinstance(model_id, str) or not model_id for model_id in raw_ids):
        raise EnsembleProfileError(f"profile {field} must only contain model ids")
    model_ids = tuple(str(model_id) for model_id in raw_ids)
    if len(set(model_ids)) != len(model_ids):
        raise EnsembleProfileError(f"profile {field} model ids must be unique")
    unknown = set(model_ids) - known_models
    if unknown:
        raise EnsembleProfileError(f"profile references unknown model: {', '.join(sorted(unknown))}")
    return model_ids


def load_ensemble_profiles(config_path: Path) -> dict[str, EnsembleProfile]:
    """Load named paper-reproduction profiles from the ensemble configuration."""
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        raw_models = raw_config["models"]
        raw_profiles = raw_config["profiles"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise EnsembleProfileError(f"cannot read ensemble profiles {config_path}: {error}") from error
    if not isinstance(raw_models, list) or not isinstance(raw_profiles, dict):
        raise EnsembleProfileError("ensemble models must be a list and profiles must be an object")
    known_models = {
        str(model["id"])
        for model in raw_models
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    }
    profiles: dict[str, EnsembleProfile] = {}
    for profile_id, raw_profile in raw_profiles.items():
        if not isinstance(profile_id, str) or not isinstance(raw_profile, dict):
            raise EnsembleProfileError("ensemble profile entries must be objects")
        raw_rrf_k = raw_profile.get("rrf_k", 60)
        if not isinstance(raw_rrf_k, int) or isinstance(raw_rrf_k, bool) or raw_rrf_k < 1:
            raise EnsembleProfileError("profile rrf_k must be a positive integer")
        profiles[profile_id] = EnsembleProfile(
            profile_id=profile_id,
            text_model_ids=_model_ids(
                raw_profile, "text_model_ids", known_models=known_models
            ),
            image_model_ids=_model_ids(
                raw_profile, "image_model_ids", known_models=known_models
            ),
            composed_model_ids=_model_ids(
                raw_profile, "composed_model_ids", known_models=known_models
            ),
            rrf_k=raw_rrf_k,
        )
    return profiles


def get_ensemble_profile(
    profile_id: str,
    *,
    config_path: Path | None = None,
) -> EnsembleProfile:
    """Return one named profile using the active ensemble configuration."""
    path = config_path or Path(os.getenv("ENSEMBLE_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
    profiles = load_ensemble_profiles(path)
    try:
        return profiles[profile_id]
    except KeyError as error:
        raise EnsembleProfileError(f"unknown ensemble profile: {profile_id}") from error
