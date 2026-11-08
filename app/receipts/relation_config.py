"""Thresholds for amount-relation checks.

These values are fixed accounting tolerances. They were not chosen by looking
at the KR01–KR50 gold set.
"""
from decimal import Decimal

RULESET_VERSION = "amount-relations-v1.1"
STRUCTURE_VERSION = "relation-structure-v1"
REREAD_POLICY_VERSION = "selective-flash-reread-v1.1"

# One won covers printed rounding. Quantity keeps a small absolute band so
# 0.001 of a fractional unit is not treated as a mismatch, and quantities are
# never truncated to integers.
ABSOLUTE_MONEY_TOLERANCE = Decimal("1")
ABSOLUTE_QUANTITY_TOLERANCE = Decimal("0.001")

MAX_REREAD_ROUNDS = 1
MAX_REREAD_REGIONS = 3

OPENAI_CAP_KRW = Decimal("10000")
GCP_CAP_KRW = Decimal("10000")
# Same cushion the existing Luna client uses: 2,200 KRW per USD.
OPENAI_KRW_PER_USD = Decimal("2200")
# Vertex ledger convention: 1,450 KRW/USD and a 10% tax margin.
GCP_USD_KRW = Decimal("1450")
GCP_TAX_MARGIN = Decimal("1.1")

OPENAI_PRICE_PER_1M = {
    "input": Decimal("0.10"),
    "cached_input": Decimal("0.01"),
    "cache_write_input": Decimal("0.125"),
    "reservation_input": Decimal("0.125"),
    "output": Decimal("0.50"),
}
GCP_FLASH_MODEL = "gemini-3.8-flash"
GCP_FLASH_PRICE_PER_1M = {
    "input": Decimal("0.75"),
    "output": Decimal("3.75"),
}
GCP_PROJECT = "project-40bc06fc-fb4b-46b6-a10"

RELATION_RULES = {
    "line_qty_unit": {"enabled": True},
    "option_link": {"enabled": True},
    "item_sum_subtotal": {"enabled": True},
    "discount_bridge": {"enabled": True},
    "tax_composition": {"enabled": True},
    "tender_composition": {"enabled": True},
    "row_anomaly": {"enabled": True},
}
