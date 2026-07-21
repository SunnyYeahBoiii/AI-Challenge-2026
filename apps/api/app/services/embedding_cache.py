from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Sequence
from threading import RLock
from typing import TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

FloatArray: TypeAlias = NDArray[np.float32]


class TextEmbeddingCache:
    """Small thread-safe LRU cache for repeated interactive Query encodings."""

    def __init__(self, max_entries: int = 512) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._values: OrderedDict[tuple[str, tuple[str, ...]], FloatArray] = OrderedDict()
        self._lock = RLock()

    def get_or_compute(
        self,
        model_id: str,
        texts: Sequence[str],
        compute: Callable[[], FloatArray],
    ) -> FloatArray:
        key = (model_id, tuple(texts))
        with self._lock:
            cached = self._values.get(key)
            if cached is not None:
                self._values.move_to_end(key)
                return cached.copy()
        value = cast(FloatArray, np.asarray(compute(), dtype=np.float32))
        with self._lock:
            self._values[key] = value.copy()
            self._values.move_to_end(key)
            while len(self._values) > self._max_entries:
                self._values.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
