"""Clinic work that needs no database: the triage levels and red flags, getting ready for a visit, and a
lab value read against the range printed on the person's own report.

Nothing here knows a reference range, a dose or a diagnosis. 'labs' compares two numbers it was given and
says which side of the printed range the value falls on; what that means is a question for the doctor.
"""
import difflib
import re
from datetime import timedelta

from . import core
from .core import command, decimal_of, die, key, load_data, more, one_line, plain, rec

# ---- triage

NUMBERS_DB = "core-pd"
ANSWER = ("a red flag ends the guessing. Lead with the number in one line, in plain words: no wit and no ears. "
          "Then stay, and say what to do while help comes. The marker is [mood: serious] [voss-serious.webp]")


def numbers(text):
    """One country's emergency numbers, as the core data lists them, with where they came from."""
    from . import library       # only this needs a database: a plain 'triage' or 'labs' does not pay for one
    con, info = library.need(NUMBERS_DB, "emergency numbers")
    try:
        library.warn_if_stale(info, core.today())
        want = str(text).strip()
        row = None
        if re.fullmatch(r"[A-Za-z]{2}", want):
            row = con.execute("SELECT code, name, eu FROM country WHERE code = ?", (want.upper(),)).fetchone()
        if row is None:
            row = con.execute("SELECT c.code, c.name, c.eu FROM country_name n JOIN country c ON c.code = n.code "
                              "WHERE n.folded = ?", (key(want),)).fetchone()
        if row is None:
            names = dict(con.execute("SELECT n.folded, c.name FROM country_name n JOIN country c ON c.code = n.code"))
            near = []
            for hit in difflib.get_close_matches(key(want), sorted(names), n=6, cutoff=0.75):
                if names[hit] not in near:
                    near.append(names[hit])
            rec("NUMBERS", "nothing on file for that country%s" % (": did you mean %s?" % " or ".join(near[:3]) if near else ""))
            more("--country takes a two-letter code (DE, GB) or a name. If the person may be in danger now, do not wait on "
                 "this: tell them to call their local emergency number")
            return
        code, name, eu = row
        listed = con.execute("SELECT number, use, source FROM emergency WHERE code = ? ORDER BY position", (code,)).fetchall()
        rec("NUMBERS", "%s (%s): %s" % (name, code, "; ".join("%s [%s]" % (n, u) if u else n for n, u, _ in listed)))
        more("the first is the one to lead with. What stands after a number is what the source says it is for; it may "
             "reach other services as well")
        sources = set(s for _, _, s in listed)
        if eu:
            fact = con.execute("SELECT value, source FROM fact WHERE key = ?", ("eu-112",)).fetchone()
            if fact:
                rec("EU", fact[0])
                sources.add(fact[1])
        for n, source in enumerate(sorted(sources)):
            (more if n else lambda text: rec("SOURCE", text))(library.tag(info, source))
        more("the numbers are listed as the source has them, and were not verified one by one: where there is time and it "
             "matters, check")
    finally:
        con.close()


def cmd_triage(a):
    data = load_data("triage")
    levels = data["levels"]
    if a.level is not None and not 1 <= a.level <= len(levels):
        die("--level is 1 to %d" % len(levels))
    everything = a.level is None and not a.flags and not a.country
    if a.level is not None:
        rec("LEVEL %d" % a.level, levels[a.level - 1])
        rec("RULE", data["rule"])
    if everything:
        rec("TRIAGE", "decide the level before anything else in a symptom question")
        for n, text in enumerate(levels, 1):
            rec("LEVEL %d" % n, text)
        rec("RULE", data["rule"])
    if everything or a.flags:
        rec("RED FLAGS", "each one is level 1, emergency now. %s" % data["flags_note"])
        for flag in data["red_flags"]:
            more("- " + flag)
    if a.country:
        numbers(a.country)
    if everything or a.flags or a.country:
        rec("ANSWER", ANSWER)
    if everything or (a.flags and not a.country):
        from . import library
        if library.have(NUMBERS_DB) is None:
            rec("NUMBERS", "none on file: %s.db is not installed. Use the list in references/clinical-rules.md, and check a "
                           "number is current before quoting it" % NUMBERS_DB)
        else:
            rec("NUMBERS", "by country: 'triage --country DE' takes a two-letter code or a name, and prints that country's "
                           "numbers with their source")


# ---- finding care

# what a person needs to know about getting care where they live. No file holds it for any country, so this is
# the list of what to find out, and the tool prints it: the finding out is a lookup, with the page named
CARE = (
    ("in an emergency", "the number to call"),
    ("at night, at a weekend or on a holiday", "where to go with what is not an emergency and cannot wait for the surgery to open: "
                                              "who may use it, whether it needs a referral, what it costs"),
    ("the emergency department", "what it is for and what it is not, and that it sees people in the order of urgency"),
    ("by telephone", "an advice or information line of the health service, if there is one, and its hours"),
    ("what a patient is owed", "information, consent, a look at their own records, a complaint, and who answers for each"),
    ("old medicines", "where they are taken back"),
)


def cmd_find(a):
    subject = one_line(" ".join(a.words), "the words", 200) if a.words else ""
    rec("FIND", "%snothing is on file about how care is arranged in any country: this is a lookup, to be cited" % (
        "%s: " % subject if subject else ""))
    rec("LOOK UP", "for the country the person is in, on the pages of its health service, its ministry of health or its "
                   "patients' ombudsman; and in its law, by article, where the question is what a person is owed")
    for head, what in CARE:
        more("- %s: %s" % (head, what))
    rec("SAY", "what you found, on which page, and on what day you read it. Opening hours and telephone numbers change, and "
               "what holds in one country does not hold in the next. Where you found nothing you can name, say you have "
               "no data")
    if a.country:
        numbers(a.country)
    else:
        more("'find --country CC' adds the emergency numbers on file for a country")
    rec("RULE", "which service a person needs now is a triage question, and comes first. A red flag is the emergency number, "
                "whatever a page says about opening hours")


# ---- visit

MAX_DIARY_DAYS = 60


def cmd_visit(a):
    data = load_data("visit")
    today = core.today()
    reason = one_line(a.reason, "--reason", 200) if a.reason else ""
    rec("VISIT", "getting ready%s" % (": " + reason if reason else ""))
    if a.on:
        day = core.a_date(a.on, "--on", today)
        gap = (day - today).days
        if gap < 0:
            die("--on is in the past: give the day of the visit that is coming")
        rec("WHEN", "%s, %s [derived]" % (core.fmt_day(day), "today" if gap == 0 else "in %s" % core.plural(gap, "day")))
    rec("FIRST", data["first"])
    rec("ASK", data["questions"][0])
    for q in data["questions"][1:]:
        more(q)
    rec("BRING", data["bring"][0])
    for item in data["bring"][1:]:
        more(item)
    rec("DIARY", "one line a day: %s" % " | ".join(data["diary"]))
    if a.diary_days:
        if not 1 <= a.diary_days <= MAX_DIARY_DAYS:
            die("--diary-days is 1 to %d" % MAX_DIARY_DAYS)
        start = core.a_date(a.start, "--from", today) if a.start else today
        for n in range(a.diary_days):
            more("%s |  |  |  |" % core.fmt_day(start + timedelta(days=n)))
    rec("SOURCE", "[general] lists written for this skill. No database is behind them, the personal file is not "
                  "read, and nothing here is advice about the complaint itself")


# ---- labs

_NUM = r"[+-]?\d+(?:[.,]\d+)?"
_BETWEEN_RE = re.compile(r"^(%s)\s*(?:-|to|\.\.+)\s*(%s)$" % (_NUM, _NUM))
_ONE_RE = re.compile(r"^(<=|>=|=<|=>|<|>)\s*(%s)$" % _NUM)
_WORD_RES = [
    (re.compile(r"^(?:up to|at most|no more than)\s+(%s)$" % _NUM), "high", True),
    (re.compile(r"^(?:below|under|less than)\s+(%s)$" % _NUM), "high", False),
    (re.compile(r"^(?:at least|no less than|from)\s+(%s)$" % _NUM), "low", True),
    (re.compile(r"^(?:above|over|more than)\s+(%s)$" % _NUM), "low", False),
    (re.compile(r"^(%s)\s+(?:or|and)\s+(?:above|over|more|higher)$" % _NUM), "low", True),
    (re.compile(r"^(%s)\s+(?:or|and)\s+(?:below|under|less|lower)$" % _NUM), "high", True),
]
_VALUE_RE = re.compile(r"^(<=|>=|<|>)?\s*(%s)$" % _NUM)
_TIDY = {"\u2264": "<=", "\u2265": ">=", "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " "}
_HIGH_FLAGS = ("H", "HH", "HIGH", "\u2191")
_LOW_FLAGS = ("L", "LL", "LOW", "\u2193")
RANGE_HELP = "write the range as the report prints it: 3.5-5.1, <5.0, >=60, 'up to 5.0', '60 or above'"


def _tidy(text):
    t = str(text)
    for odd, usual in _TIDY.items():
        t = t.replace(odd, usual)
    return " ".join(t.lower().split())


def parse_range(text):
    """A printed reference range as a dict: low, high (Decimals or None), whether each limit is part of the range,
    and the limits as they were typed."""
    t = _tidy(text)
    out = {"low": None, "high": None, "low_in": True, "high_in": True, "low_text": "", "high_text": ""}
    m = _BETWEEN_RE.match(t)
    if m:
        out.update(low=decimal_of(m.group(1), "the lower limit"), high=decimal_of(m.group(2), "the upper limit"),
                   low_text=m.group(1), high_text=m.group(2))
        if out["low"] > out["high"]:
            die("the range runs backwards: the lower limit is above the upper one. Read the report again")
        return out
    m = _ONE_RE.match(t)
    if m:
        op, number = m.group(1).replace("=<", "<=").replace("=>", ">="), m.group(2)
        side = "high" if op.startswith("<") else "low"
        out[side] = decimal_of(number, "the limit")
        out[side + "_in"] = op.endswith("=")
        out[side + "_text"] = number
        return out
    for rx, side, inclusive in _WORD_RES:
        m = rx.match(t)
        if m:
            out[side] = decimal_of(m.group(1), "the limit")
            out[side + "_in"] = inclusive
            out[side + "_text"] = m.group(1)
            return out
    die("the range was not understood: %s" % RANGE_HELP)


def range_words(r):
    if r["low"] is not None and r["high"] is not None:
        return "%s to %s" % (r["low_text"], r["high_text"])
    if r["low"] is not None:
        return "%s or above" % r["low_text"] if r["low_in"] else "above %s" % r["low_text"]
    return "up to %s" % r["high_text"] if r["high_in"] else "below %s" % r["high_text"]


def read_against(op, value, r):
    """Where a value sits against a printed range: (position, sentence). position is 'below', 'inside', 'above'
    or 'unplaced'. op is '' for a plain number, or the '<' or '>' the lab printed in front of it."""
    low, high = r["low"], r["high"]
    if not op:
        if low is not None and (value < low or (value == low and not r["low_in"])):
            if value == low:
                return "below", "on the lower limit, which the range as printed does not include"
            return "below", "below the printed range by %s" % plain(low - value)
        if high is not None and (value > high or (value == high and not r["high_in"])):
            if value == high:
                return "above", "on the upper limit, which the range as printed does not include"
            return "above", "above the printed range by %s" % plain(value - high)
        if low is not None and value == low:
            return "inside", "on the lower limit, which the printed range includes"
        if high is not None and value == high:
            return "inside", "on the upper limit, which the printed range includes"
        return "inside", "inside the printed range"
    strict = not op.endswith("=")
    if op.startswith("<"):
        if low is not None and (value < low or (value == low and (strict or not r["low_in"]))):
            return "below", "reported only as %s%s, which is below the printed range" % (op, plain(value))
        if low is None and (value < high or (value == high and (strict or r["high_in"]))):
            return "inside", "reported only as %s%s, which is inside the printed range" % (op, plain(value))
    else:
        if high is not None and (value > high or (value == high and (strict or not r["high_in"]))):
            return "above", "reported only as %s%s, which is above the printed range" % (op, plain(value))
        if high is None and (value > low or (value == low and (strict or r["low_in"]))):
            return "inside", "reported only as %s%s, which is inside the printed range" % (op, plain(value))
    return "unplaced", ("the report gives the value only as %s%s, so it cannot be placed against this range. "
                        "Say what the lab printed, and no more" % (op, plain(value)))


def cmd_labs(a):
    from . import labtests
    if a.about:
        if a.test or a.value:
            die("--about says what a test is; a value is read with --test and --value. One at a time")
        return labtests.cmd_about(a)
    if not a.test or not a.value:
        die("give the test and its value as the report prints them: --test \"Potassium\" --value 5.4 --range \"3.5-5.1\". "
            "For what a test is: labs --about WORDS")
    test = one_line(a.test, "--test", 120)
    unit = one_line(a.unit, "--unit", 40) if a.unit else ""
    m = _VALUE_RE.match(_tidy(a.value))
    if not m:
        die("--value must be the number on the report, such as 5.1, or <0.5 where the lab printed it that way")
    op, value = m.group(1) or "", decimal_of(m.group(2), "--value")
    if a.range and (a.low is not None or a.high is not None):
        die("give the range once: either --range, or --low and --high")
    if a.range:
        r = parse_range(a.range)
    elif a.low is not None or a.high is not None:
        r = {"low": None, "high": None, "low_in": True, "high_in": True, "low_text": "", "high_text": ""}
        for side, text in (("low", a.low), ("high", a.high)):
            if text is not None:
                r[side] = decimal_of(text, "--" + side)
                r[side + "_text"] = _tidy(text)
        if r["low"] is not None and r["high"] is not None and r["low"] > r["high"]:
            die("the range runs backwards: --low is above --high. Read the report again")
    else:
        r = None
    rec("TEST", test)
    rec("VALUE", "%s%s%s" % (op, m.group(2), " " + unit if unit else ""))
    if r is None:
        rec("RANGE", "none given. Ask for the range printed beside this result on the person's own report")
        rec("READING", "not made: a value is read against its own report's range, never against one remembered")
        position = None
    else:
        rec("RANGE", "%s%s [printed on the report, as given to the tool]" % (range_words(r), " " + unit if unit else ""))
        position, sentence = read_against(op, value, r)
        if unit and position in ("below", "above") and " by " in sentence:
            sentence += " " + unit
        rec("READING", "%s%s" % (sentence, "" if position == "unplaced" else " [derived]"))
    if a.flag:
        flag = one_line(a.flag, "--flag", 12)
        rec("FLAG", "%s [the lab's own, as printed: repeat it, add none]" % flag)
        said = "above" if flag.upper() in _HIGH_FLAGS else "below" if flag.upper() in _LOW_FLAGS else None
        if said and position in ("below", "inside", "above") and said != position:
            rec("CHECK", "the flag and the printed range do not agree. A digit or a limit may have been misread: "
                         "read the report again before saying anything about this result")
    else:
        rec("FLAG", "none given. Flags are the lab's: repeat one if the report has it, and add none of your own")
    rec("MEASURES", labtests.pointer(test))
    rec("RULE", "say that the value was read against the range on their report. It is not a diagnosis: offer the "
                "question to ask the doctor instead")


def register(sub):
    p = command(sub, "clinic", "triage", cmd_triage,
                "the four triage levels, the red-flag checklist, and a country's emergency numbers",
                ["triage", "triage --flags", "triage --level 2", "triage --country DE", "triage --country \"new zealand\""])
    p.add_argument("--level", type=int, help="one level only, 1 to 4")
    p.add_argument("--flags", action="store_true", help="the red-flag checklist only")
    p.add_argument("--country", metavar="CC", help="the emergency numbers of one country: a two-letter code or its name")

    p = command(sub, "clinic", "find", cmd_find,
                "where to get care in a country: no file holds that, so this is what to look up and how to cite it",
                ["find", "find night care --country IE"])
    p.add_argument("words", nargs="*", help="what is wanted, in a word or two: it heads the record")
    p.add_argument("--country", metavar="CC", help="add the numbers 'triage' has on file for this country: a two-letter code or its name")

    p = command(sub, "clinic", "visit", cmd_visit,
                "getting ready for a doctor's visit: what to ask, what to bring, and a symptom diary to fill in",
                ["visit", 'visit --reason "the cough that will not go" --on 2026-12-01 --diary-days 7'])
    p.add_argument("--reason", help="what the visit is about, in the person's words (printed, never stored)")
    p.add_argument("--on", help="the day of the visit, YYYY-MM-DD: the tool counts the days")
    p.add_argument("--diary-days", type=int, help="print that many dated diary lines to fill in (1 to 60)")
    p.add_argument("--from", dest="start", help="the first diary day (default today)")

    p = command(sub, "clinic", "labs", cmd_labs,
                "read a lab value against the range printed on that person's own report; and what a test is, in the source's words",
                ['labs --test eGFR --value 72 --unit "mL/min/1.73m2" --range ">=60"',
                 'labs --test "Potassium" --value 5,4 --unit mmol/L --range "3.5-5.1" --flag H',
                 'labs --test CRP --value "<0.5" --unit mg/L --range "<5.0"',
                 'labs --test "Vitamin D" --value 18 --unit ng/mL --low 30 --high 50', "labs --about potassium"])
    p.add_argument("--test", help="the test's name as the report prints it")
    p.add_argument("--value", help="the result: a number, or <0.5 / >100 where the lab printed it so")
    p.add_argument("--about", nargs="+", metavar="WORDS", help="what a test is and what it is used for, as MedlinePlus has it")
    p.add_argument("--unit", help="the unit printed beside it")
    p.add_argument("--range", help="the reference range printed on the report: 3.5-5.1, <5.0, >=60, '60 or above'")
    p.add_argument("--low", help="the range's lower limit, if you would rather give the two limits apart")
    p.add_argument("--high", help="the range's upper limit")
    p.add_argument("--flag", help="the lab's own flag beside the result, as printed (H, L, *)")
