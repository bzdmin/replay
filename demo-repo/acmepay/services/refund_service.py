"""Refund handling.

Refund fees are governed by BR-207, which is a separate contractual rule
from the standard transaction fee in BR-101.
"""

from decimal import Decimal

from core.config import STANDARD_FEE_RATE
from core.money import to_money


def calculate_refund_fee(amount, currency: str = "NGN") -> Decimal:
    """Fee retained by AcmePay when a payment is refunded.

    Historically this matched the standard payment fee, so it was wired
    straight to STANDARD_FEE_RATE.
    """
    return to_money(Decimal(str(amount)) * STANDARD_FEE_RATE)


def refund_amount(amount, currency: str = "NGN") -> Decimal:
    """Amount returned to the cardholder once the refund fee is retained."""
    return to_money(Decimal(str(amount)) - calculate_refund_fee(amount, currency))
