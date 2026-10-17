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


def run_app():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dualuse" / "ui.py"), default_timeout=30)
    app.run()
    return app


def test_the_sidebar_switches_the_line_profile(desk):
    queue, _ = desk
    app = run_app()
    app.selectbox(key="line_profile").set_value("cn-12345").run()
    assert queue.profile == "cn-12345"


def test_caller_text_is_shown_literally_to_caller_and_operator(desk):
    queue, _ = desk
    call = queue.add()
    raw = "I owe $500 and $200 ![x](http://h/x.png)"
    queue.say(call.call_id, raw)
    app = run_app()
    caller_view = [element.value for element in app.markdown]
    assert not any(raw in source for source in caller_view)
    assert any(r"\$500" in source and r"\!\[x\]" in source for source in caller_view)
    app.sidebar.radio[0].set_value("Operator desk").run()
    operator_view = [element.value for element in app.markdown]
    assert not any(raw in source for source in operator_view)
    assert any(r"\$500" in source for source in operator_view)


def test_the_operator_card_shows_the_callers_language_and_distress(desk):
    queue, _ = desk
    call = queue.add()
    queue.say(call.call_id, "我们被困在楼里了")
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    assert any("language: zh" in caption.value and "distress:" in caption.value for caption in app.caption)


def test_the_operator_desk_injects_a_labeled_surge(desk):
    queue, _ = desk
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    app.selectbox(key="surge_source").set_value("scripts")
    app.number_input(key="surge_span").set_value(0)
    app.button(key="surge_start").click().run()
    from dualuse import api
    api.SURGE["thread"].join(20)
    calls = queue.snapshot()["calls"]
    assert calls and all(c["origin"].startswith("simulated") for c in calls)


def test_a_tab_does_not_undo_another_tabs_profile_switch(desk):
    queue, _ = desk
    app = run_app()
    queue.profile = "cn-12345"
    app.run()
    assert queue.profile == "cn-12345"


def test_emoji_codes_and_entities_in_caller_text_stay_literal(desk):
    queue, _ = desk
    call = queue.add()
    queue.say(call.call_id, "Fire :fire: near &lt;b&gt; here")
    app = run_app()
    sources = [element.value for element in app.markdown]
    assert not any(":fire:" in source for source in sources)
    assert any(r"\&lt;" in source for source in sources)


def test_the_operator_desk_marks_a_phone_call_and_says_voice_is_not_transferred(desk):
    queue, _ = desk
    phone, typed = queue.add(origin="phone"), queue.add()
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    labels = {expander.label for expander in app.expander}
    assert any(phone.call_id in label and "📞 phone" in label for label in labels)
    assert any(typed.call_id in label and "phone" not in label for label in labels)
    queue.claim("operator-1")
    app.run()
    assert any("Voice transfer is not connected" in info.value for info in app.info)
