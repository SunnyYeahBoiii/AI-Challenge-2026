from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from app.services.embedding_cache import TextEmbeddingCache
from app.services.fusion import RankedSource, diversify_frames, reciprocal_rank_fusion
from app.services.model_registry import FloatArray, ModelRegistry, ModelSpec

FrameData = dict[str, Any]
TOP1_LINEAR_FEEDBACK_PROFILE = "top1_2025"


class EnsembleSearchError(RuntimeError):
    """Raised when no configured model can complete a retrieval request."""


class VectorSearchBackend(Protocol):
    """Database boundary required by ensemble retrieval."""

    def search(
        self,
        spec: ModelSpec,
        embedding: Sequence[float],
        top_k: int,
        expression: str | None = None,
    ) -> list[FrameData]: ...


@dataclass(frozen=True)
class EnsembleSearchOptions:
    """Per-request controls for candidate retrieval and fusion."""

    profile: str | None = None
    model_ids: tuple[str, ...] | None = None
    model_weights: Mapping[str, float] = field(default_factory=dict)
    candidate_top_k: int = 200
    result_top_k: int = 20
    rrf_k: int = 60
    use_enhanced_query: bool = True
    preserve_original_query: bool = True
    min_time_gap_seconds: float = 0.0
    max_per_video: int = 0
    allow_partial_models: bool = True

    def __post_init__(self) -> None:
        if self.candidate_top_k < 1 or self.result_top_k < 1:
            raise ValueError("top-k values must be positive")
        if self.rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        if any(not math.isfinite(weight) for weight in self.model_weights.values()):
            raise ValueError("model weights must be finite")
        if any(weight < 0 for weight in self.model_weights.values()):
            raise ValueError("model weights cannot be negative")


@dataclass(frozen=True)
class EnsembleSearchResponse:
    """Fused results plus reproducibility diagnostics for one Query."""

    query: str
    query_variants: list[str]
    results: list[FrameData]
    sources: list[str]
    models: list[str]
    errors: dict[str, str]
    rrf_k: int
    candidate_top_k: int
    composition_modes: dict[str, str] = field(default_factory=dict)
    composition_input: dict[str, str] = field(default_factory=dict)
    profile: str | None = None

    def meta(self) -> dict[str, object]:
        return {
            "queryVariants": self.query_variants,
            "sources": self.sources,
            "models": self.models,
            "errors": self.errors,
            "rrfK": self.rrf_k,
            "candidateTopK": self.candidate_top_k,
            "compositionModes": self.composition_modes,
            "compositionInput": self.composition_input,
            "profile": self.profile,
        }


class EnsembleSearchService:
    """Run model-specific retrieval and fuse independent rankings with RRF."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        vector_backend: VectorSearchBackend,
        query_enhancer: Callable[[str], str],
        embedding_cache: TextEmbeddingCache | None = None,
    ) -> None:
        self._registry = registry
        self._vector_backend = vector_backend
        self._query_enhancer = query_enhancer
        self._embedding_cache = embedding_cache or TextEmbeddingCache()

    def _encode_texts(self, spec: ModelSpec, texts: list[str]) -> FloatArray:
        return self._embedding_cache.get_or_compute(
            spec.model_id,
            texts,
            lambda: self._registry.get(spec.model_id).encode_texts(texts),
        )

    def _specs(self, options: EnsembleSearchOptions) -> list[ModelSpec]:
        specs = self._registry.enabled_specs(options.model_ids)
        if not specs:
            raise EnsembleSearchError("no embedding models are enabled")
        selected_ids = {spec.model_id for spec in specs}
        unknown_weights = set(options.model_weights) - selected_ids
        if unknown_weights:
            unknown = ", ".join(sorted(unknown_weights))
            raise EnsembleSearchError(f"weights provided for unselected models: {unknown}")
        positive_specs = [
            spec for spec in specs if self._model_weight(spec, options) > 0.0
        ]
        if not positive_specs:
            raise EnsembleSearchError("at least one selected model must have positive weight")
        return positive_specs

    def _model_weight(self, spec: ModelSpec, options: EnsembleSearchOptions) -> float:
        return float(options.model_weights.get(spec.model_id, spec.weight))

    def _query_variants(self, query: str, options: EnsembleSearchOptions) -> list[str]:
        variants = [query]
        if options.use_enhanced_query:
            enhanced = self._query_enhancer(query).strip()
            if enhanced and enhanced != query:
                variants = [query, enhanced] if options.preserve_original_query else [enhanced]
        return variants

    def _response(
        self,
        *,
        query: str,
        variants: list[str],
        sources: list[RankedSource],
        models: list[str],
        errors: dict[str, str],
        options: EnsembleSearchOptions,
        composition_modes: Mapping[str, str] | None = None,
        composition_input: Mapping[str, str] | None = None,
    ) -> EnsembleSearchResponse:
        if not sources:
            raise EnsembleSearchError(f"all embedding models failed: {errors}")
        fused = reciprocal_rank_fusion(sources, rrf_k=options.rrf_k)
        diversified = diversify_frames(
            fused,
            min_time_gap_seconds=options.min_time_gap_seconds,
            max_per_video=options.max_per_video,
            limit=options.result_top_k,
        )
        return EnsembleSearchResponse(
            query=query,
            query_variants=variants,
            results=diversified,
            sources=[source.source_id for source in sources],
            models=models,
            errors=errors,
            rrf_k=options.rrf_k,
            candidate_top_k=options.candidate_top_k,
            composition_modes=dict(composition_modes or {}),
            composition_input=dict(composition_input or {}),
            profile=options.profile,
        )

    def search_text(
        self,
        query: str,
        options: EnsembleSearchOptions,
        *,
        expression: str | None = None,
    ) -> EnsembleSearchResponse:
        """Encode all Query variants with every selected model and fuse their rankings."""
        query = query.strip()
        if not query:
            raise EnsembleSearchError("text query is required")
        variants = self._query_variants(query, options)
        sources: list[RankedSource] = []
        models: list[str] = []
        errors: dict[str, str] = {}
        for spec in self._specs(options):
            source_start = len(sources)
            try:
                embeddings = self._encode_texts(spec, variants)
                if embeddings.shape != (len(variants), spec.dimension):
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned shape {embeddings.shape}; "
                        f"expected {(len(variants), spec.dimension)}"
                    )
                if not np.isfinite(embeddings).all():
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned non-finite text embeddings"
                    )
                text_norms = np.linalg.norm(embeddings, axis=1)
                if not np.isfinite(text_norms).all() or np.any(text_norms <= 1e-12):
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned zero-norm or invalid text embeddings"
                    )
                model_weight = self._model_weight(spec, options)
                source_weight = model_weight / len(variants)
                for variant_index, (variant, embedding) in enumerate(zip(variants, embeddings)):
                    variant_id = (
                        "original"
                        if variant == query and (variant_index == 0 or len(variants) == 1)
                        else "enhanced"
                    )
                    ranking = self._vector_backend.search(
                        spec,
                        embedding.tolist(),
                        options.candidate_top_k,
                        expression,
                    )
                    sources.append(
                        RankedSource(f"{spec.model_id}:{variant_id}", ranking, source_weight)
                    )
                models.append(spec.model_id)
            except Exception as error:
                del sources[source_start:]
                errors[spec.model_id] = str(error)
                if not options.allow_partial_models:
                    raise EnsembleSearchError(str(error)) from error
        return self._response(
            query=query,
            variants=variants,
            sources=sources,
            models=models,
            errors=errors,
            options=options,
        )

    def search_image(
        self,
        image: object,
        options: EnsembleSearchOptions,
        *,
        expression: str | None = None,
    ) -> EnsembleSearchResponse:
        """Encode one reference image with every selected model and fuse rankings."""
        sources: list[RankedSource] = []
        models: list[str] = []
        errors: dict[str, str] = {}
        for spec in self._specs(options):
            try:
                embeddings = self._registry.get(spec.model_id).encode_images([image])
                expected_shape = (1, spec.dimension)
                if embeddings.shape != expected_shape:
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned shape {embeddings.shape}; "
                        f"expected {expected_shape}"
                    )
                if not np.isfinite(embeddings).all():
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned non-finite image embeddings"
                    )
                image_norms = np.linalg.norm(embeddings, axis=1)
                if not np.isfinite(image_norms).all() or np.any(image_norms <= 1e-12):
                    raise EnsembleSearchError(
                        f"{spec.model_id} returned zero-norm or invalid image embeddings"
                    )
                embedding = embeddings[0]
                ranking = self._vector_backend.search(
                    spec,
                    embedding.tolist(),
                    options.candidate_top_k,
                    expression,
                )
                sources.append(
                    RankedSource(
                        f"{spec.model_id}:image",
                        ranking,
                        self._model_weight(spec, options),
                    )
                )
                models.append(spec.model_id)
            except Exception as error:
                errors[spec.model_id] = str(error)
                if not options.allow_partial_models:
                    raise EnsembleSearchError(str(error)) from error
        return self._response(
            query="",
            variants=[],
            sources=sources,
            models=models,
            errors=errors,
            options=options,
        )

    def search_composed(
        self,
        feedback_text: str,
        image: object,
        *,
        original_query: str | None = None,
        text_weight: float,
        options: EnsembleSearchOptions,
        expression: str | None = None,
    ) -> EnsembleSearchResponse:
        """Compose text and image feedback inside each model space, then fuse rankings."""
        if not math.isfinite(text_weight) or not 0.0 <= text_weight <= 1.0:
            raise EnsembleSearchError("text_weight must be between 0 and 1")
        feedback_text = feedback_text.strip()
        original_query = (original_query or "").strip()
        if not feedback_text:
            raise EnsembleSearchError("feedback text is required")
        context_query = " ".join(
            part for part in (original_query, feedback_text) if part
        )
        # The Top-1 system linearly combines the textual refinement itself with
        # the selected image. Top-2 instead preserves the original text in its
        # native joint image-text input. Keep those published paths distinct.
        composition_query = (
            feedback_text
            if options.profile == TOP1_LINEAR_FEEDBACK_PROFILE
            else context_query
        )
        variants = self._query_variants(composition_query, options)
        composed_query = variants[-1]
        sources: list[RankedSource] = []
        models: list[str] = []
        errors: dict[str, str] = {}
        composition_modes: dict[str, str] = {}
        for spec in self._specs(options):
            try:
                model = self._registry.get(spec.model_id)
                native_embedding = model.encode_composed([image], [composed_query])
                if native_embedding is not None:
                    expected_shape = (1, spec.dimension)
                    if native_embedding.shape != expected_shape:
                        raise EnsembleSearchError(
                            f"{spec.model_id} native composed encoder returned shape "
                            f"{native_embedding.shape}, expected {expected_shape}"
                        )
                    embedding = native_embedding[0]
                    source_id = f"{spec.model_id}:joint-composed"
                    composition_mode = "joint_image_text"
                else:
                    text_embedding = self._encode_texts(spec, [composed_query])[0]
                    image_embedding = model.encode_images([image])[0]
                    if text_embedding.shape != image_embedding.shape:
                        raise EnsembleSearchError(
                            f"incompatible text/image embeddings for {spec.model_id}"
                        )
                    if text_embedding.shape != (spec.dimension,):
                        raise EnsembleSearchError(
                            f"{spec.model_id} composed encoders returned shape "
                            f"{text_embedding.shape}, expected {(spec.dimension,)}"
                        )
                    embedding = (text_weight * text_embedding) + (
                        (1.0 - text_weight) * image_embedding
                    )
                    source_id = f"{spec.model_id}:composed"
                    composition_mode = "linear_text_image"
                norm = float(np.linalg.norm(embedding))
                if not math.isfinite(norm) or norm <= 1e-12:
                    raise EnsembleSearchError(
                        f"composed embedding for {spec.model_id} has zero or invalid norm"
                    )
                embedding = embedding / norm
                ranking = self._vector_backend.search(
                    spec,
                    np.asarray(embedding, dtype=np.float32).tolist(),
                    options.candidate_top_k,
                    expression,
                )
                sources.append(
                    RankedSource(
                        source_id,
                        ranking,
                        self._model_weight(spec, options),
                    )
                )
                models.append(spec.model_id)
                composition_modes[spec.model_id] = composition_mode
            except Exception as error:
                errors[spec.model_id] = str(error)
                if not options.allow_partial_models:
                    raise EnsembleSearchError(str(error)) from error
        return self._response(
            query=composition_query,
            variants=variants,
            sources=sources,
            models=models,
            errors=errors,
            options=options,
            composition_modes=composition_modes,
            composition_input={
                "originalQuery": original_query,
                "feedbackText": feedback_text,
                "contextQuery": context_query,
                "encodedText": composed_query,
            },
        )
