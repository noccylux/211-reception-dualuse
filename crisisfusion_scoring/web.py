"""Mount-safe standalone HTTP adapter. No dependency on an enclosing host app."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from importlib.resources import files
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ScoringPlugin, RULE_VERSION, POLICY_VERSION, __version__

CSRF_HEADER = "X-CrisisFusion-Scoring"


def _origin_tuple(value):
    try:
        part = urlsplit(value)
        if part.scheme not in {"http", "https"} or not part.hostname or part.username or part.password:
            return None
        if part.path not in {"", "/"} or part.query or part.fragment:
            return None
        return (part.scheme.lower(), part.hostname.lower(), part.port or (443 if part.scheme == "https" else 80))
    except ValueError:
        return None


def create_app(db_path=":memory:", allowed_hosts=None):
    if isinstance(allowed_hosts, str):
        raise ValueError("allowed_hosts must be a collection of explicit hostnames, not one string")
    allowed = {"127.0.0.1", "localhost", "::1"} if allowed_hosts is None else set(allowed_hosts)
    if not allowed or any(not isinstance(host, str) or not host.strip() or "/" in host or "*" in host for host in allowed):
        raise ValueError("allowed_hosts must be nonempty explicit hostnames without wildcards or URL paths")
    allowed = {host.lower().strip("[]") for host in allowed}
    plugin = ScoringPlugin(db_path)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            plugin.close()

    app = FastAPI(title="CrisisFusion Scoring Plugin", version=__version__, lifespan=lifespan)
    app.state.plugin = plugin
    app.state.engine = plugin

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse({"detail": "Entity not found"}, status_code=404)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        try:
            try:
                hostname = request.url.hostname
            except ValueError:
                hostname = None
            if hostname not in allowed:
                raise HTTPException(403, "HTTP Host is not in allowed_hosts")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("origin")
                expected = _origin_tuple(f"{request.url.scheme}://{request.url.netloc}")
                if origin is not None and (expected is None or _origin_tuple(origin) != expected):
                    raise HTTPException(403, "Cross-origin mutation is disabled")
                if request.headers.get("sec-fetch-site") == "cross-site":
                    raise HTTPException(403, "Cross-site mutation is disabled")
                if not hmac.compare_digest(request.headers.get(CSRF_HEADER, "").encode("utf-8"), token.encode("ascii")):
                    raise HTTPException(403, "Missing or invalid scoring CSRF token; GET api/scoring/status first")
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "plugin": "crisisfusion-scoring", "version": __version__,
                "api_version": "1", "rule_version": RULE_VERSION, "policy_version": POLICY_VERSION}

    @app.get("/api/scoring/status")
    def status():
        return {"version": __version__, "api_version": "1", "csrf_token": token,
                "csrf_header": CSRF_HEADER, "api_key_required": False, "mode": "local_prototype",
                "store_id": plugin.store_id}

    @app.get("/api/scoring/policy")
    def policy():
        return plugin.scoring_policy()

    @app.get("/api/scoring/state")
    def state():
        return plugin.snapshot()

    @app.post("/api/scoring/calls")
    def ingest(payload: dict):
        return plugin.ingest(payload)

    @app.get("/api/scoring/calls/{call_id}/priority")
    def priority(call_id: str):
        snapshot = plugin.snapshot()
        call = next((item for item in snapshot["calls"] if item["call_id"] == call_id), None)
        if call is None:
            raise KeyError(call_id)
        return {"call_id": call_id, "assessment": call.get("priority_assessment"),
                "revisions": call["revisions"],
                "needs": [n for n in snapshot["needs"] if n["call_id"] == call_id]}

    @app.post("/api/scoring/needs/{need_id}/actions")
    def action(need_id: str, payload: dict):
        return plugin.action(need_id, payload)

    @app.post("/api/scoring/settings")
    def settings(payload: dict):
        return {"settings": plugin.configure(payload)}

    @app.post("/api/scoring/recompute")
    def recompute(payload: dict):
        return plugin.recompute_scores(payload.get("call_id"), reason="host_requested_recompute")

    @app.get("/api/scoring/metrics")
    def metrics():
        return plugin.metrics()

    assets = files("crisisfusion_scoring").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(assets)), name="scoring-static")

    @app.get("/")
    def index():
        return FileResponse(str(assets.joinpath("index.html")))

    return app
