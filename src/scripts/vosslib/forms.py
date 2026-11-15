"""The forms Voss fills in: records whose words are his, and whose shape and rules are the tool's.

assess     possible explanations in three tiers, with the one line he always closes on.
look       what a photo of a rash, a wound or a swelling shows, and the triage level it is sorted into.
decode     a doctor's letter turned into a list of things to do, with dates for a calendar.
translate  a check on a translation: every figure of the original must be in it, as written.
myth       a health claim and its verdict, with the sources and their dates.
teach      the frame of a short lesson on how the body works.
firstaid   the frame of first-aid coaching: the emergency number first, then short lines.
boxread    what was read off a medicine box, set beside what the American labels know the name as.
desk, season, checkin
           notices a person has to switch on before any is given.

None of these holds medical knowledge of its own. Each takes what Voss has worked out, refuses a record that
breaks the clinical rules (no must-not-miss, a percentage for a confidence, a verdict that is not one of the
four), and prints it in record style with the rule that goes with it.
"""
import hashlib
import re

from . import advice, core, ical, library, personal, remind
from .core import command, die, fold, load_data, more, one_line, rec

# word for word from references/clinical-rules.md, "Possible explanations", point 8
CLOSINGS = (
    "I am a reference with a bedside manner, not your doctor. Take this to one.",
    "That is my best reading. A real doctor with real hands outranks it.",
    "I can be wrong, and a doctor can examine you. Go and let them.",
)
TIERS = (("likely", "MOST LIKELY", "what this pattern usually is"),
         ("consider", "WORTH CONSIDERING", "plausible, less common"),
         ("must_not_miss", "MUST NOT MISS", "the serious causes a real doctor would want to rule out"))
CONFIDENCE = ("likely", "possible", "cannot tell")
NEVER = ("probably nothing", "it's nothing", "it is nothing", "nothing to worry about")
PART_HELP = "an explanation is  \"what it could be | what fits | what does not fit | the source, with its date\""
# from references/features.md, Photo look: these go up a level at once
SIGNS = {"mole": "a mole that is changing", "spreading": "redness that is spreading", "streaks": "red streaks",
         "black": "blackened skin", "infant": "anything on an infant"}
VERDICTS = {"supported": "supported", "mixed": "mixed", "not-supported": "not supported",
            "no-good-evidence": "no good evidence either way"}
FIRST_AID = ("cpr", "recovery", "bleeding", "burns", "choking")
DOCS = ("notes", "discharge", "referral", "letter")
# the setting, the heading, what it is called, how it is given, the rule where nothing is on file for it, and
# then what is on file: the topic, the record it is printed under, what to say of it, and the rule that goes with it
NOTICES = {
    "desk": ("desk_notices", "DESK", "desk notices",
             "one notice in a long session, like a fatigue warning: a break from the screen, posture, water. Then respect the "
             "answer, and do not give it twice",
             "no guidance on screen breaks or water is on file: give no figure for either unless you look one up from a public "
             "health or professional body and cite it",
             "breaks", "BREAKS", "what the Health and Safety Executive says about breaks from a screen, in its own words. It "
                                 "was written for people at work in Great Britain",
             "the figure for breaks is the Health and Safety Executive's: say whose it is, and give no other. Nothing is on "
             "file about water or posture: no figure for either unless you look one up and cite it"),
    "season": ("seasonal_checks", "SEASON", "seasonal checks",
               "at most one gentle reminder in a season, for where the person lives: the seasonal vaccinations, a cold snap, "
               "heat and sun",
               "no dates for seasonal vaccinations or weather advice are on file: look them up from the national health "
               "authority, with the date, or leave the reminder out",
               "flu", "FLU", "what ECDC says about when the flu vaccination is given, in its own words. It is about Europe, "
                             "and names no country's dates",
               "when the vaccination starts where the person lives, who is offered it, and anything on cold, heat or sun: "
               "look it up from the national health authority, with the date, or leave it out. Outside Europe the passage "
               "does not apply: the seasons, and the flu's, differ"),
    "checkin": ("wellbeing_checkin", "CHECK-IN", "wellbeing check-ins",
                "a short, gentle question about how things are going, and a real listen. No scores and no questionnaire unless "
                "they ask for one. Raise nothing sensitive that they have not raised themselves",
                "any sign of crisis follows the clinical rules at once: care first, the emergency number and the support line "
                "where they live, plain kind words, and stay",
                None, None, None, None),
}


def _clean(text, what, limit=600):
    """A line of Voss's own, tidied: '' for nothing at all, and an error for a phrase he never says."""
    if not str(text or "").strip():
        return ""
    value = one_line(text, what, limit)
    low = value.lower()
    for phrase in NEVER:
        if phrase in low:
            die("%s says something Voss never says. Name what it could be and what would settle it, or say you cannot tell" % what)
    return value


def _level(number):
    levels = load_data("triage")["levels"]
    if number is None or not 1 <= number <= len(levels):
        die("--level is the triage level, 1 to %d, and it is decided before anything else ('triage' lists them)" % len(levels))
    return levels[number - 1]


# ---- possible explanations

def _explanation(text, where):
    parts = [p.strip() for p in str(text).split("|")]
    if len(parts) != 4 or not parts[0]:
        die("%s was not understood: %s" % (where, PART_HELP))
    what, fits, against, source = (_clean(p, where, 400) if p not in ("", "-") else "" for p in parts)
    if not source:
        die("%s names no source: each explanation carries one, with its date. General knowledge is a source too, if you "
            "say that is what it is" % where)
    if "%" in what + fits + against:
        die("%s holds a percentage: confidence is said in plain words, and no figure is invented" % where)
    return what, fits, against, source


def cmd_assess(a):
    complaint = _clean(a.complaint or "", "--complaint", 300)
    if not complaint:
        die("say what the person came with: --complaint \"...\"")
    level = _level(a.level)
    rec("ASSESS", "%s [Clinic: possible explanations, never a diagnosis]" % complaint)
    rec("TRIAGE", "level %d: %s" % (a.level, level))
    if a.level == 1:
        rec("STOP", "a red flag ends it. No explanations are offered: the emergency number first, in one plain line, then "
                    "what to do while help comes ('triage --country CC' has the number)")
        return
    given = dict((key, [_explanation(t, "--%s" % key.replace("_", "-")) for t in getattr(a, key) or []]) for key, _, _ in TIERS)
    if not given["must_not_miss"]:
        die("no must-not-miss was named. The serious causes a doctor would want to rule out are always named, even when "
            "unlikely, so that a reassuring guess never hides a dangerous one")
    confidence = " ".join((a.confidence or "").lower().replace("can't", "cannot").split())
    if confidence not in CONFIDENCE:
        die("--confidence is said in plain words: %s" % ", ".join(CONFIDENCE))
    if not (given["likely"] or given["consider"]) and confidence != "cannot tell":
        die("with nothing named as likely or worth considering, the confidence is \"cannot tell\": say so, and the advice is "
            "to see a doctor at this level")
    settle = _clean(a.settle or "", "--settle", 400)
    if not settle:
        die("--settle says what would tell the options apart: the examination or test a real doctor would use")
    for key, heading, meaning in TIERS:
        for what, fits, against, source in given[key]:
            rec(heading, "%s [%s]" % (what, meaning))
            if fits:
                more("fits: %s" % fits)
            if against:
                more("does not fit: %s" % against)
            more("source: %s" % source)
    rec("CONFIDENCE", "%s [in plain words; no figure goes with it]" % confidence)
    if confidence == "cannot tell":
        more("say so plainly. The advice is to see a doctor, at the level above")
    rec("SETTLES IT", "%s; the way there is level %d" % (settle, a.level))
    if a.closing is not None and not 1 <= a.closing <= len(CLOSINGS):
        die("--closing is 1 to %d" % len(CLOSINGS))
    # one of the three, so that it varies: the same complaint on the same day gets the same one
    pick = a.closing - 1 if a.closing else int(hashlib.sha256(("%s|%s" % (complaint, core.today())).encode("utf-8")).hexdigest(), 16) % len(CLOSINGS)
    rec("CLOSING", "\"%s\" [one line like it, in your own voice, every time]" % CLOSINGS[pick])
    rec("RULE", "never \"it's probably nothing\", a treatment plan, a prescription, a dose change, or a verdict dressed as a "
                "possibility. If the picture changes, the level is decided again")


# ---- a photo

def cmd_look(a):
    seen = _clean(a.seen or "", "--seen", 600)
    if not seen:
        die("say what is visible, and only that: --seen \"...\"")
    level = a.level
    _level(level)
    signs = []
    for sign in a.sign or []:
        if sign not in SIGNS:
            die("--sign is one of: %s" % ", ".join("%s (%s)" % (k, v) for k, v in sorted(SIGNS.items())))
        if sign not in signs:
            signs.append(sign)
    rec("LOOK", "%s [what is visible in the picture, and nothing else in it]" % seen)
    if signs and level > 1:
        level -= 1
        rec("RAISED", "%s: that goes up a level at once, from %d to %d [derived]" % ("; ".join(SIGNS[s] for s in signs), a.level, level))
    elif signs:
        rec("SIGNS", "; ".join(SIGNS[s] for s in signs))
    rec("TRIAGE", "level %d: %s" % (level, _level(level)))
    if level == 1:
        more("the emergency number first, in one plain line ('triage --country CC' has it)")
    rec("ASK", "what a picture cannot show: when it started, whether it is changing or spreading, pain, heat, fever, and "
               "whether the person is otherwise well. Two or three questions at a time")
    rec("RULE", "never a verdict, and never \"it's nothing\". Possible explanations are for Clinic, through 'assess', with the "
                "closing line. The picture is not kept, and nothing else in it is remarked on")


# ---- a doctor's letter

def _dated(text, where):
    """'what | when' as (what, a date or a date and time, or None)."""
    what, _, when = str(text).partition("|")
    what = _clean(what, where, 300)
    if not what:
        die("%s is empty" % where)
    when = when.strip()
    if not when:
        return what, None
    tidy = personal.when_text(when)
    if not tidy:
        die("%s: the part after | is when it is due: a date, with or without a time (2026-12-01, or '2026-12-01 10:30')" % where)
    return what, tidy


def cmd_decode(a):
    kind = (a.kind or "letter").lower()
    if kind not in DOCS:
        die("--kind is one of: %s" % ", ".join(DOCS))
    todo = [_dated(t, "--todo") for t in a.todo or []]
    meds = [_clean(m, "--newmed", 200) for m in a.newmed or []]
    confirm = [_clean(c, "--confirm-with", 300) for c in a.confirm_with or []]
    if not (todo or meds or confirm):
        die("nothing was given to write down: --todo \"what | when\", --newmed \"...\", --confirm-with \"...\"")
    kind = {"discharge": "discharge letter"}.get(kind, kind)
    rec("DECODED", "the doctor's %s: what follows from it, as it stands there" % kind)
    events = []
    for what, when in todo:
        rec("TO DO", "%s%s" % (what, " - by %s" % when if when else " - no date given: ask when"))
        if when:
            start = core.a_moment(when.replace(" ", "T"), "--todo") if len(when) > 10 else core.a_date(when, "--todo")
            events.append(ical.event(what if not a.discreet else "From the doctor's %s" % kind, start))
    for med in meds:
        rec("NEW", "%s [as it stands there: 'med' says what it is, and 'watch --id ID --new NAME' checks it against the list on file]" % med)
    for item in confirm:
        rec("CONFIRM", "%s: worth confirming with your doctor or pharmacist" % item)
    if a.ics:
        if not events:
            die("there is nothing dated to put in a calendar")
        ical.deliver(a.ics, events, "after-visit-%s" % core.today().isoformat())
    rec("RULE", "the doctor is never contradicted. Where something looks inconsistent it is \"worth confirming with your "
                "doctor or pharmacist\", and nothing more. Explain the letter in plain words separately, as yours")


# ---- a translation

# a figure as it is written: 5, 2,5 or 1.250,5. The full stop that ends a sentence is not part of one
_NUMBER_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*")


def _read(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        die("%s could not be read as UTF-8 text" % what)


def _counts(items):
    out = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


def cmd_translate(a):
    source = _read(a.source, "--source") if a.source else ""
    done = _read(a.translation, "--translation") if a.translation else ""
    if not source.strip() or not done.strip():
        die("give both texts as files: --source the original, --translation yours")
    ok = True
    was, now = _counts(_NUMBER_RE.findall(source)), _counts(_NUMBER_RE.findall(done))
    lost = sorted(n for n in was if now.get(n, 0) < was[n])
    extra = sorted(n for n in now if was.get(n, 0) < now[n])
    rec("FIGURES", "%s in the original, %s in the translation" % (core.plural(sum(was.values()), "figure"), sum(now.values())))
    if lost:
        ok = False
        rec("MISSING", "in the original and not in the translation as written, %s: check each against the original" % core.plural(len(lost), "figure"))
        more("the tool does not repeat them: a figure in a medical paper may be somebody's result")
    if extra:
        ok = False
        rec("ADDED", "%s in the translation that the original does not have as written. A decimal comma turned into a point "
                     "counts: keep every figure exactly as it stands" % core.plural(len(extra), "figure"))
    for term in a.keep or []:
        # as a word of its own: "Bisoprolol" is not kept by "Bisoprololum"
        whole = re.compile(r"(?<!\w)%s(?!\w)" % re.escape(one_line(term, "--keep", 80)))
        before, after = len(whole.findall(source)), len(whole.findall(done))
        if before != after:
            ok = False
            rec("CHANGED", "a term given with --keep stands %d times in the original and %d in the translation: names of "
                           "medicines and units are kept exactly as written" % (before, after))
    marked = len(re.findall(r"\[[^\]\n]{1,80}\]", done))
    rec("MARKED", "%s in square brackets in the translation: the original term where a translation is uncertain, and "
                  "[unreadable] where it could not be read" % core.plural(marked, "note"))
    rec("RESULT", "every figure of the original is in the translation as written" if ok else
        "the translation does not carry the original's figures and terms as written: put that right before it is handed over")
    rec("RULE", "a translation is not an interpretation: translate, then offer to explain separately. The document is not "
                "kept, unless the person asks for a result to go into their file")


# ---- a health claim

def cmd_myth(a):
    if not (a.claim or "").strip():
        die("say what is claimed: --claim \"...\"")
    claim = one_line(a.claim, "--claim", 400)
    verdict = (a.verdict or "").lower()
    if verdict not in VERDICTS:
        die("--verdict is one of: %s" % ", ".join(VERDICTS))
    sources = []
    for n, text in enumerate(a.source or [], 1):
        parts = [p.strip() for p in str(text).split("|")]
        if len(parts) != 3 or not all(parts):
            die("--source is  \"the source | its date | what it says\"")
        day = personal.part_date(parts[1])
        if not day:
            die("source %d: its date is a year, a year and month, or a date" % n)
        sources.append((one_line(parts[0], "--source", 200), day, _clean(parts[2], "--source", 400)))
    if not sources and verdict != "no-good-evidence":
        die("a verdict rests on sources: give each one with its date. With none worth the name, the verdict is no-good-evidence")
    rec("CLAIM", claim)
    rec("VERDICT", VERDICTS[verdict])
    for name, day, says in sources:
        rec("SOURCE", "%s, %s: %s" % (name, day, says))
    if not sources:
        more("nothing that deserves to be called evidence was found, either way. Say that, and what was looked at")
    rec("RULE", "sharp with the claim, kind to the person who asked: they did well to check. A verdict is about the claim, "
                "not about what this person should do")


# ---- a lesson

def cmd_teach(a):
    if not " ".join(a.topic or []).strip():
        die("say what the lesson is about: teach how the heart pumps")
    topic = one_line(" ".join(a.topic), "the topic", 200)
    rec("LESSON", "%s [general knowledge: say that it is]" % topic)
    more("short, and in plain words; a diagram where this platform can draw one")
    info = library.have("core-pd")
    if info:
        more("'term' with a word or two of the subject prints what MedlinePlus says about it, where it has a topic "
             "[sourced: core-pd.db, built %s]" % info["built"].isoformat())
    rec("RULE", "a lesson is never a diagnosis. If the question is about the person's own body, it is a clinical question: "
                "triage first, and 'assess' for possible explanations")


# ---- first aid

def _number(code):
    """(the first emergency number on file for a country, where it came from), or None."""
    info = library.have("core-pd")
    if not info or not re.fullmatch(r"[A-Za-z]{2}", code or ""):
        return None
    con = library.connect(info["path"])
    try:
        row = con.execute("SELECT number, source FROM emergency WHERE code = ? ORDER BY position LIMIT 1", (code.upper(),)).fetchone()
        return (row[0], library.tag(info, row[1])) if row else None
    finally:
        con.close()


def cmd_firstaid(a):
    what = (a.what or "").lower()
    if what not in FIRST_AID:
        die("--what is one of: %s" % ", ".join(FIRST_AID))
    code = a.country
    if not code and a.id:
        kind, entry = personal.pick(personal.need(), a.id)
        code = entry.get("region") if isinstance(entry.get("region"), str) else None
    found = _number(code)
    if found:
        rec("CALL", "%s, now, before anything else [%s]" % (found[0], code.upper()))
        more(found[1])
    else:
        rec("CALL", "the local emergency number, now, before anything else%s" % (
            "" if code else " ('firstaid --country CC' prints the number on file)"))
    rec("COACH", "%s, while help is on its way. Short lines, one action each. No wit, no ears" % what)
    more("the emergency operator's instructions outrank yours: tell the person to stay on the line and do as they say")
    if what == "choking":
        more("for someone who has stopped responding: 'firstaid --what cpr'")
    if advice.show(advice.FIRST_AID, what, "ON FILE",
                   "what Wikipedia's articles say, in their own words, at the revisions named: an encyclopaedia's account of "
                   "what first-aid bodies teach, and not a guideline"):
        rec("GUIDELINE", "coach from those passages in your own short lines, one action each, and say that they are "
                         "Wikipedia's. Anyone can edit it, and the file is as old as its revisions: a current guideline of "
                         "a first-aid body, where you can look one up, outranks it, and is named with its year")
    else:
        rec("GUIDELINE", "none is on file. Give the steps in your own words, following a published first-aid guideline, and "
                         "say which one and of what year")
    rec("ANSWER", "this is an emergency answer: it leads with the number, and the marker is [mood: serious] [voss-serious.webp]")


# ---- a medicine box

def cmd_boxread(a):
    if not (a.name or "").strip():
        die("say what name is on the box: --name \"...\"")
    name = one_line(a.name, "--name", 120)
    unreadable = [fold(u) for u in a.unreadable or []]
    for part in unreadable:
        if part not in ("strength", "substance", "expiry"):
            die("--unreadable is strength, substance or expiry")
    rec("BOX", "%s [as read off the pack]" % name)
    for key, value in (("strength", a.strength), ("substance", a.substance), ("expiry", a.expiry)):
        if key in unreadable:
            rec(key.upper(), "could not be read. It is not guessed: ask the person to read it out")
        elif value:
            more("%s: %s" % (key, one_line(value, "--" + key, 120)))
    for line in a.says or []:
        more("the pack says: %s" % one_line(line, "--says", 300))
    from . import labels
    known, info = labels.known_as([name])
    if info is None:
        rec("LABELS", "no file of medicines is installed, so the name is not set beside one")
    elif name not in known:
        rec("LABELS", "not on file under that name, or on packs of different medicines: there is nothing to set the box "
                      "beside. That is a gap in the American labels, and says nothing against the box")
    else:
        shared, every = known[name]
        rec("LABELS", "in the United States that name is %s [sourced: %s.db, built %s]" % (
            "; ".join(sorted(n.replace("_", " ") for n in shared)), info["stem"], info["built"].isoformat()))
        if a.substance and "substance" not in unreadable:
            want = core.key(a.substance)
            agrees = any(want == n or (len(want) >= 5 and (want in n or n in want)) for n in every)
            rec("SUBSTANCE", "the American labels agree with the box" if agrees else
                "the American labels have another substance under that name than the one read off the box. Read the box "
                "again. A name can be another medicine outside the United States: the box in the person's hand wins, "
                "and the pharmacist is asked")
    rec("RULE", "the box in the person's hand wins over any file. A smudged strength or name is never guessed. For what the "
                "medicine is for: 'med %s'; a dose comes from the leaflet in that box, or from the pharmacist" % name)


# ---- notices a person switches on

def _notice(which, a):
    setting, heading, words, rule, caution, topic, key, lead, sourced = NOTICES[which]
    kind, entry = personal.pick(personal.need(), a.id)
    block = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
    value = block.get(setting)
    on = bool(value.get("on")) if isinstance(value, dict) else bool(value)
    if not on and not a.asked:
        rec(heading, "off for %s: %s are not switched on in their file, so none is given" % (entry["id"], words))
        more("if they ask for one now, run this with --asked. To switch them on: intake --id %s --set \"settings: %s=yes\"" % (
            entry["id"], setting + ".on" if isinstance(value, dict) or which == "checkin" else setting))
        return
    rec(heading, "%s: %s" % (entry["id"], "they asked for it" if not on else "switched on in their file%s" % (
        ", %s" % value["how_often"] if isinstance(value, dict) and value.get("how_often") else "")))
    rec("HOW", rule)
    if which == "desk":
        more("late at night: one bedtime notice. If another mind of the household gives one too, the person still gets "
             "one, not two" if a.late else "add --late for the bedtime notice")
    if which == "season":
        more("today is %s; the person's region on file: %s" % (core.today().isoformat(), entry.get("region") or "none"))
    if topic and advice.show(advice.ADVICE, topic, key, lead):
        caution = sourced
    rec("RULE", caution)
    if on and which in ("season", "checkin") and not remind.wished(entry):
        more("nothing reminds them of it between conversations: offer a reminder, once ('remind --id %s')" % entry["id"])


def cmd_desk(a):
    _notice("desk", a)


def cmd_season(a):
    _notice("season", a)


def cmd_checkin(a):
    _notice("checkin", a)


def register(sub):
    p = command(sub, "clinic", "assess", cmd_assess,
                "possible explanations in three tiers, after triage: the record, its must-not-miss, and the closing line",
                ['assess --complaint "a headache for three days" --level 3 '
                 '--likely "tension-type headache | on both sides, worse late in the day | no nausea | general knowledge" '
                 '--must-not-miss "bleeding in the head | - | no sudden onset | general knowledge" '
                 '--confidence possible --settle "an examination by a doctor"'])
    p.add_argument("--complaint", help="what the person came with, in a line")
    p.add_argument("--level", type=int, help="the triage level, decided first: 1 to 4")
    p.add_argument("--likely", action="append", metavar="TEXT", help=PART_HELP)
    p.add_argument("--consider", action="append", metavar="TEXT", help="worth considering: the same four parts")
    p.add_argument("--must-not-miss", dest="must_not_miss", action="append", metavar="TEXT", help="the serious cause to rule out: always at least one")
    p.add_argument("--confidence", help="in plain words: %s" % ", ".join(CONFIDENCE))
    p.add_argument("--settle", help="what would tell the options apart: the examination or test a doctor would use")
    p.add_argument("--closing", type=int, help="which of the closing lines, 1 to %d (default: the tool deals one)" % len(CLOSINGS))

    p = command(sub, "clinic", "look", cmd_look,
                "a photo of a rash, a wound or a swelling: what is visible, and the triage level it is sorted into",
                ['look --seen "a red patch on the forearm, about three centimetres across" --level 3',
                 'look --seen "redness around a cut on the shin" --level 3 --sign spreading'])
    p.add_argument("--seen", help="what is visible, and only that")
    p.add_argument("--level", type=int, help="the triage level you sorted it into: 1 to 4")
    p.add_argument("--sign", action="append", metavar="SIGN", help="one that raises the level at once: %s" % ", ".join(sorted(SIGNS)))

    p = command(sub, "clinic", "decode", cmd_decode,
                "a doctor's letter as a list of things to do, with dates for a calendar; what looks odd is \"worth confirming\"",
                ['decode --kind discharge --todo "blood test at the GP | 2026-12-01" --todo "ring for the results" '
                 '--newmed "Bisoprolol 2.5 mg, one in the morning" --confirm-with "the letter and the box give different strengths"'])
    p.add_argument("--kind", help="what it is: %s (default: letter)" % ", ".join(DOCS))
    p.add_argument("--todo", action="append", metavar="TEXT", help="a thing to do, and when: \"what | 2026-12-01\" or \"what | 2026-12-01 10:30\"")
    p.add_argument("--newmed", action="append", metavar="TEXT", help="a medicine the letter starts, as the letter has it")
    p.add_argument("--confirm-with", dest="confirm_with", action="append", metavar="TEXT", help="something that looks inconsistent")
    ical.add_option(p, "the dated things to do")
    p.add_argument("--discreet", action="store_true", help="calendar entries that do not say what they are for")

    p = command(sub, "desk", "translate", cmd_translate,
                "a check on a translation of a medical paper: every figure and every kept term of the original, as written",
                ["translate --source original.txt --translation translation.txt --keep Bisoprolol"])
    p.add_argument("--source", metavar="FILE", help="the original, as a text file")
    p.add_argument("--translation", metavar="FILE", help="the translation, as a text file")
    p.add_argument("--keep", action="append", metavar="TERM", help="a medicine's name or a unit that must stand exactly as written")

    p = command(sub, "clinic", "myth", cmd_myth,
                "a health claim checked against sources: one of four verdicts, with each source and its date",
                ['myth --claim "vitamin C stops a cold" --verdict not-supported '
                 '--source "a named review | 2023 | regular vitamin C did not reduce how often people caught colds"',
                 'myth --claim "an onion in a sock draws out a fever" --verdict no-good-evidence'])
    p.add_argument("--claim", help="what is claimed, as it was put")
    p.add_argument("--verdict", help="one of: %s" % ", ".join(VERDICTS))
    p.add_argument("--source", action="append", metavar="TEXT", help="\"the source | its date | what it says\"")

    p = command(sub, "desk", "teach", cmd_teach,
                "the frame of a short lesson on how the body works: general knowledge, said as such, and never a diagnosis",
                ["teach how the heart pumps"])
    p.add_argument("topic", nargs="*", help="what the lesson is about")

    p = command(sub, "clinic", "firstaid", cmd_firstaid,
                "first-aid coaching while help is on its way: the emergency number first, then short lines, one action each",
                ["firstaid --what cpr --country GB", "firstaid --what choking"])
    p.add_argument("--what", help="one of: %s" % ", ".join(FIRST_AID))
    p.add_argument("--country", metavar="CC", help="the country the person is in, for its number")
    p.add_argument("--id", help="whose file to take the country from, once their gate is open")

    p = command(sub, "medicines", "boxread", cmd_boxread,
                "what was read off a medicine box, set beside what the American labels know the name as; nothing smudged is guessed",
                ['boxread --name "Advil" --strength "200 mg" --substance ibuprofen',
                 'boxread --name "Advil" --unreadable strength'])
    p.add_argument("--name", help="the name on the box")
    p.add_argument("--strength", help="the strength on the box")
    p.add_argument("--substance", help="the active substance on the box")
    p.add_argument("--expiry", help="the expiry date on the box")
    p.add_argument("--says", action="append", metavar="TEXT", help="a line the pack or the leaflet says, as it stands")
    p.add_argument("--unreadable", action="append", metavar="PART", help="a part that could not be read: strength, substance, expiry")

    for name, func, summary in (
            ("desk", cmd_desk, "a desk-health notice for a long session, where the person switched them on: one, and no invented figures"),
            ("season", cmd_season, "a seasonal reminder, where the person switched them on: one in a season, with sourced dates only"),
            ("checkin", cmd_checkin, "a wellbeing check-in, where the person switched them on or asked: a gentle question and a real listen")):
        p = command(sub, "desk", name, func, summary, ["%s --id self" % name, "%s --id self --asked" % name])
        p.add_argument("--id", help="whose notice (default: the only profile on file)")
        p.add_argument("--asked", action="store_true", help="the person asked for one now, though it is not switched on")
        if name == "desk":
            p.add_argument("--late", action="store_true", help="it is late at night: the bedtime notice")
