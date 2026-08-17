"""Temporal reachability flags and the best-path dynamic program."""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.hybrid_search.common import (
    Frame,
    _frame_index,
    _similarity,
    _timestamp,
)


def _edge(predecessor: Frame, successor: Frame, window: float) -> bool:
    gap = _timestamp(successor) - _timestamp(predecessor)
    return (
        _frame_index(predecessor) < _frame_index(successor)
        and 0.0 < gap <= window
    )


def _combined_coordinates_are_monotonic(left: Sequence[Frame], right: Sequence[Frame]) -> bool:
    combined = sorted((*left, *right), key=lambda frame: (_timestamp(frame), _frame_index(frame)))
    return all(
        _frame_index(previous) <= _frame_index(current)
        for previous, current in zip(combined, combined[1:])
    )


def _forward_flags(
    previous: Sequence[Frame],
    current: Sequence[Frame],
    previous_flags: Sequence[bool],
    window: float,
) -> list[bool]:
    """Mark current nodes with a reachable predecessor in the prior layer."""
    if not _combined_coordinates_are_monotonic(previous, current):
        return [
            any(flag and _edge(candidate, frame, window) for candidate, flag in zip(previous, previous_flags))
            for frame in current
        ]

    active: deque[int] = deque()
    high = 0
    flags: list[bool] = []
    for frame in current:
        timestamp = _timestamp(frame)
        while high < len(previous) and _timestamp(previous[high]) < timestamp:
            if previous_flags[high]:
                active.append(high)
            high += 1
        while active and _timestamp(previous[active[0]]) < timestamp - window:
            active.popleft()
        flags.append(bool(active and _edge(previous[active[0]], frame, window)))
    return flags


def _backward_flags(
    current: Sequence[Frame],
    following: Sequence[Frame],
    following_flags: Sequence[bool],
    window: float,
) -> list[bool]:
    """Mark current nodes with a reachable successor in the next layer."""
    if not _combined_coordinates_are_monotonic(current, following):
        return [
            any(flag and _edge(frame, candidate, window) for candidate, flag in zip(following, following_flags))
            for frame in current
        ]

    active: deque[int] = deque()
    low = 0
    high = 0
    flags: list[bool] = []
    for frame in current:
        timestamp = _timestamp(frame)
        while high < len(following) and _timestamp(following[high]) <= timestamp + window:
            if following_flags[high]:
                active.append(high)
            high += 1
        while low < high and _timestamp(following[low]) <= timestamp:
            if active and active[0] == low:
                active.popleft()
            low += 1
        # Coordinates are monotonic here; the newest active successor has the
        # largest frame index, so it decides whether any strict-forward edge exists.
        flags.append(bool(active and _edge(frame, following[active[-1]], window)))
    return flags


@dataclass(frozen=True)
class _PathState:
    score_sum: float
    start_time: float
    start_frame: int
    frame_indexes: tuple[int, ...]


def _predecessor_key(state: _PathState) -> tuple[float, float, int, tuple[int, ...]]:
    # For a fixed successor: high sum, later start (short span), earlier first
    # frame, then lexicographically earlier path.
    return (-state.score_sum, -state.start_time, state.start_frame, state.frame_indexes)


def _best_path(by_box: Sequence[list[Frame]], window: float) -> tuple[list[Frame], float] | None:
    """Find the highest-scoring complete path using dense layer positions."""
    if not by_box or any(not layer for layer in by_box):
        return None

    previous_states: list[_PathState | None] = [
        _PathState(_similarity(frame), _timestamp(frame), _frame_index(frame), (_frame_index(frame),))
        for frame in by_box[0]
    ]
    parents: list[list[int]] = [[-1] * len(by_box[0])]

    for layer_index in range(1, len(by_box)):
        previous = by_box[layer_index - 1]
        current = by_box[layer_index]
        current_states: list[_PathState | None] = [None] * len(current)
        current_parents = [-1] * len(current)
        optimized = _combined_coordinates_are_monotonic(previous, current)

        if optimized:
            candidates: deque[int] = deque()
            high = 0
            for current_index, frame in enumerate(current):
                timestamp = _timestamp(frame)
                while high < len(previous) and _timestamp(previous[high]) < timestamp:
                    state = previous_states[high]
                    if state is not None:
                        while (
                            candidates
                            and _predecessor_key(state)
                            < _predecessor_key(previous_states[candidates[-1]])  # type: ignore[arg-type]
                        ):
                            candidates.pop()
                        candidates.append(high)
                    high += 1
                while candidates and _timestamp(previous[candidates[0]]) < timestamp - window:
                    candidates.popleft()
                predecessor = candidates[0] if candidates else -1
                if predecessor >= 0 and not _edge(previous[predecessor], frame, window):
                    predecessor = -1
                if predecessor >= 0:
                    prior = previous_states[predecessor]
                    assert prior is not None
                    current_states[current_index] = _PathState(
                        prior.score_sum + _similarity(frame),
                        prior.start_time,
                        prior.start_frame,
                        prior.frame_indexes + (_frame_index(frame),),
                    )
                    current_parents[current_index] = predecessor
        else:
            for current_index, frame in enumerate(current):
                eligible = [
                    index
                    for index, state in enumerate(previous_states)
                    if state is not None and _edge(previous[index], frame, window)
                ]
                if not eligible:
                    continue
                predecessor = min(
                    eligible,
                    key=lambda index: _predecessor_key(previous_states[index]),  # type: ignore[arg-type]
                )
                prior = previous_states[predecessor]
                assert prior is not None
                current_states[current_index] = _PathState(
                    prior.score_sum + _similarity(frame),
                    prior.start_time,
                    prior.start_frame,
                    prior.frame_indexes + (_frame_index(frame),),
                )
                current_parents[current_index] = predecessor

        if not any(state is not None for state in current_states):
            return None
        parents.append(current_parents)
        previous_states = current_states

    final_candidates = [index for index, state in enumerate(previous_states) if state is not None]
    if not final_candidates:
        return None

    def final_key(index: int) -> tuple[float, float, int, tuple[int, ...]]:
        state = previous_states[index]
        assert state is not None
        span = _timestamp(by_box[-1][index]) - state.start_time
        return (-state.score_sum, span, state.start_frame, state.frame_indexes)

    position = min(final_candidates, key=final_key)
    final_state = previous_states[position]
    assert final_state is not None
    positions = [position]
    for layer_index in range(len(by_box) - 1, 0, -1):
        position = parents[layer_index][position]
        positions.append(position)
    positions.reverse()
    return [by_box[index][position] for index, position in enumerate(positions)], final_state.score_sum
