"""Desk work: the boot banner, the switch between Clinic and Theatre, the typography and reply check, and
the self-test."""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

from . import core, gate, library, personal
from .core import SKILL, VossError, command, die, load_data, more, rec

IMAGES = os.path.join(SKILL, "images")
BANNER = "VOSS-01 | PROJECT ASCLEPIUS | %s | data: %s"


def banner(mode, infos=None):
    return BANNER % (mode, library.status(library.installed() if infos is None else infos))


def manifest():
    """The picture list, or None where this package carries no pictures."""
    try:
        with open(os.path.join(IMAGES, "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("moods") else None


# ---- boot

def _gate_lines(data, seed):
    people = personal.entries(data)
    for n, (kind, entry) in enumerate(people):
        (rec if n == 0 else lambda _k, v: more(v))("GATE", gate.state_line(data, kind, entry))
    waiting = [e for k, e in people if k == "profile" and gate.is_on(e) and gate.block(e)[0] == "every new conversation"]
    later = [e for k, e in people if k == "profile" and gate.is_on(e) and gate.block(e)[0] == "when it matters"]
    if len(waiting) == 1 and len([1 for k, _ in people if k == "profile"]) == 1:
        entry = waiting[0]
        questions = gate.block(entry)[1]
        order = gate.deal(questions, seed)
        more("ask: %s  (profile %s, question %d)" % (questions[order[0] - 1]["q"], entry["id"], order[0]))
        if len(order) > 1:
            more("if missed, 'ignition --id %s --q %d' gives the next%s" % (
                entry["id"], order[1], ", then --q %d" % order[2] if len(order) > 2 else ""))
        more("check the reply with: ignition --id %s --q %d --answer \"what they said\"  (it never shows an answer, and you do "
             "not open the file to look)" % (entry["id"], order[0]))
        more("no hints, no options, no first letters. Until it is passed, use nothing from the file")
    elif waiting:
        more("ask who you are speaking with; then 'ignition --id ID' deals their question")
    if later:
        more("%s: ask only when the file is about to be used ('ignition --id ID')" % ", ".join(e["id"] for e in later))


def cmd_boot(a):
    infos = library.installed()
    now = core.now()
    rec("BANNER", banner("CLINIC", infos))
    more("the first line of a new conversation, once, exactly as printed; then a short greeting in your own voice")
    good = library.usable(infos)
    if not good:
        rec("DATA", "not installed: there is no database to answer from. Anything that needs a source is a cited lookup, "
                    "or \"I have no data\"")
    else:
        rec("DATA", "%s to answer from; the oldest was built %s" % (
            core.plural(len(good), "database"), min(i["built"] for i in good).isoformat()))
        for info in good:
            stale, note = library.age_note(info, now.date())
            if stale:
                more("%s.db: %s" % (info["stem"], note))
    for info in infos:
        if info["problems"]:
            rec("DATA", "%s.db cannot be answered from: 'sources' says why" % info["stem"])
    rec("TODAY", "%s [this machine's clock, which may not be the person's]" % core.fmt_moment(now))
    readable = True
    try:
        data = personal.load()
    except VossError as e:
        rec("PERSONAL", "the personal file cannot be used: %s" % e)
        more("tell the person once, and answer in general mode")
        data, readable = None, False
    if data is None and readable:
        rec("PERSONAL", "no personal file%s: general mode. 'intake --id self --new' starts one when someone asks" % (
            " (VOSS_PERSONAL names one that is not there yet)" if personal.outside() else ""))
    elif data is not None:
        own, wards = personal.ids(data, "profile"), personal.ids(data, "dependant")
        rec("PERSONAL", "%s%s on file%s. Nothing from a file is read aloud or used before its gate is passed" % (
            core.plural(len(own), "profile"), " and %s" % core.plural(len(wards), "dependant") if wards else "",
            ": %s" % ", ".join(own + wards) if own or wards else ""))
        changed = sorted(str(e["updated"]) for _, e in personal.entries(data) if core.parse_date(str(e.get("updated") or "")))
        if changed:
            more("last changed %s. If the person saved something later than that, an older copy of the file is the one loaded"
                 % changed[-1])
        fixes = [f for f in personal.check(data, now.date()) if f[0] == "FIX"]
        if fixes:
            more("%s to fix in the file (the first is at %s). 'selftest' lists them: tell the person once" % (
                core.plural(len(fixes), "thing"), fixes[0][1]))
        if own or wards:
            try:
                _gate_lines(data, a.seed)
            except VossError as e:
                rec("GATE", str(e))
    pictures = manifest()
    if pictures:
        rec("MARKER", "every reply ends with one line: [mood: KEY] [voss-KEY.webp], and after it, if wanted, [look: KEY] [voss-KEY.webp]")
        more("moods: %s" % ", ".join(m["key"] for m in pictures["moods"]))
        more("looks: %s" % ", ".join(m["key"] for m in pictures.get("looks") or []))
        more("never a file name that is not on that list, and no marker inside a code or record block")
        if EMERGENCY_MOOD in [m["key"] for m in pictures["moods"]]:
            more("an emergency answer carries [mood: %s] [voss-%s.webp] and no look" % (EMERGENCY_MOOD, EMERGENCY_MOOD))
    else:
        rec("MARKER", "this package carries no pictures: leave the marker line out")
    rec("RULE", "general health information needs no gate, and nobody proves who they are to be told to call an emergency number. "
                "Someone who does not pass a gate still gets your full care and knowledge, only without the file")


# ---- theatre

def cmd_theatre(a):
    if a.off:
        rec("BANNER", banner("CLINIC"))
        more("show it once: the scene is over, or was left for something real")
        rec("CLINIC", "real people, real bodies, real medicine. The doctrine in full, and the closing line on every assessment")
        rec("NEXT", "if something real ended the scene, deal with it first; then offer, once: \"Shall we go back to the theatre?\"")
        return
    rec("BANNER", banner("THEATRE"))
    more("show it once, on the change")
    rec("THEATRE", "in-world bodies, in-world medicine, the personality turned up. Action lines are allowed, a few per reply")
    rec("STAYS 1", "real drugs and real doses keep their real rules: a story unlocks nothing that would work as instructions for harm")
    rec("STAYS 2", "a real symptom, real distress or a real emergency stops the scene at once: one plain line, the CLINIC banner "
                   "('theatre --off'), the clinical answer, then the offer to return")
    rec("STAYS 3", "nothing from Theatre goes into the personal file, nothing from a story is presented as real, and real advice "
                   "never shares an answer with in-world medicine")
    rec("METHOD", "playbooks/theatre.md")


# ---- typography check

_FIX = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u00ab": '"', "\u00bb": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u2026": "...", "\u00a0": " ", "\u2009": " ", "\u200a": " ", "\u202f": " ", "\u2002": " ", "\u2003": " ",
    "\u200b": "", "\ufeff": "", "\u2192": "->", "\u2190": "<-", "\u21d2": "=>", "\u2022": "-", "\u00b7": "-",
    "\u00d7": "x", "\u2713": "ok", "\u2714": "ok", "\u2717": "no", "\u2718": "no",
}
_NAMES = {
    "'": "curly apostrophe or quote", '"': "curly or angle quote", "-": "long dash or special hyphen", "...": "ellipsis character",
    " ": "special space", "": "invisible character", "->": "arrow", "<-": "arrow", "=>": "arrow", "x": "multiplication sign",
    "ok": "tick", "no": "cross",
}


def _is_decor(ch):
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2190 <= cp <= 0x21FF or 0x2500 <= cp <= 0x25FF
            or 0x2B00 <= cp <= 0x2BFF or 0xFE00 <= cp <= 0xFE0F or cp == 0x200D or 0x1F1E6 <= cp <= 0x1F1FF)


def check_text(text, code=False):
    """List of (line, column, character, what, replacement)."""
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            if ord(ch) < 128:
                continue
            if ch in _FIX:
                out.append((ln, col, ch, _NAMES.get(_FIX[ch], "special character"), _FIX[ch]))
            elif _is_decor(ch):
                out.append((ln, col, ch, "emoji or decorative symbol", ""))
            elif code:
                out.append((ln, col, ch, "non-ASCII character in code", None))
    return out


def fix_text(text):
    out = []
    for ch in text:
        if ord(ch) < 128:
            out.append(ch)
        elif ch in _FIX:
            out.append(_FIX[ch])
        elif not _is_decor(ch):
            out.append(ch)
    return "".join(out)


# ---- a drafted reply against Voss's own rules

_MARK_RE = re.compile(r"^\[mood:\s*([a-z-]+)\]\s*\[([a-z0-9.-]+)\](?:\s*\[look:\s*([a-z-]+)\]\s*\[([a-z0-9.-]+)\])?$")
_MARKISH_RE = re.compile(r"^\[\s*(mood|look)\b", re.I)
_BANNER_RE = re.compile(r"^VOSS-01 \| PROJECT ASCLEPIUS \| (CLINIC|THEATRE) \| data: \S.*$")
_BANNERISH_RE = re.compile(r"^VOSS-01\b")
_ACTION_RE = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+)\*(?![*\w])")
_EAR_RE = re.compile(r"\bears?\b", re.I)
_CALL_RE = re.compile(r"\b(call|ring|dial|phone)\b", re.I)
_NUMBER_RE = re.compile(r"\b(112|999|911|000|emergency)\b", re.I)
NEVER_SAID = ("probably nothing",)
SOFT_SAID = ("it's nothing", "it is nothing", "nothing to worry about")
DOSE_WORDS = ("stop taking", "start taking", "double the dose", "double your dose", "increase the dose", "increase your dose",
              "reduce the dose", "reduce your dose", "lower the dose", "lower your dose", "skip the dose", "skip a dose",
              "take an extra")
REPLY_LINES = 12
THEATRE_ACTIONS = 5
EMERGENCY_MOOD = "serious"


def reply_findings(text, pictures, theatre=False, emergency=False):
    """What is wrong with a drafted reply as a reply of Voss's: [(FIX or CHECK, line number or 0, what)]."""
    moods = dict((m["key"], m["file"]) for m in (pictures or {}).get("moods") or [])
    looks = dict((m["key"], m["file"]) for m in (pictures or {}).get("looks") or [])
    out, marks, banners = [], [], 0
    in_code, prose, last, first_prose = False, 0, 0, None
    ears, actions = [], []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s:
            last = n
        if s.startswith("```"):
            in_code = not in_code
            if emergency and in_code:
                out.append(("CHECK", n, "a record block in an emergency or crisis answer: plain, kind words serve better"))
            continue
        bare = s.strip("`").strip()
        if _MARKISH_RE.match(bare):
            m = _MARK_RE.match(bare)
            if in_code:
                out.append(("FIX", n, "a marker line inside a code or record block: it goes outside, as the last line"))
            elif not m:
                out.append(("FIX", n, "not a marker line as written: [mood: KEY] [voss-KEY.webp], then [look: KEY] [voss-KEY.webp] if wanted"))
            else:
                marks.append((n, m.groups()))
            continue
        for found in _ACTION_RE.finditer(s):
            (ears if _EAR_RE.search(found.group(1)) else actions).append((n, in_code))
        if in_code or not s:
            continue
        if _BANNERISH_RE.match(bare):
            banners += 1
            if not _BANNER_RE.match(bare):
                out.append(("FIX", n, "not the banner as 'boot' prints it: VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: <status>"))
            continue
        prose += 1
        if first_prose is None:
            first_prose = (n, s)
        low = s.lower().replace("\u2019", "'")
        for phrase in NEVER_SAID:
            if phrase in low:
                out.append(("FIX", n, "\"%s\" is never said. Name what it could be and what would settle it, or say you cannot tell" % phrase))
        for phrase in SOFT_SAID:
            if phrase in low:
                out.append(("CHECK", n, "\"%s\" reads like a verdict. A reassuring guess must never hide a dangerous one" % phrase))
        for phrase in DOSE_WORDS:
            if phrase in low:
                out.append(("CHECK", n, "\"%s\" reads like starting, stopping or changing a dose. That goes to the prescriber or the "
                                        "pharmacist, never from you" % phrase))
                break
        if "safe" in low and ("no interaction" in low or "nothing on file" in low or "no known interaction" in low):
            out.append(("CHECK", n, "absence is not safety: \"nothing on file\" means the file has no entry, never that a combination is safe"))
    if in_code:
        out.append(("FIX", 0, "a code block is opened and never closed"))
    if banners > 1:
        out.append(("CHECK", 0, "%d banner lines: it is shown once, on a new conversation or a change of mode" % banners))
    for n, inside in ears:
        if inside:
            out.append(("FIX", n, "an ear cue inside a record block: never there"))
    if emergency:
        if first_prose is None or not (_CALL_RE.search(first_prose[1]) and _NUMBER_RE.search(first_prose[1])):
            out.append(("FIX", first_prose[0] if first_prose else 0,
                        "an emergency answer leads with the number, in one line: call it, in plain words, before anything else"))
        for n, _ in ears + actions:
            out.append(("FIX", n, "no ears and no stage business in an emergency answer"))
    elif theatre:
        if len(ears) + len(actions) > THEATRE_ACTIONS:
            out.append(("CHECK", 0, "%d action lines: a few per reply, even on stage" % (len(ears) + len(actions))))
    else:
        if len(ears) > 1:
            out.append(("FIX", ears[1][0], "%d ear cues: at most one per message in Clinic" % len(ears)))
        for n, inside in actions:
            if not inside:
                out.append(("CHECK", n, "reads like an action line. Clinic allows one ear cue and nothing else of the kind; "
                                        "the rest belongs to Theatre"))
    if not pictures:
        for n, _ in marks:
            out.append(("FIX", n, "this package carries no pictures: leave the marker line out"))
    elif not marks:
        face = EMERGENCY_MOOD if emergency and EMERGENCY_MOOD in moods else "composed"
        out.append(("FIX", 0, "no marker line: every reply ends with one, %s [mood: %s] [voss-%s.webp]" % (
            "and an emergency answer with" if face == EMERGENCY_MOOD else "such as", face, face)))
    else:
        if len(marks) > 1:
            out.append(("FIX", marks[0][0], "%d marker lines: one, at the very end" % len(marks)))
        if marks[-1][0] != last:
            out.append(("FIX", marks[-1][0], "the marker line is not the last line of the reply"))
        for n, (mood, mood_file, look, look_file) in marks:
            if mood not in moods:
                out.append(("FIX", n, "mood '%s' is not one of: %s" % (mood, ", ".join(moods))))
            elif mood_file != moods[mood]:
                out.append(("FIX", n, "the file for mood '%s' is %s: never make up a file name" % (mood, moods[mood])))
            if look is not None:
                if look not in looks:
                    out.append(("FIX", n, "look '%s' is not one of: %s" % (look, ", ".join(looks))))
                elif look_file != looks[look]:
                    out.append(("FIX", n, "the file for look '%s' is %s: never make up a file name" % (look, looks[look])))
            if emergency and EMERGENCY_MOOD in moods:
                if mood in moods and mood != EMERGENCY_MOOD:
                    out.append(("FIX", n, "an emergency answer carries the serious face and no other: [mood: %s] [%s]" % (
                        EMERGENCY_MOOD, moods[EMERGENCY_MOOD])))
                if look is not None:
                    out.append(("FIX", n, "no look in an emergency answer: the serious face is all it carries"))
    if prose > REPLY_LINES and not emergency:
        out.append(("CHECK", 0, "%d lines of prose: a few plain lines is the rule. Cut it. Figures go in a record block; "
                                "talk stays short" % prose))
    return out


def cmd_check(a):
    if a.file and a.file != "-":
        try:
            with open(a.file, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            die("cannot read %s: %s" % (a.file, e.strerror or e))
        except UnicodeDecodeError:
            die("%s is not UTF-8 text" % a.file)
        name = a.file
    elif a.text:
        text, name = ("\n" if a.reply else " ").join(a.text), "text"
    else:
        text, name = sys.stdin.read(), "stdin"
    if a.mode not in ("clinic", "theatre"):
        die("--mode is clinic or theatre")
    code = a.code or name.lower().endswith((".py", ".js", ".php", ".json", ".css", ".html", ".sh"))
    found = check_text(text, code=code)
    if a.reply and not a.fix:
        notes = reply_findings(text, manifest(), theatre=(a.mode == "theatre"), emergency=a.emergency)
        for ln, col, ch, what, repl in found[:a.limit]:
            rec("FIX L%d" % ln, "col %d: %s U+%04X%s" % (col, what, ord(ch), "" if repl is None else " -> use '%s'" % repl if repl else " -> remove"))
        for level, ln, what in notes:
            rec("%s%s" % (level, " L%d" % ln if ln else ""), what)
        fixes = len(found) + sum(1 for x in notes if x[0] == "FIX")
        checks = sum(1 for x in notes if x[0] == "CHECK")
        kind = "an emergency answer" if a.emergency else "a %s reply" % a.mode
        if fixes or checks:
            rec("REPLY", "%d to fix, %d to look at again, in %d lines [checked as %s]" % (fixes, checks, len(text.splitlines()), kind))
        else:
            rec("REPLY", "clean as %s: typography, %s, short enough (%d lines)" % (
                kind, "the number first, no ears, the serious face" if a.emergency else "ears, one marker line at the end",
                len(text.splitlines())))
        more("this checks form only. Whether a claim is sourced, and whether the tone is right for the person, is yours to judge")
        if fixes:
            raise SystemExit(1)
        return
    if a.fix:
        sys.stdout.write(fix_text(text))
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        left = [f for f in found if f[4] is None]
        if left:
            sys.stderr.write("NOTE %d non-ASCII character(s) left in place: replace them by hand\n" % len(left))
        return
    if not found:
        rec("CHECK", "clean: straight quotes, plain hyphens%s (%d lines)" % (", ASCII only" if code else "", len(text.splitlines())))
        return
    for ln, col, ch, what, repl in found[:a.limit]:
        rec("LINE %d" % ln, "col %d: %s U+%04X%s" % (col, what, ord(ch), "" if repl is None else " -> use '%s'" % repl if repl else " -> remove"))
    if len(found) > a.limit:
        more("... and %d more" % (len(found) - a.limit))
    rec("CHECK", "%d to fix in %s%s; 'check --fix' prints the corrected text" % (len(found), name, " (code rules: ASCII only)" if code else ""))
    raise SystemExit(1)


# ---- selftest

def cmd_selftest(a):
    from . import clinic, doses, ical
    results = []

    def ok(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    ok("dates: a month after 31 January 2024 is 29 February", core.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29))
    born = date(2000, 2, 29)
    ok("dates: born on 29 February, 25 the day before 1 March 2026 and 26 on it",
       core.whole_years(born, date(2026, 2, 28)) == 25 and core.whole_years(born, date(2026, 3, 1)) == 26)
    r = clinic.parse_range("3,5 - 5.1")
    ok("labs: 5.10 is on the upper limit of 3.5 to 5.1, and 5.11 is above it by 0.01",
       clinic.read_against("", Decimal("5.10"), r)[0] == "inside"
       and clinic.read_against("", Decimal("5.11"), r) == ("above", "above the printed range by 0.01"))
    ok("labs: '<0.5' cannot be placed against 0.2 to 2.0", clinic.read_against("<", Decimal("0.5"), clinic.parse_range("0.2-2.0"))[0] == "unplaced")
    twice = doses.parse_doses(["08:00", "20:00"], "the test")
    state = doses.run_down(twice, 60, date(2026, 11, 1), datetime(2026, 11, 15, 10, 30))
    ok("refill: a pack of 60 opened on 1 November, taken twice a day, has 31 left on the 15th at 10:30 and fails the dose of 1 December 08:00",
       state["left"] == 31 and state["count"] == 29 and state["out"] == datetime(2026, 12, 1, 8, 0)
       and state["last"] == datetime(2026, 11, 30, 20, 0), "%s left, out %s" % (state["left"], state.get("out")))
    weekly = doses.parse_doses(["mon 08:00 x6"], "the test")
    state = doses.run_down(weekly, 24, date(2026, 11, 2), datetime(2026, 11, 2, 0, 0))
    ok("refill: 24 taken six at a time each Monday last four Mondays", state["last"] == datetime(2026, 11, 23, 8, 0)
       and state["out"] == datetime(2026, 11, 30, 8, 0) and state["spare"] == 0)
    half = doses.parse_entry("21:30 x1/2", "the test")
    ok("doses: half a tablet is exactly a half", half.units == Fraction(1, 2) and core.show_amount(half.units * 3) == "1.5")
    text = ical.build([ical.event("Take: " + "long name " * 12, datetime(2026, 11, 16, 8, 0), rule=weekly[0].rule(None),
                                  alarm=timedelta(0))], stamp=datetime(2026, 11, 15, tzinfo=timezone.utc))
    ok("calendar: lines end CRLF, none is over 75 octets, and a dose time carries no zone",
       all(len(line.encode("utf-8")) <= 75 for line in text.split("\r\n")) and "\n" not in text.replace("\r\n", "")
       and "DTSTART:20261116T080000\r\n" in text and "RRULE:FREQ=WEEKLY;BYDAY=MO" in text and "TRIGGER:PT0M" in text)
    ok("gate: a loose right answer passes, a wrong one fails, a list of guesses does not pass",
       gate.judge_answer("the Vistula, obviously", ["vistula", "wisla"]) == "PASS"
       and gate.judge_answer("no idea", ["vistula"]) == "FAIL"
       and gate.judge_answer("oder, vistula, or the rhine", ["vistula"]) == "CLOSE")
    # a made-up birth date and serial; the check digit is worked out here, so no real number sits in the source
    body = "9001010012"
    made_up = body + str((10 - sum(w * int(d) for w, d in zip((1, 3, 7, 9, 1, 3, 7, 9, 1, 3), body)) % 10) % 10)
    ok("never stored: a card number and a national identity number are caught, a phone number is not",
       personal.never_stored("card 4111 1111 1111 1111") and personal.never_stored(made_up)
       and personal.never_stored("+48 123 456 789", "phone") is None and personal.never_stored("took 2 tablets at 08:00") is None)
    ok("typography: a curly quote is caught and put right",
       len(check_text("\u201cso\u201d \u2014 it\u2019s")) == 4 and fix_text("\u201cso\u201d \u2014 it\u2019s") == "\"so\" - it's")
    triage = load_data("triage")
    ok("data: four triage levels, ten red flags, and the field list", len(triage["levels"]) == 4 and len(triage["red_flags"]) == 10
       and len(personal.fields()) >= 49)
    try:
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE t (k TEXT, v TEXT)")
        con.execute("INSERT INTO t VALUES (?, ?)", ("a", "b"))
        got = con.execute("SELECT v FROM t WHERE k = ?", ("a",)).fetchone()[0]
        con.close()
        ok("sqlite: this Python can read a database", got == "b")
    except Exception as e:                      # a Python built without sqlite is rare, but it exists
        ok("sqlite: this Python can read a database", False, type(e).__name__)
    infos = library.installed()
    for info in infos:
        ok("data: %s.db says where it came from and when it was built" % info["stem"], not info["problems"], "; ".join(info["problems"]))
    pictures = manifest()
    if pictures:
        rows = (pictures.get("moods") or []) + (pictures.get("looks") or []) + (pictures.get("other") or [])
        missing = [m["file"] for m in rows if not os.path.isfile(os.path.join(IMAGES, m["file"]))]
        ok("pictures: every file the manifest names is in the package", not missing, ", ".join(missing))
    findings = None
    try:
        data = personal.load()
        if data is not None:
            findings = personal.check(data, core.today())
            ok("personal file: reads, and nothing in it needs fixing", not any(f[0] == "FIX" for f in findings))
    except VossError as e:
        ok("personal file: reads", False, str(e))
    bad = [r for r in results if not r[1]]
    for name, good, detail in results:
        rec("PASS" if good else "FAIL", name + (" (got %s)" % detail if detail and not good else ""))
    for level, where, what in findings or []:
        rec(level, "%s: %s" % (where, what))
    rec("SELFTEST", "%d of %d passed; data: %s" % (len(results) - len(bad), len(results), library.status(infos)))
    if bad:
        raise SystemExit(1)


def register(sub):
    p = command(sub, "desk", "boot", cmd_boot,
                "first thing in a conversation: the banner, what data is installed, and whether a personal file and its gate are there",
                ["boot"])
    p.add_argument("--seed", type=int, help="fixed order for the gate question, for testing")

    p = command(sub, "desk", "theatre", cmd_theatre,
                "switch to Theatre (roleplay) or back to Clinic: the banner to show, and what never changes on stage",
                ["theatre", "theatre --off"])
    p.add_argument("--off", action="store_true", help="back to Clinic")

    p = command(sub, "desk", "check", cmd_check,
                "the typography rule (curly quotes, long dashes, emojis; ASCII-only for code), and a drafted reply against your own rules",
                ["check reply.txt", "check --fix draft.txt", 'check --text "some text to test"',
                 'check --reply --text "It measures how well your kidneys filter." "[mood: composed] [voss-composed.webp]"',
                 'check --reply --emergency --text "Call 112 now." "Stay with me and I will tell you what to do while you wait." '
                 '"[mood: serious] [voss-serious.webp]"',
                 "check --reply --mode theatre reply.txt"])
    p.add_argument("file", nargs="?", help="file to check ('-' or nothing: read stdin)")
    p.add_argument("--text", nargs="+", help="check this text instead of a file (with --reply, each piece is a line)")
    p.add_argument("--reply", action="store_true", help="also check it as a reply: ears, the marker line, phrases never said, length")
    p.add_argument("--mode", default="clinic", help="with --reply: clinic (default) or theatre")
    p.add_argument("--emergency", action="store_true", help="with --reply: an emergency or crisis answer (number first, no ears, the serious face as its marker)")
    p.add_argument("--code", action="store_true", help="code rules: any non-ASCII character is flagged")
    p.add_argument("--fix", action="store_true", help="print the corrected text")
    p.add_argument("--limit", type=int, default=20, help="findings to list (default 20)")

    command(sub, "desk", "selftest", cmd_selftest,
            "a quick known-answer check that the tools, the data files and the personal file are sound on this machine", ["selftest"])
