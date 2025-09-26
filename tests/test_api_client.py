import types
import pytest

import deskcoach.services.api_client as api


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, raise_for_status_exc=None):
        self.status_code = status_code
        self._json = json_data or {}
        self._exc = raise_for_status_exc

    def raise_for_status(self):
        if self._exc:
            raise self._exc

    def json(self):
        return self._json


class DummyClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


class DummyHTTPX:
    def __init__(self, responses):
        self._responses = responses
        self.Client = lambda timeout=None: DummyClient(self._responses)


def test_get_height_mm_success(monkeypatch):
    responses = [DummyResponse(json_data={"table_height": 79})]
    dummy = DummyHTTPX(responses)
    monkeypatch.setattr(api, "httpx", dummy)
    mm = api.get_height_mm("http://host")
    assert mm == 790


def test_get_height_mm_missing_key_raises(monkeypatch):
    # Even after retry, still missing key -> RuntimeError
    responses = [DummyResponse(json_data={}), DummyResponse(json_data={})]
    dummy = DummyHTTPX(responses)
    monkeypatch.setattr(api, "httpx", dummy)
    with pytest.raises(RuntimeError):
        api.get_height_mm("http://host", retries=1)
