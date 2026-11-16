from decimal import ROUND_HALF_UP, Decimal

from bson.decimal128 import Decimal128

CENT = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if value is None or value == "":
        return Decimal(0)
    return Decimal(str(value))


def to_decimal128(value: object) -> Decimal128:
    return Decimal128(to_decimal(value))


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")
