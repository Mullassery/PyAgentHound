"""FastAPI app factory. See docs/architecture.md section 9."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from pyagenthound.api.routes import router
from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="PyAgentHound",
        description=(
            "Evidence-based debugging and root-cause analysis for AI agents "
            "and LLM applications."
        ),
        version="0.1.0",
    )
    app.state.store = SQLiteTraceStore(db_path or DEFAULT_DB_PATH)
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
