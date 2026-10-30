"""Pricing calculation module."""


def calculate_discount(total: float) -> float:
    """
    Calculate customer discount rate.
    Cart total of $100.00 or more should receive a 15% discount.
    """
    if total > 100.0:  # DEFECT: Strict inequality excludes boundary total == 100.0
        return 0.15
    return 0.10
