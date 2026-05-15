"""Single source of "today" for date-sensitive checks.

Checks that compare against the current date go through `today(graph.now)` so
the `--now YYYY-MM-DD` CLI override threads through uniformly. Without an
override `graph.now` is `None` and the system date is used.
"""

from __future__ import annotations

import datetime as _dt


def today(graph_now: _dt.date | None = None) -> _dt.date:
    return graph_now or _dt.date.today()
