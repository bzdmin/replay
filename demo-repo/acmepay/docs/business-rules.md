# AcmePay Business Rules

These rules are contractual. Changes require finance and legal sign-off.

## BR-101 — Standard transaction fee

Card payments are charged a standard transaction fee of **2.5%** of the
transaction amount, rounded half-up to two decimal places.

Owner: Payments
Implemented in: `core/config.py`, `services/payment_service.py`

## BR-207 — Refund fee is contractually fixed

When a payment is refunded, AcmePay retains a refund fee of **2.5%**.

This rate is **fixed by the merchant master agreement** and is *not* tied to
the standard transaction fee in BR-101. If BR-101 changes, BR-207 does **not**
change with it. Amending BR-207 requires renegotiating the merchant contract.

Owner: Legal
Implemented in: `services/refund_service.py`

## BR-310 — Legacy plan billing

Merchants on the `legacy-2019` and `legacy-enterprise` plans are billed
through the legacy billing engine ported from the mainframe in 2019, not
through the modern billing path.

The legacy engine holds its own copy of the fee rate, expressed in basis
points against integer minor units, so that reconciliation against
historical statements still balances. Any change to BR-101 must be applied
to the legacy engine separately.

Owner: Platform
Implemented in: `services/legacy_billing.py`, `services/billing_service.py`

## BR-415 — Settlement rounding

All monetary arithmetic rounds half-up to two decimal places via
`core/money.py`. No service may implement its own rounding.

Owner: Finance
