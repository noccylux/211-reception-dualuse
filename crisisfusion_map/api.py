"""ASGI wrapper with independent host and origin checks, including mount paths."""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .geo import GeoManager, install_routes
from .store import StateStore


def create_app(db_path=":memory:", allowed_hosts=None, transport=None):
    if allowed_hosts is not None and not isinstance(allowed_hosts, (list,tuple,set,frozenset)):
        raise ValueError("allowed_hosts must be a collection of hostnames, not a string or mapping")
    hosts = frozenset(allowed_hosts if allowed_hosts is not None else ("127.0.0.1", "localhost", "::1"))
    if not hosts or any(not isinstance(host,str) or not host or "*" in host or "/" in host or "://" in host for host in hosts):
        raise ValueError("allowed_hosts must explicitly list hostnames, without scheme, port or wildcard")
    store = StateStore(db_path)
    manager = GeoManager(store, transport=transport)
    static = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="CrisisFusion Map Plugin",version="1.0.0",lifespan=lifespan)
    app.state.store = store
    app.state.geo = manager

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail":str(exc)}, status_code=400)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        try:
            host = urlsplit("//"+request.headers.get("host", "")).hostname
            if host not in hosts:
                raise HTTPException(403,"Host not allowed; default plugin access is loopback only")
            manager.guard(request)
            content_length = request.headers.get("content-length")
            if content_length and (not content_length.isdigit() or int(content_length)>1000000):
                raise HTTPException(413,"Request too large")
            if request.method not in {"GET","HEAD","OPTIONS"}:
                body=bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body)>1000000:
                        raise HTTPException(413,"Request too large")
                # Starlette's cached request replays this bounded body to routes.
                request._body=bytes(body)
        except (HTTPException, ValueError) as exc:
            return JSONResponse({"detail":getattr(exc,"detail","Invalid host")},status_code=getattr(exc,"status_code",400))
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    @app.get("/health")
    def health():
        return {"status":"ok","plugin":"crisisfusion-map","version":"1.0.0"}

    @app.post("/api/geo/calls")
    def call(payload:dict):
        result = store.upsert_call(payload)
        return {**manager.snapshot(),"upsert_result":result}

    @app.post("/api/geo/calls/{call_id}/active")
    def active(call_id:str,payload:dict):
        if set(payload)!={"active"}:
            raise ValueError("Send only the active boolean")
        result = store.set_active_call(call_id,payload["active"])
        return {**manager.snapshot(),"activity_result":result}

    install_routes(app,manager)
    app.mount("/static",StaticFiles(directory=static),name="static")
    return app
