"""Shared helpers for the Voss toolkit: records, the clock, parsing, data files, the command registry.

Python 3.9+, standard library only, no network.

One rule runs through every message in here: an error names the argument that was wrong and never
repeats what was typed, because what was typed may be somebody's date of birth or blood result.
"""
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction

LIB = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(LIB)
SKILL = os.path.dirname(SCRIPTS)
DATA = os.path.join(SCRIPTS, "data")

KEY_WIDTH = 10
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MAX_TEXT = 2000


class VossError(Exception):
    """A user-facing error: bad input, missing data. Printed as one ERROR line."""


def die(msg):
    raise VossError(msg)


# ---- record output

def rec(key, value=""):
    """Print one KEY value line. Keys longer than the column simply push the value right."""
    key = str(key)
    if value == "" or value is None:
        print(key)
    else:
        print("%-*s %s" % (KEY_WIDTH, key, value))


def more(value):
    """Continuation line under the previous record."""
    print(" " * (KEY_WIDTH + 1) + str(value))


def table(rows, header=None, indent=0, right=()):
    """Print aligned columns. rows: list of sequences. right: column indexes to right-align."""
    rows = [[str(c) for c in r] for r in rows]
    if header:
        rows = [[str(c) for c in header]] + rows
    if not rows:
        return
    widths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(max(len(r) for r in rows))]
    pad = " " * indent
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            cells.append(c.rjust(widths[i]) if i in right else c.ljust(widths[i]))
        print((pad + "  ".join(cells)).rstrip())


def plural(n, one, many=None):
    """'1 dose', '2 doses'; give the plural when adding an s will not do."""
    return "%s %s" % (n, one if n == 1 else (many or one + "s"))


# ---- the clock

def now():
    """This machine's clock, to the minute, as a plain local time. VOSS_NOW (2026-11-15T10:30) pins it for tests."""
    fixed = os.environ.get("VOSS_NOW")
    if fixed:
        try:
            return datetime.strptime(fixed, "%Y-%m-%dT%H:%M")
        except ValueError:
            die("VOSS_NOW must look like 2026-11-15T10:30")
    return datetime.now().replace(second=0, microsecond=0)


def today():
    return now().date()


def fmt_day(day):
    return "%s %s" % (day.isoformat(), DAYS[day.weekday()])


def fmt_moment(dt):
    return "%s %s %s" % (dt.date().isoformat(), DAYS[dt.weekday()], dt.strftime("%H:%M"))


def add_months(day, months):
    """The same day of the month, that many months on; the last day of the month where there is no such day."""
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    for last in (31, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last))
        except ValueError:
            continue
    raise ValueError("no such month")


_PERIOD_RE = re.compile(r"^(\d{1,4})\s*(day|days|week|weeks|month|months|year|years)$")


def period_of(text, what):
    """'28 days', '2 weeks', '6 months' or '1 year' as (count, 'days' or 'months'). How long a thing keeps is a
    figure off its own label, so nothing looser than that is read."""
    m = _PERIOD_RE.match(" ".join(str(text).lower().split()))
    if not m or int(m.group(1)) == 0:
        die("%s must be a count of days, weeks, months or years, as the label gives it: 28 days, 6 months" % what)
    count, unit = int(m.group(1)), m.group(2).rstrip("s")
    if unit == "week":
        return count * 7, "days"
    if unit == "year":
        return count * 12, "months"
    return count, unit + "s"


def after(day, period):
    """The day a period after a day: a month is a calendar month, as add_months counts it."""
    count, unit = period
    return add_months(day, count) if unit == "months" else day + timedelta(days=count)


def end_of(part):
    """The last day a date given in part could mean: 2026 is 31 December, 2026-03 is 31 March. None if it is
    not a year, a year and month, or a date."""
    text = str(part or "").strip()
    if re.fullmatch(r"\d{4}", text):
        return date(int(text), 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}", text) and 1 <= int(text[5:]) <= 12:
        return add_months(date(int(text[:4]), int(text[5:]), 1), 1) - timedelta(days=1)
    return parse_date(text) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def whole_years(born, on):
    """Completed years between two dates. Someone born on 29 February has their birthday on 1 March in other years."""
    years = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        years -= 1
    return years


# ---- parsing

_DATE_RES = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), (1, 2, 3)),
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), (3, 2, 1)),
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"), (1, 2, 3)),
]
_WORD_DAYS = {"today": 0, "tomorrow": 1, "yesterday": -1}


def parse_date(text, base=None):
    """'2026-11-08', '08.11.2026', '2026/11/08', and with a base day 'today', 'tomorrow', 'yesterday'.
    Returns a date, or None for text that is not one of those or names a day that does not exist."""
    t = str(text).strip().lower()
    if base is not None and t in _WORD_DAYS:
        return base + timedelta(days=_WORD_DAYS[t])
    for rx, order in _DATE_RES:
        m = rx.match(t)
        if m:
            try:
                return date(int(m.group(order[0])), int(m.group(order[1])), int(m.group(order[2])))
            except ValueError:
                return None
    return None


def a_date(text, what, base=None):
    """A date, or an error that names the argument and keeps the text to itself."""
    day = parse_date(text, base)
    if day is None:
        die("%s is not a date the tool can read: use YYYY-MM-DD%s" % (what, " or 'today'" if base is not None else ""))
    return day


def parse_clock(text, what="the time"):
    """'08:00', '8:00', '8.00' or '0800' as (hour, minute)."""
    t = str(text).strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", t) or re.fullmatch(r"(\d{2})(\d{2})", t)
    if not m:
        die("%s must be a clock time such as 08:00" % what)
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        die("%s is not a time of day: hours run 00 to 23, minutes 00 to 59" % what)
    return hour, minute


def a_moment(text, what, base=None):
    """'2026-11-15 10:30', '2026-11-15T10:30' or 'today 10:30' as a plain local time."""
    parts = str(text).strip().replace("T", " ", 1).split()
    if len(parts) != 2:
        die("%s must be a date and a time, such as '2026-11-15 10:30'" % what)
    day = a_date(parts[0], what, base)
    hour, minute = parse_clock(parts[1], what)
    return datetime(day.year, day.month, day.day, hour, minute)


def decimal_of(text, what):
    """A plain number, written with a point or a comma. No thousands separators: 1,234 would be read as 1.234."""
    t = str(text).strip().replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"[+-]?\d{1,12}(\.\d{1,9})?", t):
        die("%s must be a plain number such as 5.1 (no thousands separators, no units)" % what)
    try:
        return Decimal(t)
    except InvalidOperation:
        die("%s must be a plain number such as 5.1" % what)


def fraction_of(text, what):
    """An amount that may be a part of a whole: 2, 0.5, 2,5 or 1/2."""
    t = str(text).strip().replace(" ", "").replace(",", ".")
    m = re.fullmatch(r"(\d{1,6})/(\d{1,4})", t)
    if m:
        if int(m.group(2)) == 0:
            die("%s cannot be divided by zero" % what)
        return Fraction(int(m.group(1)), int(m.group(2)))
    if not re.fullmatch(r"\d{1,9}(\.\d{1,6})?", t):
        die("%s must be an amount such as 2, 0.5 or 1/2" % what)
    return Fraction(t)


def plain(number):
    """A Decimal as it would be written by hand: no exponent, no needless zeros."""
    d = number.normalize()
    text = format(d, "f")
    return "0" if text in ("-0", "") else text


def show_amount(q):
    """A Fraction for reading: 2, 0.5, or 2 1/3 where no finite decimal says it."""
    q = Fraction(q)
    if q.denominator == 1:
        return str(q.numerator)
    d = q.denominator
    for prime in (2, 5):
        while d % prime == 0:
            d //= prime
    if d == 1:
        return plain(Decimal(q.numerator) / Decimal(q.denominator))
    sign = "-" if q < 0 else ""
    whole, rest = divmod(abs(q.numerator), q.denominator)
    part = "%d/%d" % (rest, q.denominator)
    return sign + ("%d %s" % (whole, part) if whole else part)


def fold(text):
    """Lower-case, strip diacritics, collapse spaces, hyphens and dots to underscores: 'Wis\u0142a' -> 'wisla'."""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("\u0142", "l").replace("\u0141", "L").replace("\u00df", "ss").replace("\u00f8", "o").replace("\u00d8", "O")
    t = re.sub(r"[\s\-./']+", "_", t.strip().lower())
    return re.sub(r"_+", "_", t).strip("_")


def key(text):
    """fold(), and then every run of anything that is not a letter or a digit is one underscore, so that a
    name is found whatever its punctuation: 'HIV: PrEP (and PEP)' -> 'hiv_prep_and_pep'."""
    return re.sub(r"[\W_]+", "_", fold(text)).strip("_")


def one_line(text, what, limit=MAX_TEXT):
    """Free text for a record: trimmed, on one line, within a sane length."""
    t = " ".join(str(text).split())
    if not t:
        die("%s is empty" % what)
    if len(t) > limit:
        die("%s is longer than %d characters: shorten it" % (what, limit))
    return t


# ---- data files

_cache = {}


def load_data(name, required=True):
    """Load scripts/data/<name>.json once. A broken file is an error, never a silent empty."""
    if name in _cache:
        return _cache[name]
    path = os.path.join(DATA, name + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        if required:
            die("data file missing: scripts/data/%s.json" % name)
        data = None
    except ValueError as e:
        die("data file scripts/data/%s.json is not valid JSON: %s" % (name, e))
    _cache[name] = data
    return data


def out_folder(to):
    """The folder for a file that is to be handed to the person, or None if there is no such folder.
    'auto' takes the folder VOSS_OUTPUTS names, if there is one. Otherwise it takes the first of these that
    exists and is a fit place for a file about someone's health: /mnt/user-data/outputs, the current
    folder, the person's Downloads folder, their home folder."""
    if str(to).lower() == "auto":
        named = os.environ.get("VOSS_OUTPUTS")
        if named and os.path.isdir(named):
            return named
        home = os.path.expanduser("~")
        cands = ["/mnt/user-data/outputs", os.getcwd(), os.path.join(home, "Downloads"), home]
        return next((c for c in cands if os.path.isdir(c) and not unfit(c)), None)
    return to if os.path.isdir(to) else None


def unfit(folder):
    """Why a folder is no place for a file with health information in it, or '' if it will do. A calendar of
    medicine times is such a file, as much as a personal file is."""
    if within(folder, SKILL):
        return "inside the package Voss is running from, which he never changes"
    if inside_repository(folder):
        return "inside a git repository, and a file that holds health information never goes into one"
    return ""


def _canon(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def same_path(a, b):
    """True if two paths name the same place. Windows does not care about case, so neither does this."""
    return _canon(a) == _canon(b)


def within(path, folder):
    """True if the path is the folder or lies under it."""
    try:
        return os.path.commonpath([_canon(path), _canon(folder)]) == _canon(folder)
    except ValueError:
        return False        # another drive


def inside_repository(folder):
    """True if the folder sits in a git working tree. Private files are not written into one."""
    here = os.path.abspath(folder)
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return True
        parent = os.path.dirname(here)
        if parent == here:
            return False
        here = parent


# ---- command registry (each module declares its own commands)

REGISTRY = []
GROUPS = [
    ("desk", "Desk"),
    ("clinic", "Clinic"),
    ("medicines", "Medicines"),
    ("file", "The personal file"),
    ("extras", "Extras"),
]


def command(sub, group, name, func, summary, examples=()):
    """Add a subcommand with examples in its -h text, and list it in the tool index."""
    import argparse
    epilog = None
    if examples:
        epilog = "examples:\n" + "\n".join("  voss.py " + e for e in examples)
    p = sub.add_parser(name, help=summary, description=summary[:1].upper() + summary[1:] + ".", epilog=epilog,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(func=func)
    REGISTRY.append((group, name, summary, list(examples)))
    return p


def setup_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
