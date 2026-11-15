"""What a person writes down over time: a symptom diary and their lab results.

diary    a symptom, how bad it was from 0 to 10, what helped: one line a day, in the person's own words, for
         a doctor to read.
result   one lab result, with the range printed beside it on its own report.
reading  a home reading (blood pressure, pulse, temperature, weight, glucose), kept as it was read, and the
         target the person's doctor set for it. The tool knows no threshold of its own.
followup what the person agreed to be asked about again, and the visits that have just gone by.
labread  a whole report at once, as it was read off a photo or a PDF. A figure nobody could read is marked
         unreadable and is not kept: it is never guessed.
trend    each result of a test against the range of its own report. It never puts two reports on one scale,
         and it says so when the unit, the lab or the printed range changed from one to the next.

Nothing is saved until it has been read back: a command prints what it would store and a code, and the same
command with --confirm and that code writes the new file. A trend is not a diagnosis, and neither is a diary.
"""
from decimal import Decimal

from . import clinic, core, personal, rebuild
from .core import command, die, fold, more, one_line, rec

SHOW_MAX = 20
ROWS_MAX = 60
UNREADABLE = ("?", "unreadable", "illegible")
ROW_HELP = "a row is  \"test | value | unit | range | flag\"  as the report prints them; a value nobody can read is ?"


def _who(a):
    data = personal.need()
    kind, entry = personal.pick(data, a.id)
    return data, entry


def _given(pairs):
    """The parts that were given, as text, for the change machinery to read and check."""
    return dict((k, str(v)) for k, v in pairs if v is not None and str(v).strip())


# ---- the symptom diary

def cmd_diary(a):
    data, entry = _who(a)
    today = core.today()
    if a.what or a.severity is not None or a.helped or a.notes:
        if not a.what:
            die("an entry needs --what: the symptom, in the person's own words")
        value = _given((("date", a.date), ("what", a.what), ("severity", a.severity), ("helped", a.helped), ("notes", a.notes)))
        rebuild.save(a, entry["id"], [("add", "symptom_diary", value)], today)
        return
    rows = personal.rows(entry, "symptom_diary")
    since = core.a_date(a.since, "--since", today) if a.since else None
    if since:
        rows = [r for r in rows if str(r.get("date") or "") >= since.isoformat()]
    rec("DIARY", "%s: %s on file%s" % (entry["id"], core.plural(len(rows), "entry", "entries"),
                                       " since %s" % since.isoformat() if since else ""))
    for row in rows[-a.max:] if a.max > 0 else []:
        severity = row.get("severity")
        more("%s  %s%s%s%s" % (
            row.get("date") or "no date", row.get("what") or "",
            "; severity %s/10" % core.plain(Decimal(str(severity))) if severity is not None else "",
            "; helped: %s" % row["helped"] if row.get("helped") else "",
            "; notes: %s" % row["notes"] if row.get("notes") else ""))
    if len(rows) > a.max > 0:
        more("and %s before these: --max, or --since DATE" % core.plural(len(rows) - a.max, "earlier entry", "earlier entries"))
    if not rows:
        more("to add one: diary --id %s --what \"...\" --severity 0-10 --helped \"...\"" % entry["id"])
    rec("RULE", "these are the person's own words, on the days they gave. A diary is for a doctor to read: nothing in it "
                "is a diagnosis, and a pattern in it is a question to take to one")


# ---- lab results

def _value_parts(text):
    """A result as the report prints it: a plain number goes into 'value', anything else stays as it was printed."""
    tidy = " ".join(str(text).split())
    try:
        Decimal(tidy.replace(",", "."))
        return ("value", tidy)
    except ArithmeticError:
        return ("value_text", tidy)


def _result_value(test, value, unit, low, high, range_text, lab, flag, day):
    if range_text and (low is not None or high is not None):
        die("give the range once: --range as the report prints it, or --low and --high")
    return _given((("date", day), ("test", test), _value_parts(value), ("unit", unit), ("range_low", low), ("range_high", high),
                   ("range_text", range_text), ("lab", lab), ("flag", flag)))


def _shown(row):
    """A result's figure and unit, as on file."""
    value = row.get("value")
    figure = core.plain(Decimal(str(value))) if value is not None else str(row.get("value_text") or "")
    return "%s%s" % (figure, " " + row["unit"] if row.get("unit") else "")


def _range(row):
    """The range printed on a result's own report, as clinic reads one; None where there was none."""
    if row.get("range_text"):
        return clinic.parse_range(row["range_text"])
    low, high = row.get("range_low"), row.get("range_high")
    if low is None and high is None:
        return None
    r = {"low": None, "high": None, "low_in": True, "high_in": True, "low_text": "", "high_text": ""}
    for side, number in (("low", low), ("high", high)):
        if number is not None:
            r[side] = Decimal(str(number))
            r[side + "_text"] = core.plain(r[side])
    return r


def _reading(row):
    """Where a result sits against its own report's range, in words; '' where that cannot be said."""
    r = _range(row)
    if r is None:
        return "no range on file for this report, so nothing is read from it"
    if row.get("value") is not None:
        op, number = "", Decimal(str(row["value"]))
    else:
        m = clinic._VALUE_RE.match(clinic._tidy(row.get("value_text") or ""))
        if not m:
            return "printed in words, not as a figure: there is nothing to set against a range"
        op, number = m.group(1) or "", core.decimal_of(m.group(2), "the value on file")
    position, sentence = clinic.read_against(op, number, r)
    if row.get("unit") and position in ("below", "above") and " by " in sentence:
        sentence += " " + row["unit"]
    return "%s%s" % (sentence, "" if position == "unplaced" else " [derived]")


def _line(row):
    r = _range(row)
    return "%s  %s  %s%s%s" % (
        row.get("date") or "no date", _shown(row),
        "range %s" % clinic.range_words(r) if r else "no range given",
        "; flag %s [the lab's]" % row["flag"] if row.get("flag") else "",
        "; %s" % row["lab"] if row.get("lab") else "")


def cmd_result(a):
    data, entry = _who(a)
    today = core.today()
    if a.test or a.value is not None:
        if not a.test or a.value is None:
            die("a result needs --test and --value, as the report prints them, and --date, the day on the report")
        value = _result_value(a.test, a.value, a.unit, a.low, a.high, a.range, a.lab, a.flag, a.date)
        rebuild.save(a, entry["id"], [("add", "lab_results", value)], today)
        return
    rows = personal.rows(entry, "lab_results")
    rec("RESULTS", "%s: %s on file" % (entry["id"], core.plural(len(rows), "result")))
    for row in rows[-a.max:] if a.max > 0 else []:
        more("%s: %s" % (row.get("test") or "no name", _line(row)))
    if len(rows) > a.max > 0:
        more("and %s before these: --max" % core.plural(len(rows) - a.max, "earlier result"))
    if rows:
        more("'trend --id %s' reads each against the range of its own report" % entry["id"])
    else:
        more("to add one: result --id %s --test \"...\" --value ... --unit ... --range \"...\" --date ..." % entry["id"])
    rec("RULE", "figures as the person gave them, with the ranges printed on their own reports. Flags are the lab's: "
                "repeat one, add none. A result is not a diagnosis")


def cmd_labread(a):
    data, entry = _who(a)
    today = core.today()
    lines = list(a.row or [])
    if a.file:
        try:
            with open(a.file, encoding="utf-8") as f:
                lines += [ln for ln in f.read().splitlines() if ln.strip()]
        except (OSError, UnicodeDecodeError):
            die("--file could not be read as UTF-8 text")
    if not lines:
        die("no rows were given: %s" % ROW_HELP)
    if len(lines) > ROWS_MAX:
        die("that is more than %d rows: read the report in over several calls" % ROWS_MAX)
    if not a.date:
        die("--date is the day printed on the report: a result with no day cannot be set in order")
    ops, unreadable = [], []
    for n, line in enumerate(lines, 1):
        parts = [p.strip() for p in str(line).split("|")]
        if len(parts) < 2 or len(parts) > 5 or not parts[0]:
            die("row %d was not understood: %s" % (n, ROW_HELP))
        parts += [""] * (5 - len(parts))
        test, value, unit, printed, flag = parts
        test = one_line(test, "the test in row %d" % n, 120)
        if not value or value.lower() in UNREADABLE:
            unreadable.append(test)
            continue
        if printed.lower() in UNREADABLE:
            printed = ""
            unreadable.append("the range of %s" % test)
        ops.append(("add", "lab_results", _result_value(test, value, unit, None, None, printed, a.lab, flag, a.date)))
    rec("REPORT", "%s, dated %s%s: %s read%s" % (
        entry["id"], core.a_date(a.date, "--date", today).isoformat(), ", %s" % one_line(a.lab, "--lab", 120) if a.lab else "",
        core.plural(len(ops), "result"), ", %d could not be" % len(unreadable) if unreadable else ""))
    for name in unreadable:
        rec("UNREADABLE", "%s: not kept. Ask the person to read it out from the report; never fill it in" % name)
    if not ops:
        rec("NOTHING", "no row had a figure that could be read, so there is nothing to store")
        return
    rebuild.save(a, entry["id"], ops, today)


def cmd_trend(a):
    data, entry = _who(a)
    rows = personal.rows(entry, "lab_results")
    tests = {}
    for row in rows:
        tests.setdefault(fold(row.get("test") or ""), []).append(row)
    if a.test:
        want = fold(" ".join(a.test))
        hits = dict((k, v) for k, v in tests.items() if k == want) or dict((k, v) for k, v in tests.items() if want in k)
        if not hits:
            rec("TREND", "nothing on file under that test%s" % (
                ": on file are %s" % "; ".join(sorted(set(v[0].get("test") or "" for v in tests.values()))[:12]) if tests else ""))
            return
        tests = hits
    if not tests:
        rec("TREND", "no lab results are on file for %s" % entry["id"])
        more("'result' keeps one, 'labread' a whole report")
        return
    for n, (_, group) in enumerate(sorted(tests.items())):
        if n:
            print()
        rec("TREND", "%s: %s" % (group[0].get("test"), core.plural(len(group), "result")))
        last = None
        for row in group:
            more(_line(row))
            more("  %s" % _reading(row))
            if last is not None:
                between = "between %s and %s" % (last.get("date"), row.get("date"))
                if fold(last.get("unit") or "") != fold(row.get("unit") or ""):
                    rec("CHECK", "the unit changed %s (%s, then %s): the two figures cannot be set side by side" % (
                        between, last.get("unit") or "none given", row.get("unit") or "none given"))
                if last.get("lab") and row.get("lab") and fold(last["lab"]) != fold(row["lab"]):
                    rec("CHECK", "the lab changed %s: each lab measures in its own way, and its range is its own" % between)
                elif _range(last) and _range(row) and clinic.range_words(_range(last)) != clinic.range_words(_range(row)):
                    rec("CHECK", "the printed range changed %s: the lab may have changed how it measures. Each value is "
                                 "still read against its own" % between)
            last = row
    rec("RULE", "each value is read against the range printed on its own report, and never against another report's. A "
                "trend is not a diagnosis: name the question to ask the doctor, and leave the reading to them")


# ---- home readings

READ_KINDS = {"bp": "blood pressure", "blood_pressure": "blood pressure", "pressure": "blood pressure", "heart_rate": "pulse",
              "temp": "temperature", "blood_sugar": "glucose", "sugar": "glucose", "peak_flow": "peak flow",
              "oxygen": "oxygen saturation", "spo2": "oxygen saturation", "saturation": "oxygen saturation"}
# where the person's usual figure for a kind of reading sits in 'baseline_vitals', and how to say it
USUAL = {"blood pressure": ("bp", ""), "pulse": ("resting_pulse", " a minute, at rest"), "temperature": ("temperature_c", " C")}
PAST_DAYS = 14


def _kind(text):
    """What was measured, by one name: 'BP' and 'blood pressure' are the same reading."""
    words = " ".join(str(text).lower().split())
    return READ_KINDS.get(fold(words), words)


def _span(rows):
    """How far a run of readings ranged, in words. A reading of two figures has each of them told apart: the
    lowest of one and the lowest of the other need not have been read on the same day."""
    figures = [[Decimal(p.replace(",", ".")) for p in str(r.get("value") or "").split("/")] for r in rows]
    if len(set(len(f) for f in figures)) != 1:
        return ""
    names = ("it",) if len(figures[0]) == 1 else ("the first figure", "the second")
    parts = []
    for n, name in enumerate(names):
        column = [f[n] for f in figures]
        parts.append("%s ran from %s to %s" % (name, core.plain(min(column)), core.plain(max(column))))
    return "%s; the latest is %s" % (", ".join(parts), rows[-1]["value"])


def cmd_reading(a):
    data, entry = _who(a)
    today = core.today()
    if a.target:
        if not a.kind:
            die("say what the target is for: --kind \"blood pressure\" --target \"below 135/85\"")
        value = _given((("kind", _kind(a.kind)), ("target", a.target), ("set_by", a.set_by)))
        rebuild.save(a, entry["id"], [("add", "reading_targets", value)], today)
        return
    if a.value:
        if not a.kind:
            die("say what was measured: --kind \"blood pressure\" --value 128/82")
        value = _given((("date", a.date), ("time", a.time), ("kind", _kind(a.kind)), ("value", a.value), ("unit", a.unit),
                        ("note", a.note)))
        rebuild.save(a, entry["id"], [("add", "home_readings", value)], today)
        return
    rows = [r for r in personal.rows(entry, "home_readings") if isinstance(r, dict)]
    since = core.a_date(a.since, "--since", today) if a.since else None
    if since:
        rows = [r for r in rows if str(r.get("date") or "") >= since.isoformat()]
    if a.kind:
        rows = [r for r in rows if r.get("kind") == _kind(a.kind)]
    kinds = []
    for row in rows:
        if row.get("kind") not in kinds:
            kinds.append(row.get("kind"))
    rec("READINGS", "%s: %s on file%s%s" % (entry["id"], core.plural(len(rows), "home reading"),
                                            " of %s" % _kind(a.kind) if a.kind else "",
                                            " since %s" % since.isoformat() if since else ""))
    if not rows:
        more("to add one: reading --id %s --kind \"blood pressure\" --value 128/82 --unit mmHg --time 07:30" % entry["id"])
    usual = entry.get("baseline_vitals") if isinstance(entry.get("baseline_vitals"), dict) else {}
    targets = dict((t.get("kind"), t) for t in personal.rows(entry, "reading_targets") if isinstance(t, dict))
    for kind in kinds:
        mine = [r for r in rows if r.get("kind") == kind]
        rec("KIND", "%s: %s%s" % (kind, core.plural(len(mine), "reading"),
                                 ", %s to %s" % (mine[0].get("date"), mine[-1].get("date")) if len(mine) > 1 else ""))
        for row in mine[-a.max:] if a.max > 0 else []:
            more("%s%s  %s%s%s" % (row.get("date") or "no date", " %s" % row["time"] if row.get("time") else "", row.get("value"),
                                  " %s" % row["unit"] if row.get("unit") else "", "; %s" % row["note"] if row.get("note") else ""))
        if len(mine) > a.max > 0:
            more("and %s before these: --max, or --since DATE" % core.plural(len(mine) - a.max, "earlier one"))
        if len(set(fold(r.get("unit") or "") for r in mine)) > 1:
            rec("CHECK", "%s: the unit is not the same in every reading, so they are not set side by side" % kind)
        elif len(mine) > 1:
            span = _span(mine)
            if span:
                more("%s [derived]" % span)
        if kind in USUAL and usual.get(USUAL[kind][0]) not in (None, ""):
            more("their usual, as on file: %s%s%s" % (usual[USUAL[kind][0]], USUAL[kind][1],
                                                      " (measured %s)" % usual["measured"] if usual.get("measured") else ""))
        if kind in targets and targets[kind].get("target"):
            t = targets[kind]
            rec("TARGET", "%s: %s [%s, recorded %s; the tool does not judge a reading against it]" % (
                kind, t["target"], "set by %s" % t["set_by"] if t.get("set_by") else "as their doctor worded it",
                t.get("recorded") or "no date"))
    rec("RULE", "the tool keeps figures and counts them. It knows no threshold, and it does not say whether a reading is good: "
                "that is for the doctor who set the target, with the readings in front of them. A reading that worries the "
                "person, or comes with symptoms, is a triage question first")


# ---- follow-ups

def due_followups(entry, today):
    """What the person agreed to be asked about again, and may be asked now."""
    return [r for r in personal.rows(entry, "followups")
            if isinstance(r, dict) and (core.parse_date(str(r.get("date") or "")[:10]) or today) <= today]


def past_visits(entry, today):
    """Visits on file whose day went by in the last fortnight: [(when, with whom)]."""
    out = []
    for row in personal.rows(entry, "appointments"):
        day = core.parse_date(str(row.get("when") or "")[:10]) if isinstance(row, dict) else None
        if day and 0 < (today - day).days <= PAST_DAYS:
            out.append((str(row.get("when")), str(row.get("with") or "")))
    return out


def cmd_followup(a):
    data, entry = _who(a)
    today = core.today()
    if a.what:
        value = _given((("date", a.frm), ("what", a.what), ("about", a.about)))
        rebuild.save(a, entry["id"], [("add", "followups", value)], today)
        return
    rows = [r for r in personal.rows(entry, "followups") if isinstance(r, dict)]
    due = due_followups(entry, today)
    rec("FOLLOW UP", "%s: %s to ask about now, %s for later" % (entry["id"], core.plural(len(due), "thing"), len(rows) - len(due)))
    for row in due:
        rec("ASK", "%s%s [to be asked from %s]" % (row.get("what"), " (%s)" % row["about"] if row.get("about") else "", row.get("date")))
    for row in rows:
        if row not in due:
            more("from %s: %s" % (row.get("date"), row.get("what")))
    for when, who in past_visits(entry, today):
        rec("VISIT", "%s%s has been and gone: ask how it went, once. A letter from it goes to 'decode'" % (when, ", %s" % who if who else ""))
    if not rows:
        more("to note one, when they agree to be asked: followup --id %s --what \"how the X-ray went\" --from 2026-12-01" % entry["id"])
    if rows:
        rec("DONE", "once a thing has been asked and answered: forget --id %s --field followups --match \"words of it\". What they "
                    "tell you may belong in the diary ('diary') or on file ('intake')" % entry["id"])
    rec("RULE", "ask once, plainly, and take the answer as it comes. \"I did not go\" is an answer too, and gets no lecture: ask "
                "what got in the way. Nothing is asked where others can read it that the person would keep to themselves")


def register(sub):
    p = command(sub, "file", "diary", cmd_diary,
                "the symptom diary: what is on file, or one new entry read back before it is kept",
                ["diary --id self", "diary --id self --since 2026-11-01",
                 'diary --id self --what "headache behind the eyes" --severity 6 --helped "a dark room" --date yesterday'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--what", help="the symptom, in the person's own words")
    p.add_argument("--severity", help="how bad, from 0 to 10, as the person rates it")
    p.add_argument("--helped", help="what helped, if anything")
    p.add_argument("--notes", help="anything else they want the doctor to read")
    p.add_argument("--date", help="the day it happened (default: today)")
    p.add_argument("--since", help="show only entries from this day on")
    p.add_argument("--max", type=int, default=SHOW_MAX, help="entries to show, the latest (default %d)" % SHOW_MAX)
    rebuild.out_options(p)

    p = command(sub, "file", "result", cmd_result,
                "lab results on file, or one new result with the range printed on its own report, read back before it is kept",
                ["result --id self",
                 'result --id self --test TSH --value 2.1 --unit mIU/l --range "0.27-4.2" --date 2026-11-02 --lab "the hospital lab"',
                 'result --id self --test "CRP" --value "<0.5" --unit mg/l --range "<5" --date 2026-11-02'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--test", help="the name of the test, as the report prints it")
    p.add_argument("--value", help="the result as printed: 5.1, or <0.5, or a word such as negative")
    p.add_argument("--unit", help="the unit printed beside it")
    p.add_argument("--range", help="the range printed beside it: 3.5-5.1, <5.0, 'up to 5.0'")
    p.add_argument("--low", help="the lower limit, where the report prints the two apart")
    p.add_argument("--high", help="the upper limit")
    p.add_argument("--date", help="the day on the report")
    p.add_argument("--lab", help="which lab it was")
    p.add_argument("--flag", help="the lab's own flag, as printed: H, L, *")
    p.add_argument("--max", type=int, default=SHOW_MAX, help="results to show, the latest (default %d)" % SHOW_MAX)
    rebuild.out_options(p)

    p = command(sub, "file", "labread", cmd_labread,
                "a whole lab report read off a photo or a PDF: every row read back before any is kept, the unreadable ones left out",
                ['labread --id self --date 2026-11-02 --lab "the hospital lab" --row "TSH | 2.1 | mIU/l | 0.27-4.2" '
                 '--row "Glucose | ? | mg/dl | 70-99 | H"'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--date", help="the day printed on the report")
    p.add_argument("--lab", help="which lab it was")
    p.add_argument("--row", action="append", metavar="ROW", help=ROW_HELP)
    p.add_argument("--file", help="a text file with one row to a line, for a long report")
    rebuild.out_options(p)

    p = command(sub, "clinic", "trend", cmd_trend,
                "each result of a lab test over time, read against the range of its own report, with what changed in between",
                ["trend --id self", "trend --id self --test tsh"])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--test", nargs="+", metavar="NAME", help="one test only")

    p = command(sub, "file", "reading", cmd_reading,
                "home readings (blood pressure, pulse, temperature, weight, glucose) over time, and the target their doctor set",
                ["reading --id self", 'reading --id self --kind "blood pressure" --value 128/82 --unit mmHg --time 07:30',
                 'reading --id self --kind "blood pressure" --target "below 135/85 at home" --set-by "the GP"'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--kind", help="what was measured: blood pressure, pulse, temperature, weight, glucose, peak flow, or their own word")
    p.add_argument("--value", help="the figure as it was read: 128/82, 36.8")
    p.add_argument("--unit", help="its unit: mmHg, C, kg, mmol/l")
    p.add_argument("--date", help="the day it was read (default: today)")
    p.add_argument("--time", help="the time of day: 07:30")
    p.add_argument("--note", help="anything that goes with it: after a walk, left arm")
    p.add_argument("--target", help="what to aim for, in the words of the doctor who set it; with --kind")
    p.add_argument("--set-by", dest="set_by", help="with --target: who set it")
    p.add_argument("--since", help="readings from this day on")
    p.add_argument("--max", type=int, default=SHOW_MAX, help="readings to show of each kind, the latest (default %d)" % SHOW_MAX)
    rebuild.out_options(p)

    p = command(sub, "file", "followup", cmd_followup,
                "what the person agreed to be asked about again, what is due to be asked now, and visits that have just gone by",
                ["followup --id self", 'followup --id self --what "how the X-ray went" --from 2026-12-01 --about "the chest X-ray"'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--what", help="what to ask about again, in a line")
    p.add_argument("--from", dest="frm", metavar="DATE", help="the day to ask from (default: today)")
    p.add_argument("--about", help="what it belongs to: a visit, a test, a new medicine")
    rebuild.out_options(p)
