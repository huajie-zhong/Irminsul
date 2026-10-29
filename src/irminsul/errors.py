"""The one error a command reports as a message and an exit status."""

from __future__ import annotations


class UserError(Exception):
    """A failure the person who ran the command can act on.

    The CLI prints the message in red on stderr and exits with `code`; the MCP server hands
    the same message to the agent as a tool error. `code` is 2 for a command that was
    misused or pointed at something that is not there, and 1 only where the raise site
    says the command refused to proceed on the state it found.
    """

    code = 2

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
