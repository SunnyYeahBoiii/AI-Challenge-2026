from pathlib import Path

from app.services.encoders import beit3


def test_ensure_weight_downloads_missing_file(monkeypatch, tmp_path: Path) -> None:
    destination = tmp_path / "model.pth"
    calls: list[tuple[str, str]] = []

    def fake_download(url: str, path: str, *, progress: bool) -> None:
        calls.append((url, path))
        Path(path).write_bytes(b"checkpoint")

    monkeypatch.setattr(beit3.torch.hub, "download_url_to_file", fake_download)

    beit3._ensure_weight(destination, "https://example.test/model.pth")

    assert destination.read_bytes() == b"checkpoint"
    assert calls == [("https://example.test/model.pth", str(destination))]


def test_ensure_weight_reuses_existing_file(monkeypatch, tmp_path: Path) -> None:
    destination = tmp_path / "model.pth"
    destination.write_bytes(b"existing")

    def fail_download(url: str, path: str, *, progress: bool) -> None:
        raise AssertionError(f"unexpected download: {url} -> {path}")

    monkeypatch.setattr(beit3.torch.hub, "download_url_to_file", fail_download)

    beit3._ensure_weight(destination, "https://example.test/model.pth")

    assert destination.read_bytes() == b"existing"
