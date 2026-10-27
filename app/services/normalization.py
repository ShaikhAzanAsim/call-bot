"""Turn spoken or messy input into canonical strings.

Validators in validation.py decide whether the result is acceptable. This module
only interprets what the caller said.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
    "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
    "twenty-first": 21, "twenty-second": 22, "twenty-third": 23, "twenty-fourth": 24,
    "twenty-fifth": 25, "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28,
    "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31,
}
ORDINAL_WORDS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth",
    13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth",
    17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth",
    21: "twenty-first", 22: "twenty-second", 23: "twenty-third", 24: "twenty-fourth",
    25: "twenty-fifth", 26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth",
    29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first",
}
DIGIT_WORDS = {
    "zero": 0, "oh": 0, "o": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
DATE_FILLER = {
    "born", "on", "the", "of", "in", "my", "birthday", "birth", "date", "is", "was",
    "its", "it's", "please", "um", "uh", "a", "and", "year", "i", "im", "i'm",
}
PHONE_FILLER = {
    "my", "number", "is", "phone", "telephone", "call", "me", "at", "it's", "its",
    "it", "um", "uh", "like", "the", "please", "area", "code",
}
NATO = {
    "alpha": "a", "bravo": "b", "charlie": "c", "delta": "d", "echo": "e",
    "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i", "juliet": "j",
    "kilo": "k", "lima": "l", "mike": "m", "november": "n", "oscar": "o",
    "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
    "uniform": "u", "victor": "v", "whiskey": "w", "xray": "x", "x-ray": "x",
    "yankee": "y", "zulu": "z",
}
STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington d c": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "american samoa": "AS", "guam": "GU",
    "northern mariana islands": "MP", "puerto rico": "PR", "us virgin islands": "VI",
    "u s virgin islands": "VI", "virgin islands": "VI",
}
MAC_EXCEPTIONS = {"mack", "macy", "mace", "mach", "macro", "macaw"}


@dataclass
class ParseResult:
    value: str | None = None
    reason: str | None = None
    incomplete: bool = False
    note: str | None = None


def sanitize_text(value: str, max_len: int) -> str:
    cleaned = []
    for char in str(value):
        code = ord(char)
        if char in "\n\r\t":
            cleaned.append(" ")
        elif code >= 32 and code != 127:
            cleaned.append(char)
    text = re.sub(r"\s+", " ", "".join(cleaned)).strip()
    return text[:max_len]


def expand_two_digit_year(year: int, today: date) -> int:
    """Latest century that is not in the future and not more than 120 years ago."""
    candidates = [2000 + year, 1900 + year]
    valid = [item for item in candidates if item <= today.year and today.year - item <= 120]
    if valid:
        return max(valid)
    past = [item for item in candidates if item <= today.year]
    return max(past) if past else candidates[0]


def _year_words(year: int) -> str:
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = [
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if 2000 <= year <= 2009:
        tail = "thousand" if year == 2000 else f"thousand {ones[year - 2000]}"
        return f"two {tail}"
    if 2010 <= year <= 2099:
        rest = year - 2000
        if rest < 20:
            return f"twenty {teens[rest - 10]}"
        ten, one = divmod(rest, 10)
        return f"twenty {tens[ten]}" + (f" {ones[one]}" if one else "")
    century, rest = divmod(year, 100)
    century_word = {
        18: "eighteen", 19: "nineteen", 20: "twenty", 17: "seventeen",
    }.get(century, str(century))
    if rest == 0:
        return f"{century_word} hundred"
    if rest < 10:
        return f"{century_word} oh {ones[rest]}"
    if rest < 20:
        return f"{century_word} {teens[rest - 10]}"
    ten, one = divmod(rest, 10)
    return f"{century_word} {tens[ten]}" + (f" {ones[one]}" if one else "")


def speak_date(value: date) -> str:
    return f"{MONTH_NAMES[value.month]} {ORDINAL_WORDS[value.day]}, {_year_words(value.year)}"


def speak_phone(digits: str) -> str:
    groups = [digits[0:3], digits[3:6], digits[6:10]]
    return ", ".join(" ".join(group) for group in groups)


def speak_email(email: str) -> str:
    spoken = []
    for char in email:
        if char == "@":
            spoken.append("at")
        elif char == ".":
            spoken.append("dot")
        elif char == "_":
            spoken.append("underscore")
        elif char == "-":
            spoken.append("dash")
        elif char == "+":
            spoken.append("plus")
        else:
            spoken.append(char.upper())
    return " ".join(spoken)


def _classify_token(token: str) -> tuple[str, int | None]:
    if token in MONTHS:
        return "month", MONTHS[token]
    if token in ORDINALS:
        return "ordinal", ORDINALS[token]
    if token.isdigit():
        number = int(token)
        if number > 31:
            return "yearish", number
        return "number", number
    if token in DIGIT_WORDS:
        return "digit", DIGIT_WORDS[token]
    if token in TEENS:
        return "teen", TEENS[token]
    if token in TENS:
        return "tens", TENS[token]
    if token == "thousand":
        return "thousand", 1000
    if token == "hundred":
        return "hundred", 100
    return "word", None


def _consume_year(tokens: list[tuple[str, int | None]], today: date) -> tuple[int | None, int]:
    """Parse a year from the end of the token list. Returns (year, tokens_consumed)."""
    if not tokens:
        return None, 0
    kinds = [kind for kind, _ in tokens]
    values = [value for _, value in tokens]

    # nineteen ninety two / eighteen oh five / twenty twenty four handled below.
    if kinds[-1] == "yearish" and values[-1] is not None and values[-1] >= 1000:
        return values[-1], 1
    if len(tokens) >= 2 and kinds[-2] == "yearish" and values[-2] is not None and values[-2] >= 1000:
        return values[-2], 1

    # Walk a window from the right, longest first.
    for size in range(min(6, len(tokens)), 0, -1):
        window = tokens[-size:]
        year = _year_from_window(window, today)
        if year is not None:
            return year, size
    return None, 0


def _year_from_window(window: list[tuple[str, int | None]], today: date) -> int | None:
    kinds = [kind for kind, _ in window]
    values = [value if value is not None else 0 for _, value in window]
    if any(kind == "month" for kind in kinds):
        return None

    if kinds == ["yearish"] and values[0] >= 1000:
        return values[0]
    if kinds == ["number"] and values[0] > 999:
        return values[0]
    if len(window) == 1 and kinds[0] in {"number", "digit", "yearish"} and 0 <= values[0] <= 99:
        return expand_two_digit_year(values[0], today)

    # two thousand / two thousand five / two thousand twenty one
    if kinds[0] == "digit" and values[0] == 2 and "thousand" in kinds:
        rest = window[kinds.index("thousand") + 1 :]
        if not rest:
            return 2000
        extra = _small_number(rest)
        if extra is None or extra > 99:
            return None
        return 2000 + extra

    # nineteen ninety two / eighteen seventy six
    if kinds[0] == "teen" and values[0] in (17, 18, 19):
        rest = window[1:]
        if not rest:
            return None
        extra = _small_number(rest)
        if extra is None or extra > 99:
            return None
        return values[0] * 100 + extra

    # twenty twenty four / twenty five -> 2024 / 2005. "Fifth" is an ordinal, not a year.
    if kinds[0] == "tens" and values[0] == 20 and len(window) >= 2:
        if any(kind == "ordinal" for kind, _ in window[1:]):
            return None
        extra = _small_number(window[1:])
        if extra is None or extra > 99:
            return None
        return 2000 + extra

    # ninety two -> 92, then the century rule. Keeps "oh three oh five ninety two" working.
    if kinds in (["tens", "digit"], ["tens", "number"]) and values[0] >= 20:
        return expand_two_digit_year(values[0] + values[1], today)
    if kinds == ["tens"] and values[0] >= 20:
        return expand_two_digit_year(values[0], today)
    return None


def _small_number(window: list[tuple[str, int | None]]) -> int | None:
    if not window:
        return 0
    kinds = [kind for kind, _ in window]
    values = [value if value is not None else 0 for _, value in window]
    if len(window) == 1 and kinds[0] in {"digit", "number", "teen", "tens", "yearish"}:
        return values[0]
    if len(window) == 2 and kinds[0] == "tens" and kinds[1] in {"digit", "number"}:
        return values[0] + values[1]
    if len(window) == 2 and kinds == ["digit", "digit"]:
        return values[0] * 10 + values[1]
    if kinds == ["digit", "hundred"]:
        return values[0] * 100
    if len(window) == 2 and kinds[0] == "tens" and kinds[1] == "digit":
        return values[0] + values[1]
    if all(kind in {"digit", "number"} and values[index] < 10 for index, kind in enumerate(kinds)):
        number = 0
        for value in values:
            number = number * 10 + value
        return number
    return None


def _date_tokens(text: str) -> list[str]:
    cleaned = text.lower().replace(",", " ").replace(".", " ")
    cleaned = cleaned.replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9'\s]", " ", cleaned)
    raw_tokens = [token for token in cleaned.split() if token]
    tokens = []
    for token in raw_tokens:
        token = re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", token)
        if token in DATE_FILLER:
            continue
        tokens.append(token)
    return tokens


def _build_date(month: int, day: int, year: int) -> ParseResult:
    if not 1 <= month <= 12:
        return ParseResult(reason="That month isn't one I recognize. Could you say the month again?")
    if not 1 <= day <= 31:
        return ParseResult(reason="That day doesn't look right. Days run from 1 to 31.")
    try:
        value = date(year, month, day)
    except ValueError:
        month_name = MONTH_NAMES.get(month, "That month")
        if month == 2 and day == 29:
            return ParseResult(reason=f"{year} wasn't a leap year, so February 29 isn't a valid date.")
        return ParseResult(
            reason=f"{month_name} doesn't have {day} days. Could you double-check the day?"
        )
    return ParseResult(value=value.strftime("%m/%d/%Y"))


def parse_date(text: str, today: date | None = None) -> ParseResult:
    today = today or date.today()
    raw = sanitize_text(text, 80)
    if not raw:
        return ParseResult(incomplete=True, reason="I still need the month, the day, and the year.")

    numeric = re.fullmatch(
        r"\s*(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\s*",
        raw,
    )
    if numeric:
        year = int(numeric.group(3))
        if year < 100:
            year = expand_two_digit_year(year, today)
        return _build_date(int(numeric.group(1)), int(numeric.group(2)), year)

    iso = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", raw)
    if iso:
        return _build_date(int(iso.group(2)), int(iso.group(3)), int(iso.group(1)))

    tokens = _date_tokens(raw)
    if not tokens:
        return ParseResult(incomplete=True, reason="I still need the month, the day, and the year.")
    classified = [_classify_token(token) for token in tokens]

    month = None
    month_at = None
    for index, (kind, value) in enumerate(classified):
        if kind == "month":
            month = value
            month_at = index
            break

    if month is not None and month_at is not None:
        rest = classified[:month_at] + classified[month_at + 1 :]
        return _date_from_month_and_rest(month, rest, today)

    # Spoken digits with no month name: "oh three oh five ninety two".
    year, consumed = _consume_year(classified, today)
    if year is None or consumed == 0:
        return ParseResult(reason="I couldn't catch the date. Please say the month, the day, and the year.")
    prefix = classified[:-consumed] if consumed else classified
    if not prefix:
        return ParseResult(
            incomplete=True,
            reason=f"I heard the year {year}, but I still need the month and the day.",
        )
    if all(kind == "digit" for kind, _ in prefix) and len(prefix) in {3, 4, 6, 8}:
        digits = "".join(str(value) for _, value in prefix)
        if len(digits) == 8:
            return _build_date(int(digits[0:2]), int(digits[2:4]), int(digits[4:8]))
        if len(digits) == 6:
            return _build_date(int(digits[0:2]), int(digits[2:4]), expand_two_digit_year(int(digits[4:6]), today))
        if len(digits) == 4:
            return _build_date(int(digits[0:2]), int(digits[2:4]), year)
        if len(digits) == 3:
            return _build_date(int(digits[0]), int(digits[1:3]), year)
    numbers = []
    for kind, value in prefix:
        if kind in {"digit", "number", "ordinal"} and value is not None and value <= 31:
            numbers.append(value)
        else:
            numbers = []
            break
    if len(numbers) == 2:
        return _build_date(numbers[0], numbers[1], year)
    if len(numbers) == 1:
        return ParseResult(
            incomplete=True,
            reason=f"I have day {numbers[0]} and year {year}, but I still need the month.",
        )
    return ParseResult(reason="I couldn't catch the date. Please say the month, the day, and the year.")


def _date_from_month_and_rest(
    month: int,
    rest: list[tuple[str, int | None]],
    today: date,
) -> ParseResult:
    if not rest:
        return ParseResult(
            incomplete=True,
            reason=f"I heard {MONTH_NAMES[month]}, but I still need the day and the year.",
        )
    year, consumed = _consume_year(rest, today)
    prefix = rest[:-consumed] if consumed else rest
    day = _day_from_prefix(prefix)
    if year is None:
        if day is not None:
            return ParseResult(
                incomplete=True,
                reason=f"I have {MONTH_NAMES[month]} {ORDINAL_WORDS.get(day, day)}, but I still need the year.",
            )
        return ParseResult(
            incomplete=True,
            reason=f"I heard {MONTH_NAMES[month]}, but I still need the day and the year.",
        )
    if day is None:
        return ParseResult(
            incomplete=True,
            reason=f"I have {MONTH_NAMES[month]} {year}, but I still need the day.",
        )
    return _build_date(month, day, year)


def _day_from_prefix(prefix: list[tuple[str, int | None]]) -> int | None:
    if len(prefix) == 1:
        kind, value = prefix[0]
        if kind in {"ordinal", "digit", "number", "teen"} and value is not None and 1 <= value <= 31:
            return value
    if len(prefix) == 2 and prefix[0][0] == "tens" and prefix[1][0] in {"digit", "number", "ordinal"}:
        total = (prefix[0][1] or 0) + (prefix[1][1] or 0)
        if 1 <= total <= 31:
            return total
    return None


def _expand_repeats(text: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        count_word = match.group(1)
        word = match.group(2)
        count = {"double": 2, "triple": 3, "quadruple": 4}[count_word]
        return " ".join([word] * count)

    return re.sub(
        r"\b(double|triple|quadruple)\s+([a-z0-9]+)\b",
        replacer,
        text,
    )


def _words_to_digits(text: str) -> str:
    lowered = _expand_repeats(text.lower())
    lowered = lowered.replace("+", " plus ")
    tokens = re.findall(r"[a-z0-9]+", lowered)
    digits: list[str] = []
    skip_plus_one = False
    for token in tokens:
        if token in PHONE_FILLER or token in {"plus", "country"}:
            continue
        if token.isdigit():
            digits.append(token)
            continue
        if token in DIGIT_WORDS:
            digits.append(str(DIGIT_WORDS[token]))
            continue
        if token in TEENS:
            digits.append(str(TEENS[token]))
            continue
        # Ignore leftover words rather than failing the whole number.
        continue
    joined = "".join(digits)
    if joined.startswith("1") and len(joined) == 11:
        joined = joined[1:]
    return joined


def _count_word(count: int) -> str:
    words = {
        0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
        5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
    }
    return words.get(count, str(count))


def parse_phone(text: str) -> ParseResult:
    raw = sanitize_text(text, 80)
    if not raw:
        return ParseResult(reason="I didn't catch a phone number. Could you say the ten digits?")
    digits = _words_to_digits(raw)
    if not digits:
        return ParseResult(reason="I didn't hear any digits. Could you say the ten-digit phone number?")
    if len(digits) < 10:
        count = _count_word(len(digits))
        if len(digits) <= 3:
            return ParseResult(
                reason=(
                    f"That's only {count} digit{'s' if len(digits) != 1 else ''}. "
                    "A U.S. number has ten digits. Could you start with the area code?"
                )
            )
        if len(digits) == 9:
            return ParseResult(
                reason="That's only nine digits. Could you give me the area code too?"
            )
        return ParseResult(
            reason=f"That's only {count} digits. A U.S. number has ten. Could you repeat the whole number?"
        )
    if len(digits) > 10:
        return ParseResult(
            reason="That has more than ten digits. Please say just the ten-digit U.S. number, without the country code."
        )
    if digits[0] in "01":
        return ParseResult(reason="U.S. area codes can't start with zero or one. Could you repeat the area code?")
    if digits[3] in "01":
        return ParseResult(
            reason="The middle three digits can't start with zero or one. Could you repeat those?"
        )
    if digits[1:3] == "11" or digits[4:6] == "11":
        return ParseResult(
            reason="That doesn't look like a regular U.S. phone number. Could you repeat all ten digits?"
        )
    return ParseResult(value=digits)


def parse_zip(text: str) -> ParseResult:
    raw = sanitize_text(text, 40).lower().replace("dash", " ").replace("hyphen", " ")
    digits = _words_to_digits(raw)
    if len(digits) == 5:
        return ParseResult(value=digits)
    if len(digits) == 9:
        return ParseResult(value=f"{digits[:5]}-{digits[5:]}")
    if not digits:
        return ParseResult(reason="I didn't catch a ZIP code. Please say the five digits.")
    return ParseResult(
        reason=f"I heard {len(digits)} digit{'s' if len(digits) != 1 else ''} for the ZIP. I need five, or nine for ZIP+4."
    )


def parse_email(text: str) -> ParseResult:
    raw = sanitize_text(text, 160).lower()
    if not raw:
        return ParseResult(reason="I didn't catch an email. You can spell it, or we can skip it.")
    if "@" in raw and " " not in raw and re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", raw):
        return ParseResult(value=raw)

    tokens = re.findall(r"[a-z0-9]+", raw)
    mapped: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index : index + 3] == ["all", "one", "word"]:
            index += 3
            continue
        token = tokens[index]
        mapped.append(
            {
                "dot": ".",
                "period": ".",
                "point": ".",
                "underscore": "_",
                "under": "_",
                "score": "",
                "dash": "-",
                "hyphen": "-",
                "at": "@",
                "plus": "+",
            }.get(token, token)
        )
        index += 1
    # "under score" already became underscore as one token if spoken "underscore".
    parts: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            parts.append("".join(buffer))
            buffer.clear()

    for token in mapped:
        if token in {".", "@", "_", "-", "+"}:
            flush()
            parts.append(token)
        elif token == "":
            continue
        else:
            buffer.append(token)
    flush()
    email = "".join(parts)
    email = email.strip(".-_")
    if email.count("@") != 1:
        return ParseResult(
            reason="I need that email with 'at' in the middle, like jane at clinic dot com."
        )
    local, _, domain = email.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return ParseResult(reason="That email looks incomplete. Could you say it again, with 'dot' before the ending?")
    if not re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", email):
        return ParseResult(reason="That email has a character I can't use. Could you spell it?")
    return ParseResult(value=email)


def parse_state(text: str) -> ParseResult:
    raw = sanitize_text(text, 40).lower().replace(".", "")
    raw = re.sub(r"^(the\s+)?state\s+(of\s+)?", "", raw).strip()
    compact = re.sub(r"[^a-z]", "", raw)
    spaced = re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", "", raw)).strip()
    if len(compact) == 2 and compact.upper() in set(STATE_NAMES.values()):
        return ParseResult(value=compact.upper())
    if spaced in STATE_NAMES:
        return ParseResult(value=STATE_NAMES[spaced])
    if compact in {re.sub(r"\s+", "", name): code for name, code in STATE_NAMES.items()}:
        folded = {re.sub(r"\s+", "", name): code for name, code in STATE_NAMES.items()}
        return ParseResult(value=folded[compact])
    return ParseResult(
        reason="I need a U.S. state, like Texas or T X. Which state is the address in?"
    )


def _cap_name_token(token: str) -> str:
    if not token:
        return token
    lower = token.lower()
    if lower.startswith("mc") and len(lower) > 2 and lower[2].isalpha():
        return "Mc" + lower[2:].capitalize()
    if lower.startswith("mac") and len(lower) > 4 and lower not in MAC_EXCEPTIONS:
        return "Mac" + lower[3:].capitalize()
    return lower.capitalize()


def smart_name_case(value: str) -> str:
    words = []
    for word in value.split(" "):
        hyphen_parts = []
        for part in word.split("-"):
            apostrophe_parts = [_cap_name_token(piece) for piece in part.split("'")]
            hyphen_parts.append("'".join(apostrophe_parts))
        words.append("-".join(hyphen_parts))
    return " ".join(words)


def parse_name(text: str) -> ParseResult:
    raw = sanitize_text(text, 80)
    if not raw:
        return ParseResult(reason="I didn't catch the name. Could you say it again?")
    stripped = re.sub(
        r"^(my name is|my first name is|my last name is|first name is|last name is|"
        r"i am|i'm|this is|it's|it is|call me)\s+",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip(" .,")
    spelled = _spelled_name(stripped)
    if spelled:
        return ParseResult(value=smart_name_case(spelled))
    if not re.fullmatch(r"[A-Za-z]+(?:['-][A-Za-z]+)*(?:[ ][A-Za-z]+(?:['-][A-Za-z]+)*)*", stripped):
        return ParseResult(
            reason="Names can use letters, spaces, hyphens, and apostrophes. Could you say just the name?"
        )
    if not 1 <= len(stripped) <= 50:
        return ParseResult(reason="That name needs to be between 1 and 50 characters.")
    return ParseResult(value=smart_name_case(stripped))


def _spelled_name(text: str) -> str | None:
    lowered = text.lower().replace(",", " ")
    lowered = re.sub(r"\b([a-z])\s+as\s+in\s+[a-z]+\b", r"\1", lowered)
    lowered = lowered.replace("x-ray", "xray").replace("double u", "w")
    tokens = [token for token in re.split(r"[\s,]+", lowered) if token]
    tokens = [token for token in tokens if token not in {"as", "in", "like", "the", "letter", "capital"}]
    if len(tokens) < 2:
        return None
    letters = []
    for token in tokens:
        if token in NATO:
            letters.append(NATO[token])
        elif len(token) == 1 and token.isalpha():
            letters.append(token)
        else:
            return None
    return "".join(letters)


def parse_sex(text: str) -> ParseResult:
    raw = sanitize_text(text, 40).lower()
    raw = re.sub(r"[^a-z\s\-]", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"^(i am|i'm|it's|it is|sex is|gender is)\s+", "", raw)
    decline = {
        "decline", "decline to answer", "prefer not to say", "prefer not",
        "rather not say", "rather not", "no comment", "dont want to say",
        "don't want to say", "do not want to say", "skip",
    }
    other = {"other", "non-binary", "nonbinary", "non binary", "nb", "enby"}
    female = {"female", "woman", "f", "girl", "lady"}
    male = {"male", "man", "m", "boy", "guy"}
    if raw in decline:
        return ParseResult(value="Decline to Answer")
    if raw in other:
        return ParseResult(value="Other")
    if raw in female:
        return ParseResult(value="Female")
    if raw in male:
        return ParseResult(value="Male")
    return ParseResult(
        reason="Please say male, female, other, or decline to answer."
    )


def parse_city(text: str) -> ParseResult:
    raw = sanitize_text(text, 100)
    raw = re.sub(r"^(the city of|city of|city is|in)\s+", "", raw, flags=re.IGNORECASE).strip()
    if not raw or len(raw) > 100:
        return ParseResult(reason="I need the city, and it has to be 100 characters or fewer.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{0,99}", raw):
        return ParseResult(reason="I didn't catch the city. Could you say just the city name?")
    return ParseResult(value=smart_name_case(raw.replace(".", "")))


def parse_address_line(text: str, required: bool) -> ParseResult:
    raw = sanitize_text(text, 200)
    raw = re.sub(
        r"^(my address is|address is|i live at|it's|it is)\s+",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    if not raw:
        if required:
            return ParseResult(reason="I still need the street address.")
        return ParseResult(value=None, incomplete=True, reason="No apartment or suite.")
    return ParseResult(value=raw)


def parse_free_text(text: str, max_len: int, empty_reason: str) -> ParseResult:
    raw = sanitize_text(text, max_len)
    if not raw:
        return ParseResult(reason=empty_reason)
    return ParseResult(value=raw)


def parse_member_id(text: str) -> ParseResult:
    raw = sanitize_text(text, 40)
    compact = re.sub(r"[\s\-]", "", raw)
    if not compact:
        return ParseResult(reason="I didn't catch the member ID. You can spell it, or we can skip it.")
    if not re.fullmatch(r"[A-Za-z0-9]+", compact):
        return ParseResult(reason="Member IDs use only letters and numbers. Could you repeat it?")
    return ParseResult(value=compact.upper())


def parse_language(text: str) -> ParseResult:
    raw = sanitize_text(text, 50)
    lowered = raw.lower()
    if lowered in {"spanish", "espanol", "español", "hablo espanol", "hablo español"}:
        return ParseResult(value="Spanish")
    if lowered in {"english", "ingles", "inglés"}:
        return ParseResult(value="English")
    if not raw or not re.fullmatch(r"[A-Za-z][A-Za-z \-]{0,49}", raw):
        return ParseResult(reason="What language should we note? English and Spanish are both fine.")
    return ParseResult(value=smart_name_case(raw))
