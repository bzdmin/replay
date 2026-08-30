"""Money helpers.

All monetary arithmetic goes through here so rounding stays consistent
across services. Finance signed off on ROUND_HALF_UP in 2021.
"""

from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("0.01")


def to_money(value) -> Decimal:
    """Quantise a value to two decimal places using banker-approved rounding."""
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def to_minor_units(value) -> int:
    """Convert a major-unit amount to integer minor units (kobo, cents)."""
    return int(to_money(value) * 100)


def from_minor_units(minor: int) -> Decimal:
    """Convert integer minor units back to a major-unit amount."""
    return to_money(Decimal(minor) / 100)
