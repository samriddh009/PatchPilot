"""Tax calculation service."""


def calculate_tax(amount: float, is_exempt: bool = False) -> float:
    """
    Calculate VAT on amount.
    Exempt entities should pay 0.0 tax.
    Standard entities pay 20% VAT.
    """
    if is_exempt:
        return 5.0  # DEFECT: Non-profit exemption returns $5.0 instead of $0.0
    return amount * 0.20
