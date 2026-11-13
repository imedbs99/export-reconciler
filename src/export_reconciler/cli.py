import argparse
import csv
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

from .profile import InputError, load_profile
from .reconcile import compare
from .report import write_report
from .sources import read_source


def delimiter_arg(value: str) -> str:
    if value == "tab":
        return "\t"
    if len(value) != 1 or value in "\r\n\x00\"":
        raise argparse.ArgumentTypeError("use one separator character or 'tab'")
    return value


def date_arg(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() == value:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("use YYYY-MM-DD")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare two exports and create an Excel exception report.")
    parser.add_argument("left", type=Path, help="left .csv or .xlsx export")
    parser.add_argument("right", type=Path, help="right .csv or .xlsx export")
    parser.add_argument("--profile", required=True, type=Path, help="JSON column mappings and rules")
    parser.add_argument("--out", required=True, type=Path, help="destination .xlsx report")
    parser.add_argument("--left-sheet", help="worksheet name, defaulting to the first sheet")
    parser.add_argument("--right-sheet", help="worksheet name, defaulting to the first sheet")
    parser.add_argument("--left-delimiter", type=delimiter_arg, default=",", help="left CSV separator or 'tab'")
    parser.add_argument("--right-delimiter", type=delimiter_arg, default=",", help="right CSV separator or 'tab'")
    parser.add_argument("--as-of", type=date_arg, default=date.today(), help="expiry review date in YYYY-MM-DD")
    parser.add_argument("--fail-on-exceptions", action="store_true", help="exit 1 after writing a report with exceptions")
    args = parser.parse_args(argv)

    try:
        if args.out.suffix.lower() != ".xlsx":
            raise InputError("report destination must end in .xlsx")
        inputs = (args.left, args.right, args.profile)
        if any(args.out.resolve() == source.resolve() for source in inputs):
            raise InputError("report destination must differ from the input files")
        profile = load_profile(args.profile)
        left = read_source(args.left, args.left_sheet, args.left_delimiter, profile.columns("left"))
        right = read_source(args.right, args.right_sheet, args.right_delimiter, profile.columns("right"))
        issues = compare(left, right, profile, args.as_of)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_report(args.out, args.left, args.right, args.as_of, len(left), len(right), issues)
    except (ValueError, OSError, csv.Error, BadZipFile, InvalidFileException, ParseError) as exc:
        parser.exit(2, f"export-reconcile: {exc}\n")

    print(f"Compared {len(left)} left rows and {len(right)} right rows. "
          f"Wrote {len(issues)} exception rows to {args.out}.")
    return int(args.fail_on_exceptions and bool(issues))
