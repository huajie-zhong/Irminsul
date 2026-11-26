"""The command that changes the ledger for good."""

from typing import Annotated

import typer
from ledger.cli import app
from ledger.core import Ledger


@app.command()
def reset(
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
) -> None:
    """Empty the ledger, after asking unless `confirm` is set."""
    if confirm or typer.confirm("Empty the ledger?"):
        Ledger().amounts.clear()
