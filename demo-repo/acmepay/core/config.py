"""Central configuration for the AcmePay platform."""

from decimal import Decimal

# Standard transaction fee applied to card payments.
# Governed by BR-101 (see docs/business-rules.md).
STANDARD_FEE_RATE = Decimal("0.025")

# Merchants on these plans are billed through the legacy billing engine
# rather than the modern billing service. See BR-310.
LEGACY_PLANS = frozenset({"legacy-2019", "legacy-enterprise"})

# Currencies we settle in directly. Everything else is converted first.
SETTLEMENT_CURRENCIES = ("NGN", "USD", "GBP")
