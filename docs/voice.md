# Phone calls and public access for the 211 desk

How to let people phone the 211 reception desk through Retell and watch the
desk from another network. Describes the build on branch `voice-retell-bridge`;
the design record is [changes/2026-10-17-010-voice-bridge.md](changes/2026-10-17-010-voice-bridge.md).

## How it fits

```text
caller phone ─► Retell (number, speech-to-text, text-to-speech)
                  │  wss  /llm-websocket/<RETELL_WS_SECRET>/<retell call id>
                  │  https /retell-webhook   (call_ended, signed)
                  ▼
          voice bridge :8010  ──REST──►  desk API :8000  ◄──  Streamlit UI :8501
          dualuse/voice_bridge.py         dualuse/api.py        dualuse/ui.py
```

* The bridge is a separate process and uses only the desk's REST endpoints,
  so each phone call is an ordinary desk call: it appears in the operator
  desk, the queue order and the incident reports like a typed one.
* The bridge opens each desk call with `{"origin": "phone"}`. `POST /calls`
  accepts only `live` (the default, typed calls) or `phone`; anything else
  is a 422. The operator desk marks phone calls "📞 phone" in the queue and,
  on handoff, reminds the operator that the caller's voice is not transferred.
* The desk decides what the caller hears, starting with its welcome. The
  bridge adds only fixed lines: "Okay." while a turn is processed, an
  operator-pickup notice when the operator reserves the call, and a short
  "still here" notice in place of a desk reply identical to the previous one.
  Since Sat 2026-10-17 it no longer speaks a demo-line notice first; the
  welcome is kept short on mentor advice.
* The phone line is English only. The Retell agent's voice and recognizer are
  English, so the bridge drops the line profile's invitation to speak Spanish
  or Chinese (`welcome_extra` in `dualuse/profiles.py`) from the welcome. It
  reads that fixed text from the code; desk state still comes only through
  REST. Typed calls keep the invitation. With
  the `cn-12345` profile the desk welcome is Chinese; the bridge logs a
  warning and the English voice reads it as is, so use `la-211` for calls.
* Retell silence reminders become desk silence events. A `call_ended`
  webhook with reason `user_hangup` becomes a hang-up; any other reason, or
  no webhook within 15 s of the socket closing, becomes a lost connection.
* Not connected: voice transfer to a human, dispatch and outbound callback.

## Run on the desktop

Each command in its own terminal, from the repository root (PowerShell).

```text
.\scripts\uv-run.ps1 uvicorn dualuse.api:app --host 127.0.0.1 --port 8000
.\scripts\uv-run.ps1 streamlit run dualuse/ui.py --server.port 8501 --server.headless true
.\scripts\uv-run.ps1 uvicorn --factory dualuse.voice_bridge:from_env --host 127.0.0.1 --port 8010
```

The bridge needs `RETELL_API_KEY` and `RETELL_WS_SECRET` in `.env`, and finds
the desk at `DUALUSE_API_URL` (default `http://localhost:8000`).

## Public HTTPS with Cloudflare quick tunnels

Install once (Windows): `winget install --id Cloudflare.cloudflared`. Then run
two tunnels; each prints a random `https://<name>.trycloudflare.com` URL.

```text
cloudflared tunnel --url http://localhost:8501
cloudflared tunnel --url http://localhost:8010
```

* Open the first URL on the laptop (any network). Each browser chooses its
  own workspace, so one screen can show the operator desk and another the
  incident reports, all on the same queue.
* The UI has no login: anyone with the URL can act on the desk and reset it.
  Share the URL only with the team.
* Quick-tunnel URLs change whenever `cloudflared` restarts; then rerun the
  setup below.

## Point Retell at the bridge

```text
.\scripts\uv-run.ps1 python scripts/retell_setup.py https://<bridge-name>.trycloudflare.com
```

The first run creates the agent and prints `RETELL_AGENT_ID` to add to `.env`;
later runs update it. It lists the phone numbers that route to the agent.
Buying or binding a number is done in the Retell dashboard and is charged to
the account; without a number, use the dashboard's test call for the agent.

## Check it

* `curl http://localhost:8010/health` returns `{"status":"ok"}`.
* A test call shows a new waiting call marked "📞 phone" in the operator desk, with each
  sentence in its conversation. Reserving it in the desk makes the caller
  hear the operator-pickup notice.
* The bridge log names each Retell call and its desk call, and warns about
  rejected webhooks. A rejected webhook usually means `RETELL_API_KEY` is not
  the key with the webhook badge in the Retell dashboard.
* The bridge keeps the Retell-to-desk call map in memory; restarting it
  during calls leaves those desk calls waiting until an operator handles them.
