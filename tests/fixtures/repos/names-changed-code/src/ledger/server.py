"""The ledger's tools for an agent."""

from ledger.core import Ledger
from mcp.server.fastmcp import FastMCP


def build_server() -> FastMCP:
    """A server that answers from a new ledger."""
    server = FastMCP("ledger")

    @server.tool()
    def ledger_total() -> int:
        """The sum of every amount."""
        return Ledger().total()

    @server.tool()
    def ledger_count() -> int:
        """How many amounts the ledger holds."""
        return len(Ledger().amounts)

    return server
