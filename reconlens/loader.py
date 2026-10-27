"""Input loading and normalisation.

Real bank exports are hostile: `(1,234.56)` for negatives, `¥` prefixes,
`DD/MM/YYYY` in one file and `YYYY-MM-DD` in the other, amounts with
thousands separators, currency symbols glued to digits. Everything that
reach the matcher is normalised here so the matcher never has to guess.
"""

import csv
import io
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .model import Entry

DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
DATE_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
DATE_DOT = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")

# Anything that is not a digit, a separator, or a sign is decoration.
_AMOUNT_JUNK = re.compile(r"[^0-9.,\-()]")


def parse_amount(raw):
    """Parse a money string into signed integer minor units.

    Handles: ``1,234.56`` ``-1234.56`` ``(1,234.56)`` ``¥1 234.56``
    ``1234`` ``1.234,56`` (European grouping).

    Returns ``None`` when the string cannot be read as money — the caller
    then decides whether that is fatal. Guessing is never acceptable here:
    a silently misread amount is worse than a reported failure.
    """
    if raw is None:
        return None
    if isinstance(raw, (int,)):
        return int(raw) * 100
    if isinstance(raw, float):
        return int(round(raw * 100))

    s = str(raw).strip()
    if not s:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]

    s = _AMOUNT_JUNK.sub("", s)
    if not s or not any(ch.isdigit() for ch in s):
        return None

    if s.startswith("-"):
        negative = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]

    # Decide which separator is the decimal point by last occurrence.
    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        if last_dot > last_comma:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif last_comma >= 0:
        # A lone comma: decimal only if it looks like one (exactly 1 or 2
        # trailing digits and no other comma). Otherwise it is grouping.
        tail = s[last_comma + 1:]
        if len(tail) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    if s.count(".") > 1:
        s = s.replace(".", "", s.count(".") - 1)

    # Decimal + ROUND_HALF_UP, not float: ``round(0.005 * 100)`` is 0 under
    # banker's rounding, and a half-cent that vanishes is exactly the kind
    # of silent error this library exists to prevent.
    try:
        cents = Decimal(s).quantize(Decimal("0.01"),
                                    rounding=ROUND_HALF_UP) * 100
        minor = int(cents)
    except (InvalidOperation, ValueError):
        return None

    return -minor if negative else minor


def parse_date(raw):
    """Normalise a date to ``YYYY-MM-DD``; ``None`` if unreadable."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = DATE_ISO.match(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = DATE_SLASH.match(s) or DATE_DOT.match(s)
        if not m:
            return None
        d, mo, y = (int(g) for g in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _pick(column_map, row, *candidates):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    for c in candidates:
        for k in row:
            if k and k.strip().lower() == c:
                return row[k]
    return None


def load_csv(path, side, currency_default="CNY"):
    """Load one side of the reconciliation from a CSV file.

    Column names are matched case-insensitively against common aliases so
    that an untouched bank export usually loads without editing.
    """
    with io.open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return load_rows(csv.DictReader(fh), side, currency_default)


def load_rows(rows, side, currency_default="CNY"):
    """Load from an iterable of dicts (shared by the CSV and JSON paths)."""
    entries = []
    problems = []
    for i, row in enumerate(rows):
        if row is None:
            continue
        clean = {}
        for k, v in row.items():
            if k is None:
                continue
            clean[str(k).strip().lower()] = v

        raw_amount = _pick(clean, clean, "amount", "金额", "debit_credit",
                           "value", "amt")
        amount = parse_amount(raw_amount)
        if amount is None:
            problems.append("row %d: unreadable amount %r" % (i, raw_amount))
            continue

        date = parse_date(_pick(clean, clean, "date", "日期", "posted",
                                "posting_date", "value_date"))
        if date is None:
            problems.append("row %d: unreadable date" % i)
            continue

        eid = _pick(clean, clean, "id", "编号", "凭证号")
        eid = ("" if eid is None else str(eid).strip())
        if not eid:
            eid = "%s-%03d" % (side, i + 1)

        # The reference is its own column when the file has one. Falling
        # back to the row id keeps banks that omit it loadable, but the
        # fallback must never shadow a real reference column.
        ref = _pick(clean, clean, "ref", "reference", "编号", "凭证号")
        ref = ("" if ref is None else str(ref).strip()) or eid

        desc = _pick(clean, clean, "description", "desc", "narrative",
                     "摘要", "memo") or ""
        cur = _pick(clean, clean, "currency", "ccy", "币种") or currency_default

        entries.append(Entry(eid, date, amount, str(cur).strip().upper(),
                             str(desc).strip(), ref, side))
    return entries, problems


def load_json(path, side, currency_default="CNY"):
    """Load from a JSON list of objects, or ``{"entries": [...]}``."""
    import json

    with io.open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("entries", data.get("rows", []))
    return load_rows(data, side, currency_default)


def load_any(path, side, currency_default="CNY"):
    if not os.path.exists(path):
        raise IOError("no such file: %s" % path)
    if path.lower().endswith(".json"):
        return load_json(path, side, currency_default)
    return load_csv(path, side, currency_default)
