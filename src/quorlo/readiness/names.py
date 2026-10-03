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


# --- Personal data -------------------------------------------------------------------
# Words that mean personal data wherever they appear.
_PII_ALWAYS = {
    "email": "email address",
    "eml": "email address",
    "phone": "phone number",
    "phn": "phone number",
    "mobile": "phone number",
    "ssn": "national identifier",
    "passport": "national identifier",
    "dob": "date of birth",
    "birth": "birth details",
    "birthdate": "date of birth",
    "birthday": "date of birth",
    "surname": "person name",
    "firstname": "person name",
    "lastname": "person name",
    "fullname": "person name",
    "iban": "bank account",
    "salary": "salary",
    "gender": "sensitive attribute",
    "ethnicity": "sensitive attribute",
    "religion": "sensitive attribute",
    "ip": "IP address",
}
# Words that mean personal data only in a table or column about people:
# `customer.name` is personal, `product.name` is not.
_PII_ABOUT_PEOPLE = {
    "name": "person name",
    "nm": "person name",
    "address": "postal address",
    "addr": "postal address",
    "street": "postal address",
    "postal": "postal address",
    "postcode": "postal address",
    "zip": "postal address",
    "zipcode": "postal address",
    "pc": "postal address",
}
_NAME_QUALIFIERS = {"first", "last", "middle", "given", "family", "full", "maiden"}
_PEOPLE = {
    "cust", "customer", "customers", "client", "clients", "user", "users", "person",
    "people", "member", "members", "employee", "employees", "emp", "patient", "patients",
    "contact", "contacts", "student", "students", "guest", "guests", "subscriber",
}  # fmt: skip
_IP_TYPES = {"inet", "cidr"}


def pii_category(column: str, table: str, raw_type: str = "") -> str | None:
    """The kind of personal data a column probably holds, judged only from names and type."""
    if raw_type.lower() in _IP_TYPES:
        return "IP address"
    words = tokens(column)
    about_people = bool(_PEOPLE & set(words) or _PEOPLE & set(tokens(table)))
    for i, word in enumerate(words):
        if word in _PII_ALWAYS:
            return _PII_ALWAYS[word]
        if word in ("name", "nm") and i and words[i - 1] in _NAME_QUALIFIERS:
            return "person name"
        if word in ("card", "cc") and words[i + 1 : i + 2] in (["number"], ["no"], ["num"]):
            return "payment card number"
        if about_people and word in _PII_ABOUT_PEOPLE:
            return _PII_ABOUT_PEOPLE[word]
    return None


# --- Freshness -----------------------------------------------------------------------
# Words in a timestamp column's name that say when a row last changed or arrived.
FRESHNESS_WORDS = frozenset(
    {
        "updated", "modified", "changed", "loaded", "load", "ingested", "ingestion",
        "refreshed", "synced", "extracted", "etl",
    }
)  # fmt: skip


def is_freshness_column_name(name: str) -> bool:
    """True for names like updated_at, last_modified, _etl_loaded_at or ingestion_ts."""
    return bool(FRESHNESS_WORDS & set(tokens(name)))


# --- Duplicates ----------------------------------------------------------------------
# Words that mark a version or copy of a table rather than what it holds.
COPY_MARKERS = frozenset(
    {"v", "old", "new", "bak", "backup", "copy", "tmp", "temp", "final", "latest", "prev"}
)


def concept_key(table_name: str) -> frozenset[str]:
    """What a table is about, ignoring word order and version or copy markers.

    revenue_daily and daily_revenue_v2 both give {'daily', 'revenue'}.
    """
    return frozenset(w for w in tokens(table_name) if not w.isdigit() and w not in COPY_MARKERS)
