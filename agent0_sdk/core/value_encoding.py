"""
Value encoding utilities for ReputationRegistry (Jan 2026).

On-chain representation: (value:int128, valueDecimals:uint8)
Human representation:    value / 10^valueDecimals
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Tuple, Union

logger = logging.getLogger(__name__)

# Plenty of headroom for scaling and clamping checks
getcontext().prec = 120

MAX_DECIMALS = 18
# Solidity constant (raw int128 magnitude). Contract enforces abs(value) <= 1e38.
MAX_ABS_VALUE_RAW = 10**38


def encode_feedback_value(input_value: Union[int, float, str, Decimal]) -> Tuple[int, int, str]:
    """
    Encode a user-facing value into the on-chain (value, valueDecimals) pair.

    Rules:
    - str: parsed using Decimal (no float casting). If >18 decimals, it is rounded half-up to 18 decimals.
    - float: accepted and rounded half-up to 18 decimals (never rejected).
    - int/Decimal: treated similarly; Decimal preserves precision.

    Returns: (value_raw:int, value_decimals:int, normalized:str)
    """
    if isinstance(input_value, Decimal):
        dec = input_value
        normalized = format(dec, "f")
    elif isinstance(input_value, int):
        dec = Decimal(input_value)
        normalized = str(input_value)
    elif isinstance(input_value, float):
        # Avoid binary float artifacts by going through Decimal(str(x)), then quantize to 18 places.
        dec = Decimal(str(input_value)).quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP)
        normalized = format(dec, "f")
    elif isinstance(input_value, str):
        s = input_value.strip()
        if s == "":
            raise ValueError("value cannot be an empty string")
        dec = Decimal(s)
        # Expand to plain decimal string (no exponent) for determining decimals
        normalized = format(dec, "f")
    else:
        raise TypeError(f"value must be int|float|str|Decimal, got {type(input_value)}")

    # Determine decimals from the normalized representation.
    # This preserves trailing zeros for string inputs like "1.2300".
    if "." in normalized:
        decimals = len(normalized.split(".", 1)[1])
    else:
        decimals = 0

    if decimals > MAX_DECIMALS:
        dec = dec.quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP)
        normalized = format(dec, "f")  # keeps fixed 18 decimals
        decimals = MAX_DECIMALS

    scale = Decimal(10) ** decimals
    raw_decimal = dec * scale
    raw_int = int(raw_decimal.to_integral_value(rounding=ROUND_HALF_UP))

    if abs(raw_int) > MAX_ABS_VALUE_RAW:
        raw_int = MAX_ABS_VALUE_RAW if raw_int > 0 else -MAX_ABS_VALUE_RAW
        clamped = Decimal(raw_int) / (Decimal(10) ** decimals)
        normalized = format(clamped, "f")
        logger.warning(
            "Feedback value %r exceeds on-chain max magnitude; clamped to %s (decimals=%s)",
            input_value,
            normalized,
            decimals,
        )

    return raw_int, decimals, normalized


def decode_feedback_value(value_raw: int, value_decimals: int) -> float:
    """Decode (value, valueDecimals) into a Python float."""
    if value_decimals < 0:
        raise ValueError("valueDecimals cannot be negative")
    return float(Decimal(value_raw) / (Decimal(10) ** int(value_decimals)))


