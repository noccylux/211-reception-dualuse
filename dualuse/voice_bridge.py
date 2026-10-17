"""Retell voice bridge: phone callers reach the 211 desk through its REST API only.

Run as its own process next to the desk API:
    uvicorn --factory dualuse.voice_bridge:from_env --host 0.0.0.0 --port 8010
Every word the caller hears is the desk's own text, except the fixed lines below.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import re
import time

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from dualuse.config import require

log = logging.getLogger("voice_bridge")

DEMO_NOTICE = "This is a hackathon demonstration line, not a real 211 service."
# Spoken at once while the desk's interview runs, which can take seconds.
ACK = "Okay."
HANDOFF = ("An operator now has your case on the demo console. "
           "Voice transfer to a person is not connected in this demo, so please stay on the line.")
STILL_HERE = "I'm still here, and you remain in the queue."
NOT_RECORDED ="I could not record that. You remain in the queue."
DESK_DOWN = "The reception system is having a problem right now. You have not been removed from the queue."
SIGNATURE = re.compile(r"v=(\d+),d=([0-9a-f]+)")


def verify_signature(body: bytes, header: str | None, api_key: str, now_ms: int) -> bool:
    """Retell signs the raw body plus the millisecond timestamp with HMAC-SHA256 and the API key."""
    match = SIGNATURE.fullmatch(header or "")
    if not match or abs(now_ms - int(match[1])) > 5 * 60 * 1000:
        return False
    digest = hmac.new(api_key.encode(), body + match[1].encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, match[2])


class Line:
    """One Retell call and the desk call it is attached to."""

    def __init__(self, desk_id: str, spoken: int):
        self.desk_id = desk_id
        self.spoken = spoken  # desk dialogue entries already accounted for
        self.forwarded = 0  # caller transcript entries already sent to the desk
        self.pending: list[str] = []
        self.last_desk_speech = ""
        self.response_id = 0
        self.status = "waiting"
        self.interrupts = 0
        self.ws: WebSocket | None = None
        self.send_lock = asyncio.Lock()
        self.turn: asyncio.Task | None = None
        self.watcher: asyncio.Task | None = None
        self.grace: asyncio.Task | None = None
        self.ended = False

    async def send(self, message: dict):
        async with self.send_lock:
            await self.ws.send_json(message)

    async def respond(self, content: str, complete: bool = True, response_id: int | None = None):
        await self.send({"response_type": "response", "response_id": self.response_id if response_id is None else response_id,
                         "content": content, "content_complete": complete})


def new_speech(line: Line, call: dict) -> str:
    texts = [t["text"] for t in call["dialogue"][line.spoken:] if t["speaker"] == "assistant"]
    line.spoken = len(call["dialogue"])
    return " ".join(texts)


def create_app(desk: httpx.AsyncClient, ws_secret: str, retell_api_key: str, *,
               end_grace_s: float = 15.0, poll_s: float = 2.0) -> FastAPI:
    app = FastAPI(title="211 Retell voice bridge")
    lines: dict[str, Line] = {}

    async def get_call(line: Line) -> dict:
        response = await desk.get(f"/calls/{line.desk_id}")
        response.raise_for_status()
        return response.json()

    async def run_turn(line: Line):
        try:
            while line.pending:
                text = " ".join(line.pending)
                line.pending.clear()
                response = await desk.post(f"/calls/{line.desk_id}/say", json={"text": text})
                if response.status_code == 422:
                    log.warning("desk rejected caller text for %s: %s", line.desk_id, response.text)
                    await line.respond(NOT_RECORDED)
                    return
                if response.status_code not in (200, 409, 502):
                    response.raise_for_status()
                if response.status_code == 502:
                    log.error("desk interview failed for %s: %s", line.desk_id, response.text)
                call = await get_call(line)
                if call["status"] != "waiting":
                    line.spoken = len(call["dialogue"])
                    await line.respond(HANDOFF)
                    return
                if response.status_code == 409:
                    raise RuntimeError(f"desk refused a turn for waiting call {line.desk_id}: {response.text}")
                if line.pending:
                    line.spoken = len(call["dialogue"])  # the caller said more; this reply is stale
                    continue
                speech = new_speech(line, call)
                # Recognizer fragments ("ok", "yeah") make the desk repeat its wait line; on a
                # phone that sounds like a loop, so a repeat becomes a short notice.
                repeated = speech == line.last_desk_speech
                line.last_desk_speech = speech
                # Text that arrives while this reply is sent is picked up by the loop.
                await line.respond(STILL_HERE if repeated else speech)
        except Exception:
            log.exception("voice turn failed for %s", line.desk_id)
            await line.respond(DESK_DOWN)

    async def on_reminder(line: Line):
        try:
            response = await desk.post(f"/calls/{line.desk_id}/silence")
            if response.status_code == 409:
                await line.respond("")
            else:
                response.raise_for_status()
                await line.respond(new_speech(line, response.json()))
        except Exception:
            log.exception("silence check-in failed for %s", line.desk_id)
            await line.respond(DESK_DOWN)
        if line.pending:
            await run_turn(line)

    async def watch(line: Line):
        try:
            await watch_status(line)
        except Exception:
            log.exception("status watch failed for %s; operator pickups will not be announced", line.desk_id)

    async def watch_status(line: Line):
        while not line.ended:
            await asyncio.sleep(poll_s)
            status = (await get_call(line))["status"]
            if status != line.status and line.status == "waiting" and status in ("connecting", "handed_off"):
                line.interrupts += 1
                await line.send({"response_type": "agent_interrupt", "interrupt_id": line.interrupts,
                                 "content": HANDOFF, "content_complete": True})
            line.status = status
            if status not in ("waiting", "connecting", "handed_off"):
                return

    async def end(retell_id: str, disconnected: bool):
        line = lines[retell_id]
        if line.ended:
            return
        line.ended = True
        path = "disconnect" if disconnected else "hangup"
        response = await desk.post(f"/calls/{line.desk_id}/{path}")
        if response.status_code == 409:
            log.info("desk call %s had already left the queue: %s", line.desk_id, response.text)
        else:
            response.raise_for_status()

    async def end_after_grace(retell_id: str):
        await asyncio.sleep(end_grace_s)
        log.warning("no call_ended webhook for %s; recording a disconnect", retell_id)
        await end(retell_id, disconnected=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/llm-websocket/{secret}/{retell_id}")
    async def llm_websocket(ws: WebSocket, secret: str, retell_id: str):
        if not hmac.compare_digest(secret, ws_secret):
            await ws.close(code=1008)
            return
        await ws.accept()
        line = lines.get(retell_id)
        reconnect = line is not None
        if reconnect:
            if line.grace:
                line.grace.cancel()
        else:
            response = await desk.post("/calls", json={})
            response.raise_for_status()
            call = response.json()
            line = lines[retell_id] = Line(call["call_id"], 0)
            welcome = DEMO_NOTICE + " " + new_speech(line, call)
        line.ws = ws
        await line.send({"response_type": "config", "config": {"auto_reconnect": True, "call_details": False}})
        await line.respond("" if reconnect else welcome, response_id=0)
        log.info("retell %s attached to desk %s%s", retell_id, line.desk_id, " (reconnect)" if reconnect else "")
        line.watcher = asyncio.create_task(watch(line))
        try:
            while True:
                message = await ws.receive_json()
                kind = message["interaction_type"]
                if kind == "ping_pong":
                    await line.send({"response_type": "ping_pong", "timestamp": message["timestamp"]})
                elif kind == "response_required":
                    line.response_id = message["response_id"]
                    said = [t["content"] for t in message["transcript"] if t["role"] == "user"]
                    text = " ".join(s.strip() for s in said[line.forwarded:] if s.strip())
                    line.forwarded = len(said)
                    if line.status != "waiting":
                        await line.respond(HANDOFF)
                    elif not text:
                        await line.respond("")
                    else:
                        line.pending.append(text)
                        await line.respond(ACK, complete=False)
                        if not line.turn or line.turn.done():
                            line.turn = asyncio.create_task(run_turn(line))
                elif kind == "reminder_required":
                    line.response_id = message["response_id"]
                    # A running turn answers on the latest response id when it finishes.
                    if (not line.turn or line.turn.done()) and line.status == "waiting":
                        line.turn = asyncio.create_task(on_reminder(line))
        except WebSocketDisconnect:
            pass
        finally:
            line.watcher.cancel()
            if not line.ended:
                line.grace = asyncio.create_task(end_after_grace(retell_id))

    @app.post("/retell-webhook")
    async def retell_webhook(request: Request) -> dict:
        body = await request.body()
        if not verify_signature(body, request.headers.get("x-retell-signature"), retell_api_key, int(time.time() * 1000)):
            log.warning("rejected a webhook with a bad X-Retell-Signature")
            raise HTTPException(401, "bad signature")
        event = await request.json()
        if event["event"] != "call_ended":
            return {"ignored": event["event"]}
        retell_id = event["call"]["call_id"]
        if retell_id not in lines:
            log.warning("call_ended for unknown Retell call %s (bridge restarted?)", retell_id)
            return {"ignored": "unknown call"}
        line = lines[retell_id]
        if line.grace:
            line.grace.cancel()
        await end(retell_id, disconnected=event["call"].get("disconnection_reason") != "user_hangup")
        return {"desk_call": line.desk_id}

    return app


def from_env() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    desk = httpx.AsyncClient(base_url=os.environ.get("DUALUSE_API_URL", "http://localhost:8000"), timeout=45)
    return create_app(desk, require("RETELL_WS_SECRET"), require("RETELL_API_KEY"))
