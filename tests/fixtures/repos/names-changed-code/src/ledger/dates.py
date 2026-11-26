"""How a day is printed."""

import os


def date_format() -> str:
    """The format a day prints in."""
    return os.environ.get("LEDGER_DATE_FORMAT", "%Y-%m-%d")


def short_date_format() -> str:
    """The format a day prints in where space is short."""
    return "%m-%d"
