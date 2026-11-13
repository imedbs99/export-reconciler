from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from .profile import Field, Profile, date_from_format
from .sources import InvalidCell, SourceRow, empty


@dataclass(frozen=True)
class ExceptionRow:
    rule: str
    key: str = ""
    field: str = ""
    left_row: int | None = None
    right_row: int | None = None
    left_value: object = None
    right_value: object = None
    detail: str = ""


def key_text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def index_rows(records: list[SourceRow], key_column: str, side: str):
    indexed = defaultdict(list)
    issues = []
    for record in records:
        value = record.values[key_column]
        context = {f"{side}_row": record.number, f"{side}_value": value}
        if empty(value):
            issues.append(ExceptionRow("Blank ID", field=key_column, **context))
        elif isinstance(value, (InvalidCell, bool, date)):
            issues.append(ExceptionRow("Invalid ID", field=key_column, detail="Use a text or numeric ID.", **context))
        else:
            indexed[key_text(value)].append(record)
    return indexed, issues


def normalized(value, field: Field, side: str):
    if isinstance(value, InvalidCell):
        return value
    if empty(value):
        return None
    if field.comparison == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        fmt = getattr(field, f"{side}_format") or "%Y-%m-%d"
        try:
            return date_from_format(str(value).strip(), fmt)
        except ValueError:
            return InvalidCell(f"Expected date format {fmt}.")
    value = str(value).strip()
    return value.casefold() if field.comparison == "casefold" else value


def field_issues(key: str, field: Field, left: SourceRow | None, right: SourceRow | None, as_of: date):
    originals = [row.values[getattr(field, side)] if row is not None else None
                 for side, row in (("left", left), ("right", right))]
    values = [normalized(value, field, side) for side, value in zip(("left", "right"), originals)]
    context = dict(key=key, field=field.name, left_row=left.number if left else None,
                   right_row=right.number if right else None, left_value=originals[0], right_value=originals[1])
    invalid = []
    overdue = []
    for side, value in zip(("Left", "Right"), values):
        if isinstance(value, InvalidCell):
            invalid.append(f"{side}: {value.reason}")
        elif field.grace_days is not None and isinstance(value, date):
            days_since = (as_of - value).days
            if days_since > field.grace_days:
                overdue.append(f"{side}: {days_since} days since expiry")
    if invalid:
        yield ExceptionRow("Invalid value", detail=" ".join(invalid), **context)
    elif left is not None and right is not None and values[0] != values[1]:
        yield ExceptionRow("Field mismatch", **context)
    if overdue:
        detail = f"{'; '.join(overdue)}. Grace period: {field.grace_days} days."
        yield ExceptionRow("Expiry beyond grace", detail=detail, **context)


def compare(left: list[SourceRow], right: list[SourceRow], profile: Profile, as_of: date) -> list[ExceptionRow]:
    left_index, issues = index_rows(left, profile.left_key, "left")
    right_index, right_issues = index_rows(right, profile.right_key, "right")
    issues.extend(right_issues)
    for key in sorted(left_index.keys() | right_index.keys()):
        left_rows = left_index.get(key, [])
        right_rows = right_index.get(key, [])
        if len(left_rows) > 1 or len(right_rows) > 1:
            detail = f"Left occurrences: {len(left_rows)}. Right occurrences: {len(right_rows)}. Resolve the duplicate before matching."
            for side, records in (("left", left_rows), ("right", right_rows)):
                for row in records:
                    column = getattr(profile, f"{side}_key")
                    context = {f"{side}_row": row.number, f"{side}_value": row.values[column]}
                    issues.append(ExceptionRow("Duplicate ID", key, "Match key", detail=detail, **context))
            continue
        left_row = next(iter(left_rows), None)
        right_row = next(iter(right_rows), None)
        if left_row is None:
            issues.append(ExceptionRow("Missing on left", key, right_row=right_row.number,
                                       right_value=right_row.values[profile.right_key]))
        if right_row is None:
            issues.append(ExceptionRow("Missing on right", key, left_row=left_row.number,
                                       left_value=left_row.values[profile.left_key]))
        for field in profile.fields:
            issues.extend(field_issues(key, field, left_row, right_row, as_of))
    return issues
