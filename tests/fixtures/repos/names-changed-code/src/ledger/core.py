"""The ledger: amounts in the order they were entered."""


class Ledger:
    """Amounts in cents, kept in the order they were added."""

    def __init__(self) -> None:
        self.amounts: list[int] = []

    def add(self, amount: int) -> None:
        """Enter `amount` after every amount already there."""
        self.amounts.append(amount)

    def remove(self, index: int) -> None:
        """Drop the amount at `index`."""
        del self.amounts[index]

    def total(self) -> int:
        """The sum of every amount."""
        return sum(self.amounts)


def parse_amount(text: str) -> int:
    """The cents `text` names, such as 1250 for "12.50"."""
    return round(float(text) * 100)
