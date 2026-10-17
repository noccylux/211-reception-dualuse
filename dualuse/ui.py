"""Streamlit supervisor board for the hold-queue assistant, a client of `dualuse.api`.

Run: bash scripts/uv-run.sh streamlit run dualuse/ui.py --server.port 8501
Every panel says whether what it shows is live, recorded or simulated.
"""

import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_URL = os.environ.get("DUALUSE_API_URL", "http://localhost:8000")

TIER_ICON = {"immediate": "🔴", "priority": "🟠", "unknown": "⚪", "normal": "🟢"}
TIER_TEXT = {
    "immediate": "IMMEDIATE, life-threatening now",
    "priority": "PRIORITY, needs a person soon",
    "unknown": "UNKNOWN, not enough information (kept with priority)",
    "normal": "NORMAL, can wait",
}
MODE_TEXT = {
    "model": "Model: Claude extracts fields, rules decide the tier",
    "rules": "Rules: keyword baseline, no model",
    "fifo": "FIFO: classification off, today's order (degraded mode)",
}
POLICY_TEXT = {
    "fifo": "FIFO (today)",
    "rules": "Keyword rules + FIFO inside a tier (assumed accuracy)",
    "model": "Model tiers + FIFO inside a tier",
}
# Categorical slots 1 to 3 of the validated default palette (dataviz skill, light surface).
POLICY_COLOR = {"fifo": "#2a78d6", "rules": "#eb6834", "model": "#1baf7a"}
TRUE_TIERS = ["immediate", "priority", "normal"]

st.set_page_config(page_title="Hold-queue assistant", layout="wide")


class ApiError(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"{status}: {text}")
        self.status = status


def api(method: str, path: str, **kwargs) -> dict | list:
    try:
        response = httpx.request(method, f"{API_URL}{path}", timeout=60, **kwargs)
    except httpx.HTTPError as error:
        st.error(f"API at {API_URL} is unreachable: {error}")
        st.stop()
    if response.status_code >= 400:
        raise ApiError(response.status_code, response.text)
    return response.json()


def call_api(method: str, path: str, **kwargs) -> dict | list:
    """Like `api`, but an error ends the run with the message on screen."""
    try:
        return api(method, path, **kwargs)
    except ApiError as error:
        st.error(f"{method} {path} failed with {error}")
        st.stop()


def fmt_wait(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def minutes(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds / 60, 1)


def tier_line(call: dict) -> str:
    return f"{TIER_ICON[call['tier']]} {call['call_id']} · {call['tier']} · waited {fmt_wait(call['waited_s'])}"


state = call_api("GET", "/state")

with st.sidebar:
    st.title("Hold-queue assistant")
    st.caption("211-type community and disaster line · supervisor board · demo build")
    st.subheader("Mode")
    modes = list(MODE_TEXT)
    chosen = st.radio("Classification", modes, index=modes.index(state["mode"]), format_func=MODE_TEXT.get)
    if chosen != state["mode"]:
        try:
            api("POST", "/mode", json={"mode": chosen})
        except ApiError as error:
            st.warning(f"Could not switch: {error}")
        else:
            st.rerun()
    if not state["model_available"]:
        st.info("ANTHROPIC_API_KEY is not set, so model mode is unavailable; the rules baseline runs instead.")
    if st.button("Reset the queue"):
        call_api("POST", "/reset", json={})
        st.session_state.pop("handoff", None)
        st.rerun()
    st.subheader("Never automated")
    for line in state["invariants"]:
        st.markdown(f"✅ {line}")

live, replay, about = st.tabs(["Live hold queue", "Surge replay (simulated)", "About the data"])

with live:
    top = st.columns(4)
    top[0].metric("Waiting", len(state["waiting"]))
    top[1].metric("Active order", state["active_policy"])
    top[2].metric("Handed off", len(state["handoffs"]))
    top[3].metric("Hung up (caller's choice)", len(state["departed"]))

    st.subheader("A caller joins the hold queue")
    st.caption("Sample utterances were written by the team for the demo; they are simulated callers, not recordings.")
    samples = call_api("GET", "/samples")
    labels = {f"{sample['text']}  (expected: {sample['expected']})": sample["text"] for sample in samples}
    with st.form("join", clear_on_submit=True):
        pick = st.selectbox("Pick a sample or write your own below", ["(write your own)"] + list(labels))
        typed = st.text_input("What the caller says", placeholder="e.g. we evacuated and have nowhere to sleep tonight")
        join = st.columns(2)
        says = join[0].form_submit_button("Caller joins and says this", type="primary")
        silent = join[1].form_submit_button("A silent caller joins")
    if says:
        text = typed.strip() or labels.get(pick, "")
        if not text:
            st.warning("Pick a sample or type something first.")
        else:
            call_api("POST", "/calls", json={"text": text})
            st.rerun()
    if silent:
        call_api("POST", "/calls", json={})
        st.rerun()

    st.subheader("Two orders of the same queue")
    fifo_col, tiered_col = st.columns(2)
    by_fifo = sorted(state["waiting"], key=lambda call: call["fifo_position"])
    with fifo_col:
        st.markdown("**FIFO, today's behavior**")
        for call in by_fifo:
            st.markdown(f"{call['fifo_position'] + 1}. {tier_line(call)}")
        if not by_fifo:
            st.caption("Nobody is waiting.")
    with tiered_col:
        st.markdown(f"**Tiered, this build** (FIFO inside a tier; normal promoted after {state['max_normal_wait_s'] // 60:.0f} min)")
        for call in state["waiting"]:
            st.markdown(f"{call['tiered_position'] + 1}. {tier_line(call)}")
        if not state["waiting"]:
            st.caption("Nobody is waiting.")

    if st.button("An operator is free: transfer the head of the queue", type="primary"):
        result = call_api("POST", "/operator/free")
        st.session_state["handoff"] = result["handoff"]
        st.rerun()
    handoff = st.session_state.get("handoff")
    if handoff is not None:
        with st.container(border=True):
            st.markdown(f"**Handoff card for {handoff['call_id']}** · {TIER_ICON[handoff['tier']]} {TIER_TEXT[handoff['tier']]}")
            st.code(handoff["summary"], language=None)
            if handoff["transcript"]:
                st.caption("Transcript: " + " / ".join(handoff["transcript"]))
    elif "handoff" in st.session_state:
        st.info("Nobody was waiting.")

    st.subheader("Waiting callers")
    for call in state["waiting"]:
        with st.expander(tier_line(call), expanded=call["tier"] in ("immediate", "unknown")):
            st.markdown(f"Tier: **{TIER_TEXT[call['tier']]}** · source: `{call['source']}`")
            if call["transcript"]:
                st.markdown("Transcript:")
                for line in call["transcript"]:
                    st.markdown(f"> {line}")
            else:
                st.caption("The caller has not said anything yet.")
            if call["extraction"]:
                x = call["extraction"]
                st.markdown(
                    f"- Situation: {x['situation']}\n"
                    f"- Need: {x['need'] or 'not stated'}\n"
                    f"- Location: {x['location'] or 'not confirmed'}\n"
                    f"- Life threat now: {x['life_threat_now']} · needs a person soon: {x['needs_person_soon']} · "
                    f"enough information: {x['enough_information']}\n"
                    f"- Evidence: {'; '.join(x['evidence']) or 'none'}\n"
                    f"- Still unknown: {', '.join(x['missing']) or 'nothing flagged'}\n"
                    f"- Language: {x['language']}"
                )
            more = st.text_input("The caller says more", key=f"more-{call['call_id']}")
            row = st.columns(2)
            if row[0].button("Add what they said", key=f"say-{call['call_id']}"):
                if more.strip():
                    call_api("POST", f"/calls/{call['call_id']}/say", json={"text": more.strip()})
                    st.rerun()
            if row[1].button("Caller hangs up (their choice)", key=f"hangup-{call['call_id']}"):
                call_api("POST", f"/calls/{call['call_id']}/hangup")
                st.rerun()

    st.subheader("Watch: incident clusters from what waiting callers said")
    if state["clusters"]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "location (as stated)": cluster["location"],
                        "callers": cluster["count"],
                        "tiers": ", ".join(f"{k} {v}" for k, v in cluster["tiers"].items()),
                        "situations": " | ".join(cluster["situations"]),
                    }
                    for cluster in state["clusters"]
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No stated locations yet. Clusters appear when several waiting callers name the same place.")

    if state["handoffs"]:
        st.subheader("Recent handoffs")
        for item in reversed(state["handoffs"]):
            st.markdown(f"{TIER_ICON[item['tier']]} {item['call_id']} · {item['tier']} · waited {fmt_wait(item['waited_s'])}")

with replay:
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

with about:
    st.markdown(
        """
| Source | Live / recorded / simulated | Used for |
|---|---|---|
| Sample utterances on the live tab | simulated (written by the team) | Driving the extraction and the queue in the demo |
| Live typed or spoken calls | live | The same path with real input |
| Synthetic surge (replay tab) | simulated, labeled | Comparing queue policies on identical inputs |
| 211 LA January 2025 wildfires after-action report, Appendix D | recorded, daily aggregates | Scenario defaults and the problem's scale |
| Austin APD 911 Calls for Service 2023 to 2026 | recorded (police dispatch records) | Planned: arrival timestamps and priority mix |
| Munro disaster response messages | recorded (real disaster SMS, CC BY 4.0) | Planned: extraction evaluation, including the original-language column |
| spikecodes 911 transcripts | recorded, edited by the publisher | Planned: demo utterances only, never evaluation |

The queue never ends a call, never makes the final decision and never contacts agencies on its own.
Design and rationale: `docs/architecture.md` and `docs/changes/` in the repository.
"""
    )
