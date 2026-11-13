import contextlib
import io
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

from export_reconciler.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.report = self.directory / "exceptions.xlsx"

    def run_cli(self, left, right, *flags):
        with contextlib.redirect_stdout(io.StringIO()):
            return main([str(left), str(right), "--profile", str(EXAMPLES / "profile.json"),
                         "--out", str(self.report), "--as-of", "2026-06-30", *flags])

    def test_documented_example(self):
        result = self.run_cli(EXAMPLES / "left.csv", EXAMPLES / "right.csv", "--fail-on-exceptions")
        self.assertEqual(result, 1)
        workbook = load_workbook(self.report)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook["Summary"]["B7"].value, 10)
        rows = list(workbook["Exceptions"].values)[1:]
        self.assertEqual(Counter(row[0] for row in rows), {
            "Blank ID": 1, "Field mismatch": 2, "Expiry beyond grace": 1,
            "Missing on right": 1, "Duplicate ID": 3, "Missing on left": 1, "Invalid value": 1,
        })
        duplicates = [row for row in rows if row[0] == "Duplicate ID"]
        self.assertEqual([(row[1], row[3], row[4]) for row in duplicates],
                         [("0004", 5, None), ("0004", 6, None), ("0004", None, 4)])

    def test_excel_zero_masks_date_cells_and_untrusted_text(self):
        left = self.directory / "left.xlsx"
        right = self.directory / "right.csv"
        workbook = Workbook()
        sheet = workbook.create_sheet("Records")
        sheet.append(["Customer ID", "Birth Date", "Nationality", "ID Expiry"])
        sheet.append([6, date(1998, 2, 10), "TN", date(2026, 4, 1)])
        sheet["A2"].number_format = "0000"
        sheet.append(["0007", date(1998, 2, 10), "TN", date(2026, 3, 31)])
        sheet.append(["0008", "=TODAY()", "TN", date(2027, 1, 1)])
        workbook.save(left)
        workbook.close()
        right.write_text("Record Number,DOB,Country,Expiry Date\n"
                         "0006,10/02/1998,tn,01/04/2026\n"
                         "0007,10/02/1998,=1+1,31/03/2026\n"
                         "0008,10/02/1998,TN,01/01/2027\n", encoding="utf-8")

        self.assertEqual(self.run_cli(left, right, "--left-sheet", "Records"), 0)
        result = load_workbook(self.report)
        self.addCleanup(result.close)
        rows = list(result["Exceptions"].iter_rows(min_row=2))
        self.assertEqual([(row[0].value, row[1].value) for row in rows], [
            ("Field mismatch", "0007"), ("Expiry beyond grace", "0007"), ("Invalid value", "0008"),
        ])
        self.assertEqual(rows[0][6].value, "=1+1")
        self.assertEqual(rows[0][6].data_type, "s")

    def test_missing_columns_exit_without_overwriting_report(self):
        left = self.directory / "wrong.csv"
        left.write_text("Wrong column\n123\n", encoding="utf-8")
        self.report.write_bytes(b"existing report")
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as status:
            self.run_cli(left, EXAMPLES / "right.csv")
        self.assertEqual(status.exception.code, 2)
        self.assertIn("missing columns", error.getvalue())
        self.assertEqual(self.report.read_bytes(), b"existing report")
