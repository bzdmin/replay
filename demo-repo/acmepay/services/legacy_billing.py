"""Legacy billing engine (2019).

Ported line-for-line from the original COBOL billing module during the
2019 migration. Fee arithmetic is done in basis points against integer
minor units, exactly the way the mainframe did it, so that reconciliation
against historical statements still balances.

Do not refactor the arithmetic without finance sign-off. See BR-310.
"""

# 250 basis points == 2.50%. Mirrored BR-101 at the time of the port.
_FEE_BASIS_POINTS = 250

_BASIS_POINT_DIVISOR = 10_000


def compute_fee_minor(amount_minor: int) -> int:
    """Fee in minor units, truncated, matching the mainframe's integer maths."""
    return (int(amount_minor) * _FEE_BASIS_POINTS) // _BASIS_POINT_DIVISOR


def describe_rate() -> str:
    """Human-readable rate, used on legacy merchant statements."""
    return f"{_FEE_BASIS_POINTS / 100:.2f}%"
