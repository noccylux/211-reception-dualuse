"""The Streamlit desk run against the real API in-process (no servers, no model calls)."""
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from dualuse import api
from dualuse.extract import Classification, Extraction
from dualuse.holdqueue import Conflict, HoldQueue
from dualuse.triage import Tier


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


def run_app():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dualuse" / "ui.py"), default_timeout=30)
    app.run()
    return app


def fire_report(_text):
    x = Extraction(situation="Caller reports smoke", need="report smoke", location="12 Oak Street",
                   life_threat_now=False, needs_person_soon=True, enough_information=True, evidence=["smoke"],
                   missing=[], language="English", incident_kind="fire", report_only=True)
    return Classification(x, Tier.PRIORITY, "test")


def test_the_chosen_caller_stays_selected_while_the_wait_grows_and_the_queue_reorders(desk):
    queue, clock = desk
    first, second = queue.add(), queue.add()
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    assert app.selectbox(key="detail_call").value == first.call_id  # the head of the queue by default
    labels = set(app.selectbox(key="detail_call").options)
    clock.now += 7
    queue.say(second.call_id, "My neighbor collapsed and he is not breathing")  # moves ahead and changes its tier
    app.run()
    assert app.selectbox(key="detail_call").value == first.call_id
    # A browser sends back the label it was shown, so a label that changed with the tier would lose the choice.
    assert set(app.selectbox(key="detail_call").options) == labels
    app.selectbox(key="detail_call").set_value(second.call_id).run()
    clock.now += 7
    app.run()
    assert app.selectbox(key="detail_call").value == second.call_id


def test_the_queue_is_one_compact_table_with_details_for_the_chosen_caller(desk):
    queue, _ = desk
    first, second, third = queue.add(), queue.add(), queue.add()
    queue.say(first.call_id, "Where can I renew my CalFresh card?")
    for call in (second, third):
        queue.say(call.call_id, "I see smoke at 12 Oak Street", classify=fire_report)
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    table = next(frame.value for frame in app.dataframe if "queue position" in frame.value.columns)
    assert list(table.columns) == ["queue position", "call", "tier", "wait", "FIFO position", "language", "review",
                                   "shadow score (advisory)", "origin"]
    assert not [expander for expander in app.expander if first.call_id in expander.label]  # no panel per caller
    app.selectbox(key="detail_call").set_value(first.call_id).run()
    conversation = " ".join(element.value for element in app.markdown)
    assert "CalFresh" in conversation and "Oak" not in conversation
    assert not any("Possible shared incident" in info.value for info in app.info)
    app.selectbox(key="detail_call").set_value(second.call_id).run()
    assert any("Possible shared incident" in info.value and "2 reports of fire" in info.value for info in app.info)


def test_the_caller_page_offers_a_silent_text_line(desk):
    app = run_app()
    assert any("plays no sound" in info.value for info in app.info)


def test_the_operator_and_a_typed_caller_exchange_messages_after_takeover(desk):
    queue, _ = desk
    call = queue.add()
    queue.say(call.call_id, "Where can I renew my CalFresh card?")
    queue.confirm(queue.claim("operator-1").transfer_id, True)
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()
    app.chat_input(key=f"reply-{call.call_id}").set_value("This is the 211 operator. How can I help?").run()
    assert {k: call.dialogue[-1][k] for k in ("speaker", "text")} == {
        "speaker": "operator", "text": "This is the 211 operator. How can I help?"}
    app.sidebar.radio[0].set_value("Caller conversation").run()
    assert any("**Operator:**" in element.value and "This is the 211 operator" in element.value for element in app.markdown)
    assert any("An operator has taken over" in info.value for info in app.info)
    # One key per call, so a draft survives the placeholder change when an operator takes over.
    app.chat_input(key=f"caller-input-{call.call_id}").set_value("Which office is open today?").run()
    assert {k: call.dialogue[-1][k] for k in ("speaker", "text")} == {"speaker": "caller", "text": "Which office is open today?"}


def test_a_reply_refused_after_the_card_closed_still_shows_its_error(desk, monkeypatch):
    queue, _ = desk
    call = queue.add()
    queue.confirm(queue.claim("operator-1").transfer_id, True)
    app = run_app()
    app.sidebar.radio[0].set_value("Operator desk").run()

    def completed_in_another_tab(call_id, operator_id, text):
        queue.finish(call_id)
        raise Conflict("Only the operator who took over this call can reply")

    monkeypatch.setattr(queue, "operator_say", completed_in_another_tab)
    app.chat_input(key=f"reply-{call.call_id}").set_value("Are you safe?").run()
    app.run()  # AppTest cannot rerun a fragment alone; the browser shows this state on its next refresh
    assert not app.chat_input  # the card closed with the call
    assert any("not sent" in error.value and "409" in error.value for error in app.error)


def test_the_sidebar_switches_the_line_profile(desk):
    queue, _ = desk
    app = run_app()
    app.selectbox(key="line_profile").set_value("cn-12345").run()
    assert queue.profile == "cn-12345"


@pytest.mark.parametrize(("map_url", "src"), [
    (None, "http://localhost:8000/plugins/map/?line=la-211"),
    ("", "http://localhost:8000/plugins/map/?line=la-211"),  # WSLENV can forward an empty variable
    ("https://demo.example.org/", "https://demo.example.org/plugins/map/?line=la-211"),
])
def test_the_incident_map_frame_uses_the_browser_facing_map_url(desk, monkeypatch, map_url, src):
    if map_url is None:
        monkeypatch.delenv("DUALUSE_MAP_URL", raising=False)
    else:
        monkeypatch.setenv("DUALUSE_MAP_URL", map_url)
    app = run_app()
    app.sidebar.radio[0].set_value("Incident map").run()
    assert [frame.proto.src for frame in app.get("iframe")] == [src]


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
    labels = app.selectbox(key="detail_call").options
    assert any(phone.call_id in label and "📞 phone" in label for label in labels)
    assert any(typed.call_id in label and "phone" not in label for label in labels)
    token = queue.claim("operator-1").transfer_id
    app.run()
    assert any("Voice transfer is not connected" in info.value for info in app.info)
    queue.confirm(token, True)
    app.run()
    assert any("Voice transfer is not connected" in info.value for info in app.info)
    assert len(app.chat_input) == 0  # a phone caller cannot see typed replies


def extracted(**fields):
    base = dict(situation="Caller reports smoke", need="", location=None, life_threat_now=False, needs_person_soon=True,
                enough_information=True, evidence=["smoke"], missing=["location"], language="English", incident_kind="fire")
    return lambda _text: Classification(Extraction(**(base | fields)), Tier.PRIORITY, "test")


def checklist_row(app, label):
    return next(element.value for element in app.markdown if f"**{label}**" in element.value)


def test_call_records_list_every_call_newest_first_and_keep_an_ended_calls_conversation(desk):
    queue, _ = desk
    ended, live = queue.add(), queue.add()
    queue.say(ended.call_id, "Where can I renew my CalFresh card?")
    queue.hang_up(ended.call_id)
    app = run_app()
    app.sidebar.radio[0].set_value("Call records").run()
    table = next(frame.value for frame in app.dataframe if "caller messages" in frame.value.columns)
    assert list(table["call"]) == [live.call_id, ended.call_id]
    assert list(table["status"]) == ["waiting", "hung up"]
    assert app.selectbox(key="record_call").value == live.call_id
    assert any("0 of 5 answers extracted" in element.value for element in app.markdown)
    app.selectbox(key="record_call").set_value(ended.call_id).run()
    assert any("hung up" in caption.value for caption in app.caption)
    assert any("CalFresh" in element.value for element in app.markdown)  # the caller's own words
    assert any("What is happening?" in element.value for element in app.markdown)  # the desk's welcome


def test_the_intake_checklist_fills_in_and_marks_what_the_latest_message_changed(desk):
    queue, _ = desk
    call = queue.add()
    queue.say(call.call_id, "I see smoke", classify=extracted())
    app = run_app()
    app.sidebar.radio[0].set_value("Call records").run()
    assert checklist_row(app, "Situation").startswith("✅") and "Caller reports smoke" in checklist_row(app, "Situation")
    assert checklist_row(app, "Location").startswith("⏳")
    assert "updated by" not in checklist_row(app, "Situation")  # what was there on first look is the baseline
    assert "no extracted field" in checklist_row(app, "Medical or mobility")
    assert any("1 of 5 answers extracted" in element.value for element in app.markdown)

    queue.say(call.call_id, "Unit #2, 12 Oak Street", classify=extracted(location="Unit #2, 12 Oak Street"))
    app.run()
    location = checklist_row(app, "Location")
    assert location.startswith("✅") and r"Unit \#2" in location  # caller words stay literal
    assert "updated by caller message 2" in location
    assert "updated by" not in checklist_row(app, "Situation")

    queue.say(call.call_id, "Two of us", classify=extracted(location="Unit #2, 12 Oak Street", people="2 people"))
    app.run()
    assert "updated by caller message 3" in checklist_row(app, "People")
    assert "updated by" not in checklist_row(app, "Location")
    assert any("3 of 5 answers extracted" in element.value for element in app.markdown)


def replay_table(app):
    return next(frame.value for frame in app.dataframe if "policy" in frame.value.columns)


def test_the_simulator_labels_measured_rates_and_replays_them_next_to_assumed_ones(desk, evaluation_file):
    evaluation_file()
    app = run_app()
    app.sidebar.radio[0].set_value("Scenario simulator").run()
    captions = " ".join(caption.value for caption in app.caption)
    assert "Recorded SMS (test fixture), proxy labels" in captions and "not 211 accuracy" in captions
    measured = next(frame.value for frame in app.dataframe if "method" in frame.value.columns)
    assert list(measured["method"].unique()) == ["FIFO (reference)", "Offline keyword rules", "Claude model mode"]
    assert measured.iloc[0]["miss: needs a person → NORMAL"] == "100% by construction"
    app.radio(key="measured_text").set_value("original").run()
    shares = next(frame.value for frame in app.dataframe if "simulated true tier" in frame.value.columns)
    assert list(shares["UNKNOWN"]) == ["100%"] * 6  # the fixture's originals were all UNKNOWN
    app.button(key="run_replay").click().run()
    policies = set(replay_table(app)["policy"])
    assert policies == {"FIFO", "Keyword rules · assumed rates", "Keyword rules · measured tiers",
                        "Claude · assumed rates (sliders)", "Claude · measured tiers"}
    assert any("(Original text, first message only)" in caption.value for caption in app.caption)
    hung_up = [metric.value for metric in app.metric if metric.label == "Immediate callers who hung up"]
    assert len(hung_up) == 2 and all(" of " in value for value in hung_up)  # assumed and measured Claude rows


def test_without_an_evaluation_the_simulator_says_so_and_replays_assumed_rates(desk):
    app = run_app()
    app.sidebar.radio[0].set_value("Scenario simulator").run()
    assert any("Measured error rates are not available" in warning.value for warning in app.warning)
    app.button(key="run_replay").click().run()
    assert set(replay_table(app)["policy"]) == {"FIFO", "Keyword rules · assumed rates", "Claude · assumed rates (sliders)"}
