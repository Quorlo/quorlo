"""Reading meaning from identifiers: splitting names into words and spotting abbreviations."""

from __future__ import annotations

import re

# Abbreviations common in legacy schemas that an agent cannot reliably expand.
CRYPTIC_ABBREVIATIONS = frozenset(
    {"amt", "qty", "dt", "cd", "nm", "flg", "st", "addr", "eml", "cnt", "typ", "ind"}
)
# Short tokens that are widely understood and should not be flagged.
ALLOWED_SHORT_TOKENS = frozenset(
    {"id", "url", "uri", "sku", "ip", "utc", "iso", "api", "gps", "vat", "http", "html"}
)
_VOWELS = set("aeiouy")
_GENERIC_NAME = re.compile(r"^[a-z]{1,3}_?\d+$")  # col1, c2, f_3
_TOKEN = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def tokens(name: str) -> list[str]:
    """Split an identifier into lowercase words: 'custNm_addr1' -> ['cust', 'nm', 'addr', '1']."""
    return [t.lower() for t in _TOKEN.findall(name)]


def cryptic_reason(name: str) -> str | None:
    """Why a column name is hard for an agent to interpret, or None if it reads fine."""
    lowered = name.lower()
    if lowered in ALLOWED_SHORT_TOKENS:
        return None
    if _GENERIC_NAME.match(lowered):
        return "generic positional name"
    if len(lowered) <= 2:
        return "name is too short to carry meaning"
    for token in tokens(name):
        if token.isdigit() or len(token) < 2 or token in ALLOWED_SHORT_TOKENS:
            continue
        if token in CRYPTIC_ABBREVIATIONS:
            return f"abbreviation '{token}'"
        if not _VOWELS & set(token):
            return f"abbreviation '{token}'"
    return None
