"""Pages made from a personal file, for somebody else to read.

card      a medical ID: a page to print, and plain text for the emergency screen of a phone.
passport  a full summary for a new doctor, or a doctor abroad.
brief     one page for a visit: the symptom diary, the medicines, and the questions the person wants answered.
staykit   before a planned stay in hospital: what to pack, what to ask, what to bring.
timetable the medicine schedule on file as a page to print, for the fridge or for a carer.
note      a note of a conversation for the person to keep: what was said, what to do, what to watch for.

The person chooses every line. A command first lists what could go on the page; then, with the lines they
chose, it prints the page as it would be written; and only with --write does it write a file. What is on a
page is what the person told Voss, in their own words. The headings are in English; for a reader of another
language Voss gives each heading in that language too, and the two stand side by side.

A page is health information. It is never written into a git working tree or into the skill's own folder,
and anyone who is handed the page, or sees the phone's lock screen, can read it.
"""
import hashlib
import html
import os

from . import core, personal, record
from .core import command, die, more, rec

# the headings of a page. The entries under them are the person's own words, as they stand in the file
HEADINGS = {
    "card": "Medical ID",
    "passport": "Health passport",
    "brief": "For the doctor",
    "name": "Name",
    "born": "Date of birth",
    "blood": "Blood type",
    "languages": "Languages",
    "allergies": "Allergies",
    "intolerances": "Intolerances",
    "medicines": "Medicines",
    "supplements": "Supplements",
    "conditions": "Conditions",
    "procedures": "Operations and hospital stays",
    "vaccinations": "Vaccinations",
    "devices": "Implants and devices",
    "aids": "Glasses and hearing aids",
    "pregnancy": "Pregnancy",
    "contact": "Emergency contact",
    "doctor": "Own doctor",
    "wishes": "Care wishes",
    "needs": "How to talk with me",
    "diary": "Symptom diary",
    "questions": "Questions for the doctor",
}
FOOT = "In the person's own words, as told on the dates on file. Not a medical record."
TITLE = "title"
# what may go on each page, in the order it is printed
PAGES = {
    "card": ("name", "born", "blood", "allergies", "medicines", "conditions", "devices", "pregnancy", "contact", "wishes", "needs"),
    "passport": ("name", "born", "blood", "languages", "allergies", "intolerances", "medicines", "supplements", "conditions", "procedures",
                 "vaccinations", "devices", "aids", "contact", "doctor", "wishes", "needs"),
    "brief": ("name", "born", "diary", "medicines", "supplements", "allergies", "conditions", "procedures", "questions"),
}
WARNING = ("anyone who is handed this page, or sees it on a lock screen, can read it. Say so once, and let the person "
           "choose each line")


def _medicine(row):
    return " ".join(str(row.get(k) or "").strip() for k in ("name", "strength") if str(row.get(k) or "").strip()) + (
        ": %s" % row["how_taken"] if row.get("how_taken") else "")


def _entries(entry, key, a, today):
    """The lines one part of a page would hold, from what is on file; [] where there is nothing."""
    def rows(name):
        return [r for r in personal.rows(entry, name) if isinstance(r, dict)]

    def text(name):
        value = entry.get(name)
        return [str(value)] if isinstance(value, str) and value.strip() and value != personal.DECLINED else []
    if key == "name":
        return text("call_me")
    if key == "born":
        born = entry.get("date_of_birth")
        return ["%s (%s)" % (born, record.age_words(born, today).split(" [")[0])] if born and born != personal.DECLINED else []
    if key == "blood":
        block = entry.get("blood_type")
        return [str(block["value"])] if isinstance(block, dict) and block.get("value") else []
    if key == "languages":
        block = entry.get("languages") if isinstance(entry.get("languages"), dict) else {}
        said = [str(block["talk"])] if block.get("talk") else []
        return said + ["documents: %s" % ", ".join(block["documents"])] if block.get("documents") else said
    if key == "allergies":
        return ["%s%s" % (r.get("substance") or "", ": %s" % r["reaction"] if r.get("reaction") else "") for r in rows("allergies")]
    if key == "intolerances":
        return ["%s%s" % (r.get("substance") or "", ": %s" % r["what_happens"] if r.get("what_happens") else "") for r in rows("intolerances")]
    if key in ("medicines", "supplements"):
        return [_medicine(r) for r in rows(key) if r.get("name")]
    if key == "conditions":
        return [str(r.get("in_their_words")) for r in rows("conditions") if r.get("in_their_words")]
    if key == "procedures":
        return ["%s%s" % (r.get("what") or "", " (%s)" % r["year"] if r.get("year") else "") for r in rows("past_procedures")]
    if key == "vaccinations":
        return ["%s%s" % (r.get("name") or "", " (%s)" % r["date"] if r.get("date") else "") for r in rows("vaccinations")]
    if key == "devices":
        return ["%s%s" % (r.get("what") or "", " (since %s)" % r["since"] if r.get("since") else "") for r in rows("implants_devices")]
    if key == "aids":
        value = entry.get("sensory_aids")
        return [str(x) for x in value if str(x).strip()] if isinstance(value, list) else []
    if key == "pregnancy":
        block = entry.get("pregnancy")
        return ["%s (recorded %s)" % (block["status"], block.get("recorded") or "no date")] if isinstance(block, dict) and block.get("status") else []
    if key == "contact":
        block = (entry.get("care_contacts") or {}).get("emergency_contact") if isinstance(entry.get("care_contacts"), dict) else None
        if not isinstance(block, dict) or personal.blankish(block):
            return []
        return [", ".join(str(block[k]) for k in ("name", "relation", "phone") if block.get(k))]
    if key == "doctor":
        block = entry.get("care_contacts") if isinstance(entry.get("care_contacts"), dict) else {}
        return [str(block["doctor"])] if block.get("doctor") else []
    if key == "wishes":
        return text("care_wishes")
    if key == "needs":
        return text("communication_needs")
    if key == "diary":
        since = core.a_date(a.since, "--since", today).isoformat() if getattr(a, "since", None) else ""
        out = []
        for r in rows("symptom_diary"):
            if str(r.get("date") or "") >= since:
                out.append("%s  %s%s%s%s" % (
                    r.get("date") or "", r.get("what") or "",
                    "; %s/10" % (int(r["severity"]) if r["severity"] == int(r["severity"]) else r["severity"]) if r.get("severity") is not None else "",
                    "; helped: %s" % r["helped"] if r.get("helped") else "", "; %s" % r["notes"] if r.get("notes") else ""))
        return out
    if key == "questions":
        return [core.one_line(q, "--question", 400) for q in (getattr(a, "question", None) or [])]
    return []


def _second(kind, given, foot):
    """The headings Voss gave in a second language, as {key: text}, with the page's title under 'title' and the
    last line under 'foot'. The tool cannot check a translation: it prints what it is given, beside the English."""
    allowed = (TITLE,) + PAGES[kind]
    out = {}
    for item in given or []:
        key, mark, words = str(item).partition("=")
        key = key.strip().lower()
        if not mark or key not in allowed:
            die("--heading is KEY=TEXT, the heading in the reader's language, where KEY is one of: %s" % ", ".join(allowed))
        out[key] = core.one_line(words, "--heading", 80)
    if foot:
        out["foot"] = core.one_line(foot, "--foot", 200)
    return out


def _heading(key, second):
    return "%s / %s" % (HEADINGS[key], second[key]) if key in second else HEADINGS[key]


def _page(kind, entry, chosen, second, a, today):
    """The page as (title, [(heading, [lines])], foot)."""
    parts = []
    for key in PAGES[kind]:
        if key in chosen:
            lines = _entries(entry, key, a, today)
            if lines:
                parts.append((_heading(key, second), lines))
    title = "%s / %s" % (HEADINGS[kind], second[TITLE]) if TITLE in second else HEADINGS[kind]
    foot = "%s %s" % (FOOT, second["foot"]) if "foot" in second else FOOT
    return title, parts, "%s %s" % (foot, today.isoformat())


def _as_text(title, parts, foot):
    out = [title.upper(), ""]
    for heading, lines in parts:
        out.append("%s:" % heading)
        out += ["  %s" % line for line in lines]
        out.append("")
    return "\n".join(out + [foot]) + "\n"


def _as_html(title, parts, foot):
    body = "".join("<h2>%s</h2><ul>%s</ul>" % (html.escape(heading), "".join("<li>%s</li>" % html.escape(line) for line in lines))
                   for heading, lines in parts)
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>%s</title>\n"
            "<style>body{font-family:sans-serif;max-width:40em;margin:2em auto;line-height:1.4}h1{font-size:1.5em;"
            "border-bottom:2px solid #000}h2{font-size:1.05em;margin:1em 0 .2em}ul{margin:0;padding-left:1.2em}"
            "footer{margin-top:2em;font-size:.8em;color:#444}@media print{body{margin:1em}}</style></head>\n"
            "<body><h1>%s</h1>%s<footer>%s</footer></body></html>\n" % (html.escape(title), html.escape(title), body, html.escape(foot)))


def _write(kind, pid, files, where):
    folder = core.out_folder(where or "auto")
    if not folder:
        die("nowhere fit to write the page was found: every folder tried is a git working tree or part of the skill. "
            "Give --out a folder outside them" if (where or "auto").lower() == "auto" else "no such folder to write into")
    why = core.unfit(folder)
    if why:
        die("that folder is %s. Give --out a folder outside it" % why)
    for ending, text in files:
        path = os.path.join(folder, "voss-%s-%s.%s" % (kind, pid, ending))
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError as e:
            die("could not write %s: %s" % (path, e.strerror or e))
        rec("WRITTEN", path)
    rec("PRIVATE", "it holds health information. It goes to the person, and where it goes after that is theirs to decide")
    rec("NEXT", "present the file to the person (attach or link it); if this environment cannot show files, say so in one line")


def _make(kind, a):
    data = personal.need()
    who, entry = personal.pick(data, a.id)
    today = core.today()
    second = _second(kind, a.heading, a.foot)
    possible = PAGES[kind]
    have = dict((key, _entries(entry, key, a, today)) for key in possible)
    if not a.lines and not a.all:
        rec(kind.upper(), "%s: what could go on the page. The person chooses each line" % entry["id"])
        for key in possible:
            if key == "questions":
                more("questions: theirs to give, each with --question \"...\"")
            elif have[key]:
                more("%s: %s on file (%s)" % (key, core.plural(len(have[key]), "entry", "entries"), HEADINGS[key]))
        empty = [key for key in possible if key != "questions" and not have[key]]
        if empty:
            more("nothing on file for: %s" % ", ".join(empty))
        rec("HEADINGS", "in English. For a reader of another language, give each heading in it as well: --heading KEY=TEXT, "
                        "and the page's title as --heading title=TEXT. The two stand side by side, and the entries stay in "
                        "the person's own words")
        rec("RULE", WARNING)
        rec("NEXT", "ask which lines they want, then: %s --id %s --lines %s" % (
            kind, entry["id"], ",".join(k for k in possible if have[k] or k == "questions") or "..."))
        return
    chosen = list(possible) if a.all else [k.strip().lower() for k in a.lines.split(",") if k.strip()]
    for key in chosen:
        if key not in possible:
            die("--lines names what goes on the page, from: %s" % ", ".join(possible))
    title, parts, foot = _page(kind, entry, chosen, second, a, today)
    if not parts:
        die("nothing is on file for the lines that were chosen, so there is no page to make")
    text = _as_text(title, parts, foot)
    missing = [key for key in chosen if not have[key]]
    # a code for exactly this page, so that what is written is what was read back
    code = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    if not a.write:
        rec("READ BACK", "the %s for %s, as it would be written. Nothing is written yet" % (kind, entry["id"]))
        print(text, end="")
        if missing:
            rec("LEFT OUT", "nothing on file for: %s" % ", ".join(missing))
        rec("CONFIRM", code)
        if second:
            rec("HEADINGS", "the second language is your translation, and no tool has checked it: read those headings back too")
        rec("RULE", WARNING)
        rec("NEXT", "read it back. If they agree with every line, run this again with --write --confirm %s" % code)
        return
    if (a.confirm or "").strip().lower() != code:
        die("nothing is written without the read-back: run this without --write, read the page back to the person, and give "
            "the code it prints as --confirm. A different page, or a different day, gives a different code")
    files = [("txt", text)]
    if kind != "brief" or a.html:
        files.append(("html", _as_html(title, parts, foot)))
    _write(kind, entry["id"], files, a.out)
    if kind == "card":
        more("the text file is laid out for a phone's medical ID or emergency screen: it is typed or pasted in there by "
             "the person, and the phone then shows it without being unlocked")


def cmd_card(a):
    _make("card", a)


def cmd_passport(a):
    _make("passport", a)


def cmd_brief(a):
    _make("brief", a)


def cmd_staykit(a):
    data = core.load_data("stay")
    today = core.today()
    entry = None
    if a.id:
        who, entry = personal.pick(personal.need(), a.id)
    elif personal.load() is not None:
        # with no name given, the page is made personal only where there is no doubt whose it is
        own = [e for k, e in personal.entries(personal.load()) if k == "profile"]
        entry = own[0] if len(own) == 1 else None
    rec("STAY", "before a planned stay in hospital%s" % (", for %s" % entry["id"] if entry else ""))
    for heading, key in (("PACK", "pack"), ("ASK", "ask"), ("BRING", "bring")):
        rec(heading, data[key + "_note"])
        for line in data[key]:
            more("- " + line)
    if entry:
        aids = [str(x) for x in entry.get("sensory_aids") or [] if str(x).strip()] if isinstance(entry.get("sensory_aids"), list) else []
        if aids:
            rec("THEIRS", "on file, and easy to leave behind: %s" % ", ".join(aids))
        coming = [r for r in personal.rows(entry, "appointments") if isinstance(r, dict) and (core.parse_date(str(r.get("when") or "")[:10]) or today) >= today]
        for row in coming[:2]:
            more("on file: %s%s" % (row.get("when"), ", %s" % row["with"] if row.get("with") else ""))
        rec("PAPERS", "'passport --id %s' writes the summary to hand over, and 'profile --id %s --section medicines' reads out "
                      "the medicine list" % (entry["id"], entry["id"]))
    rec("RIGHTS", "nothing on file about a patient's rights in any country: look them up for where the hospital is, in its law "
                  "or on its ombudsman's pages, and cite them")
    rec("RULE", data["rule"])


# ---- a timetable of medicines

TIMETABLE_FOOT = ("The schedule as it is on file: what was prescribed, or what the label says. This page repeats it and sets "
                  "nothing. A change comes from the prescriber or the pharmacist. Not a medical record.")


def _read_back(kind, pid, text, left_out, rule, a, files):
    """The page read back with its code, or, with the code, written. One way for every page."""
    code = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    if not a.write:
        rec("READ BACK", "the %s%s, as it would be written. Nothing is written yet" % (kind, " for %s" % pid if pid else ""))
        print(text, end="")
        for line in left_out:
            rec("LEFT OUT", line)
        rec("CONFIRM", code)
        rec("RULE", rule)
        rec("NEXT", "read it back. If they agree with every line, run this again with --write --confirm %s" % code)
        return
    if (a.confirm or "").strip().lower() != code:
        die("nothing is written without the read-back: run this without --write, read the page back to the person, and give "
            "the code it prints as --confirm. A different page, or a different day, gives a different code")
    _write(kind, pid or core.today().isoformat(), files, a.out)


def cmd_timetable(a):
    from . import doses
    who, entry = personal.pick(personal.need(), a.id)
    today = core.today()
    meds, no_times = doses.from_file(entry, supplements=a.supplements)
    if not meds:
        die("no medicine on file has dose times, so there is no timetable to make. Times go into the file with 'intake', as "
            "the schedule of a medicine")
    slots = {}
    for med in meds:
        for dose in med["doses"]:
            # "08:00 every day, 2 each time" without its clock, which is the heading it stands under
            line = "%s: %s%s" % (med["name"], dose.words().split(" ", 1)[1], "; %s" % med["how"] if med["how"] else "")
            slots.setdefault((dose.hour, dose.minute), []).append(line)
    parts = [("At %02d:%02d" % key, sorted(slots[key], key=lambda s: s.lower())) for key in sorted(slots)]
    if a.needed and no_times:
        parts.append(("No set time", sorted(no_times, key=lambda s: s.lower())))
    name = entry.get("call_me") if a.name and isinstance(entry.get("call_me"), str) and entry.get("call_me").strip() else ""
    title = "Medicine timetable%s" % (": %s" % name if name else "")
    foot = "%s %s" % (TIMETABLE_FOOT, today.isoformat())
    text = _as_text(title, parts, foot)
    left_out = ["no dose times on file, so not on the page: %s. --needed lists them under \"No set time\"" % "; ".join(no_times)] \
        if no_times and not a.needed else []
    _read_back("timetable", entry["id"], text, left_out,
               "anyone who sees this page can read which medicines the person takes: where it hangs is theirs to decide. It "
               "repeats the schedule on file and never sets one", a,
               [("txt", text), ("html", _as_html(title, parts, foot))])


# ---- a note of a conversation

NOTE_FOOT = ("Written by Voss, a reference with a bedside manner, from what was said in the conversation. He cannot examine "
             "anyone and can be wrong: a real doctor outranks this note. Not a medical record.")


def _own_lines(values, what):
    """Lines of Voss's own for a page: each on one line, and none a phrase he never says."""
    from . import forms
    out = []
    for value in values or []:
        line = core.one_line(value, what, 400)
        if any(phrase in line.lower() for phrase in forms.NEVER):
            die("%s says something Voss never says. Name what it could be and what would settle it, or say you cannot tell" % what)
        out.append(line)
    return out


def cmd_note(a):
    today = core.today()
    if not (a.about or "").strip():
        die("say what the conversation was about: --about \"...\"")
    said = _own_lines(a.said, "--said")
    if not said:
        die("a note says what was said: --said \"...\", once for each point, in plain words")
    todo = []
    for item in a.todo or []:
        what, _, when = str(item).partition("|")
        what, when = core.one_line(what, "--todo", 300), when.strip()
        if when and not personal.when_text(when):
            die("--todo: the part after | is when it is due: a date, with or without a time (2026-12-01, or '2026-12-01 10:30')")
        todo.append("%s%s" % (what, " - by %s" % personal.when_text(when) if when else ""))
    parts = [("About", _own_lines([a.about], "--about")), ("What was said", said)]
    for heading, lines in (("To do", todo), ("Watch for, and get help sooner if", _own_lines(a.watch, "--watch")),
                           ("To ask the doctor", _own_lines(a.ask, "--ask")), ("Sources named", _own_lines(a.source, "--source"))):
        if lines:
            parts.append((heading, lines))
    title = "Note of a conversation with Voss%s" % (": %s" % core.one_line(a.name, "--name", 60) if (a.name or "").strip() else "")
    foot = "%s %s" % (NOTE_FOOT, today.isoformat())
    text = _as_text(title, parts, foot)
    files = [("txt", text)] + ([("html", _as_html(title, parts, foot))] if a.html else [])
    _read_back("note", "", text, [],
               "the note is the person's to keep, and it is not kept by you: nothing of it goes into a personal file unless they "
               "ask for a part of it to. It holds what was said and no more: no diagnosis, no dose, nothing new", a, files)


def _page_options(p):
    p.add_argument("--id", help="whose page (default: the only profile on file)")
    p.add_argument("--lines", metavar="KEY,KEY", help="the lines the person chose, by the names the first run lists")
    p.add_argument("--all", action="store_true", help="every line that is on file: only if the person said so")
    p.add_argument("--heading", action="append", metavar="KEY=TEXT",
                   help="a heading in the reader's language, to stand beside the English: allergies=Allergien. 'title' is the page's own")
    p.add_argument("--foot", metavar="TEXT", help="the page's last line in that language, to follow the English")
    p.add_argument("--write", action="store_true", help="write the page to a file, once it has been read back")
    p.add_argument("--confirm", metavar="CODE", help="with --write: the code the read-back printed")
    p.add_argument("--out", help="where to write: 'auto' (default) or a folder outside any git repository")


def register(sub):
    p = command(sub, "file", "card", cmd_card,
                "a medical ID from the personal file, line by line as the person chooses: a page to print, and text for a phone",
                ["card --id self", "card --id self --lines name,allergies,medicines,contact --heading allergies=Allergien "
                 "--heading medicines=Medikamente --heading title=Notfallausweis"])
    _page_options(p)

    p = command(sub, "file", "passport", cmd_passport,
                "a health summary for a new doctor or one abroad, from the personal file, line by line as the person chooses",
                ["passport --id self", "passport --id self --all"])
    _page_options(p)

    p = command(sub, "clinic", "brief", cmd_brief,
                "one page for a visit: the symptom diary, the medicines, what the person chose, and their questions for the doctor",
                ["brief --id self", 'brief --id self --lines diary,medicines,allergies,questions --question "Could the tablets be the cause?"'])
    _page_options(p)
    p.add_argument("--since", help="the diary from this day on")
    p.add_argument("--question", action="append", metavar="TEXT", help="a question the person wants answered; give it once for each")
    p.add_argument("--html", action="store_true", help="with --write: a page to print as well as the text")

    p = command(sub, "clinic", "staykit", cmd_staykit,
                "before a planned stay in hospital: what to pack, what to ask the ward and what to bring",
                ["staykit", "staykit --id self"])
    p.add_argument("--id", help="whose stay (default: the only profile on file, if there is a file)")

    p = command(sub, "medicines", "timetable", cmd_timetable,
                "the medicine schedule on file as one page to print, for the fridge or for a carer; read back before it is written",
                ["timetable --id self", "timetable --id self --needed --name"])
    p.add_argument("--id", help="whose timetable (default: the only profile on file)")
    p.add_argument("--needed", action="store_true", help="also list the medicines that have no set time, under their own heading")
    p.add_argument("--supplements", action="store_true", help="the supplements on file as well")
    p.add_argument("--name", action="store_true", help="put the person's name on the page: only if they say so")
    p.add_argument("--write", action="store_true", help="write the page to a file, once it has been read back")
    p.add_argument("--confirm", metavar="CODE", help="with --write: the code the read-back printed")
    p.add_argument("--out", help="where to write: 'auto' (default) or a folder outside any git repository")

    p = command(sub, "clinic", "note", cmd_note,
                "a note of a conversation for the person to keep: what was said, what to do, what to watch for; read back first",
                ['note --about "a headache for three days" --said "Triage put it at level 3: your own doctor, within days." '
                 '--said "Three possible explanations were named, and none of them is a diagnosis." '
                 '--todo "ring the surgery for an appointment | 2026-11-17" --watch "a sudden, severe headache: that is an emergency"'])
    p.add_argument("--about", help="what the conversation was about, in a line")
    p.add_argument("--said", action="append", metavar="TEXT", help="a point that was made, in plain words; give it once for each")
    p.add_argument("--todo", action="append", metavar="TEXT", help="a thing to do, and when: \"what | 2026-12-01\"")
    p.add_argument("--watch", action="append", metavar="TEXT", help="what to watch for, and when to get help sooner")
    p.add_argument("--ask", action="append", metavar="TEXT", help="a question to take to the doctor")
    p.add_argument("--source", action="append", metavar="TEXT", help="a source that was named, with its date")
    p.add_argument("--name", help="the person's name for the top of the page: only if they say so")
    p.add_argument("--html", action="store_true", help="with --write: a page to print as well as the text")
    p.add_argument("--write", action="store_true", help="write the note to a file, once it has been read back")
    p.add_argument("--confirm", metavar="CODE", help="with --write: the code the read-back printed")
    p.add_argument("--out", help="where to write: 'auto' (default) or a folder outside any git repository")
