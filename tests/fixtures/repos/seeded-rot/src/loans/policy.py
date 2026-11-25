"""Loan rules: how long a loan runs, how often it renews, what a late return costs."""


def due_day(start_day: int, days: int = 14) -> int:
    """The day a loan that started on `start_day` falls due."""
    return start_day + days


def can_renew(renewals: int) -> bool:
    """Whether a loan already renewed `renewals` times may be renewed again."""
    return renewals < 2


def late_fee(days_late: int) -> int:
    """The fine in cents for a return `days_late` days after the due day."""
    return min(max(days_late, 0) * 25, 500)
