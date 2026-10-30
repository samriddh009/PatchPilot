"""Tax service unit and regression tests."""

from service.tax import calculate_tax


def test_tax_exemption():
    """Target test: Non-profit exemption must yield 0.0 tax."""
    assert calculate_tax(100.0, is_exempt=True) == 0.0


def test_standard_vat_rate():
    """Regression test: Standard rate must yield 20% VAT."""
    assert calculate_tax(100.0, is_exempt=False) == 20.0


def test_tax_zero():
    """Regression test: Zero amount yields zero tax."""
    assert calculate_tax(0.0, is_exempt=False) == 0.0
