"""TRAKE agent: tool guards and the Claude loop (fake client)."""

from types import SimpleNamespace
from typing import Any

from app.services.agent import runner, tools
from app.services.agent.tools import AgentContext


def _frame(index: int = 10, fps: float = 25.0, ts: float = 4.0) -> dict[str, Any]:
    return {"video_id": "L01_V001", "frame_index": index, "fps": fps, "timestamp": ts, "score": 0.9}


def _ctx(**kw: Any) -> AgentContext:
    ctx = AgentContext(event_ids={"e1"}, **kw)
    ctx.remember(_frame())
    return ctx


def _args(event: str = "e1", index: int = 10) -> dict[str, Any]:
    return {"event_id": event, "video_id": "L01_V001", "frame_index": index}


def test_add_candidate_posts_payload(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(tools.cloud_api_client, "add_candidate", sent.append)
    monkeypatch.setattr(tools, "keyframe_url", lambda v, i: f"/k/{v}/{i}")
    ctx = _ctx()
    assert '"ok": true' in tools.add_candidate(ctx, _args())
    assert sent[0]["addedBy"] == "agent"
    assert sent[0]["ptsTime"] == 4.0 and sent[0]["previewFrameId"] == "10"


def test_add_candidate_rejects_unknown_event_unseen_frame_and_dupes(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(tools.cloud_api_client, "add_candidate", sent.append)
    monkeypatch.setattr(tools, "keyframe_url", lambda v, i: "")
    ctx = _ctx()
    assert "unknown event_id" in tools.add_candidate(ctx, _args("zzz"))
    assert "not seen" in tools.add_candidate(ctx, _args(index=99))
    tools.add_candidate(ctx, _args())
    assert "already added" in tools.add_candidate(ctx, _args())
    assert len(sent) == 1


def test_add_candidate_respects_cap_and_zero_timestamp(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(tools.cloud_api_client, "add_candidate", sent.append)
    monkeypatch.setattr(tools, "keyframe_url", lambda v, i: "")
    monkeypatch.setattr(tools, "search_video_frames", lambda *a: [])
    ctx = _ctx(max_candidates_per_event=1)
    ctx.remember(_frame(11))
    ctx.remember(_frame(12, ts=0.0))
    tools.add_candidate(ctx, _args())
    assert "stop adding" in tools.add_candidate(ctx, _args(index=11))
    assert "no reliable timestamp" in tools.add_candidate(_ctx_with_zero(), _args(index=12))
    assert len(sent) == 1


def _ctx_with_zero() -> AgentContext:
    ctx = AgentContext(event_ids={"e1"})
    ctx.remember(_frame(12, ts=0.0))
    return ctx


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = SimpleNamespace(create=lambda **kw: responses.pop(0))


def _resp(blocks: list[Any], stop: str) -> Any:
    return SimpleNamespace(content=blocks, stop_reason=stop)


def test_runner_loops_until_end_turn(monkeypatch) -> None:
    board = {"events": [{"id": "e1", "displayLabel": "Event 1", "labelText": "xe"}]}
    monkeypatch.setattr(runner.cloud_api_client, "get_board", lambda: board)
    monkeypatch.setitem(runner.HANDLERS, "keyword_search", lambda ctx, a: '{"hits": []}')
    call = SimpleNamespace(type="tool_use", id="t1", name="keyword_search", input={})
    bad = SimpleNamespace(type="tool_use", id="t2", name="delete_everything", input={})
    done = SimpleNamespace(type="text", text="xong")
    client = _FakeClient([_resp([call, bad], "tool_use"), _resp([done], "end_turn")])
    steps: list[dict[str, Any]] = []
    assert runner.run_agent("", None, steps.append, client=client) == "xong"  # type: ignore[arg-type]
    assert [s["tool"] for s in steps] == ["keyword_search", "delete_everything"]
    assert "unknown tool" in steps[1]["result"]


def test_runner_rejects_empty_board(monkeypatch) -> None:
    monkeypatch.setattr(runner.cloud_api_client, "get_board", lambda: {"events": []})
    try:
        runner.run_agent("", None, lambda s: None, client=_FakeClient([]))  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("expected ValueError")
