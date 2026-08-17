import logging
import threading
from typing import Literal, TypedDict

from app.services.encoders.base import Embeddings, Encoder
from app.services.encoders.registry import ENCODER_REGISTRY

logger = logging.getLogger(__name__)

State = Literal["none", "loading", "ready", "error"]


class Status(TypedDict):
    state: State
    model_id: str | None
    collection_name: str | None
    embedding_dim: int | None
    error: str | None


class NoActiveModelError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("No encoder model is currently loaded. Load one via POST /api/admin/model.")


_lock = threading.RLock()
_state: State = "none"
_active: Encoder | None = None
_error: str | None = None
_collection_name: str | None = None


def list_models() -> list[str]:
    return sorted(ENCODER_REGISTRY.keys())


def get_status() -> Status:
    with _lock:
        return Status(
            state=_state,
            model_id=_active.model_id if _active else None,
            collection_name=_collection_name,
            embedding_dim=_active.embedding_dim if _active else None,
            error=_error,
        )


def swap(model_id: str, collection_name: str | None = None) -> Status:
    """Unload whatever is active (if anything), then load `model_id`. Never holds two models at once.

    `collection_name` overrides the encoder's default Milvus collection — useful when
    existing indexed data lives under a different name than the registry default.
    """
    if model_id not in ENCODER_REGISTRY:
        raise ValueError(f"Unknown model_id '{model_id}'. Known: {list_models()}")

    global _state, _active, _error, _collection_name
    with _lock:
        if _active is not None:
            logger.info("Unloading encoder %s", _active.model_id)
            _active.unload()
            _active = None
        _state = "loading"
        _error = None

        encoder = ENCODER_REGISTRY[model_id]()
        try:
            logger.info("Loading encoder %s", model_id)
            encoder.load()
        except Exception as exc:
            _state = "error"
            _error = str(exc)
            logger.exception("Failed to load encoder %s", model_id)
            raise

        _active = encoder
        _collection_name = (collection_name or "").strip() or encoder.collection_name
        _state = "ready"
        return get_status()


def swap_async(model_id: str, collection_name: str | None = None) -> Status:
    """Same as `swap()` but runs the actual load in a background thread.

    Returns immediately with state ``loading`` so the caller can poll ``get_status()``
    for progress instead of blocking on a single HTTP request.
    """
    if model_id not in ENCODER_REGISTRY:
        raise ValueError(f"Unknown model_id '{model_id}'. Known: {list_models()}")

    global _state, _active, _error, _collection_name

    # Snapshot the collection override before the background thread takes over.
    _pending_collection = (collection_name or "").strip()
    _pending_model_id = model_id

    def _worker() -> None:
        global _state, _active, _error, _collection_name
        with _lock:
            if _active is not None:
                logger.info("Unloading encoder %s", _active.model_id)
                _active.unload()
                _active = None
            _state = "loading"
            _error = None

        encoder = ENCODER_REGISTRY[_pending_model_id]()
        try:
            logger.info("Loading encoder %s", _pending_model_id)
            encoder.load()
        except Exception as exc:
            with _lock:
                _state = "error"
                _error = str(exc)
            logger.exception("Failed to load encoder %s", _pending_model_id)
            return

        with _lock:
            _active = encoder
            _collection_name = _pending_collection or encoder.collection_name
            _state = "ready"
        logger.info("Encoder %s ready", _pending_model_id)

    threading.Thread(target=_worker, daemon=True).start()

    with _lock:
        _state = "loading"
        _error = None
    return get_status()


def unload() -> Status:
    global _state, _active, _error, _collection_name
    with _lock:
        if _active is not None:
            logger.info("Unloading encoder %s", _active.model_id)
            _active.unload()
            _active = None
        _state = "none"
        _error = None
        _collection_name = None
        return get_status()


def _require_active() -> Encoder:
    if _active is None:
        raise NoActiveModelError()
    return _active


def embed_text(texts: list[str]) -> Embeddings:
    return _require_active().embed_text(texts)


def embed_image(image_bytes: bytes) -> Embeddings:
    return _require_active().embed_image(image_bytes)


def embed_images(images: list[bytes]) -> Embeddings:
    return _require_active().embed_images(images)


def active_collection_name() -> str:
    _require_active()
    assert _collection_name is not None
    return _collection_name
