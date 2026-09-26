"""Tools the TRAKE agent may call. Everything except `add_candidate` is read-only.

The LLM never touches ids it invented: `add_candidate` only accepts frames the
agent has already seen through a search/inspect tool, so `pts_time`/`fps` come
from the index and not from model output. There is deliberately no Selection or
DRES tool.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import Config
from app.models import BoxQuery
from app.services import cloud_api_client
from app.services.es_client import es_client
from app.services.hybrid_search import multi_box_search, search_video_frames
from app.services.storage import keyframe_url

logger = logging.getLogger(__name__)

MAX_VIDEOS_PER_SEARCH = 5
MAX_FRAMES_PER_VIDEO = 6
MAX_KEYWORD_HITS = 30
MAX_IMAGES = 4
BOX_TOPK = 300
TEXT_SNIPPET = 200

FrameKey = tuple[str, int]
ToolResult = str | list[dict[str, Any]]


@dataclass
class AgentContext:
    """Per-run state: which board events exist and which frames were seen."""

    event_ids: set[str]
    max_candidates_per_event: int = Config.AGENT_MAX_CANDIDATES_PER_EVENT
    seen: dict[FrameKey, dict[str, Any]] = field(default_factory=dict)
    added: dict[str, list[FrameKey]] = field(default_factory=dict)

    def remember(self, frame: dict[str, Any]) -> dict[str, Any]:
        video_id = str(frame.get("video_id") or "")
        index = frame.get("frame_index", frame.get("frame_idx"))
        if not video_id or index is None:
            return {}
        key = (video_id, int(index))
        self.seen[key] = frame
        return {
            "video_id": video_id,
            "frame_index": int(index),
            "timestamp": round(float(frame.get("timestamp") or 0.0), 2),
            "score": round(float(frame.get("score") or 0.0), 4),
        }


def _snippet(text: object) -> str:
    return str(text or "")[:TEXT_SNIPPET]


def _brief(ctx: AgentContext, frame: dict[str, Any]) -> dict[str, Any]:
    brief = ctx.remember(frame)
    if not brief:
        return {}
    if frame.get("ocr_text"):
        brief["ocr"] = _snippet(frame["ocr_text"])
    if frame.get("asr_text"):
        brief["asr"] = _snippet(frame["asr_text"])
    return brief


def search_moments(ctx: AgentContext, args: dict[str, Any]) -> ToolResult:
    boxes = [
        BoxQuery(**{**query, "topk": BOX_TOPK}).model_dump()
        for query in args["queries"]
    ]
    result = multi_box_search(
        box_queries=boxes,
        temporal_window=float(args.get("temporal_window_seconds", 90.0)),
        enhance=False,
        mode=args.get("mode", "parallel"),
        video_prefixes=args.get("video_prefixes") or None,
    )
    videos = []
    for video in result["videos"][:MAX_VIDEOS_PER_SEARCH]:
        frames = video["best_sequence"]["frames"] or video["valid_frames"]
        videos.append({
            "video_id": video["video_id"],
            "video_score": round(float(video["video_score"]), 4),
            "frames": [
                {**_brief(ctx, frame), "query_index": frame.get("query_index")}
                for frame in frames[:MAX_FRAMES_PER_VIDEO]
            ],
        })
    return _json({"total_videos": result["total_videos"], "videos": videos})


def keyword_search(ctx: AgentContext, args: dict[str, Any]) -> ToolResult:
    hits: list[tuple[str, int, float]] = []
    for hit in es_client.iter_keyword_frame_hits(
        ocr_keywords=args.get("ocr_keywords") or [],
        asr_keywords=args.get("asr_keywords") or [],
        keyword_field_mode=args.get("field_mode", "or"),
        video_prefixes=args.get("video_prefixes") or None,
    ):
        hits.append(hit)
        if len(hits) >= MAX_KEYWORD_HITS:
            break
    texts = es_client.fetch_frame_texts((video_id, frame_id) for video_id, frame_id, _ in hits)
    out = []
    for video_id, frame_id, score in hits:
        text = texts.get((video_id, frame_id), {})
        frame = {"video_id": video_id, "frame_index": frame_id, "score": score, **text}
        # Timestamp/fps are unknown here; inspect_frames resolves them.
        ctx.seen.setdefault((video_id, frame_id), frame)
        out.append({
            "video_id": video_id,
            "frame_index": frame_id,
            "score": round(score, 3),
            "ocr": _snippet(text.get("ocr_text")),
            "asr": _snippet(text.get("asr_text")),
        })
    return _json({"hits": out})


def inspect_frames(ctx: AgentContext, args: dict[str, Any]) -> ToolResult:
    video_id = str(args["video_id"])
    frames = search_video_frames(
        video_id, int(args["frame_index"]), int(args.get("radius", 5))
    )
    rows = [_brief(ctx, frame) for frame in frames]
    if not args.get("with_images"):
        return _json({"frames": rows})
    content: list[dict[str, Any]] = [{"type": "text", "text": _json({"frames": rows})}]
    for frame in frames[:MAX_IMAGES]:
        image = _image_block(video_id, int(frame["frame_index"]))
        if image:
            content.append({"type": "text", "text": f"{video_id} frame {frame['frame_index']}"})
            content.append(image)
    return content


def add_candidate(ctx: AgentContext, args: dict[str, Any]) -> ToolResult:
    event_id = str(args["event_id"])
    if event_id not in ctx.event_ids:
        return _error(f"unknown event_id {event_id}")
    key = (str(args["video_id"]), int(args["frame_index"]))
    frame = ctx.seen.get(key)
    if frame is None:
        return _error("frame not seen; get it from search_moments/keyword_search/inspect_frames first")
    if not frame.get("fps") or not frame.get("timestamp"):
        resolved = _resolve(key)
        if resolved is None:
            return _error("frame has no reliable timestamp/fps (skip it)")
        frame = resolved
        ctx.seen[key] = frame
    added = ctx.added.setdefault(event_id, [])
    if key in added:
        return _error("already added for this event")
    if len(added) >= ctx.max_candidates_per_event:
        return _error(f"event already has {len(added)} candidates; stop adding")
    cloud_api_client.add_candidate({
        "eventId": event_id,
        "videoId": key[0],
        "ptsTime": float(frame["timestamp"]),
        "previewFrameId": str(key[1]),
        "fps": float(frame["fps"]),
        "frameIdx": key[1],
        "thumbnailUrl": keyframe_url(*key),
        "addedBy": "agent",
    })
    added.append(key)
    return _json({"ok": True, "event_id": event_id, "candidates_for_event": len(added)})


def _resolve(key: FrameKey) -> dict[str, Any] | None:
    """Fetch the indexed frame (timestamp/fps) — keyword hits and N-video OCR
    docs created without timing carry timestamp 0, which must not be submitted."""
    for frame in search_video_frames(key[0], key[1], 0):
        if int(frame.get("frame_index", -1)) == key[1] and frame.get("fps") and frame.get("timestamp"):
            return frame
    return None


def _image_block(video_id: str, frame_index: int) -> dict[str, Any] | None:
    level = video_id.split("_")[0].split("-")[0]
    path = Path(Config.KEYFRAMES_DIR) / level / video_id / f"{frame_index}.webp"
    try:
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        logger.warning("keyframe not readable: %s", path)
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": "image/webp", "data": data}}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(message: str) -> str:
    return _json({"error": message})


HANDLERS: dict[str, Callable[[AgentContext, dict[str, Any]], ToolResult]] = {
    "search_moments": search_moments,
    "keyword_search": keyword_search,
    "inspect_frames": inspect_frames,
    "add_candidate": add_candidate,
}

_PREFIXES = {"type": "array", "items": {"type": "string"},
             "description": "Optional video prefixes, e.g. L21_V, M, N."}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_moments",
        "description": (
            "Semantic (CLIP-style) search with optional OCR/ASR keyword filters. One query = one "
            "moment. Several queries = ordered moments in the SAME video within the window "
            "(temporal search). Write `text` as a concrete visual description in English."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "ocr_keywords": {"type": "array", "items": {"type": "string"}},
                            "asr_keywords": {"type": "array", "items": {"type": "string"}},
                            "tags": {"type": "array", "items": {"type": "string"},
                                     "description": "COCO class names, e.g. 'traffic light'."},
                        },
                    },
                },
                "mode": {"type": "string", "enum": ["parallel", "sequential"]},
                "temporal_window_seconds": {"type": "number"},
                "video_prefixes": _PREFIXES,
            },
            "required": ["queries"],
        },
    },
    {
        "name": "keyword_search",
        "description": "Pure OCR/ASR text lookup across all frames (exact phrase). Best for on-screen text and speech.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ocr_keywords": {"type": "array", "items": {"type": "string"}},
                "asr_keywords": {"type": "array", "items": {"type": "string"}},
                "field_mode": {"type": "string", "enum": ["ocr", "asr", "or", "and"]},
                "video_prefixes": _PREFIXES,
            },
        },
    },
    {
        "name": "inspect_frames",
        "description": (
            "Frames around a keyframe of a video with OCR/ASR text and timestamps. "
            "Set with_images=true to actually SEE up to 4 of them (use to verify before adding)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
                "frame_index": {"type": "integer"},
                "radius": {"type": "integer", "minimum": 0, "maximum": 10},
                "with_images": {"type": "boolean"},
            },
            "required": ["video_id", "frame_index"],
        },
    },
    {
        "name": "add_candidate",
        "description": (
            "Propose a frame as a Candidate for a board Event (shared with the team). Only for "
            "frames you verified. Never a final selection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "video_id": {"type": "string"},
                "frame_index": {"type": "integer"},
            },
            "required": ["event_id", "video_id", "frame_index"],
        },
    },
]
