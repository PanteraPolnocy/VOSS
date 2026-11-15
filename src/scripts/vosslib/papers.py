"""Pages made from a personal file, for somebody else to read.

card      a medical ID: a page to print, and plain text for the emergency screen of a phone.
passport  a full summary for a new doctor, or a doctor abroad.
brief     one page for a visit: the symptom diary, the medicines, and the questions the person wants answered.
staykit   before a planned stay in hospital: what to pack, what to ask, what to bring.

The person chooses every line. A command first lists what could go on the page; then, with the lines they
chose, it prints the page as it would be written; and only with --write does it write a file. What is on a
page is what the person told Voss, in their own words: the tool translates the headings and nothing else.

A page is health information. It is never written into a git working tree or into the skill's own folder,
and anyone who is handed the page, or sees the phone's lock screen, can read it.
"""
import hashlib
import html
import os

from . import core, personal, record
from .core import command, die, more, rec

LANGS = ("en", "pl", "both")
# the headings of a page, in English and in Polish. Only headings are translated: the entries are the
# person's own words, as they stand in the file
HEADINGS = {
    "card": ("Medical ID", "Karta ratunkowa"),
    "passport": ("Health passport", "Paszport zdrowia"),
    "brief": ("For the doctor", "Dla lekarza"),
    "name": ("Name", "Imi\u0119"),
    "born": ("Date of birth", "Data urodzenia"),
    "blood": ("Blood type", "Grupa krwi"),
    "languages": ("Languages", "J\u0119zyki"),
    "allergies": ("Allergies", "Alergie"),
    "intolerances": ("Intolerances", "Nietolerancje"),
    "medicines": ("Medicines", "Leki"),
    "supplements": ("Supplements", "Suplementy"),
    "conditions": ("Conditions", "Choroby"),
    "procedures": ("Operations and hospital stays", "Operacje i pobyty w szpitalu"),
    "vaccinations": ("Vaccinations", "Szczepienia"),
    "devices": ("Implants and devices", "Implanty i urz\u0105dzenia"),
    "aids": ("Glasses and hearing aids", "Okulary i aparaty s\u0142uchowe"),
    "pregnancy": ("Pregnancy", "Ci\u0105\u017ca"),
    "contact": ("Emergency contact", "Kontakt w nag\u0142ym wypadku"),
    "doctor": ("Own doctor", "Lekarz prowadz\u0105cy"),
    "wishes": ("Care wishes", "\u017byczenia dotycz\u0105ce opieki"),
    "needs": ("How to talk with me", "Jak ze mn\u0105 rozmawia\u0107"),
    "diary": ("Symptom diary", "Dziennik objaw\u00f3w"),
    "questions": ("Questions for the doctor", "Pytania do lekarza"),
}
FOOT = ("In the person's own words, as told on the dates on file. Not a medical record.",
        "W\u0142asnymi s\u0142owami pacjenta, wed\u0142ug stanu na dzie\u0144 zapisu. To nie jest dokumentacja medyczna.")
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


def _heading(key, lang):
    en, pl = HEADINGS[key]
    return en if lang == "en" else pl if lang == "pl" else "%s / %s" % (en, pl)


def _page(kind, entry, chosen, lang, a, today):
    """The page as (title, [(heading, [lines])], foot)."""
    parts = []
    for key in PAGES[kind]:
        if key in chosen:
            lines = _entries(entry, key, a, today)
            if lines:
                parts.append((_heading(key, lang), lines))
    foot = FOOT[0] if lang == "en" else FOOT[1] if lang == "pl" else "%s %s" % FOOT
    return _heading(kind, lang), parts, "%s %s" % (foot, today.isoformat())


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
    lang = (a.lang or "en").lower()
    if lang not in LANGS:
        die("--lang is one of: %s" % ", ".join(LANGS))
    possible = PAGES[kind]
    have = dict((key, _entries(entry, key, a, today)) for key in possible)
    if not a.lines and not a.all:
        rec(kind.upper(), "%s: what could go on the page. The person chooses each line" % entry["id"])
        for key in possible:
            if key == "questions":
                more("questions: theirs to give, each with --question \"...\"")
            elif have[key]:
                more("%s: %s on file (%s)" % (key, core.plural(len(have[key]), "entry", "entries"), HEADINGS[key][0]))
        empty = [key for key in possible if key != "questions" and not have[key]]
        if empty:
            more("nothing on file for: %s" % ", ".join(empty))
        rec("RULE", WARNING)
        rec("NEXT", "ask which lines they want, then: %s --id %s --lines %s" % (
            kind, entry["id"], ",".join(k for k in possible if have[k] or k == "questions") or "..."))
        return
    chosen = list(possible) if a.all else [k.strip().lower() for k in a.lines.split(",") if k.strip()]
    for key in chosen:
        if key not in possible:
            die("--lines names what goes on the page, from: %s" % ", ".join(possible))
    title, parts, foot = _page(kind, entry, chosen, lang, a, today)
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


def _page_options(p):
    p.add_argument("--id", help="whose page (default: the only profile on file)")
    p.add_argument("--lines", metavar="KEY,KEY", help="the lines the person chose, by the names the first run lists")
    p.add_argument("--all", action="store_true", help="every line that is on file: only if the person said so")
    p.add_argument("--lang", help="the headings: en, pl or both (default: en). The entries stay in the person's own words")
    p.add_argument("--write", action="store_true", help="write the page to a file, once it has been read back")
    p.add_argument("--confirm", metavar="CODE", help="with --write: the code the read-back printed")
    p.add_argument("--out", help="where to write: 'auto' (default) or a folder outside any git repository")


def register(sub):
    p = command(sub, "file", "card", cmd_card,
                "a medical ID from the personal file, line by line as the person chooses: a page to print, and text for a phone",
                ["card --id self", "card --id self --lines name,allergies,medicines,contact --lang both"])
    _page_options(p)

    p = command(sub, "file", "passport", cmd_passport,
                "a health summary for a new doctor or one abroad, from the personal file, line by line as the person chooses",
                ["passport --id self", "passport --id self --all --lang both"])
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
