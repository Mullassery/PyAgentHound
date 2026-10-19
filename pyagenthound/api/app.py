"""FastAPI app factory. See docs/architecture.md section 9."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pyagenthound.api.routes import router
from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.ingest.otlp import OTLPUnavailable, otlp_json_to_traces, parse_otlp_protobuf
from pyagenthound.storage.sqlite_store import SQLiteTraceStore
from pyagenthound.ui.routes import router as ui_router

_STATIC_DIR = Path(__file__).parent.parent / "ui" / "static"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="PyAgentHound",
        description=(
            "Evidence-based debugging and root-cause analysis for AI agents and LLM applications."
        ),
        version="0.1.0",
    )
    app.state.store = SQLiteTraceStore(db_path or DEFAULT_DB_PATH)
    app.include_router(router)
    app.include_router(ui_router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/traces")
    async def ingest_otlp(request: Request) -> Response:
        """OTLP/HTTP trace receiver (JSON and protobuf)."""
        content_type = request.headers.get("content-type", "")
        body = await request.body()
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception as exc:
                return JSONResponse({"error": f"invalid JSON: {exc}"}, status_code=400)
            traces = otlp_json_to_traces(payload)
            for trace in traces:
                request.app.state.store.save_trace(trace)
            return JSONResponse({})
        if "protobuf" in content_type or "application/x-protobuf" in content_type:
            try:
                payload = parse_otlp_protobuf(body)
            except OTLPUnavailable as exc:
                return JSONResponse({"error": str(exc)}, status_code=415)
            except Exception as exc:
                return JSONResponse({"error": f"invalid protobuf: {exc}"}, status_code=400)
            traces = otlp_json_to_traces(payload)
            for trace in traces:
                request.app.state.store.save_trace(trace)
            # Empty ExportTraceServiceResponse is a valid protobuf response.
            return Response(content=b"", media_type="application/x-protobuf")
        return JSONResponse(
            {"error": "unsupported content-type; use application/json or application/x-protobuf"},
            status_code=415,
        )

    return app
