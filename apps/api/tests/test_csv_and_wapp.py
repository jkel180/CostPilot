from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.csvutil import CsvError, parse_date, parse_decimal, read_rows
from app.purchases import group_wapp, parse_purchase_file, suggest_mapping, weighted_average_price


@pytest.mark.parametrize(
    "raw,expected",
    [("1234.5", "1234.5"), ("1,234.5", "1234.5"), ("1.234,5", "1234.5"), ("1234,5", "1234.5"),
     ("1 234,50", "1234.50"), ("€ 3,10", "3.10"), ("12", "12")],
)
def test_parse_decimal_locales(raw, expected):
    assert parse_decimal(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", "1.2.3,4,5"])
def test_parse_decimal_rejects(raw):
    with pytest.raises(ValueError):
        parse_decimal(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [("2026-03-15", date(2026, 3, 15)), ("15/03/2026", date(2026, 3, 15)), ("15.03.2026", date(2026, 3, 15)),
     ("2026-03", date(2026, 3, 1)), ("2026-03-15T10:00:00", date(2026, 3, 15))],
)
def test_parse_date_formats(raw, expected):
    assert parse_date(raw) == expected


def test_read_rows_detects_semicolon_and_skips_blank_lines():
    header, rows, delim = read_rows("a;b\n1;2\n\n3;4\n".encode("utf-8-sig"))
    assert (header, delim, len(rows)) == (["a", "b"], ";", 2)


def test_read_rows_rejects_binary_and_empty():
    with pytest.raises(CsvError):
        read_rows(b"\x00\x01\x02")
    with pytest.raises(CsvError):
        read_rows(b"")


# ------------------------------------------------------------------ WAPP (acceptance criterion 5)


def test_wapp_formula():
    # (1000 kg x 3.00) + (3000 kg x 2.00) = 9000 over 4000 kg = 2.25
    assert weighted_average_price([(Decimal(1000), Decimal("3.00")), (Decimal(3000), Decimal("2.00"))]) == Decimal("2.25")


def test_wapp_differs_from_simple_average():
    items = [(Decimal(100), Decimal(10)), (Decimal(900), Decimal(2))]
    assert weighted_average_price(items) == Decimal("2.8")  # simple mean would be 6


def test_wapp_empty_is_none():
    assert weighted_average_price([]) is None


def _p(supplier, qty, price, unit="kg", currency="EUR", d=date(2026, 1, 1)):
    return SimpleNamespace(supplier=supplier, quantity=Decimal(qty), unit_price=Decimal(price), unit=unit,
                           currency=currency, purchase_date=d, product_description="LJC")


def test_groups_never_mix_units_or_currencies():
    ps = [_p("A", 1000, "3"), _p("A", 1, "2800", unit="t"), _p("A", 500, "3.5", currency="USD")]
    groups = group_wapp(ps, lambda p: p.supplier)
    assert sorted((g["unit"], g["currency"]) for g in groups) == [("kg", "EUR"), ("kg", "USD"), ("t", "EUR")]
    assert all(g["purchases"] == 1 for g in groups)


# ------------------------------------------------------------------ purchase file parsing

ITALIAN_FILE = (
    "Data;Fornitore;Descrizione;Quantità;UM;Prezzo unitario;Valuta;Brix;Origine;Incoterm\n"
    "15/01/2026;Citrus SA;Succo di limone concentrato 400 GPL;1.000;kg;3,10;EUR;48;AR;CIF Genova\n"
    "20/02/2026;Agrumi Srl;Succo di limone concentrato;2000;kgs;2,95;EUR;;IT;DAP\n"
)


def test_suggests_mapping_for_italian_headers():
    m = suggest_mapping(["Data", "Fornitore", "Descrizione", "Quantità", "UM", "Prezzo unitario", "Valuta"])
    assert m["purchase_date"] == "Data" and m["supplier"] == "Fornitore" and m["quantity"] == "Quantità"
    assert m["unit"] == "UM" and m["unit_price"] == "Prezzo unitario" and m["currency"] == "Valuta"


def test_parses_italian_file():
    parsed = parse_purchase_file(ITALIAN_FILE.encode())
    assert parsed.mapping_errors == [] and len(parsed.valid) == 2
    first, second = (r.values for r in parsed.valid)
    assert first["quantity"] == Decimal("1000") and first["unit_price"] == Decimal("3.10")
    assert first["brix"] == Decimal("48") and first["incoterm"] == "CIF"
    assert second["unit"] == "kg"  # alias normalized


def test_row_errors_are_reported_per_line():
    content = (
        "date,supplier,product,quantity,unit,price,currency\n"
        "2026-01-10,A,LJC,0,kg,3,EUR\n"
        "not-a-date,B,LJC,10,kg,-1,EURO\n"
        "2026-01-12,,LJC,10,kg,3,EUR\n"
    ).encode()
    parsed = parse_purchase_file(content)
    errs = {r.line: r.errors for r in parsed.invalid}
    assert set(errs) == {2, 3, 4}
    assert any("quantity" in e for e in errs[2])
    assert {e.split(":")[0] for e in errs[3]} >= {"purchase_date", "unit_price", "currency"}
    assert any("supplier" in e for e in errs[4])


def test_missing_required_mapping():
    parsed = parse_purchase_file(b"date,supplier\n2026-01-01,A\n")
    assert parsed.rows == [] and any("quantity" in e for e in parsed.mapping_errors)


def test_number_format_is_inferred_per_file():
    eu = parse_purchase_file(b"date;supplier;product;quantity;unit;price;currency\n2026-01-01;A;LJC;1.000;kg;3,10;EUR\n")
    assert eu.number_format == "1.234,56" and eu.valid[0].values["quantity"] == Decimal("1000")
    en = parse_purchase_file(b"date,supplier,product,quantity,unit,price,currency\n2026-01-01,A,LJC,1000.5,kg,3.10,EUR\n")
    assert en.number_format == "1,234.56" and en.valid[0].values["quantity"] == Decimal("1000.5")
