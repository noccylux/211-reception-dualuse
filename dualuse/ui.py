"""Caller conversation and operator desk for the local 211 text demo."""
import os
import re

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_URL = os.environ.get("DUALUSE_API_URL", "http://localhost:8000")
TIER_ICON = {"immediate": "🔴", "priority": "🟠", "unknown": "⚪", "normal": "🟢"}
POLICY_TEXT = {"fifo": "FIFO", "rules": "Assumed keyword accuracy", "model": "Assumed model accuracy"}
POLICY_COLOR = {"fifo": "#2a78d6", "rules": "#eb6834", "model": "#1baf7a"}
TRUE_TIERS = ["immediate", "priority", "normal"]
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


def origin_label(call):
    return "📞 phone (voice bridge)" if call["origin"] == "phone" else call["origin"]


def tier_line(call):
    # No ticking wait time here: Streamlit collapses an expander whenever its label changes.
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


def literal(text):
    """Caller words are untrusted: escape Markdown, math ($) and entities, and break :emoji: codes
    with a zero-width space (Streamlit replaces them even after escaping), so text shows as typed."""
    escaped = re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$:&])", r"\\\1", text)
    return escaped.replace("\\:", "\\:\u200b")


st.title("211 Reception")
st.caption("Demonstration desk · typed calls, and phone calls through the Retell voice bridge when it runs · "
           "no voice transfer to a person, dispatch, or automatic callback")
view = st.sidebar.radio("Workspace", ["Caller conversation", "Operator desk", "Incident reports", "Incident map", "Scenario simulator", "About this demo"])
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
    else:
        st.info("Call status: " + call["status"].replace("_", " "))
    if call["error"]:
        st.warning("The last message was saved, but automated processing failed. An operator can review it.")
    st.caption(f"Line: {next(p['name'] for p in state['profiles'] if p['key'] == call['profile'])}")
    for turn in call["dialogue"]:
        with st.chat_message("user" if turn["speaker"] == "caller" else "assistant"):
            st.markdown(literal(turn["text"]))
    if call["processing"]:
        st.caption("The assistant is processing your message. An operator can still take over.")
    text = st.chat_input("Tell the assistant what is happening", max_chars=4000,
                         disabled=call["status"] != "waiting" or call["processing"])
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


@st.fragment(run_every="2s")
def operator_panel():
    state = call_api("GET", "/state")
    metrics = st.columns(4)
    metrics[0].metric("Waiting", len(state["waiting"]))
    metrics[1].metric("Immediate", sum(c["tier"] == "immediate" for c in state["waiting"]))
    metrics[2].metric("Needs review", sum(bool(c["attention"]) for c in state["calls"] if c["status"] == "waiting"))
    metrics[3].metric("Callback tasks", sum(c["callback_status"] == "pending_review" for c in state["calls"]))
    with st.expander("Demo surge: inject callers (simulated arrivals)"):
        st.caption("Scripts are team-written callers (simulated). Messages are real disaster SMS from the Munro "
                   "dataset (Haiti 2010, Sandy, Pakistan floods; English translation) used as first messages, not "
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
        call_api("POST", "/operator/free", json={"operator_id": operator})
        st.rerun(scope="fragment")
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
                elif st.button("Operator finished this call", key=f"done-{call['call_id']}"):
                    call_api("POST", f"/calls/{call['call_id']}/complete")
                    st.rerun(scope="fragment")
    st.subheader("Waiting queue")
    scorer = state["scorer"]
    opinions = scorer["opinions"]
    if scorer["error"]:
        st.error(literal(f"Shadow scorer stopped updating: {scorer['error']}"))
    if state["waiting"]:
        st.dataframe([{"call": c["call_id"], "tier": c["tier"],
                       "shadow scorer (display only)": scorer_cell(opinions.get(c["call_id"])),
                       "open needs (scorer)": ", ".join((opinions.get(c["call_id"]) or {}).get("needs", [])),
                       "wait": fmt_wait(c["waited_s"]),
                       "FIFO position": c["fifo_position"] + 1, "tiered position": c["tiered_position"] + 1,
                       "language": c["language"], "processing": c["processing"], "review": c["attention"],
                       "origin": origin_label(c)} for c in state["waiting"]], hide_index=True)
        st.caption("Shadow scorer: the CrisisFusion Human Attention Index (classmate's English/Spanish rules) reads only "
                   "the caller's words. It never changes a tier or the queue order. " + scorer["rule"])
    for call in state["waiting"]:
        opinion = opinions.get(call["call_id"])
        with st.expander(tier_line(call)):
            st.caption(f"Waiting {fmt_wait(call['waited_s'])} · origin: {origin_label(call)} · source: {call['source']} · "
                       f"interview {'running' if call['processing'] else 'idle'} · "
                       f"language: {call['language']} · distress: {call['distress']}")
            st.caption(f"Shadow scorer (display only): {scorer_cell(opinion)}"
                       + (f" · open needs: {', '.join(opinion['needs'])}" if opinion and opinion["needs"] else ""))
            if call["attention"]:
                st.warning(literal(call["attention"]))
            st.text(call["summary"])
            st.write(call["extraction"] or "No extraction yet")
            for turn in call["dialogue"]:
                st.markdown(literal(f"{turn['speaker']}: {turn['text']}"))
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
elif view == "Incident reports":
    incident_panel()
elif view == "Incident map":
    status = initial["map"]
    if status["error"]:
        st.error(f"The map stopped updating: {status['error']}")
    st.info(f"{status['area']} service area for the active line, from the CrisisFusion map plugin. The base map "
            "covers the world; only this line's calls are drawn. A call located outside the area is grey and marked "
            "'outside service area — transfer': real lines route by jurisdiction. Test calls can come from anywhere in the world; use 'Show all calls' on the map to reach them. Shape shows how far a caller's stated "
            "address is verified; color shows official alerts or USGS quakes around it, fetched only when you press "
            "refresh. Grey means unknown or out of area, never safe. Calls with coordinates from test data are labeled "
            "synthetic replay. The map does not change any queue tier.")
    if status["other_lines"]:
        st.caption(f"{status['other_lines']} calls answered under another line profile are not drawn on this map.")
    # Not a timed fragment: re-rendering would reload the iframe. The plugin page has its own refresh.
    # The profile in the URL reloads the frame when the desk switches line and the map app is replaced.
    st.components.v1.iframe(f"{API_URL}/plugins/map/?line={status['profile']}", height=1500, scrolling=True)
elif view == "Scenario simulator":
    st.markdown(
        "**Simulated.** A synthetic surge from the parameters below, replayed under three queue policies with the "
        "same arrivals, operators, service times and caller patience. Defaults are informed by 211 LA's "
        "January 2025 after-action report (2025-01-08: 7,815 contacts, 60.66% abandoned, 1 h 23 min average "
        "wait, 6 min 16 s handle time); the arrival process, tier mix, patience and error rates are assumptions."
    )
    left, middle, right = st.columns(3)
    duration_h = left.number_input("Surge length (hours)", 0.5, 12.0, 2.0, 0.5)
    arrivals = left.number_input("Calls per hour", 10, 1000, 120, 10)
    operators = left.number_input("Operators on shift", 1, 100, 8)
    service_s = middle.number_input("Mean handle time (s)", 30, 1800, 376, 10)
    patience_min = middle.number_input("Mean caller patience (min)", 1.0, 240.0, 20.0, 1.0)
    decision_s = middle.number_input("Interview + extraction delay (s)", 0, 600, 45, 5)
    immediate_share = right.slider("True share: immediate", 0.0, 0.5, 0.03, 0.01)
    priority_share = right.slider("True share: priority", 0.0, 0.9, 0.22, 0.01)
    miss_rate = right.slider("Model miss rate (urgent ranked normal)", 0.0, 0.5, 0.05, 0.01)
    false_alarm = right.slider("Model false-alarm rate (normal ranked priority)", 0.0, 0.5, 0.10, 0.01)
    aging_min = right.number_input("Aging guard: promote normal after (min)", 5, 180, 30, 5)
    seed = right.number_input("Seed", 0, 10_000, 7)
    normal_share = round(1 - immediate_share - priority_share, 4)
    st.caption(f"True share: normal = {normal_share:.2f}. The keyword-rules policy assumes a 25% miss rate and 30% false alarms.")

    if st.button("Run the replay", type="primary"):
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
        }
        try:
            st.session_state["replay"] = api("POST", "/simulate", json=body)
        except ApiError as error:
            st.error(f"The scenario was rejected: {error}")

    result = st.session_state.get("replay")
    if result:
        results = result["results"]
        rows = []
        for policy, summary in results.items():
            for tier in TRUE_TIERS:
                stats = summary["by_true_tier"][tier]
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
        for policy, summary in results.items():
            fig.add_bar(
                name=POLICY_TEXT[policy],
                x=TRUE_TIERS,
                y=[minutes(summary["by_true_tier"][tier]["wait_p95"]) for tier in TRUE_TIERS],
                marker_color=POLICY_COLOR[policy],
                marker_line_width=0,
                hovertemplate="%{x}: P95 wait %{y} min<extra>" + POLICY_TEXT[policy] + "</extra>",
            )
        fig.update_layout(
            barmode="group",
            bargap=0.3,
            bargroupgap=0.08,
            title="P95 wait for a human, by true tier (minutes, simulated)",
            yaxis_title="minutes",
            xaxis_title="true tier",
            legend_title="queue policy",
            plot_bgcolor="#fcfcfb",
            paper_bgcolor="#fcfcfb",
            margin=dict(t=60, r=20, l=40, b=40),
        )
        fig.update_yaxes(gridcolor="#e1e0d9", zerolinecolor="#c3c2b7")
        st.plotly_chart(fig, use_container_width=True)

        gains = st.columns(3)
        fifo_imm = results["fifo"]["by_true_tier"]["immediate"]["wait_p95"]
        model_imm = results["model"]["by_true_tier"]["immediate"]["wait_p95"]
        fifo_norm = results["fifo"]["by_true_tier"]["normal"]["wait_p95"]
        model_norm = results["model"]["by_true_tier"]["normal"]["wait_p95"]
        gains[0].metric(
            "Immediate tier, P95 wait",
            f"{minutes(model_imm)} min" if model_imm is not None else "n/a",
            delta=(f"{minutes(model_imm - fifo_imm)} min vs FIFO" if None not in (model_imm, fifo_imm) else None),
            delta_color="inverse",
        )
        gains[1].metric(
            "Normal tier, P95 wait (the cost)",
            f"{minutes(model_norm)} min" if model_norm is not None else "n/a",
            delta=(f"{minutes(model_norm - fifo_norm)} min vs FIFO" if None not in (model_norm, fifo_norm) else None),
            delta_color="inverse",
        )
        gains[2].metric(
            "Urgent calls ranked normal (misses)",
            results["model"]["misses"],
            delta=f"rules: {results['rules']['misses']}",
            delta_color="off",
        )
        st.dataframe(table, hide_index=True, use_container_width=True)
        shares = pd.DataFrame(
            {POLICY_TEXT[policy]: summary["assigned_share"] for policy, summary in results.items()}
        ).T
        st.caption("Share of calls in each assigned tier (the policy's view), and totals served / abandoned:")
        shares["served"] = [summary["served"] for summary in results.values()]
        shares["abandoned"] = [summary["abandoned"] for summary in results.values()]
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

The scenario simulator uses synthetic calls and **assumed** classifier error rates. It does not
run Claude or measure real-world waiting times. No model has been trained or evaluated on the
downloaded datasets in this version. Real-data evaluation is a separate next step.
""")
    for invariant in initial["invariants"]:
        st.write("• " + invariant)
