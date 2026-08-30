"""Billing service.

Routes a transaction to either the modern fee calculation or the legacy
billing engine, depending on the merchant's plan. See BR-310.
"""

from decimal import Decimal

from core.config import LEGACY_PLANS, STANDARD_FEE_RATE
from core.money import from_minor_units, to_minor_units, to_money
from services import legacy_billing


def bill_transaction(amount, merchant_plan: str = "standard") -> Decimal:
    """Fee billed to a merchant for one transaction."""
    if merchant_plan in LEGACY_PLANS:
        minor = to_minor_units(amount)
        return from_minor_units(legacy_billing.compute_fee_minor(minor))
    return to_money(Decimal(str(amount)) * STANDARD_FEE_RATE)


def statement_rate(merchant_plan: str = "standard") -> str:
    """Rate printed on the merchant's monthly statement."""
    if merchant_plan in LEGACY_PLANS:
        return legacy_billing.describe_rate()
    return f"{STANDARD_FEE_RATE * 100:.2f}%"
