import os
from collections import Counter
from dataclasses import fields
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .reconcile import ExceptionRow
from .sources import InvalidCell


HEADERS = ("Rule", "Match ID", "Field", "Left row", "Right row", "Left value", "Right value", "Detail")


def append_values(sheet, values):
    cells = []
    for value in values:
        if isinstance(value, InvalidCell):
            value = value.reason
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub(lambda match: f"\\x{ord(match[0]):02x}", value)
            if len(value) > 32767:
                value = value[:32754] + "… [truncated]"
        cell = Cell(sheet, value=value)
        if isinstance(value, str):
            # Keep source values as text, including strings that look like formulas or errors.
            cell.data_type = "s"
        cells.append(cell)
    sheet.append(cells)


def format_sheet(sheet, widths, header_row):
    sheet.freeze_panes = f"A{header_row + 1}"
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    for cell in sheet[header_row]:
        cell.fill = PatternFill("solid", fgColor="17334A")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[header_row].height = 25


def write_report(path: Path, left: Path, right: Path, as_of: date,
                 left_count: int, right_count: int, issues: list[ExceptionRow]):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    append_values(summary, ("Reconciliation summary", "Value"))
    for label, value in (("As of", as_of.isoformat()), ("Left file", left.name),
                         ("Right file", right.name), ("Left input rows", left_count),
                         ("Right input rows", right_count), ("Exception rows", len(issues))):
        append_values(summary, (label, value))
    summary.append([None, None])
    for rule, count in sorted(Counter(issue.rule for issue in issues).items()):
        append_values(summary, (rule, count))
    format_sheet(summary, (33, 48), 1)

    page_size = 1_048_575
    issue_fields = fields(ExceptionRow)
    for offset in range(0, max(1, len(issues)), page_size):
        title = "Exceptions" if offset == 0 else f"Exceptions {offset // page_size + 1}"
        detail = workbook.create_sheet(title)
        append_values(detail, HEADERS)
        for issue in issues[offset:offset + page_size]:
            append_values(detail, (getattr(issue, field.name) for field in issue_fields))
        detail.auto_filter.ref = detail.dimensions
        format_sheet(detail, (23, 19, 23, 13, 13, 24, 24, 84), 1)

    # Write beside the destination so an interrupted run cannot leave a partial report there.
    with NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        workbook.save(temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
        workbook.close()
