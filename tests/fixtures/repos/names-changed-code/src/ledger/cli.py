"""The ledger's commands."""

from typing import Annotated

import typer
from ledger.core import Ledger

app = typer.Typer()


@app.command("list")
def list_amounts(
    limit: Annotated[int, typer.Option("--limit")] = 0,
) -> None:
    """Print every amount, oldest first."""
    amounts = Ledger().amounts
    for amount in amounts[-limit:] if limit else amounts:
        typer.echo(amount)


@app.command()
def report(
    plain: Annotated[bool, typer.Option("--plain")] = False,
) -> None:
    """Print the total."""
    total = Ledger().total()
    typer.echo(total if plain else f"total: {total}")
