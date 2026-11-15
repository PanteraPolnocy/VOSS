"""Calendar files (iCalendar, RFC 5545) for medicine times and refill days.

A dose time is written as a floating local time, with no zone: 08:00 is 08:00 wherever the phone is and
whatever the clocks did last night, which is what "take it at eight" means. An all-day entry (a refill
day) carries a date and no time. Plain text, no network.
"""
import hashlib
import os
from datetime import date, datetime, timedelta, timezone

from .core import die, more, out_folder, rec, unfit

PRODID = "-//VOSS-01//Project Asclepius toolkit//EN"
LINE_OCTETS = 75


def _esc(text):
    """Escape a text value: backslash, semicolon, comma and line breaks."""
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def fold_line(line):
    """Fold one content line at 75 octets, never inside a character. Returns the physical lines."""
    if len(line.encode("utf-8")) <= LINE_OCTETS:
        return [line]
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > LINE_OCTETS:
            out.append(cur)
            cur, size = " " + ch, 1 + n
        else:
            cur += ch
            size += n
    out.append(cur)
    return out


def _is_day(value):
    return isinstance(value, date) and not isinstance(value, datetime)


def _trigger(before):
    """A timedelta before the start as an iCalendar duration: PT0M (on the dot), -PT30M, -PT2H, -P7D."""
    secs = int(round(before.total_seconds()))
    if secs < 0:
        die("an alarm rings before its entry, or on it: never after")
    if secs == 0:
        return "PT0M"
    if secs % 86400 == 0:
        return "-P%dD" % (secs // 86400)
    if secs % 3600 == 0:
        return "-PT%dH" % (secs // 3600)
    return "-PT%dM" % max(1, int(round(secs / 60.0)))


def event(summary, start, rule=None, description="", alarm=None):
    """One calendar entry. start is a plain local datetime (a moment that repeats by the rule, if one is given)
    or a date (all day). alarm is a timedelta before the start, zero for on the dot, or None for no alarm."""
    if not _is_day(start):
        if not isinstance(start, datetime):
            die("a calendar entry starts on a date or at a time")
        if start.tzinfo is not None:
            die("dose times are written without a zone: pass a plain local time")
    if rule and _is_day(start):
        die("an all-day entry does not repeat here")
    return {"summary": str(summary), "start": start, "rule": rule, "description": str(description or ""), "alarm": alarm}


def _sort_key(ev):
    s = ev["start"]
    return (datetime(s.year, s.month, s.day) if _is_day(s) else s, ev["summary"])


def build(events, stamp=None):
    """The text of a calendar file holding these entries, lines folded and ended as the format requires.
    stamp is the moment the file was made, in UTC; it defaults to now."""
    stamp = stamp or datetime.now(timezone.utc)
    stamp_text = stamp.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:" + PRODID, "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    seen = {}
    for ev in sorted(events, key=_sort_key):
        start = ev["start"]
        if _is_day(start):
            when = ["DTSTART;VALUE=DATE:" + start.strftime("%Y%m%d"),
                    "DTEND;VALUE=DATE:" + (start + timedelta(days=1)).strftime("%Y%m%d")]
            key = start.isoformat()
        else:
            when = ["DTSTART:" + start.strftime("%Y%m%dT%H%M%S")]
            key = start.strftime("%Y%m%dT%H%M")
        base = "%s|%s|%s" % (ev["summary"], key, ev["rule"] or "")
        seen[base] = seen.get(base, 0) + 1
        uid = hashlib.sha1(("%s|%d" % (base, seen[base])).encode("utf-8")).hexdigest()[:24]
        lines += ["BEGIN:VEVENT", "UID:%s@voss-01" % uid, "DTSTAMP:" + stamp_text] + when
        if ev["rule"]:
            lines.append("RRULE:" + ev["rule"])
        lines.append("SUMMARY:" + _esc(ev["summary"]))
        if ev["description"]:
            lines.append("DESCRIPTION:" + _esc(ev["description"]))
        if ev["alarm"] is not None:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc(ev["summary"]),
                      "TRIGGER:" + _trigger(ev["alarm"]), "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    physical = []
    for line in lines:
        physical.extend(fold_line(line))
    return "\r\n".join(physical) + "\r\n"


def add_option(p, what):
    p.add_argument("--ics", metavar="WHERE",
                   help="write %s as a calendar file: 'auto' (the outputs folder if there is one; else the current folder, "
                        "or the Downloads folder where that one is a git working tree), a folder, or a name ending .ics" % what)


def deliver(where, events, stem, stamp=None):
    """Write the calendar file and say where it is. Returns the path."""
    if not events:
        die("there is nothing to put in a calendar")
    if where.lower().endswith(".ics"):
        path = where
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            die("no such folder for the calendar file: %s" % folder)
    else:
        folder = out_folder(where)
        if not folder and where.lower() == "auto":
            die("nowhere fit for the calendar file was found: every folder tried is a git working tree or part of the "
                "skill. Give --ics a folder outside them")
        if not folder:
            die("no such folder for the calendar file: %s (use 'auto', a folder, or a name ending .ics)" % where)
        path = os.path.join(folder, "voss-%s.ics" % stem)
    # medicine names are health information: the same two places are refused as for a personal file
    why = unfit(folder)
    if why:
        die("that folder is %s. Give --ics a folder outside it" % why)
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(build(events, stamp))
    except OSError as e:
        die("could not write the calendar file %s: %s" % (path, e.strerror or e))
    rec("CALENDAR", path)
    more("%s; anyone who can see that calendar can read what is in it" % ("1 entry" if len(events) == 1 else "%d entries" % len(events)))
    return path
