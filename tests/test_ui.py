"""The Streamlit desk run against the real API in-process (no servers, no model calls)."""
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from dualuse import api
from dualuse.holdqueue import HoldQueue


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def desk(monkeypatch):
    clock = Clock(1000.0)
    queue = HoldQueue(1800, clock=clock, mode="rules")
    monkeypatch.setattr(api, "QUEUE", queue)
    client = TestClient(api.app)
    base = "http://localhost:8000"

    def request(method, url, timeout=None, **kwargs):
        return client.request(method, url.removeprefix(base), **kwargs)

    monkeypatch.setattr(httpx, "request", request)
    return queue, clock


def test_waiting_call_details_keep_their_label_while_the_wait_grows(desk):
    queue, clock = desk
    call = queue.add()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dualuse" / "ui.py"), default_timeout=30)
    app.run()
    app.sidebar.radio[0].set_value("Operator desk").run()

    def label():
        return next(expander.label for expander in app.expander if call.call_id in expander.label)

    first = label()
    clock.now += 7
    app.run()
    assert label() == first
