from __future__ import annotations

import click

from pyagenthound.config import DEFAULT_DB_PATH, DEFAULT_HOST, DEFAULT_PORT


@click.command("serve")
@click.option("--host", default=DEFAULT_HOST, show_default=True)
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int)
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def serve_command(host: str, port: int, db_path: str) -> None:
    """Run the PyAgentHound API server."""
    import uvicorn

    from pyagenthound.api.app import create_app

    app = create_app(db_path)
    click.echo(f"PyAgentHound serving on http://{host}:{port}  (docs at /docs)")
    uvicorn.run(app, host=host, port=port)
