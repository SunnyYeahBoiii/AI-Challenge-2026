"""Tests for expanding official search results with neighbouring keyframes."""

from app.services import frame_context


def frame(video_id: str, frame_index: int) -> dict[str, object]:
    return {"video_id": video_id, "frame_index": frame_index, "frame_idx": frame_index}


def test_context_uses_es_neighbours_and_milvus_metadata(monkeypatch):
    requested_windows: list[tuple[str, int, int]] = []

    def fake_keys(windows, count):
        requested_windows.extend(windows)
        assert count == 10
        return [([("V1", 90)], [("V1", 110), ("V1", 120)])]

    class FakeMilvus:
        def query_frame_keys(self, keys):
            assert keys == [("V1", 90), ("V1", 110), ("V1", 120)]
            return [frame(video_id, frame_index) for video_id, frame_index in keys]

    monkeypatch.setattr(frame_context.es_client, "context_frame_keys", fake_keys)
    monkeypatch.setattr(frame_context.manager, "active_collection_name", lambda: "data_frames_siglip2")
    monkeypatch.setattr(frame_context, "get_milvus_client", lambda _collection: FakeMilvus())
    monkeypatch.setattr(frame_context, "_enrich_frames", lambda frames: list(frames))

    collection_name, contexts = frame_context.get_frame_contexts([("V1", 100, 105)])

    assert collection_name == "data_frames_siglip2"
    assert requested_windows == [("V1", 100, 105)]
    assert [item["frame_index"] for item in contexts[0]["before"]] == [90]
    assert [item["frame_index"] for item in contexts[0]["after"]] == [110, 120]


def test_context_preserves_windows_when_some_metadata_is_missing(monkeypatch):
    monkeypatch.setattr(
        frame_context.es_client,
        "context_frame_keys",
        lambda _windows, _count: [([("V1", 90)], [("V1", 110)]), ([], [("V2", 20)])],
    )
    monkeypatch.setattr(frame_context.manager, "active_collection_name", lambda: "data_frames_siglip2")
    monkeypatch.setattr(
        frame_context,
        "get_milvus_client",
        lambda _collection: type(
            "FakeMilvus",
            (),
            {"query_frame_keys": lambda _self, _keys: [frame("V1", 110), frame("V2", 20)]},
        )(),
    )
    monkeypatch.setattr(frame_context, "_enrich_frames", lambda frames: list(frames))

    _, contexts = frame_context.get_frame_contexts([("V1", 100, 100), ("V2", 10, 10)])

    assert contexts[0]["before"] == []
    assert [item["frame_index"] for item in contexts[0]["after"]] == [110]
    assert contexts[1]["before"] == []
    assert [item["frame_index"] for item in contexts[1]["after"]] == [20]
