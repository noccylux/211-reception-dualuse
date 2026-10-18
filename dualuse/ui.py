"""Caller conversation and operator desk for the local 211 text demo."""
import os
import re

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_URL = os.environ.get("DUALUSE_API_URL", "http://localhost:8000")
# The viewer's browser loads the map frame, so behind a tunnel it needs the public URL, not the server-side API_URL.
MAP_URL = (os.environ.get("DUALUSE_MAP_URL") or API_URL).rstrip("/")
TIER_ICON = {"immediate": "🔴", "priority": "🟠", "unknown": "⚪", "normal": "🟢"}
POLICY_TEXT = {"fifo": "FIFO", "rules": "Keyword rules · assumed rates", "rules_measured": "Keyword rules · measured tiers",
               "model": "Claude · assumed rates (sliders)", "model_measured": "Claude · measured tiers"}
# Hue names the method; hatching marks assumed error rates, solid bars measured ones.
POLICY_COLOR = {"fifo": "#2a78d6", "rules": "#eb6834", "rules_measured": "#eb6834", "model": "#1baf7a", "model_measured": "#1baf7a"}
ASSUMED = ("rules", "model")
METHOD_NAMES = {"fifo": "FIFO (reference)", "rules": "Offline keyword rules", "model": "Claude model mode"}
TEXT_NAMES = {"english": "English translation", "original": "Original text"}
# Which recorded messages stand in for each true tier of a simulated caller (dualuse.evaluation.PROXY_FOR).
PROXY_NAMES = {"immediate": "rescue, medical or death subset", "priority": "needs-a-person sample", "normal": "routine sample"}
TRUE_TIERS = ["immediate", "priority", "normal"]
# The intake playbook's fixed questions in its order (dualuse/playbooks/intake.md): key, label, wording.
INTAKE = [("situation", "Situation", "What is happening?"),
          ("safety", "Safety", "Is anyone hurt, trapped, or in danger right now?"),
          ("location", "Location", "What is the address, or the nearest cross street or landmark?"),
          ("people", "People", "How many people are with you or affected?"),
          ("need", "Need", "What help do you need most right now?"),
          ("detail", "Medical or mobility", "Does anyone there have medical needs, a disability, or trouble moving?")]
SAFETY_TEXT = {"danger": "danger reported", "no_immediate_danger": "no immediate danger reported"}
st.set_page_config(page_title="211 Reception", layout="wide")


class ApiError(Exception):
    pass


def api(method, path, **kwargs):
    try:
        response = httpx.request(method, API_URL + path, timeout=45, **kwargs)
    except httpx.HTTPError as error:
        raise ApiError(f"API unavailable: {type(error).__name__}. Refresh to check whether your action was saved.") from error
    if response.status_code >= 400:
        raise ApiError(f"{response.status_code}: {response.text}")
    return response.json()


def call_api(method, path, **kwargs):
    try:
        return api(method, path, **kwargs)
    except ApiError as error:
        st.error(literal(str(error)))  # error bodies can echo caller text
        st.stop()


def fmt_wait(seconds):
    minutes, rest = divmod(max(0, int(seconds)), 60)
    return f"{minutes}m {rest}s"


def minutes(seconds):
    return None if seconds is None else round(seconds / 60, 1)


def interval(p, by_construction=False):
    if p is None:
        return "n/a"
    if by_construction:
        return f"{p['rate']:.0%} by construction"
    return f"{p['rate']:.1%} ({p['low']:.1%}–{p['high']:.1%})"


def measured_table(saved):
    """One row per method and text column, from the recorded-message evaluation."""
    rows = []
    for method, name in METHOD_NAMES.items():
        for text, text_name in TEXT_NAMES.items():
            m = saved["summaries"][method][text]
            fixed = m.get("by_construction", False)
            subset_n = m["subset_miss"]["n"] if m["subset_miss"] else 0
            rows.append({
                "method": name, "text": text_name,
                "miss: needs a person → NORMAL": interval(m["miss"], fixed),
                "false alarm: routine → IMMEDIATE or PRIORITY": interval(m["false_alarm"], fixed),
                "routine ranked ahead, UNKNOWN included": interval(m["routine_ahead"], fixed),
                "rescue, medical or death → NORMAL": interval(m["subset_miss"], fixed),
                "review flag (needs / routine)": "n/a" if fixed else f"{m['review']['needs']['rate']:.0%} / {m['review']['routine']['rate']:.0%}",
                "failed turns": "n/a" if fixed else str(m["failed"]),
                "n (needs / routine / subset)": f"{m['miss']['n']} / {m['false_alarm']['n']} / {subset_n}",
            })
    return pd.DataFrame(rows)


def mix_table(saved, text):
    """The assigned-tier shares the measured policies replay, per method and simulated true tier."""
    rows = []
    for method in ("rules", "model"):
        for true_tier, proxy in PROXY_NAMES.items():
            shares = saved["assigned_mix"][text][method][true_tier]
            rows.append({"method": METHOD_NAMES[method], "simulated true tier": true_tier, "tiers measured on": proxy,
                         **{tier.upper(): f"{shares[tier]:.0%}" for tier in ("immediate", "priority", "unknown", "normal")}})
    return pd.DataFrame(rows)


def policy_gains(title, results, policy, keyword_policy):
    """One tiered policy against FIFO: waits of served callers and, because waits alone hide callers who
    gave up, immediate callers who hung up; misses against the keyword policy with the same rate source."""
    st.caption(title)
    cols = st.columns(4)
    fifo, ours = results["fifo"]["by_true_tier"], results[policy]["by_true_tier"]
    for col, tier, label in ((cols[0], "immediate", "Immediate tier, P95 wait"), (cols[2], "normal", "Normal tier, P95 wait (the cost)")):
        wait, baseline = ours[tier]["wait_p95"], fifo[tier]["wait_p95"]
        change = minutes(wait - baseline) if None not in (wait, baseline) else None
        col.metric(label, f"{minutes(wait)} min" if wait is not None else "n/a",
                   delta=f"{change} min vs FIFO" if change else None, delta_color="inverse")  # no arrow for no change
    hung_up = ours["immediate"]["abandoned"]
    change = hung_up - fifo["immediate"]["abandoned"]
    cols[1].metric("Immediate callers who hung up", f"{hung_up} of {ours['immediate']['calls']}",
                   delta=f"{change} vs FIFO" if change else None, delta_color="inverse")
    cols[3].metric("Urgent calls ranked normal (misses)", results[policy]["misses"],
                   delta=f"keyword rules: {results[keyword_policy]['misses']}", delta_color="off")


def origin_label(call):
    return "📞 phone (voice bridge)" if call["origin"] == "phone" else call["origin"]


def tier_line(call):
    phone = " · 📞 phone" if call["origin"] == "phone" else ""
    return f"{TIER_ICON[call['tier']]} {call['call_id']} · {call['tier']}{phone}"


def scorer_cell(opinion):
    """The shadow scorer's view of a call, for display next to our tier; it never changes the tier."""
    if not opinion:
        return "—"
    if not opinion["supported"]:
        return opinion["note"]
    if opinion["score"] is None:
        return opinion["note"]
    return f"{opinion['score']} · {opinion['band']}" + (" · ⚠ tier and scorer disagree — operator check" if opinion["disagree"] else "")


def scorer_number(opinion):
    """The shadow score alone for the queue table; the caller details explain it."""
    if not opinion or not opinion["supported"] or opinion["score"] is None:
        return "—"
    return f"{opinion['score']}" + (" ⚠" if opinion["disagree"] else "")


def literal(text):
    """Caller words are untrusted: escape Markdown, math ($) and entities, and break :emoji: codes
    with a zero-width space (Streamlit replaces them even after escaping), so text shows as typed."""
    escaped = re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$:&])", r"\\\1", text)
    return escaped.replace("\\:", "\\:\u200b")


def conversation(dialogue):
    for turn in dialogue:
        if turn["speaker"] == "operator":
            with st.chat_message("operator", avatar=":material/support_agent:"):
                st.markdown("**Operator:** " + literal(turn["text"]))
        else:
            with st.chat_message("user" if turn["speaker"] == "caller" else "assistant"):
                st.markdown(literal(turn["text"]))


def caller_messages(call):
    return sum(turn["speaker"] == "caller" for turn in call["dialogue"])


def intake_answers(extraction):
    """The extracted answer to each intake question that has a field, None while unanswered. The medical or
    mobility question has no field, so its answer is only in the conversation."""
    if not extraction:
        return dict.fromkeys(("situation", "safety", "location", "people", "need"))
    x = extraction
    return {"situation": x["situation"] if x["enough_information"] else None,
            "safety": SAFETY_TEXT.get("danger" if x["life_threat_now"] else x["safety"]),
            "location": x["location"], "people": x["people"], "need": x["need"] or None}


def answer_changes(record, answers, messages):
    """After which caller message each answer last changed, as this browser tab saw it. The first look at a
    call is the baseline, so only changes that happen while someone watches are marked."""
    seen = st.session_state.setdefault("record_seen", {})
    if record not in seen:
        seen[record] = {key: (value, None) for key, value in answers.items()}
    for key, value in answers.items():
        if seen[record][key][0] != value:
            seen[record][key] = (value, messages)
    return {key: message for key, (_, message) in seen[record].items()}


st.title("211 Reception")
st.caption("Demonstration desk · typed calls, and phone calls through the Retell voice bridge when it runs · "
           "no voice transfer to a person, dispatch, or automatic callback")
view = st.sidebar.radio("Workspace", ["Caller conversation", "Operator desk", "Call records", "Incident reports", "Incident map", "Scenario simulator", "About this demo"])
initial = call_api("GET", "/state")
with st.sidebar:
    st.caption("Persistent local desk" if initial["persistent"] else "Memory-only desk")
    mode = st.selectbox("Reception mode", ["model", "rules", "fifo"], index=["model", "rules", "fifo"].index(initial["mode"]),
                        format_func=lambda m: {"model": "Claude: contextual interview", "rules": "Offline: English keyword baseline", "fifo": "FIFO: record without interviewing"}[m])
    if mode != initial["mode"]:
        call_api("POST", "/mode", json={"mode": mode})
        st.rerun()
    if not initial["model_available"]:
        st.info("Model credentials are unavailable. Select the labeled offline mode.")
    names = {p["key"]: p["name"] for p in initial["profiles"]}
    if st.session_state.get("line_profile_seen") != initial["profile"]:
        # Another tab switched the desk: show its choice instead of posting this tab's stale one.
        st.session_state["line_profile"] = st.session_state["line_profile_seen"] = initial["profile"]
    profile = st.selectbox("Line profile (new calls)", list(names), format_func=names.get, key="line_profile")
    if profile != initial["profile"]:
        call_api("POST", "/profile", json={"profile": profile})
        st.session_state["line_profile_seen"] = profile
        st.rerun()
    st.caption("Use two browser tabs for caller and operator. One shared demo queue; no authentication.")
    with st.expander("Reset local demo"):
        clear = st.checkbox("Clear stored calls, reports and history")
        if st.button("Reset desk", disabled=not clear):
            call_api("POST", "/reset", json={"mode": mode})
            st.session_state.pop("selected_call", None)
            st.rerun()


@st.fragment(run_every="2s")
def caller_panel():
    state = call_api("GET", "/state")
    st.info("**Text line.** Type instead of talking: this page plays no sound, so you can use it when speaking is unsafe.")
    if st.button("Join as a new caller", type="primary"):
        row = call_api("POST", "/calls", json={})
        st.session_state["selected_call"] = row["call_id"]
        st.rerun(scope="fragment")
    ids = [c["call_id"] for c in state["calls"]]
    if not ids:
        st.info("Join the queue to start a conversation with the reception assistant.")
        return
    if st.session_state.get("selected_call") not in ids:
        st.session_state["selected_call"] = ids[-1]
    call_id = st.selectbox("Conversation", ids, key="selected_call")
    call = next(c for c in state["calls"] if c["call_id"] == call_id)
    if call["status"] == "waiting":
        position = call["fifo_position"] if state["active_policy"] == "fifo" else call["tiered_position"]
        st.info(f"Waiting · currently {position} callers ahead · {fmt_wait(call['waited_s'])}. Order may change with urgency.")
    elif call["status"] == "connecting":
        st.info("An operator is joining. You can keep typing; your messages are saved for them.")
    elif call["status"] == "handed_off" and call["origin"] != "phone":
        st.info("An operator has taken over. Their replies appear below; type here to answer.")
    else:
        st.info("Call status: " + call["status"].replace("_", " "))
    if call["error"]:
        st.warning("The last message was saved, but automated processing failed. An operator can review it.")
    st.caption(f"Line: {next(p['name'] for p in state['profiles'] if p['key'] == call['profile'])}")
    conversation(call["dialogue"])
    if call["processing"]:
        st.caption("The assistant is processing your message. An operator can still take over.")
    # Keyed: without a key the placeholder change at takeover would remount the input and drop a draft.
    text = st.chat_input("Tell the assistant what is happening" if call["status"] == "waiting" else "Type a message to the operator",
                         key=f"caller-input-{call_id}", max_chars=4000,
                         disabled=call["status"] not in ("waiting", "connecting", "handed_off") or call["processing"])
    if text:
        try:
            api("POST", f"/calls/{call_id}/say", json={"text": text})
        except ApiError as error:
            st.session_state["turn_error"] = str(error)
        st.rerun(scope="fragment")
    if "turn_error" in st.session_state:
        st.error(literal(st.session_state.pop("turn_error")))
    with st.expander("Demo call events and sample prompts"):
        st.caption("These controls simulate connection events; there is no audio detector or phone call.")
        cols = st.columns(3)
        waiting = call["status"] == "waiting"
        active = call["status"] in ("waiting", "connecting")
        if cols[0].button("No response event", disabled=not waiting or call["processing"]):
            call_api("POST", f"/calls/{call_id}/silence")
            st.rerun(scope="fragment")
        if cols[1].button("Connection lost", disabled=not active):
            call_api("POST", f"/calls/{call_id}/disconnect")
            st.rerun(scope="fragment")
        if cols[2].button("Caller chooses to hang up", disabled=not active):
            call_api("POST", f"/calls/{call_id}/hangup")
            st.rerun(scope="fragment")
        st.caption("Team-written scenario: 'I see smoke' → 'at 12 Oak Street' → 'someone is shouting for help inside'.")


def caller_details(state, opinions, rule):
    """One details panel for the waiting caller picked in the selector, instead of one panel per caller."""
    waiting = {c["call_id"]: c for c in state["waiting"]}
    if st.session_state.get("detail_call") not in waiting:
        st.session_state["detail_call"] = next(iter(waiting))  # the head of the queue
    # Labels must not change while a call waits: the browser sends back the label it showed, and a
    # label that changed with the tier would no longer match, dropping the operator's choice.
    call = waiting[st.selectbox("Caller details", list(waiting), key="detail_call",
                                format_func=lambda i: i + (" · 📞 phone" if waiting[i]["origin"] == "phone" else ""))]
    opinion = opinions.get(call["call_id"])
    with st.container(border=True):
        st.caption(f"{tier_line(call)} · waiting {fmt_wait(call['waited_s'])} · origin: {origin_label(call)} · source: {call['source']} · "
                   f"interview {'running' if call['processing'] else 'idle'} · "
                   f"language: {call['language']} · distress: {call['distress']}")
        if call["attention"]:
            st.warning(literal(call["attention"]))
        st.text(call["summary"])
        shared = next((c for c in state["clusters"] if call["call_id"] in c["call_ids"] and c["count"] > 1), None)
        if shared:
            st.info(literal(f"Possible shared incident, unverified: {shared['count']} reports of {shared['kind']} at "
                            f"{shared['location']} ({', '.join(shared['call_ids'])})"))
        st.caption(f"Shadow scorer (display only): {scorer_cell(opinion)}"
                   + (f" · open needs: {', '.join(opinion['needs'])}" if opinion and opinion["needs"] else "")
                   + ". The CrisisFusion Human Attention Index (classmate's English/Spanish rules) reads only the "
                   "caller's words. It never changes a tier or the queue order. " + rule)
        with st.expander("Extracted fields"):
            st.write(call["extraction"] or "No extraction yet")
        for turn in call["dialogue"]:
            st.markdown(literal(f"{turn['speaker']}: {turn['text']}"))


@st.fragment(run_every="2s")
def operator_panel():
    state = call_api("GET", "/state")
    metrics = st.columns(4)
    metrics[0].metric("Waiting", len(state["waiting"]))
    metrics[1].metric("Immediate", sum(c["tier"] == "immediate" for c in state["waiting"]))
    metrics[2].metric("Needs review", sum(bool(c["attention"]) for c in state["calls"] if c["status"] == "waiting"))
    metrics[3].metric("Callback tasks", sum(c["callback_status"] == "pending_review" for c in state["calls"]))
    with st.expander("Demo surge: inject callers (simulated arrivals)"):
        st.caption("Scripts are team-written callers (simulated). Messages are recorded disaster messages from the "
                   "Munro dataset (2010 Haiti and Pakistan SMS, Hurricane Sandy posts; English translation) used as first messages, not "
                   "211 calls. The Austin pattern time-compresses real APD 911 dispatch timestamps.")
        cols = st.columns(4)
        count = cols[0].number_input("Callers", 1, 60, 20, key="surge_count")
        source = cols[1].selectbox("Content", ["mixed", "scripts", "messages"], key="surge_source")
        pattern = cols[2].selectbox("Arrivals", ["austin", "even"], key="surge_pattern")
        span = cols[3].number_input("Over seconds", 0, 600, 60, key="surge_span")
        if st.button("Inject surge", key="surge_start"):
            call_api("POST", "/demo/surge", json={"count": int(count), "source": source, "pattern": pattern,
                                                  "span_s": float(span), "seed": 7})
        surge = call_api("GET", "/demo/surge")
        if surge.get("planned"):
            st.caption(f"Surge {'running' if surge['running'] else 'finished'}: {surge['joined']} of {surge['planned']} "
                       f"callers joined, {surge['turns']} caller turns")
            for error in surge["errors"]:
                st.error(literal(error))
    operator = st.selectbox("Operator seat", ["operator-1", "operator-2", "operator-3"])
    busy = any(c["operator_id"] == operator and c["status"] in ("connecting", "handed_off") for c in state["calls"])
    if st.button("Available: reserve next caller", type="primary", disabled=busy or not state["waiting"]):
        st.session_state.pop("reply_error", None)
        call_api("POST", "/operator/free", json={"operator_id": operator})
        st.rerun(scope="fragment")
    if "reply_error" in st.session_state:
        # Outside the call card, which closes if the call ended meanwhile; the next reply or reservation clears it.
        st.error(literal(st.session_state["reply_error"]))
    for call in state["calls"]:
        if call["operator_id"] == operator and call["status"] in ("connecting", "handed_off"):
            with st.container(border=True):
                st.subheader(f"{call['call_id']} · {call['status']}")
                if call["origin"] == "phone":
                    st.info("Phone caller on the Retell voice bridge. Voice transfer is not connected: the caller "
                            "hears a fixed notice that an operator has the case and cannot hear you from this console.")
                st.text(call["summary"])
                with st.expander("Full conversation", expanded=False):
                    for turn in call["dialogue"]:
                        st.markdown(literal(f"{turn['speaker']}: {turn['text']}"))
                if call["status"] == "connecting":
                    cols = st.columns(2)
                    if cols[0].button("Confirm human takeover", key=f"confirm-{call['transfer_id']}"):
                        call_api("POST", f"/handoffs/{call['transfer_id']}/confirm", json={"success": True})
                        st.rerun(scope="fragment")
                    if cols[1].button("Transfer failed: return to queue", key=f"fail-{call['transfer_id']}"):
                        call_api("POST", f"/handoffs/{call['transfer_id']}/confirm", json={"success": False})
                        st.rerun(scope="fragment")
                else:
                    if call["origin"] != "phone":
                        st.caption("Latest messages" if call["origin"] == "live" else
                                   "Latest messages · simulated or replayed caller: replies are saved, but nobody reads them")
                        for turn in call["dialogue"][-6:]:
                            st.markdown(literal(f"{turn['speaker']}: {turn['text']}"))
                        reply = st.chat_input("Reply to the caller", key=f"reply-{call['call_id']}", max_chars=4000)
                        if reply:
                            try:
                                api("POST", f"/calls/{call['call_id']}/operator-message",
                                    json={"operator_id": operator, "text": reply})
                                st.session_state.pop("reply_error", None)
                            except ApiError as error:
                                st.session_state["reply_error"] = f"Reply to {call['call_id']} not sent: {error}"
                            st.rerun(scope="fragment")
                    if st.button("Operator finished this call", key=f"done-{call['call_id']}"):
                        call_api("POST", f"/calls/{call['call_id']}/complete")
                        st.rerun(scope="fragment")
    st.subheader("Waiting queue")
    scorer = state["scorer"]
    opinions = scorer["opinions"]
    if scorer["error"]:
        st.error(literal(f"Shadow scorer stopped updating: {scorer['error']}"))
    if state["waiting"]:
        st.dataframe([{"queue position": i + 1, "call": c["call_id"], "tier": f"{TIER_ICON[c['tier']]} {c['tier']}",
                       "wait": fmt_wait(c["waited_s"]), "FIFO position": c["fifo_position"] + 1,
                       "language": c["language"], "review": "⚑" if c["attention"] else "",
                       "shadow score (advisory)": scorer_number(opinions.get(c["call_id"])), "origin": origin_label(c)}
                      for i, c in enumerate(state["waiting"])], hide_index=True)
        caller_details(state, opinions, scorer["rule"])
    tasks = [c for c in state["calls"] if c["callback_status"] == "pending_review"]
    if tasks:
        st.subheader("Callback review · no automatic dialing")
    for call in tasks:
        with st.expander(f"{call['call_id']} · {call['status']} · {call['tier']}"):
            st.text(call["summary"])
            st.caption("The desk stores no caller telephone number, phone calls included. Record the operator's review outcome only.")
            disposition = st.selectbox("Outcome", ["handled_by_operator", "no_callback_needed"], key=f"review-{call['call_id']}")
            if st.button("Record review", key=f"review-save-{call['call_id']}"):
                call_api("POST", f"/calls/{call['call_id']}/callback-review", json={"disposition": disposition})
                st.rerun(scope="fragment")
    with st.expander("Audit trail and completed handoffs"):
        st.dataframe(list(reversed(state["events"])), hide_index=True)
        for handoff in reversed(state["handoffs"]):
            st.write(f"{handoff['call_id']} → {handoff['operator_id']}")
            st.text(handoff["summary"])


@st.fragment(run_every="2s")
def records_panel():
    state = call_api("GET", "/state")
    calls = list(reversed(state["calls"]))  # newest first
    if not calls:
        st.info("No calls yet. A record appears here as soon as a caller joins.")
        return
    st.caption("Every call on the desk, ended calls included. Answers are what the assistant extracted from the "
               "caller's words; nobody has verified them.")
    st.dataframe([{"call": c["call_id"], "status": c["status"].replace("_", " "), "tier": f"{TIER_ICON[c['tier']]} {c['tier']}",
                   "caller messages": caller_messages(c), "time on the line": fmt_wait(c["waited_s"]), "origin": origin_label(c)}
                  for c in calls], hide_index=True)
    by_id = {c["call_id"]: c for c in calls}
    if st.session_state.get("record_call") not in by_id:
        st.session_state["record_call"] = calls[0]["call_id"]
    # Labels stay fixed while the status and tier change, as in caller_details.
    call = by_id[st.selectbox("Call record", list(by_id), key="record_call",
                              format_func=lambda i: i + (" · 📞 phone" if by_id[i]["origin"] == "phone" else ""))]
    st.caption(f"{tier_line(call)} · {call['status'].replace('_', ' ')} · on the line {fmt_wait(call['waited_s'])} · "
               f"origin: {origin_label(call)} · language: {call['language']} · distress: {call['distress']}"
               + (f" · operator: {call['operator_id']}" if call["operator_id"] else "")
               + (" · interview running" if call["processing"] else ""))
    if call["attention"]:
        st.warning(literal(call["attention"]))
    if call["error"]:
        st.warning(literal(call["error"]))
    answers = intake_answers(call["extraction"])
    messages = caller_messages(call)
    changed = answer_changes(f"{call['call_id']}@{call['arrival']}", answers, messages)
    done = sum(value is not None for value in answers.values())
    left, right = st.columns([2, 3])
    with left.container(border=True):
        st.markdown(f"**Intake checklist** · {done} of {len(answers)} answers extracted")
        st.progress(done / len(answers))
        for key, label, question in INTAKE:
            if key not in answers:
                st.markdown(f"➖ **{label}** · no extracted field; read the conversation", help=question)
                continue
            value = answers[key]
            new = value is not None and changed[key] == messages
            st.markdown(("✅" if value is not None else "⏳") + f" **{label}** · "
                        + (literal(value) if value is not None else "not answered yet")
                        + (f" :orange-badge[updated by caller message {messages}]" if new else ""), help=question)
        if call["extraction"]:
            evidence = "; ".join(f'"{quote}"' for quote in call["extraction"]["evidence"]) or "none"
            st.caption(literal(f"Caller's words behind the tier: {evidence}"))
            st.caption(literal("Still unknown, per the assistant: " + (", ".join(call["extraction"]["missing"]) or "nothing flagged")))
    with right.container(border=True):
        st.markdown("**Full conversation**")
        conversation(call["dialogue"])


@st.fragment(run_every="2s")
def incident_panel():
    state = call_api("GET", "/state")
    st.info("Unverified caller reports. Matching kind and stated location suggests a possible shared incident; it does not verify the event or dispatch anyone.")
    for cluster in state["clusters"]:
        with st.container(border=True):
            st.subheader(literal(f"{cluster['kind']} · {cluster['location']}"))
            st.write(f"{cluster['count']} reports · " + ", ".join(cluster["call_ids"]))
            for call_id, situation in zip(cluster["call_ids"], cluster["situations"]):
                st.markdown(literal(f"{call_id}: {situation}"))
    if not state["clusters"]:
        st.caption("Reports appear when callers identify an incident and its location.")


if view == "Caller conversation":
    caller_panel()
elif view == "Operator desk":
    operator_panel()
elif view == "Call records":
    records_panel()
elif view == "Incident reports":
    incident_panel()
elif view == "Incident map":
    status = initial["map"]
    if status["error"]:
        st.error(f"The map stopped updating: {status['error']}")
    if status["locate_error"]:
        st.error(f"Automatic address lookup stopped: {status['locate_error']}")
    st.info(f"{status['area']} service area for the active line, from the CrisisFusion map plugin. The base map "
            "covers the world; only this line's calls are drawn. A call located outside the area is grey and marked "
            "'outside service area — transfer': real lines route by jurisdiction. Test calls can come from anywhere in the world; use 'Show all calls' on the map to reach them. "
            "The place the desk extracts from a call is looked up automatically in OpenStreetMap, inside the service "
            "area only; only that place text is sent, never the call text. A single match is drawn as an unverified "
            "diamond until a person confirms it; several matches are listed for the operator. Shape shows how far a caller's stated "
            "address is verified; color shows official alerts or USGS quakes around it, fetched only when you press "
            "refresh. Grey means unknown or out of area, never safe. Calls with coordinates from test data are labeled "
            "synthetic replay. The map does not change any queue tier.")
    if status["other_lines"]:
        st.caption(f"{status['other_lines']} calls answered under another line profile are not drawn on this map.")
    # Not a timed fragment: re-rendering would reload the iframe. The plugin page has its own refresh.
    # The profile in the URL reloads the frame when the desk switches line and the map app is replaced.
    st.components.v1.iframe(f"{MAP_URL}/plugins/map/?line={status['profile']}", height=1500, scrolling=True)
elif view == "Scenario simulator":
    st.markdown(
        "**Simulated.** A synthetic surge from the parameters below, replayed under several queue policies with the "
        "same arrivals, operators, service times and caller patience. Defaults are informed by 211 LA's "
        "January 2025 after-action report (2025-01-08: 7,815 contacts, 60.66% abandoned, 1 h 23 min average "
        "wait, 6 min 16 s handle time); the arrival process, tier mix, patience and assumed error rates are "
        "assumptions. Measured error rates come from recorded messages, below."
    )
    saved = call_api("GET", "/evaluation")
    measured_text = "english"
    with st.container(border=True):
        if saved["available"]:
            st.markdown("**Measured error rates · recorded messages, proxy labels**")
            st.caption(f"{saved['label']}. Scored against the dataset's category labels as proxies (request = needs a "
                       "person), one message per caller, through the desk's own offline and Claude paths. These are not "
                       "211 calls, so the rates are not 211 accuracy. 95% Wilson intervals in parentheses. Run: "
                       f"{saved['generated_at']}; method and limits in docs/evaluation.md.")
            st.dataframe(measured_table(saved), hide_index=True, use_container_width=True)
            measured_text = st.radio("Replay the measured tiers from", list(TEXT_NAMES), format_func=TEXT_NAMES.get,
                                     horizontal=True, key="measured_text")
            with st.expander("Tier shares the measured policies replay"):
                st.dataframe(mix_table(saved, measured_text), hide_index=True, use_container_width=True)
        else:
            st.warning("Measured error rates are not available: run scripts/evaluate_messages.py (docs/evaluation.md), "
                       "which writes data/processed/eval_messages.json. The replay uses assumed rates only.")
    left, middle, right = st.columns(3)
    duration_h = left.number_input("Surge length (hours)", 0.5, 12.0, 2.0, 0.5)
    arrivals = left.number_input("Calls per hour", 10, 1000, 120, 10)
    operators = left.number_input("Operators on shift", 1, 100, 8)
    service_s = middle.number_input("Mean handle time (s)", 30, 1800, 376, 10)
    patience_min = middle.number_input("Mean caller patience (min)", 1.0, 240.0, 20.0, 1.0)
    decision_s = middle.number_input("Interview + extraction delay (s)", 0, 600, 45, 5)
    immediate_share = right.slider("True share: immediate", 0.0, 0.5, 0.03, 0.01)
    priority_share = right.slider("True share: priority", 0.0, 0.9, 0.22, 0.01)
    miss_rate = right.slider("Assumed Claude miss rate (urgent ranked normal)", 0.0, 0.5, 0.05, 0.01)
    false_alarm = right.slider("Assumed Claude false-alarm rate (routine ranked with priority)", 0.0, 0.5, 0.10, 0.01)
    aging_min = right.number_input("Aging guard: promote normal after (min)", 5, 180, 30, 5)
    seed = right.number_input("Seed", 0, 10_000, 7)
    normal_share = round(1 - immediate_share - priority_share, 4)
    st.caption(f"True share: normal = {normal_share:.2f}. The assumed keyword-rules policy uses a 25% miss rate and 30% "
               "false alarms. Measured policies give each simulated caller a tier drawn from the tiers the desk gave "
               "recorded messages: a true IMMEDIATE caller from the rescue, medical or death subset, PRIORITY from the "
               "needs-a-person sample, NORMAL from the routine sample. UNKNOWN shares PRIORITY's queue rank.")

    if st.button("Run the replay", type="primary", key="run_replay"):
        body = {
            "duration_s": duration_h * 3600,
            "arrivals_per_hour": arrivals,
            "operators": int(operators),
            "tier_mix": {"immediate": immediate_share, "priority": priority_share, "normal": normal_share},
            "mean_service_s": service_s,
            "mean_patience_s": patience_min * 60,
            "decision_delay_s": decision_s,
            "miss_rate": miss_rate,
            "false_alarm_rate": false_alarm,
            "seed": int(seed),
            "max_normal_wait_s": aging_min * 60,
            "measured_text": measured_text,
        }
        try:
            st.session_state["replay"] = api("POST", "/simulate", json=body)
        except ApiError as error:
            st.error(f"The scenario was rejected: {error}")

    result = st.session_state.get("replay")
    if result:
        results = result["results"]
        policies = [policy for policy in POLICY_TEXT if policy in results]
        rows = []
        for policy in policies:
            for tier in TRUE_TIERS:
                stats = results[policy]["by_true_tier"][tier]
                rows.append(
                    {
                        "policy": POLICY_TEXT[policy],
                        "true tier": tier,
                        "calls": stats["calls"],
                        "served": stats["served"],
                        "abandoned": stats["abandoned"],
                        "wait P50 (min)": minutes(stats["wait_p50"]),
                        "wait P95 (min)": minutes(stats["wait_p95"]),
                        "wait mean (min)": minutes(stats["wait_mean"]),
                    }
                )
        table = pd.DataFrame(rows)

        fig = go.Figure()
        for policy in policies:
            fig.add_bar(
                name=POLICY_TEXT[policy],
                x=TRUE_TIERS,
                y=[minutes(results[policy]["by_true_tier"][tier]["wait_p95"]) for tier in TRUE_TIERS],
                marker_color=POLICY_COLOR[policy],
                marker_pattern_shape="/" if policy in ASSUMED else "",
                marker_pattern_fgcolor="#fcfcfb",
                marker_line_width=0,
                hovertemplate="%{x}: P95 wait %{y} min<extra>" + POLICY_TEXT[policy] + "</extra>",
            )
        fig.update_layout(
            barmode="group",
            bargap=0.3,
            bargroupgap=0.08,
            title="P95 wait for a human, by true tier (minutes, simulated surge)",
            yaxis_title="minutes",
            xaxis_title="true tier",
            legend_title="queue policy",
            plot_bgcolor="#fcfcfb",
            paper_bgcolor="#fcfcfb",
            margin=dict(t=60, r=20, l=40, b=40),
        )
        fig.update_yaxes(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7")
        st.plotly_chart(fig, use_container_width=True)
        measured = result["measured"]
        st.caption("Hatched bars use assumed error rates. " + (
            f"Solid bars draw tiers measured on recorded disaster messages with proxy labels ({TEXT_NAMES[measured['text']]}, "
            "first message only); the surge itself is simulated." if measured else "No measured tiers were available for this replay."))
        st.caption("One replay is one random draw. At a 3% immediate share a two-hour run has only a handful of immediate "
                   "callers, so their waits swing between seeds, and a P95 wait covers only callers who did not hang up.")

        policy_gains("Claude at the assumed rates (sliders):", results, "model", "rules")
        if measured:
            policy_gains("Claude with tiers measured on recorded disaster messages (proxy labels, not 211 accuracy):",
                         results, "model_measured", "rules_measured")
        st.dataframe(table, hide_index=True, use_container_width=True)
        shares = pd.DataFrame({POLICY_TEXT[policy]: results[policy]["assigned_share"] for policy in policies}).T
        st.caption("Share of calls in each assigned tier (the policy's view), and totals served / abandoned:")
        shares["served"] = [results[policy]["served"] for policy in policies]
        shares["abandoned"] = [results[policy]["abandoned"] for policy in policies]
        st.dataframe(shares, use_container_width=True)
        st.caption(result["note"])


elif view == "About this demo":
    st.markdown("""
This build interviews callers through typed messages and, when the separate Retell voice bridge
runs, through English phone calls marked 📞 phone. Claude extracts fields and proposes a
contextual follow-up question; the program controls queue ordering, recording and handoff.
Offline mode uses English keywords and fixed questions and is explicitly labeled.

Calls, conversations, reports, callback tasks and audit events persist in a local SQLite database.
A phone caller's voice is never transferred to a person: on handoff the caller hears a fixed notice.
There is no medical advice workflow, dispatch, or automated callback.
The operator confirms handoff using the demo controls. Treat the desk as a local, single-process demo.

The scenario simulator uses synthetic calls. Its error rates are either **assumed** (the sliders and
the keyword-rules default) or **measured** on recorded 2010 Haiti and Pakistan SMS and Hurricane Sandy
posts, first message only, against the dataset's category labels as proxies (docs/evaluation.md). Those messages are not 211
calls, so the measured rates are not 211 accuracy. The simulator does not run Claude or measure
real-world waiting times. No model has been trained on the downloaded datasets.
""")
    for invariant in initial["invariants"]:
        st.write("• " + invariant)
