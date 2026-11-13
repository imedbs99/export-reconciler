import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """An input file or profile could not be used."""


@dataclass(frozen=True)
class Field:
    name: str
    left: str
    right: str
    comparison: str
    left_format: str | None
    right_format: str | None
    grace_days: int | None


@dataclass(frozen=True)
class Profile:
    left_key: str
    right_key: str
    fields: tuple[Field, ...]

    def columns(self, side: str) -> set[str]:
        return {getattr(self, f"{side}_key"), *(getattr(field, side) for field in self.fields)}


def object_at(value: Any, label: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be a JSON object")
    unknown = value.keys() - allowed
    if unknown:
        raise InputError(f"{label} has unknown options: {', '.join(sorted(unknown))}")
    return value


def text_at(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string")
    return value.strip()


def parse_field(value: Any, index: int) -> Field:
    label = f"fields[{index}]"
    item = object_at(value, label, {
        "name", "left", "right", "comparison", "left_format", "right_format", "grace_days"
    })
    comparison = item.get("comparison", "text")
    if comparison not in ("text", "casefold", "date"):
        raise InputError(f"{label}.comparison must be text, casefold, or date")
    date_options = item.keys() & {"left_format", "right_format", "grace_days"}
    if date_options and comparison != "date":
        raise InputError(f"{label} date formats and grace_days require a date comparison")
    formats = [text_at(item[key], f"{label}.{key}") if key in item else None
               for key in ("left_format", "right_format")]
    for fmt in (fmt for fmt in formats if fmt is not None):
        try:
            sample = date(2004, 11, 23)
            if date_from_format(sample.strftime(fmt), fmt) != sample:
                raise ValueError
        except ValueError as exc:
            raise InputError(f"{label} has a date format that does not round-trip: {fmt}") from exc
    grace = item.get("grace_days")
    if "grace_days" in item and (type(grace) is not int or grace < 0):
        raise InputError(f"{label}.grace_days must be a nonnegative integer")
    return Field(
        text_at(item.get("name"), f"{label}.name"),
        text_at(item.get("left"), f"{label}.left"),
        text_at(item.get("right"), f"{label}.right"),
        comparison, *formats, grace,
    )


def date_from_format(value: str, fmt: str) -> date:
    return datetime.strptime(value, fmt).date()


def load_profile(path: Path) -> Profile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"{path}: invalid UTF-8 JSON profile: {exc}") from exc
    item = object_at(raw, "profile", {"key", "fields"})
    key = object_at(item.get("key"), "key", {"left", "right"})
    raw_fields = item.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise InputError("fields must be a non-empty array")
    fields = tuple(parse_field(field, index) for index, field in enumerate(raw_fields))
    if len({field.name for field in fields}) != len(fields):
        raise InputError("field names must be unique")
    return Profile(text_at(key.get("left"), "key.left"), text_at(key.get("right"), "key.right"), fields)
