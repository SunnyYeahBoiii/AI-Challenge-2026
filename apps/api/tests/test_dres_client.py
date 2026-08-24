import pytest

from app.services.dres_client import DresClient, DresError


def test_dres_client_accepts_http_server_override() -> None:
    client = DresClient()

    assert client._resolve_base_url("https://dres.example.test/") == "https://dres.example.test"


@pytest.mark.parametrize("url", ["dres.example.test", "ftp://dres.example.test"])
def test_dres_client_rejects_invalid_server_override(url: str) -> None:
    client = DresClient()

    with pytest.raises(DresError, match="DRES URL must be"):
        client._resolve_base_url(url)
