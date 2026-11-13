# Export Reconciler

Compare two CSV or Excel exports locally and generate an Excel workbook of exceptions. A JSON profile maps different column names, so the same checks can run again on the next batch. The project includes fictional records and can run without a network connection after installation.

## Try the example

Install with Python 3.10 or newer from the repository root:

```sh
python -m pip install .
export-reconcile examples/left.csv examples/right.csv --profile examples/profile.json --as-of 2026-06-30 --out output/example.xlsx
```

If the `export-reconcile` executable is outside your PATH, use `python -m export_reconciler` with the same arguments. The example compares 7 left rows and 5 right rows and writes 10 exceptions. Open `output/example.xlsx` and use the `Exceptions` filter to review the findings. The `Summary` tab shows counts by rule, input row counts, filenames and the expiry review date. One input record may produce several exceptions.

## Use it with your exports

1. Copy `examples/profile.json`. Set each side of `key` to the column containing the same unique ID. Set `fields` to the columns you want to check.
2. Run the example command with your paths. Files can be CSV, XLSX, or one of each. Use `--left-sheet` or `--right-sheet` to pick an Excel tab. The first tab is the default. CSV inputs must be UTF-8. Use `--left-delimiter` or `--right-delimiter` for exports using a separator such as `';'` or `tab`.
3. Review the output workbook. `Left row` and `Right row` are the original Excel row numbers or the starting line numbers of CSV records. Choose `--as-of YYYY-MM-DD` for repeatable expiry checks. The local date is the default.

### Rules

- IDs are case-sensitive after trimming surrounding whitespace. Use text cells for IDs in Excel. The tool also recognizes simple Excel zero masks like `000000`. Zeros and precision lost when the source was saved as numeric data cannot be recovered.
- A duplicate ID appears once per occurrence, including any matching row in the other source. Resolve the duplicate before comparing fields for that ID. Missing IDs and records present on only one side are reported separately.
- Field comparison defaults to `text`, which trims surrounding whitespace. `casefold` also ignores letter case. `date` compares actual dates. Excel date cells work directly, while text dates default to `YYYY-MM-DD`. Set `left_format` or `right_format` for other date formats using Python `strptime` directives.
- For date fields with `grace_days`, an expiry is flagged once the number of days since expiry exceeds the grace period. An expiry exactly 90 days ago is within a 90-day grace period. A blank date is treated as missing. Excel formula cells and error cells are flagged for review. Export formula results as values to compare them.
- Exit status is `0` when the report is written, or `2` for unusable input or output. With `--fail-on-exceptions`, a report with exceptions returns `1`, so the same command can be used in a batch job.

Inputs must have headers in the first row. Matching uses one ID column per file and loads input rows into memory. Reports include original field values and should be handled with the same care as the input exports. Use synthetic examples when sharing issues or contributing.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Licensed under the [MIT License](LICENSE).
