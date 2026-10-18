from __future__ import annotations

import click

from pyagenthound.config import DEFAULT_DB_PATH, DEFAULT_HOST, DEFAULT_PORT

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@click.command("serve")
@click.option("--host", default=DEFAULT_HOST, show_default=True)
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int)
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
@click.option(
    "--allow-external",
    is_flag=True,
    default=False,
    help=(
        "Permit binding to a non-loopback host. The API has no authentication, "
        "so this exposes full read access to your stored traces to anyone who "
        "can reach the port; only use it behind a trusted proxy/network."
    ),
)
def serve_command(host: str, port: int, db_path: str, allow_external: bool) -> None:
    """Run the PyAgentHound API server.

    Binds to loopback by default. Because the API is unauthenticated (it is
    designed as a single-user, local tool), serving on a routable host
    requires the explicit --allow-external flag as a deliberate opt-in.
    """
    if host not in _LOOPBACK_HOSTS and not allow_external:
        raise click.ClickException(
            f"refusing to bind to non-loopback host {host!r}: PyAgentHound's API "
            "has no authentication. Re-run with --allow-external if you "
            "understand this exposes your stored traces on the network."
        )

    import uvicorn

    from pyagenthound.api.app import create_app

    app = create_app(db_path)
    click.echo(f"PyAgentHound serving on http://{host}:{port}  (docs at /docs)")
    uvicorn.run(app, host=host, port=port)
