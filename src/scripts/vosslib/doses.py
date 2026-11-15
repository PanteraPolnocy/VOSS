"""Medicine times as a calendar file, and how long a pack will last.

The tool repeats a schedule it was given: what was prescribed, or what the label says. It never sets one
and never changes one. The counting is exact (fractions and whole days), and it assumes every scheduled
dose was taken, because it has no way to know otherwise; the output says so every time.

A dose is written as  [DAYS] HH:MM [xAMOUNT] :
  08:00                              every day at eight, one at a time
  20:00 x2                           every day, two at a time (x0.5 and x1/2 are half)
  mon thu 08:00                      on those days of the week
  every 2 days from 2026-11-01 08:00 every second day, counted from that day
"""
import re
from datetime import datetime, timedelta
from fractions import Fraction

from . import core, ical
from .core import command, die, fold, fraction_of, more, one_line, rec, show_amount

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_DAY_WORDS = dict((w, n) for n, w in enumerate(WEEKDAYS))
_DAY_WORDS.update(dict((w, n) for n, w in enumerate(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))))
_AMOUNT_RE = re.compile(r"(?:^|\s)x\s*(\d[\d.,/]*)$")
_TIME_RE = re.compile(r"(?:^|\s)(\d{1,2}[:.]\d{2})$")
_EVERY_RE = re.compile(r"^every\s+(\d{1,3})\s+days?(?:\s+from\s+(\S+))?$")
MAX_UNITS = 1000
MAX_EVERY = 366
MAX_PACK = 100000
MAX_DAYS = 3660
MAX_MEDICINES = 60
ENTRY_HELP = "a dose is  [DAYS] HH:MM [xAMOUNT] , such as  08:00 ,  mon thu 08:00 x2  or  every 2 days from 2026-11-01 08:00"


class Dose(object):
    """One line of a schedule: a time of day, how much, and which days."""
    __slots__ = ("hour", "minute", "units", "days", "every", "anchor")

    def __init__(self, hour, minute, units=Fraction(1), days=None, every=None, anchor=None):
        self.hour, self.minute, self.units = hour, minute, units
        self.days, self.every, self.anchor = days, every, anchor

    def falls_on(self, day, first_day):
        if self.days is not None:
            return day.weekday() in self.days
        if self.every:
            gap = (day - (self.anchor or first_day)).days
            return gap >= 0 and gap % self.every == 0
        return True

    def words(self):
        clock = "%02d:%02d" % (self.hour, self.minute)
        if self.days is not None:
            names = [DAY_NAMES[n] for n in sorted(self.days)]
            pattern = "on " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
        elif self.every:
            pattern = "every %d days%s" % (self.every, " from %s" % self.anchor.isoformat() if self.anchor else "")
        else:
            pattern = "every day"
        return "%s %s%s" % (clock, pattern, "" if self.units == 1 else ", %s each time" % show_amount(self.units))

    def rule(self, until):
        if self.days is not None:
            parts = ["FREQ=WEEKLY", "BYDAY=" + ",".join(BYDAY[n] for n in sorted(self.days))]
        elif self.every:
            parts = ["FREQ=DAILY", "INTERVAL=%d" % self.every]
        else:
            parts = ["FREQ=DAILY"]
        if until:
            parts.append("UNTIL=%sT235959" % until.strftime("%Y%m%d"))
        return ";".join(parts)


def parse_entry(text, what):
    """One dose line as a Dose. 'what' names the entry in an error; the entry itself is never repeated."""
    t = " ".join(str(text).lower().split())
    if not t:
        die("%s is empty: %s" % (what, ENTRY_HELP))
    units = Fraction(1)
    m = _AMOUNT_RE.search(t)
    if m:
        units = fraction_of(m.group(1), "the amount in %s" % what)
        t = t[:m.start()].strip()
        if not 0 < units <= MAX_UNITS:
            die("the amount in %s must be more than zero, and at most %d" % (what, MAX_UNITS))
    m = _TIME_RE.search(t)
    if not m:
        die("%s has no clock time: %s" % (what, ENTRY_HELP))
    hour, minute = core.parse_clock(m.group(1), "the time in %s" % what)
    rest = t[:m.start()].strip()
    if rest in ("", "daily", "every day"):
        return Dose(hour, minute, units)
    if rest == "every other day":
        return Dose(hour, minute, units, every=2)
    m = _EVERY_RE.match(rest)
    if m:
        every = int(m.group(1))
        if not 1 <= every <= MAX_EVERY:
            die("%s: 'every N days' takes 1 to %d" % (what, MAX_EVERY))
        anchor = core.a_date(m.group(2), "the 'from' day in %s" % what) if m.group(2) else None
        return Dose(hour, minute, units, every=None if every == 1 else every, anchor=anchor if every > 1 else None)
    days = set()
    for word in re.split(r"[\s/+&]+", rest):
        if word in ("", "and", "on"):
            continue
        if word not in _DAY_WORDS:
            die("%s was not understood: %s" % (what, ENTRY_HELP))
        days.add(_DAY_WORDS[word])
    if not days:
        die("%s was not understood: %s" % (what, ENTRY_HELP))
    return Dose(hour, minute, units, days=frozenset(days))


def parse_doses(entries, what):
    """A list of dose lines as Doses. The same time on the same days twice is a mistake worth stopping for."""
    doses, seen = [], set()
    for n, text in enumerate(entries, 1):
        dose = parse_entry(text, "dose %d of %s" % (n, what))
        key = (dose.hour, dose.minute, dose.days, dose.every, dose.anchor)
        if key in seen:
            die("dose %d of %s repeats an earlier one: each time is written once (use x2 for two at a time)" % (n, what))
        seen.add(key)
        doses.append(dose)
    return doses


def parse_med(spec):
    """'Name 10 mg: 08:00, 20:00 x2' as a medicine: its name and its doses."""
    name, sep, body = str(spec).partition(":")
    # "08:00, 20:00" with no name splits at the clock's own colon, and leaves an hour where the name should be
    if not sep or not name.strip() or re.fullmatch(r"\d{1,2}", name.strip()):
        die("--med looks like  \"Name 10 mg: 08:00, 20:00\"  (%s)" % ENTRY_HELP)
    name = one_line(name, "the medicine's name", 80)
    entries = [e for e in body.split(",") if e.strip()]
    if not entries:
        die("no dose times were given for that medicine: one taken only when needed has no schedule to write")
    return {"name": name, "doses": parse_doses(entries, "that medicine"), "how": "", "pack": None, "opened": None}


def from_file(entry, supplements=False):
    """The medicines on file that have dose times, and the names of those that have none."""
    meds, left_out = [], []
    rows = [("medicine", r) for r in (entry.get("medicines") or [])]
    if supplements:
        rows += [("supplement", r) for r in (entry.get("supplements") or [])]
    for n, (kind, row) in enumerate(rows, 1):
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        name = " ".join(x for x in (str(row.get("name")).strip(), str(row.get("strength") or "").strip()) if x)
        times = [t for t in (row.get("schedule") or []) if str(t).strip()]
        if not times:
            left_out.append(name)
            continue
        med = {"name": name, "doses": parse_doses(times, "%s %d on file" % (kind, n)),
               "how": str(row.get("how_taken") or "").strip(), "pack": None, "opened": None}
        if row.get("pack_size") not in (None, ""):
            med["pack"] = fraction_of(row["pack_size"], "the pack size of %s %d on file" % (kind, n))
        if str(row.get("pack_opened") or "").strip():
            med["opened"] = core.a_date(row["pack_opened"], "the pack date of %s %d on file" % (kind, n))
        meds.append(med)
    return meds, left_out


def walk(doses, first_day, days=MAX_DAYS):
    """Every dose from first_day on, in order, as (moment, amount). Stops after that many days."""
    for n in range(days):
        day = first_day + timedelta(days=n)
        todays = sorted((d for d in doses if d.falls_on(day, first_day)), key=lambda d: (d.hour, d.minute))
        for d in todays:
            yield datetime(day.year, day.month, day.day, d.hour, d.minute), d.units


def first_day(dose, start, until=None):
    """The first day on or after start that this dose falls on, or None if there is none before 'until'."""
    for n in range(MAX_EVERY + 1):
        day = start + timedelta(days=n)
        if until and day > until:
            return None
        if dose.falls_on(day, start):
            return day
    return None


def _gather(a, supplements=False):
    """Medicines named on the command line, and those on file if a profile was asked for."""
    meds, left_out = [], []
    for spec in a.med or []:
        meds.append(parse_med(spec))
    if a.id:
        from . import personal
        data = personal.need()
        kind, entry = personal.pick(data, a.id)
        found, left_out = from_file(entry, supplements)
        meds += found
    if len(meds) > MAX_MEDICINES:
        die("that is more than %d medicines: split them over several calls" % MAX_MEDICINES)
    return meds, left_out


# ---- schedule

def cmd_schedule(a):
    today = core.today()
    start = core.a_date(a.start, "--from", today) if a.start else today
    until = core.a_date(a.until, "--until", today) if a.until else None
    if a.days is not None:
        if until:
            die("give the end once: --until or --days")
        if not 1 <= a.days <= MAX_DAYS:
            die("--days is 1 to %d" % MAX_DAYS)
        until = start + timedelta(days=a.days - 1)
    if until and until < start:
        die("--until is before the first day")
    if a.alarm < 0 or a.alarm > 1440:
        die("--alarm is minutes before the dose: 0 to 1440")
    meds, left_out = _gather(a, a.supplements)
    if not meds:
        if left_out:
            die("nothing on file has dose times, so there is no schedule to write: ask what the label or the prescription says")
        die("no medicine was given: --med \"Name 10 mg: 08:00, 20:00\", or --id for the ones on file")
    events, notes = [], []
    rec("SCHEDULE", "%s from %s%s [as given: this repeats a schedule, it does not set one]" % (
        core.plural(len(meds), "medicine"), core.fmt_day(start), " to %s" % core.fmt_day(until) if until else ""))
    for n, med in enumerate(meds, 1):
        rec("MEDICINE", med["name"])
        for dose in med["doses"]:
            day = first_day(dose, start, until)
            if day is None:
                more("%s: no dose falls inside the dates given, so it is left out" % dose.words())
                continue
            more("%s; first on %s" % (dose.words(), core.fmt_day(day)))
            if dose.every and not dose.anchor:
                notes.append("%s: 'every %d days' is counted from %s. If the real first day differs, write it as "
                             "'every %d days from YYYY-MM-DD'" % (med["name"], dose.every, start.isoformat(), dose.every))
            amount = "" if dose.units == 1 else " %s" % show_amount(dose.units)
            if a.discreet:
                summary, text = "Medicine %d" % n, ""
            else:
                summary = "Take%s: %s" % (amount, med["name"])
                text = "%sThe schedule as it was given on %s. If the label, the prescription or the pharmacist says otherwise, " \
                       "they are right." % (med["how"] + ". " if med["how"] else "", today.isoformat())
            events.append(ical.event(summary, datetime(day.year, day.month, day.day, dose.hour, dose.minute),
                                     rule=dose.rule(until), description=text,
                                     alarm=None if a.no_alarm else timedelta(minutes=a.alarm)))
    for name in left_out:
        rec("LEFT OUT", "%s: no dose times on file (taken as needed, or not told)" % name)
    for note in notes:
        rec("NOTE", note)
    rec("RULE", "the prescription label and the pharmacist come first. Never add, move or drop a dose to make it tidy")
    if not events:
        die("no dose falls inside the dates given: nothing to put in a calendar")
    if not a.ics:
        rec("NEXT", "read it back to the person. When they confirm it, run this again with --ics auto for the calendar file")
        return
    ical.deliver(a.ics, events, "medicines-%s" % start.isoformat())
    more("times carry no zone: 08:00 stays 08:00 wherever the phone is, and across a clock change")
    if not a.discreet:
        more("the entries name the medicines, and a phone may show them on its lock screen: --discreet leaves the names out")
    rec("NEXT", "present that file to the person (attach or link it); if this environment cannot show files, say so in one line")


# ---- refill

def run_down(doses, amount, first, now, after=None):
    """Walk the schedule from the day 'first' with 'amount' in hand.

    Doses at or before 'after' are not counted (they came out of an earlier pack). Returns a dict:
    out (the first dose the pack cannot cover), last (the last it covers), spare (what is left over then),
    used and count (taken up to 'now'), left (in hand at 'now'). Raises if the pack outlasts ten years."""
    left, last = Fraction(amount), None
    state = {"used": Fraction(0), "count": 0, "left": Fraction(amount)}
    for when, units in walk(doses, first):
        if after is not None and when <= after:
            continue
        if units > left:
            state.update(out=when, last=last, spare=left)
            return state
        left -= units
        last = when
        if when <= now:
            state["used"] += units
            state["count"] += 1
            state["left"] = left
    die("by this schedule the pack lasts more than ten years: check the pack size and the dose")


def _refill_one(med, now, lead, counted=None):
    """Print the sum for one medicine. Returns the reminder event's (day, summary, text), or None."""
    rec("REFILL", med["name"])
    for dose in med["doses"]:
        more(dose.words())
        if dose.every and not dose.anchor:
            die("an 'every N days' dose needs its first day for this sum: write it as 'every %d days from YYYY-MM-DD HH:MM'"
                % dose.every)
    if counted is not None:
        rec("LEFT", "%s [counted by the person, as of %s]" % (show_amount(counted), core.fmt_moment(now)))
        state = run_down(med["doses"], counted, now.date(), now, after=now)
    else:
        if med["pack"] is None or med["opened"] is None:
            rec("LEFT OUT", "no pack size or opening date: ask (the box says how many, the person knows when it was opened)")
            return None
        if not 0 < med["pack"] <= MAX_PACK:
            die("the pack size must be more than zero, and at most %d" % MAX_PACK)
        if med["opened"] > now.date():
            die("the pack's opening date is in the future")
        rec("PACK", "%s, opened %s" % (show_amount(med["pack"]), core.fmt_day(med["opened"])))
        state = run_down(med["doses"], med["pack"], med["opened"], now)
        if state["out"] <= now:
            rec("RAN OUT", "by this schedule the pack could not cover the dose of %s [derived]" % core.fmt_moment(state["out"]))
            more("so doses were missed, a new pack was opened, or a figure is off. Ask which: do not guess")
            return None
        rec("USED", "%s in %s up to now [derived: every scheduled dose counted as taken, the opening day included]" % (
            show_amount(state["used"]), core.plural(state["count"], "dose")))
        rec("LEFT", "%s [derived]" % show_amount(state["left"]))
    if state["last"] is None:
        rec("RUNS OUT", "now: what is left does not cover the next dose, at %s [derived]" % core.fmt_moment(state["out"]))
    else:
        rec("LAST DOSE", "%s is the last this pack covers [derived]" % core.fmt_moment(state["last"]))
        days = (state["out"].date() - now.date()).days
        rec("RUNS OUT", "%s, the first dose it cannot cover; %s [derived]" % (
            core.fmt_moment(state["out"]), "today" if days == 0 else "%s from today" % core.plural(days, "day")))
    if state["spare"] > 0:
        more("%s will be left over, less than that dose needs" % show_amount(state["spare"]))
    remind = state["out"].date() - timedelta(days=lead)
    if remind <= now.date():
        rec("REMIND", "now: the pack runs out inside the %d-day lead" % lead)
        remind = now.date()
    else:
        rec("REMIND", "%s, %s before it runs out" % (core.fmt_day(remind), core.plural(lead, "day")))
    rec("NOTE", "arithmetic on the schedule as given. It knows nothing of missed or extra doses: count the pack when it matters")
    text = "By the schedule as given, this pack's first uncovered dose is on %s. Arithmetic only: count the pack." % (
        state["out"].date().isoformat())
    return remind, med["name"], text


def cmd_refill(a):
    now = core.a_moment(a.now, "--now", core.today()) if a.now else core.now()
    if not 0 <= a.lead <= 90:
        die("--lead is days of warning before the pack runs out: 0 to 90")
    meds, left_out = _gather(a)
    if a.name:
        want = fold(a.name)
        meds = [m for m in meds if want in fold(m["name"])]
        left_out = [n for n in left_out if want in fold(n)]
    counted = None
    if a.left is not None or a.pack is not None or a.opened:
        if len(meds) != 1:
            die("--pack, --opened and --left describe one pack: give one medicine (--med, or --name to pick one on file)")
        if a.left is not None:
            if a.pack is not None or a.opened:
                die("give --left (counted today), or --pack with --opened: not both")
            counted = fraction_of(a.left, "--left")
            if counted > MAX_PACK:
                die("--left is at most %d" % MAX_PACK)
        else:
            if a.pack is None or not a.opened:
                die("--pack and --opened go together: how many were in the pack, and the day it was opened")
            meds[0]["pack"] = fraction_of(a.pack, "--pack")
            meds[0]["opened"] = core.a_date(a.opened, "--opened", now.date())
    if not meds and not left_out:
        die("no medicine was given: --med \"Name 10 mg: 08:00, 20:00\" with --pack and --opened, or --id for the ones on file")
    rec("CLOCK", "%s [%s]" % (core.fmt_moment(now), "as given with --now" if a.now else
                              "this machine's clock: pass --now if the person's local time differs"))
    reminders = []
    for med in meds:
        got = _refill_one(med, now, a.lead, counted)
        if got:
            reminders.append(got)
    for name in left_out:
        rec("LEFT OUT", "%s: no dose times on file, so there is nothing to count" % name)
    if not a.ics:
        return
    if not reminders:
        die("there is no refill day to put in a calendar")
    events = []
    for n, (day, name, text) in enumerate(reminders, 1):
        if a.discreet:
            events.append(ical.event("Refill reminder %d" % n, day, alarm=timedelta(0)))
        else:
            events.append(ical.event("Refill: %s" % name, day, description=text, alarm=timedelta(0)))
    ical.deliver(a.ics, events, "refill-%s" % now.date().isoformat())
    rec("NEXT", "present that file to the person (attach or link it); if this environment cannot show files, say so in one line")


def _file_options(p, what):
    p.add_argument("--id", help="take %s from this profile in the personal file, once its gate is open" % what)


def register(sub):
    p = command(sub, "medicines", "schedule", cmd_schedule,
                "a medicine schedule as given, read back, and written as a calendar file with --ics",
                ['schedule --med "Metformin 500 mg: 08:00, 20:00"',
                 'schedule --med "Amoxicillin 500 mg: 07:00, 15:00, 23:00" --from 2026-11-16 --days 7',
                 'schedule --med "Methotrexate 2.5 mg: mon 08:00 x6" --med "Folic acid 5 mg: wed 08:00"',
                 'schedule --med "Patch: every 3 days from 2026-11-14 09:00" --discreet'])
    p.add_argument("--med", action="append", metavar='"Name: DOSE, DOSE"',
                   help="a medicine and its doses, as prescribed or as the label says. " + ENTRY_HELP)
    _file_options(p, "the medicines")
    p.add_argument("--supplements", action="store_true", help="with --id: the supplements on file as well")
    p.add_argument("--from", dest="start", help="the first day (default today)")
    p.add_argument("--until", help="the last day, for a course that ends")
    p.add_argument("--days", type=int, help="or the length of the course in days, the first day included")
    p.add_argument("--alarm", type=int, default=0, metavar="MIN", help="minutes of warning before each dose (default 0: on the dot)")
    p.add_argument("--no-alarm", action="store_true", help="no alarm on the entries")
    p.add_argument("--discreet", action="store_true", help="leave the medicine names out of the calendar entries")
    ical.add_option(p, "the schedule")

    p = command(sub, "medicines", "refill", cmd_refill,
                "how much of a pack is left by its schedule, the dose it runs out on, and the day to renew it",
                ['refill --med "Metformin 500 mg: 08:00, 20:00" --pack 60 --opened 2026-11-01',
                 'refill --med "Levothyroxine 50 mcg: 07:00" --left 12 --lead 10',
                 'refill --med "Methotrexate 2.5 mg: mon 08:00 x6" --pack 24 --opened 2026-11-02 --now "2026-11-15 21:00"'])
    p.add_argument("--med", action="append", metavar='"Name: DOSE, DOSE"', help="the medicine and its doses. " + ENTRY_HELP)
    _file_options(p, "the medicines and their packs")
    p.add_argument("--name", help="with --id: only the medicine whose name holds this")
    p.add_argument("--pack", help="how many were in the pack when it was opened")
    p.add_argument("--opened", help="the day the pack was opened, YYYY-MM-DD")
    p.add_argument("--left", help="or how many are left, counted by the person just now")
    p.add_argument("--now", help="the person's local date and time, 'YYYY-MM-DD HH:MM' (default: this machine's clock)")
    p.add_argument("--lead", type=int, default=7, metavar="DAYS", help="days of warning before the pack runs out (default 7)")
    p.add_argument("--discreet", action="store_true", help="leave the medicine names out of the calendar entry")
    ical.add_option(p, "the refill days")
