from __future__ import annotations

import click

from pyagenthound.cli.commands.init import init_command
from pyagenthound.cli.commands.inspect import inspect_command
from pyagenthound.cli.commands.serve import serve_command


@click.group()
@click.version_option()
def cli() -> None:
    """PyAgentHound — evidence-based debugging for AI agents and LLM applications."""


cli.add_command(init_command)
cli.add_command(serve_command)
cli.add_command(inspect_command)


if __name__ == "__main__":
    cli()
