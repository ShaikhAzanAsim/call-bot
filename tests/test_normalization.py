from datetime import date

from app.services.normalization import (
    parse_date,
    parse_email,
    parse_name,
    parse_phone,
    parse_sex,
    parse_state,
    parse_zip,
    smart_name_case,
)

TODAY = date(2026, 10, 27)


def test_spoken_date_phrases():
    assert parse_date("March fifth, nineteen ninety-two", today=TODAY).value == "03/05/1992"
    assert parse_date("3/5/92", today=TODAY).value == "03/05/1992"
    assert parse_date("oh three oh five ninety two", today=TODAY).value == "03/05/1992"
    partial = parse_date("born in March of ninety-two", today=TODAY)
    assert partial.value is None
    assert partial.incomplete
    assert "day" in (partial.reason or "").lower()


def test_impossible_and_numeric_dates():
    feb = parse_date("February 30, 1992", today=TODAY)
    assert feb.value is None
    assert "30" in (feb.reason or "")
    assert parse_date("03-05-1992", today=TODAY).value == "03/05/1992"


def test_phone_spoken_forms():
    assert parse_phone("my number is 206, 555, 0142").value == "2065550142"
    assert parse_phone("plus one two oh six double five five oh one four two").value == "2065550142"
    nine = parse_phone("206555014")
    assert nine.value is None
    assert "nine" in (nine.reason or "")
    three = parse_phone("555")
    assert three.value is None
    assert "three" in (three.reason or "")
    bad_area = parse_phone("1235550100")
    assert bad_area.value is None
    assert "area" in (bad_area.reason or "").lower()


def test_email_spoken():
    assert parse_email("john dot smith at gmail dot com").value == "john.smith@gmail.com"
    assert parse_email("j o h n underscore smith at gmail dot com").value == "john_smith@gmail.com"
    joined = parse_email("mary jane all one word at clinic dot org")
    assert joined.value == "maryjane@clinic.org"


def test_state_and_zip():
    assert parse_state("Texas").value == "TX"
    assert parse_state("texas").value == "TX"
    assert parse_state("T X").value == "TX"
    assert parse_state("new york").value == "NY"
    assert parse_zip("nine eight one oh one").value == "98101"
    assert parse_zip("98101-1234").value == "98101-1234"


def test_names_and_sex():
    assert parse_name("D as in David, A, V, I, S").value == "Davis"
    assert parse_name("o'brien").value == "O'Brien"
    assert parse_name("smith-jones").value == "Smith-Jones"
    assert smart_name_case("mcdonald") == "McDonald"
    assert parse_name("Mary Ann").value == "Mary Ann"
    assert parse_sex("woman").value == "Female"
    assert parse_sex("prefer not to say").value == "Decline to Answer"
    assert parse_sex("non-binary").value == "Other"
    assert parse_sex("male").value == "Male"
