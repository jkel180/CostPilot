"""Tolerant CSV reading for files exported from Excel / ERPs (Italian and English locales)."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000


class CsvError(ValueError):
    pass


def decode(content: bytes) -> str:
    if len(content) > MAX_BYTES:
        raise CsvError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if b"\x00" in content[:4096]:
        raise CsvError("This does not look like a text CSV file")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise CsvError("Unsupported text encoding (use UTF-8)")


def read_rows(content: bytes) -> tuple[list[str], list[dict[str, str]], str]:
    """Return (header, rows, delimiter). Rows are dicts keyed by the original header."""
    text = decode(content)
    sample = text[:10_000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration as exc:
        raise CsvError("The file is empty") from exc
    if not any(header):
        raise CsvError("The first row must contain column names")
    if len(set(h.lower() for h in header if h)) != len([h for h in header if h]):
        raise CsvError("Column names must be unique")
    rows = []
    for i, values in enumerate(reader):
        if i >= MAX_ROWS:
            raise CsvError(f"Too many rows (max {MAX_ROWS})")
        if not any(v.strip() for v in values):
            continue
        rows.append({h: (values[j].strip() if j < len(values) else "") for j, h in enumerate(header) if h})
    return header, rows, delimiter


_NUM_CLEAN = re.compile(r"[\s '€$£]")


def parse_decimal(raw: str, decimal_comma: bool | None = None) -> Decimal:
    """Parse a number.

    ``decimal_comma=True``: European format (1.234,5); ``False``: English (1,234.5).
    ``None`` guesses per value, which is ambiguous for e.g. ``1.000``, so file imports
    always pass the format inferred for the whole file.
    """
    s = _NUM_CLEAN.sub("", raw or "")
    if not s:
        raise ValueError("empty number")
    if decimal_comma is True:
        s = s.replace(".", "").replace(",", ".")
    elif decimal_comma is False:
        s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        # a single comma followed by exactly 3 digits is ambiguous: treat as thousands only if more groups
        s = s.replace(",", ".") if len(parts) == 2 else s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"'{raw}' is not a number") from exc


def infer_decimal_comma(delimiter: str, samples: list[str]) -> bool:
    """European number format if the file is ';'-separated or values look like 1.234,56 / 3,10."""
    if delimiter == ";":
        return True
    comma_dec = sum(1 for v in samples if re.fullmatch(r"-?[\d.]*\d,\d{1,2}", v.strip()))
    dot_dec = sum(1 for v in samples if re.fullmatch(r"-?[\d,]*\d\.\d{1,2}", v.strip()))
    return comma_dec > dot_dec


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y")


def parse_date(raw: str) -> date:
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty date")
    s = s.split("T")[0].split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    raise ValueError(f"'{raw}' is not a date (use YYYY-MM-DD or DD/MM/YYYY)")
