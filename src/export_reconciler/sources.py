import csv
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from .profile import InputError


@dataclass(frozen=True)
class InvalidCell:
    reason: str


@dataclass(frozen=True)
class SourceRow:
    number: int
    values: dict


def excel_value(cell):
    if cell.data_type == "f":
        return InvalidCell("Formula cell. Export the calculated value as a constant.")
    if cell.data_type == "e":
        return InvalidCell(f"Excel error {cell.value}.")
    value = cell.value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Preserve a fixed-width identifier displayed with a simple Excel zero mask.
        if value >= 0 and value == int(value) and re.fullmatch(r"0{2,}", cell.number_format or ""):
            return str(int(value)).zfill(len(cell.number_format))
    return value


def csv_rows(reader):
    while True:
        number = reader.line_num + 1
        try:
            values = next(reader)
        except StopIteration:
            return
        yield number, values


@contextmanager
def rows_from(path: Path, sheet: str | None, delimiter: str):
    if path.suffix.lower() == ".csv":
        if sheet is not None:
            raise InputError(f"{path}: worksheet selection is only available for .xlsx files")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            yield csv_rows(csv.reader(stream, delimiter=delimiter, strict=True))
        return
    if path.suffix.lower() != ".xlsx":
        raise InputError(f"{path}: expected a .csv or .xlsx file")
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        if sheet is not None and sheet not in workbook.sheetnames:
            raise InputError(f"{path}: worksheet {sheet!r} not found")
        worksheet = workbook[sheet] if sheet is not None else workbook.worksheets[0]
        yield ((number, [excel_value(cell) for cell in cells])
               for number, cells in enumerate(worksheet.iter_rows(), start=1))
    finally:
        workbook.close()


def empty(value) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def read_source(path: Path, sheet: str | None, delimiter: str, required: set[str]) -> list[SourceRow]:
    with rows_from(path, sheet, delimiter) as rows:
        _, values = next(rows, (1, []))
        headers = [str(value).strip() if value is not None else "" for value in values]
        named = [header for header in headers if header]
        if len(set(named)) != len(named):
            raise InputError(f"{path}: duplicate column names on the header row")
        missing = required - set(named)
        if missing:
            raise InputError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        indexes = {header: index for index, header in enumerate(headers) if header in required}
        records = []
        for number, cells in rows:
            if all(empty(cell) for cell in cells):
                continue
            if len(cells) > len(headers) and any(not empty(cell) for cell in cells[len(headers):]):
                raise InputError(f"{path}: row {number} has data beyond the last header column")
            records.append(SourceRow(number, {
                header: cells[index] if index < len(cells) else None for header, index in indexes.items()
            }))
        return records
