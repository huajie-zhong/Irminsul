"""The desk: lending a book, renewing a loan and taking a book back."""

from loans.policy import can_renew, due_day, late_fee


def check_out(book: str, day: int) -> dict[str, object]:
    """Lend `book` on `day`."""
    return {"book": book, "due": due_day(day), "renewals": 0}


def renew(loan: dict[str, int], day: int) -> dict[str, int]:
    """Renew `loan` on `day`, or raise when it has no renewal left."""
    if not can_renew(loan["renewals"]):
        raise ValueError("no renewal left")
    return {**loan, "due": due_day(day), "renewals": loan["renewals"] + 1}


def check_in(loan: dict[str, int], day: int) -> int:
    """Take the book back on `day` and return the fine owed, in cents."""
    return late_fee(day - loan["due"])
