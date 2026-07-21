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

    def meta(self) -> dict[str, object]:
        return {
            "queryVariants": self.query_variants,
            "sources": self.sources,
            "models": self.models,
            "errors": self.errors,
            "rrfK": self.rrf_k,
            "candidateTopK": self.candidate_top_k,
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
                embedding = self._registry.get(spec.model_id).encode_images([image])[0]
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
        query: str,
        image: object,
        *,
        text_weight: float,
        options: EnsembleSearchOptions,
        expression: str | None = None,
    ) -> EnsembleSearchResponse:
        """Compose text and image feedback inside each model space, then fuse rankings."""
        if not math.isfinite(text_weight) or not 0.0 <= text_weight <= 1.0:
            raise EnsembleSearchError("text_weight must be between 0 and 1")
        query = query.strip()
        if not query:
            raise EnsembleSearchError("text query is required")
        variants = self._query_variants(query, options)
        composed_query = variants[-1]
        sources: list[RankedSource] = []
        models: list[str] = []
        errors: dict[str, str] = {}
        for spec in self._specs(options):
            try:
                model = self._registry.get(spec.model_id)
                text_embedding = self._encode_texts(spec, [composed_query])[0]
                image_embedding = model.encode_images([image])[0]
                if text_embedding.shape != image_embedding.shape:
                    raise EnsembleSearchError(
                        f"incompatible text/image embeddings for {spec.model_id}"
                    )
                embedding = (text_weight * text_embedding) + (
                    (1.0 - text_weight) * image_embedding
                )
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
                        f"{spec.model_id}:composed",
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
            query=query,
            variants=variants,
            sources=sources,
            models=models,
            errors=errors,
            options=options,
        )
