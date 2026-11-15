"""Reminders: how a weekly round, a seasonal check or a check-in finds its way back to the person.

Nothing in this toolkit runs by itself. A round happens when somebody opens a conversation. So what can
remind a person has to live outside it: a calendar entry on their own phone, or, where the platform Voss
runs on has a tool for it, a scheduled task, a reminder or a message.

remind  what can be reminded of for a person, the words a reminder may carry, and, with --ics, a calendar
        file that repeats it.

A reminder is an invitation and nothing else. It is read on lock screens and in inboxes, where nobody passes
a gate, so it never names a medicine, a condition, a result or anything else from the personal file. The
tool writes the words for that reason, and they are the same for everybody.
"""
from datetime import date, datetime, timedelta

from . import core, ical, personal
from .core import command, die, more, rec

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
SEASONS = ((3, 1), (6, 1), (9, 1), (12, 1))
# what can be reminded of: the setting that switches it on, how it is named, the entry's title, and the
# words a reminder carries. Nothing in them is about anyone's health
KINDS = {
    "round": ("weekly_round", "the weekly round", "Voss: weekly round",
              "Your weekly round with Voss is due. Open a conversation and say \"weekly round\" whenever it suits you."),
    "season": ("seasonal_checks", "seasonal checks", "Voss: seasonal check",
               "A new season has begun, and Voss has a seasonal check for you. Open a conversation and say \"seasonal "
               "check\" whenever it suits you."),
    "checkin": ("wellbeing_checkin", "wellbeing check-ins", "Voss: check-in",
                "Voss would like to hear how you are. Open a conversation whenever it suits you."),
}
ORDER = ("round", "season", "checkin")
NOTE = "A reminder to talk to Voss. Nothing in this entry is about your health."


def _settings(entry):
    return entry.get("settings") if isinstance(entry.get("settings"), dict) else {}


def _on(entry, kind):
    value = _settings(entry).get(KINDS[kind][0])
    return bool(value.get("on")) if isinstance(value, dict) else bool(value)


def _wish(entry):
    """How the person said they want to be reminded: the 'reminders' part of their settings, or {}."""
    block = _settings(entry).get("reminders")
    return block if isinstance(block, dict) else {}


def wished(entry):
    """True if the file says how this person wants to be reminded."""
    return bool(str(_wish(entry).get("how") or "").strip())


def _when(text):
    """'mon 09:00' as (weekday number, hour, minute); None where the text is not that."""
    parts = str(text or "").lower().split()
    if len(parts) != 2 or parts[0][:3] not in DAYS:
        return None
    try:
        hour, minute = core.parse_clock(parts[1])
    except core.VossError:
        return None
    return DAYS.index(parts[0][:3]), hour, minute


def _period(text):
    """How often a check-in comes round, as (count, 'days' or 'months'); None where the words do not say."""
    words = " ".join(str(text or "").lower().replace("every", " ").replace("once a", "1").replace("-", " ").split())
    known = {"daily": (1, "days"), "day": (1, "days"), "weekly": (7, "days"), "week": (7, "days"), "1 week": (7, "days"),
             "fortnightly": (14, "days"), "fortnight": (14, "days"), "other week": (14, "days"), "monthly": (1, "months"),
             "month": (1, "months"), "1 month": (1, "months")}
    if words in known:
        return known[words]
    try:
        return core.period_of(words, "how often")
    except core.VossError:
        return None


def _rule(period):
    count, unit = period
    if unit == "months":
        return "FREQ=MONTHLY" + (";INTERVAL=%d" % count if count > 1 else "")
    if count % 7 == 0:
        return "FREQ=WEEKLY" + (";INTERVAL=%d" % (count // 7) if count > 7 else "")
    return "FREQ=DAILY" + (";INTERVAL=%d" % count if count > 1 else "")


def _often(period):
    count, unit = period
    if unit == "days" and count % 7 == 0:
        count, unit = count // 7, "weeks"
    return "every %s" % unit[:-1] if count == 1 else "every %d %s" % (count, unit)


def _next_weekday(today, weekday):
    """The next such weekday after today: a reminder never starts in the past, or on the day it is set."""
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def plan(entry, kinds, weekday, hour, minute, every, today):
    """[(kind, when in words, [calendar entries])] for what is to be reminded of."""
    out = []
    for kind in kinds:
        title, words = KINDS[kind][2], KINDS[kind][3]
        text = "%s %s" % (words, NOTE)
        if kind == "round":
            day = _next_weekday(today, weekday)
            start = datetime(day.year, day.month, day.day, hour, minute)
            entries = [ical.event(title, start, rule="FREQ=WEEKLY;BYDAY=%s" % BYDAY[weekday], description=text, alarm=timedelta(0))]
            when = "every %s at %02d:%02d" % (core.DAYS[weekday], hour, minute)
        elif kind == "season":
            entries = []
            for month, day in SEASONS:
                first = date(today.year, month, day)
                if first <= today:
                    first = date(today.year + 1, month, day)
                entries.append(ical.event(title, datetime(first.year, first.month, first.day, hour, minute), rule="FREQ=YEARLY",
                                          description=text, alarm=timedelta(0)))
            when = "four times a year, on the first of March, June, September and December, at %02d:%02d" % (hour, minute)
        else:
            day = core.after(today, every)
            start = datetime(day.year, day.month, day.day, hour, minute)
            entries = [ical.event(title, start, rule=_rule(every), description=text, alarm=timedelta(0))]
            when = "%s at %02d:%02d, from %s" % (_often(every), hour, minute, day.isoformat())
        out.append((kind, when, entries))
    return out


BY = ("task", "email")


def _task_words(kind, when, address):
    """What a scheduled task is told, word for word: one reminder, the words it carries, and nothing more."""
    title, words = KINDS[kind][2], KINDS[kind][3]
    if address is None:
        return "%s: post this message and nothing else: \"%s\" Open no personal file." % (when, words)
    return ("%s: send an e-mail to %s. Subject: \"%s\". Body: \"%s\" Send that and nothing else, and open no personal file. If "
            "no e-mail can be sent when this runs, say so in one line where this task reports, and do not let that line "
            "stand in for the e-mail." % (when, address, title, words))


def by(how, planned, wish, a):
    """What it takes to remind by a scheduled task or by e-mail, and the instructions to give the task."""
    address = None
    if how == "email":
        given = (a.address or "").strip() or str(wish.get("address") or "").strip()
        address = core.one_line(given, "the address", 120) if given else "the address they give for this"
        rec("EMAIL", "an e-mail arrives only if three things are true. Check each before you promise one:")
        more("1. you have a tool here that sends mail. One that only writes a draft does not send")
        more("2. there is an address: %s" % (address if given else "none is on file, so ask for one, for this and nothing else"))
        more("3. something runs on the day. A reminder that lives only in this conversation is never sent: it takes a "
             "scheduled task, and the task's own instructions have to say \"send this e-mail\"")
        more("with one of the three missing, say which, in one line, before anything is set, and offer what does work: a task "
             "that reports in the app, or the calendar file")
    rec("TASK", "what to tell a scheduled task, word for word, one task for each reminder:")
    for name, when, entries in planned:
        more(_task_words(name, when, address))
    rec("SAY FIRST", "where the reminder will turn up. A scheduled task reports as a message in the app unless its instructions "
                     "send it somewhere else, and a send that waits for the person's approval does not go out while nobody is "
                     "there. \"I will e-mail you\" is said only when all of that has been checked")
    rec("AFTER", "say what was set, as the tool confirmed it, and what could not be done. A message in the chat never stands in "
                 "for an e-mail without that being said first")


def cmd_remind(a):
    kind, entry = personal.pick(personal.need(), a.id)
    today = core.today()
    wish = _wish(entry)
    on = [k for k in ORDER if _on(entry, k)]
    if a.what:
        kinds = []
        for name in a.what.lower().split(","):
            name = name.strip()
            if name not in KINDS:
                die("--what names what to be reminded of, from: %s" % ", ".join(ORDER))
            if name not in kinds:
                kinds.append(name)
    else:
        kinds = on
    rec("REMIND", "%s: %s" % (entry["id"], "switched on in their file: %s" % ", ".join(KINDS[k][1] for k in on) if on else
                              "none of the weekly round, seasonal checks and wellbeing check-ins is switched on in their file"))
    if wish.get("how"):
        more("how they asked to be reminded, as on file: %s%s%s" % (
            wish["how"], ", %s" % wish["when"] if wish.get("when") else "",
            "; an address is on file for it" if wish.get("address") else ""))
    if not kinds:
        more("a reminder needs something to be reminded of. To switch one on: intake --id %s --set \"settings: weekly_round=yes\" "
             "(or seasonal_checks=yes, or wellbeing_checkin.on=yes; wellbeing_checkin.how_often=monthly)" % entry["id"])
        rec("ALSO", "a medicine's times and the day a pack runs out have calendar files of their own: 'schedule --ics' and "
                    "'refill --ics'; and the dates in a doctor's letter: 'decode --ics'")
        return
    stored = _when(wish.get("when"))
    weekday = DAYS.index(a.day[:3].lower()) if a.day and a.day[:3].lower() in DAYS else None
    if a.day and weekday is None:
        die("--day is a day of the week: %s" % ", ".join(DAYS))
    if weekday is None:
        weekday = stored[0] if stored else 0
    hour, minute = core.parse_clock(a.at, "--at") if a.at else (stored[1], stored[2]) if stored else (9, 0)
    every = None
    if "checkin" in kinds:
        value = _settings(entry).get("wellbeing_checkin")
        said = a.every or (value.get("how_often") if isinstance(value, dict) else "")
        every = _period(said)
        if every is None:
            die("how often the check-in comes round is not on file in a form a calendar can repeat: give --every \"2 weeks\" "
                "(a count of days, weeks or months)")
    planned = plan(entry, kinds, weekday, hour, minute, every, today)
    for name, when, entries in planned:
        rec(name.upper(), "%s%s" % (when, "" if name in on else " [not switched on in their file yet: switch it on as well, or the "
                                                              "reminder invites them to something that says it is off]"))
        more("the entry is called \"%s\"" % KINDS[name][2])
        more("the words a reminder may carry: %s" % KINDS[name][3])
    how = (a.by or "").strip().lower()
    if how and how not in BY:
        die("--by is one of: %s (a calendar file is --ics)" % ", ".join(BY))
    if how:
        by(how, planned, wish, a)
    if a.ics:
        ical.deliver(a.ics, [e for _, _, entries in planned for e in entries], "reminders-%s" % entry["id"])
        more("it repeats until the person deletes it from their calendar: say so, and that importing it twice gives each "
             "entry twice on some calendars")
    rec("WAYS", "look at the tools you have here, and offer only what one of them can really do:")
    more("1. a scheduled task or a reminder, where this platform gives you a tool that sets one. Say what will run, when, "
         "where it will report, and how to stop it, and set it only on their yes ('--by task' gives its instructions)")
    more("2. a calendar entry, where you have a tool or a card that adds one to their calendar")
    more("3. a calendar file, wherever a file can be handed over: this command with --ics auto. It works on any phone")
    more("4. a message by e-mail, only where you have a tool that sends one, to an address they gave for this, and after "
         "saying once that e-mail is not private ('--by email' says what it takes)")
    more("with none of those, say so plainly, and suggest they put it in their own calendar by hand")
    rec("RULE", "a reminder is an invitation and nothing else. It never names a medicine, a condition, a result or anything "
                "else from the personal file: it is read on lock screens and in inboxes, where nobody passes a gate. Use the "
                "words above. General information with its source may go with it; nothing about the person does")
    more("a task that runs with nobody there never opens the personal file: it delivers the invitation, and the round "
         "happens when the person answers and their gate is passed")
    more("never say that a reminder is set unless a tool has confirmed it. Offer once; a \"no\" is kept, and not asked again")
    if not wish.get("how"):
        rec("NEXT", "store what they chose, so that it is not asked twice: intake --id %s --set \"settings: reminders.how=calendar; "
                    "reminders.when=%s %02d:%02d\" (and reminders.address=... only if they want an address kept)" % (
                        entry["id"], DAYS[weekday], hour, minute))


def register(sub):
    p = command(sub, "household", "remind", cmd_remind,
                "reminders of a round, a seasonal check or a check-in: the words one may carry, and a calendar file that repeats it",
                ["remind --id self", "remind --id self --what round --day mon --at 09:00", "remind --id self --what round --by email",
                 "remind --id self --what round,season --ics auto"])
    p.add_argument("--id", help="whose reminders (default: the only profile on file)")
    p.add_argument("--what", metavar="KIND,KIND", help="what to be reminded of: %s (default: what is switched on in the file)" % ", ".join(ORDER))
    p.add_argument("--day", help="the day of the week for the weekly round: %s (default: mon, or as on file)" % ", ".join(DAYS))
    p.add_argument("--at", metavar="HH:MM", help="the time of day for a reminder (default: 09:00, or as on file)")
    p.add_argument("--every", metavar="PERIOD", help="how often the check-in comes round, where the file does not say: 2 weeks, 1 month")
    p.add_argument("--by", help="what it takes to remind this way, and the instructions to give: task (a scheduled task) or email")
    p.add_argument("--address", help="with --by email: the address they gave for this, where none is on file")
    ical.add_option(p, "the reminders")
