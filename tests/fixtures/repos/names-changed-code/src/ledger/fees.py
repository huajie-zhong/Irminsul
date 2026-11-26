"""What a late payment costs."""


def late_fee(days: int) -> int:
    """The fee, in cents, for a payment `days` late."""
    return min(days * 50, 500)


def due_day(entered: int) -> int:
    """The day a payment entered on day `entered` is due."""
    return entered + 30
