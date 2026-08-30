"""Payment processing.

This is the service most engineers reach for when the transaction fee changes.
"""

from decimal import Decimal

from core.config import STANDARD_FEE_RATE
from core.money import to_money


def calculate_fee(amount, currency: str = "NGN") -> Decimal:
    """Fee charged on a standard card payment. BR-101."""
    return to_money(Decimal(str(amount)) * STANDARD_FEE_RATE)


def net_settlement(amount, currency: str = "NGN") -> Decimal:
    """What the merchant actually receives after the fee is deducted."""
    return to_money(Decimal(str(amount)) - calculate_fee(amount, currency))
