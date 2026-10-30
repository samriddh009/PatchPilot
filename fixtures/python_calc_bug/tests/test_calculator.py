"""Calculator unit and regression tests."""

from calculator.pricing import calculate_discount


def test_discount_boundary():
    """Target test: Boundary case $100.00 cart total must receive 15% discount."""
    assert calculate_discount(100.0) == 0.15


def test_discount_above_100():
    """Regression test: Cart above $100.00 receives 15%."""
    assert calculate_discount(150.0) == 0.15


def test_discount_below_100():
    """Regression test: Cart below $100.00 receives 10%."""
    assert calculate_discount(50.0) == 0.10


def test_discount_zero():
    """Regression test: Zero total receives 10%."""
    assert calculate_discount(0.0) == 0.10


def test_discount_99():
    """Regression test: $99.99 receives 10%."""
    assert calculate_discount(99.99) == 0.10


def test_discount_high():
    """Regression test: $1000.00 receives 15%."""
    assert calculate_discount(1000.0) == 0.15
