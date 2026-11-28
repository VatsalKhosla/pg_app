"""Reading the owners-and-PGs template (ADR 0072): what a row says, and every way a row can be
wrong. Every name, number and address here is fictional."""

import csv
import io

from app.modules.catalog.domain.listing import GenderPolicy, Meals
from app.modules.catalog.domain.listing_import import (
    COLUMNS,
    MAX_ROWS,
    parse_listing_import,
)
from app.modules.catalog.domain.rooms import Occupancy

HEADER = ",".join(COLUMNS)


def _row(**values: str) -> str:
    base = {
        "owner_name": "A Fictional Owner",
        "owner_phone": "98765 43210",
        "pg_name": "Fictional House",
        "locality": "Kamla-Nagar",
        "address": "House 1, a fictional lane",
        "gender": "Girls",
        "room_type": "double",
        "rent": "11,000",
        "deposit": "11000",
    }
    base.update(values)
    return ",".join(f'"{base.get(column, "")}"' for column in COLUMNS)


def _file(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_rows_of_one_pg_become_one_pg_with_its_room_types() -> None:
    parsed = parse_listing_import(
        _file(
            _row(
                owner_email="Owner@Example.com",
                latitude="28.6883",
                longitude="77.2102",
                meals="three",
                house_rules="No pets; Minimum stay: 11 months",
                amenities="wifi; Hot-Water",
                ac="yes",
            ),
            _row(room_type="single", rent="₹18,000", deposit="18000", room_label="Single room"),
        )
    )

    assert parsed.problems == ()
    [pg] = parsed.pgs
    assert (pg.row, pg.owner_phone, pg.owner_email) == (1, "+919876543210", "owner@example.com")
    # The business is the PG and the legal name the owner's, unless the file says otherwise.
    assert (pg.business_name, pg.legal_name) == ("Fictional House", "A Fictional Owner")
    assert (pg.locality, pg.gender_policy, pg.meals) == (
        "kamla-nagar",
        GenderPolicy.GIRLS,
        Meals.THREE,
    )
    assert pg.location == (28.6883, 77.2102)
    assert pg.house_rules == ("No pets", "Minimum stay: 11 months")
    assert pg.amenities == ("wifi", "hot-water")
    double, single = pg.room_types
    assert (double.occupancy, double.label, double.rent_paise, double.ac) == (
        Occupancy.DOUBLE,
        "Twin sharing",
        1_100_000,
        True,
    )
    assert (single.label, single.rent_paise, single.deposit_paise) == (
        "Single room",
        1_800_000,
        1_800_000,
    )


def test_a_pg_without_a_pin_is_read_and_waits_for_one() -> None:
    [pg] = parse_listing_import(_file(_row())).pgs

    assert pg.location is None
    assert pg.meals is Meals.NONE


def test_a_file_without_the_needed_columns_is_refused_whole() -> None:
    parsed = parse_listing_import("owner_name,owner_phone\nA,9876543210\n")

    assert parsed.pgs == ()
    assert parsed.problems == (
        "Columns missing: pg_name, locality, address, gender, room_type, rent, deposit. "
        "The header row has: owner_name, owner_phone.",
    )


def _cells(row: str) -> list[str]:
    return next(csv.reader([row]))


def test_a_copy_from_a_spreadsheet_or_a_semicolon_export_reads_as_the_csv_does() -> None:
    # Copied cells reach the clipboard separated by tabs; some spreadsheets export semicolons.
    # Lists inside a cell keep their own semicolons, quoted.
    rows = [COLUMNS, _cells(_row(amenities="wifi; cctv")), _cells(_row(room_type="single"))]
    saved = parse_listing_import(_file(_row(amenities="wifi; cctv"), _row(room_type="single")))

    for delimiter in ("\t", ";"):
        text = io.StringIO()
        csv.writer(text, delimiter=delimiter, lineterminator="\n").writerows(rows)
        assert parse_listing_import(text.getvalue()) == saved

    assert saved.problems == ()
    [pg] = saved.pgs
    assert (pg.amenities, len(pg.room_types)) == (("wifi", "cctv"), 2)


def test_the_header_may_sit_below_a_title_and_name_columns_as_people_write_them() -> None:
    header = ",".join(name.replace("_", " ").title() for name in COLUMNS)
    titled = "Owner survey, November\n\n" + header + "\n" + _row() + "\n"

    parsed = parse_listing_import(titled)

    assert parsed.problems == ()
    assert [pg.name for pg in parsed.pgs] == ["Fictional House"]


def test_columns_the_template_doesnt_have_are_left_out() -> None:
    header = HEADER + ",brokerage,notice_period"
    parsed = parse_listing_import(f"{header}\n{_row()},None,One month\n")

    assert parsed.problems == ()
    assert len(parsed.pgs) == 1


def test_without_its_header_row_a_file_says_so() -> None:
    parsed = parse_listing_import(_row() + "\n" + _row(room_type="single") + "\n")

    assert parsed.pgs == ()
    [problem] = parsed.problems
    assert problem.startswith("The template's header row is missing")
    assert "this one starts A Fictional Owner, 98765 43210" in problem


def test_a_google_forms_export_is_named_as_such() -> None:
    survey = (
        "Timestamp,1. Your Name,2. Contact Number / WhatsApp Number,"
        '3. Name of PG / Property,"4. Where"\n'
        "2026/11/20 10:00:00,A Fictional Owner,9876543210,Fictional House,A fictional lane\n"
    )

    [problem] = parse_listing_import(survey).problems

    assert problem.startswith("This is the survey's own responses export (Google Forms)")
    assert "(Timestamp, 1. Your Name, 2. Contact Number / WhatsApp Number, 3. Name of PG" in problem


def test_each_wrong_row_is_named_and_left_out() -> None:
    parsed = parse_listing_import(
        _file(
            _row(pg_name="Fine House"),
            _row(pg_name="Ranged House", rent="18,000 to 22,000"),
            _row(pg_name="Blank House", address=""),
            _row(pg_name="Odd House", gender="men"),
            _row(pg_name="Unsure House", ac="maybe"),
            _row(pg_name="Half-pinned House", latitude="28.7"),
            _row(pg_name="Wrong Number House", owner_phone="12345"),
            _row(pg_name="Wrong Address House", owner_email="not-an-address"),
        )
    )

    assert [pg.name for pg in parsed.pgs] == ["Fine House"]
    assert parsed.problems == (
        "Row 2: rent must be whole rupees, like 6000.",
        "Row 3: address empty.",
        "Row 5: ac must be yes or no.",
        "Row 4: gender must be one of boys, girls, coed.",
        "Row 6: latitude and longitude must both be numbers, or both empty.",
        "Row 7: owner_phone isn't a 10-digit Indian mobile number.",
        "Row 8: owner_email isn't an email address.",
    )


def test_blank_lines_and_a_spreadsheets_byte_order_mark_are_fine() -> None:
    parsed = parse_listing_import("﻿" + _file(_row(), "", ",,,"))

    assert parsed.problems == ()
    assert len(parsed.pgs) == 1


def test_a_file_reads_only_so_many_rows() -> None:
    rows = [_row(pg_name=f"Fictional House {index}") for index in range(MAX_ROWS + 1)]

    parsed = parse_listing_import(_file(*rows))

    assert len(parsed.pgs) == MAX_ROWS
    assert parsed.problems == (f"Only the first {MAX_ROWS} rows are read: split the file.",)
