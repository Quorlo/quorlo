"""Postgres type names, as format_type() spells them, mapped to neutral TypeKinds."""

from __future__ import annotations

import re

from quorlo.models import DataType, TypeKind

_TYPE_KINDS = {
    TypeKind.STRING: {
        "text",
        "character varying",
        "character",
        "varchar",
        "char",
        "bpchar",
        "name",
        "citext",
    },
    TypeKind.INTEGER: {"smallint", "integer", "bigint", "int2", "int4", "int8"},
    TypeKind.DECIMAL: {"numeric", "decimal", "money"},
    TypeKind.FLOAT: {"real", "double precision", "float4", "float8"},
    TypeKind.BOOLEAN: {"boolean", "bool"},
    TypeKind.DATE: {"date"},
    TypeKind.TIME: {"time without time zone", "time with time zone"},
    TypeKind.TIMESTAMP: {"timestamp without time zone", "timestamp with time zone"},
    TypeKind.INTERVAL: {"interval"},
    TypeKind.BINARY: {"bytea"},
    TypeKind.JSON: {"json", "jsonb"},
    TypeKind.UUID: {"uuid"},
}
_KIND_BY_NAME = {name: kind for kind, names in _TYPE_KINDS.items() for name in names}
_MODIFIERS = re.compile(r"\(([^)]*)\)")


def parse_type(raw: str, typtype: str = "b") -> DataType:
    """Map a `format_type()` spelling such as 'numeric(10,2)' to a neutral DataType."""
    if raw.endswith("[]"):
        return DataType(raw=raw, kind=TypeKind.ARRAY)

    mods = [int(m) for m in _MODIFIERS.findall(raw)[0].split(",")] if "(" in raw else []
    base = " ".join(_MODIFIERS.sub("", raw).split())
    kind = _KIND_BY_NAME.get(base, TypeKind.STRING if typtype == "e" else TypeKind.OTHER)

    length = precision = scale = None
    if kind is TypeKind.STRING and mods:
        length = mods[0]
    elif kind is TypeKind.DECIMAL and mods:
        precision = mods[0]
        scale = mods[1] if len(mods) > 1 else 0
    elif kind in (TypeKind.TIME, TypeKind.TIMESTAMP, TypeKind.INTERVAL) and mods:
        precision = mods[0]
    return DataType(raw=raw, kind=kind, length=length, precision=precision, scale=scale)
