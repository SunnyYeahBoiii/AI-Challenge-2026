"""Canonical parsing of FrameSeeker video identifiers.

The corpus is not uniform, so the level must be parsed rather than sliced:

* level length varies — ``L21``/``M01``/``S01`` are three characters, ``N001``
  is four, so ``video_id[:3]`` truncates every N-series id to a level that does
  not exist on disk;
* the series separator varies — L/M ship ``L21_V001``, S/N ship ``S01-V001``.
  The N series additionally stores its *video* directories with an underscore
  (``data/video/N001_V001``) while its keyframe directories and the search index
  both use the dash (``N001-V001``), so on-disk lookups must try both spellings.
"""

from __future__ import annotations

import re

_LEVEL_PATTERN = re.compile(r"^[A-Za-z]\d+")
_SERIES_PATTERN = re.compile(r"^(?P<level>[A-Za-z]\d+)(?P<sep>[-_])(?P<tail>V.+)$")


def level_of(video_id: str) -> str:
    """Return the level directory that owns ``video_id``.

    Args:
        video_id: Canonical video id, e.g. ``L21_V001`` or ``N001-V001``.

    Returns:
        The level directory name (e.g. ``L21``, ``N001``), or an empty string
        when the id carries no level prefix. This stays total because the URL
        builders run over raw search hits, which may lack a ``video_id``.
    """
    match = _LEVEL_PATTERN.match(video_id)
    return match.group(0) if match is not None else ""


def name_variants(video_id: str) -> tuple[str, ...]:
    """Return on-disk name candidates for ``video_id``, tolerating the separator.

    The requested spelling comes first so callers keep the id verbatim in URLs
    unless a differently-spelled directory is the one that exists.

    Args:
        video_id: Canonical video id, e.g. ``N001-V001``.

    Returns:
        One candidate when the id has no recognisable series separator, otherwise
        the dash and underscore spellings.
    """
    match = _SERIES_PATTERN.match(video_id)
    if match is None:
        return (video_id,)
    level, tail = match.group("level"), match.group("tail")
    dash, underscore = f"{level}-{tail}", f"{level}_{tail}"
    return (dash, underscore) if match.group("sep") == "-" else (underscore, dash)
