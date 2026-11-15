"""Which medicines are known to interact.

'interact' and 'watch' read ddinter.db: pairs of medicines, each with the severity grade DDInter 2.0 gives
it. That is all the file holds, and the tools say so every time:

  - a grade, and no more. DDInter's downloads carry no account of why two medicines interact or what to do
    about it, and nothing on food or on illnesses. What to do is for the pharmacist or the prescriber.
  - not every pair. A pair is in the downloads only if at least one of its medicines belongs to certain
    groups of the ATC classification. Two medicines from the other groups are not there, however well
    known their interaction.

So "not listed" is never "safe", and the output never lets it read that way.

A medicine is found under DDInter's own name or under another name for the same substance. The output says
what each name was read as, so a wrong reading can be caught.
"""
import difflib

from . import core, library
from .core import command, die, key, more, rec

STEM = "ddinter"
WHAT = "interactions between medicines"
GRADES = {3: "Major", 2: "Moderate", 1: "Minor", 0: "listed, with no grade given"}
LEVELS = {"major": 3, "moderate": 2, "minor": 1, "unknown": 0}
GROUP_WORDS = {"A": "the gut and metabolism", "B": "the blood", "C": "the heart and circulation", "D": "the skin",
               "G": "the urinary and reproductive system, and sex hormones", "H": "hormones", "J": "infections",
               "L": "cancer and the immune system", "M": "muscles, bones and joints", "N": "the nervous system",
               "P": "parasites", "R": "breathing", "S": "the eyes and ears", "V": "various"}
MAX_NAMES = 25
LIST_MAX = 20
# words after a medicine's name that say how much or in what shape, not what it is
FORMS = frozenset("mg mcg ug g kg ml l iu units unit micrograms microgram milligrams milligram grams gram percent tablet tablets "
                  "tab tabs capsule capsules caps cap pill pills inhaler puffer spray drops drop syrup solution suspension cream "
                  "ointment gel patch patches injection pen sachet sachets suppository suppositories lozenge lozenges er sr xr xl "
                  "mr cr forte retard extra strength oral".split())
RULE = ("a grade is DDInter's, about the two substances: it is not a verdict on this person, their doses or their "
        "health. What to do about it is for the pharmacist or the prescriber. Never tell anyone to start, stop or "
        "change a medicine")


def resolve(con, text):
    """What a typed name is read as: ([(drug number, DDInter's name, the name it was found under, kind of name)],
    [the words left off its end]). A strength or a form after the name is dropped ('Metformin 500 mg',
    'Salbutamol inhaler'), and so is anything else that stands in the way of a match: the caller says so,
    because 'calcium carbonate' read as 'calcium' is not the same medicine. No rows if the file has nothing
    under that name; several where one name fits more than one entry."""
    words = [w for w in key(text).split("_") if w]
    dropped = []
    while words:
        rows = con.execute("SELECT n.drug, d.name, n.shown, n.kind FROM drug_name n JOIN drug d ON d.id = n.drug "
                           "WHERE n.folded = ? ORDER BY n.kind = 'name' DESC, d.name", ("_".join(words),)).fetchall()
        if rows:
            # the entry's own name beats another substance's alias
            own = [r for r in rows if r[3] == "name"]
            return own or rows, dropped[::-1]
        dropped.append(words.pop())
    return [], []


def _plain_ending(words):
    """True if the words left off a name are only a strength or a form, which change nothing about what it is."""
    return all(w.isdigit() or w in FORMS or (w[:1].isdigit() and w.lstrip("0123456789") in FORMS) for w in words)


def near(con, text):
    """Up to three names in the file that are close to a name it does not have."""
    names = dict(con.execute("SELECT folded, shown FROM drug_name"))
    out = []
    for hit in difflib.get_close_matches(key(text), sorted(names), n=6, cutoff=0.8):
        if names[hit] not in out:
            out.append(names[hit])
    return out[:3]


def grade(con, a, b):
    """The grade DDInter gives a pair of entries, or None if the pair is not in the file."""
    row = con.execute("SELECT level FROM pair WHERE a = ? AND b = ?", (min(a, b), max(a, b))).fetchone()
    return None if row is None else row[0]


def _fact(con, name, default=""):
    row = con.execute("SELECT value FROM build WHERE key = ?", (name,)).fetchone()
    return row[0] if row else default


def limits(con):
    """What the file does not hold, said the same way every time."""
    have = _fact(con, "groups")
    missing = [g for g in sorted(GROUP_WORDS) if g not in have]
    rec("PARTIAL", "this file holds pairs and grades only, and only pairs with at least one medicine in ATC group %s"
        % ", ".join(have))
    more("two medicines that are both from the other groups are not in it, however well known their interaction: %s"
         % "; ".join("%s (%s)" % (g, GROUP_WORDS[g]) for g in missing))
    more("it has no reasons, no advice on what to do, and nothing on food, drink or illnesses. DDInter itself says: "
         "\"the absence of an interaction does not necessarily mean no interactions exist\"")


def _read(con, given):
    """Print what each name was read as. Returns [(label for the output, drug number, DDInter's name)]: one
    for each entry a name fits, so a name with two forms is checked as both."""
    found, unknown = [], []
    lines = []
    for text in given:
        shown = " ".join(str(text).split())
        hits, dropped = resolve(con, text)
        if not hits:
            unknown.append((shown, near(con, text)))
            continue
        for number, name, under, kind in hits:
            how = "" if key(under) == key(name) and kind == "name" else " [found under \"%s\"%s]" % (
                under, "" if kind == "name" else ", " + kind.replace("also called", "another name for it, from Wikidata"))
            lines.append("%s -> %s%s" % (shown, name, how))
            if (number, name) not in [(f[1], f[2]) for f in found]:
                found.append((shown, number, name))
        if len(hits) > 1:
            lines.append("  that name fits %d entries: each is checked, under DDInter's own name for it" % len(hits))
        if dropped and not _plain_ending(dropped):
            lines.append("  only the start of that name matched (\"%s\" was left off): make sure this is the medicine meant"
                         % " ".join(dropped))
    for n, line in enumerate(lines):
        (more if n else lambda t: rec("READ AS", t))(line)
    for shown, close in unknown:
        rec("UNKNOWN", "\"%s\": nothing in this file under that name%s. It was not checked against anything: say so"
            % (shown, " (did you mean %s?)" % " or ".join(close) if close else ""))
    return found, [u[0] for u in unknown]


def _order(pair):
    """Listed pairs first, the most serious at the top; then the ones the file cannot hold; then the unlisted."""
    return (-pair[0] - 3 if pair[0] is not None else -2 if pair[3] else -1, pair[1], pair[2])


def _pairs(con, left, right):
    """Every pair of one entry from each list, once: [(grade or None, name, name, out of the file's reach)]."""
    seen, out = set(), []
    numbers = sorted(set(x[1] for x in left + right))
    reach = dict(con.execute("SELECT id, reach FROM drug WHERE id IN (%s)" % ",".join("?" * len(numbers)), numbers)) if numbers else {}
    for typed_a, a, name_a in left:
        for typed_b, b, name_b in right:
            # two entries that one typed name fits are two readings of one medicine, not a pair to check
            if a == b or typed_a == typed_b or (min(a, b), max(a, b)) in seen:
                continue
            seen.add((min(a, b), max(a, b)))
            level = grade(con, a, b)
            out.append((level, name_a, name_b, level is None and not reach.get(a) and not reach.get(b)))
    return sorted(out, key=_order)


def _report(con, info, pairs):
    for level, a, b, _ in [p for p in pairs if p[0] is not None]:
        rec("PAIR", "%s + %s: %s%s" % (a, b, GRADES[level], " [DDInter's grade]" if level else " [DDInter lists the pair]"))
    beyond = [p for p in pairs if p[0] is None and p[3]]
    for _, a, b, _ in beyond[:LIST_MAX]:
        rec("OUT OF REACH", "%s + %s: neither is in a group this file covers, so the pair could not be in it whether or "
                            "not the two interact. The file says nothing about them: look it up and cite it, or send it to "
                            "the pharmacist" % (a, b))
    absent = [p for p in pairs if p[0] is None and not p[3]]
    for _, a, b, _ in absent[:LIST_MAX]:
        rec("NOT LISTED", "%s + %s: no interaction between these two is in this file. That is not \"safe\"" % (a, b))
    hidden = max(len(absent) - LIST_MAX, 0) + max(len(beyond) - LIST_MAX, 0)
    if hidden:
        more("and %d more pairs that are not in the file" % hidden)
    limits(con)
    rec("SOURCE", library.tag(info, 1))
    rec("CREDIT", library.credit(info, 1))
    rec("RULE", RULE)


def _on_file(a):
    """The medicines and supplements in a personal file, by name."""
    from . import personal
    data = personal.need()
    _, entry = personal.pick(data, a.id)
    names = [str(row.get("name") or "").strip() for field in ("medicines", "supplements") for row in personal.rows(entry, field)
             if isinstance(row, dict)]
    return entry["id"], [n for n in names if n]


def _one(con, info, found, level, limit):
    """Everything on file for one medicine: how many pairs at each grade, and the names at one of them."""
    for shown, number, name in found:
        rows = con.execute("SELECT d.name, p.level FROM pair p JOIN drug d ON d.id = CASE WHEN p.a = ? THEN p.b ELSE p.a END "
                           "WHERE p.a = ? OR p.b = ? ORDER BY d.name", (number, number, number)).fetchall()
        counts = dict((n, sum(1 for r in rows if r[1] == n)) for n in GRADES)
        rec("MEDICINE", "%s: %s on file (%d major, %d moderate, %d minor, %d with no grade)" % (
            name, core.plural(len(rows), "interaction"), counts[3], counts[2], counts[1], counts[0]))
        if not con.execute("SELECT reach FROM drug WHERE id = ?", (number,)).fetchone()[0]:
            more("this medicine is in none of the groups the file covers: only its pairs with medicines that are in one are "
                 "here, and the rest are missing")
        wanted = [r[0] for r in rows if r[1] == level]
        if wanted:
            rec(GRADES[level].split(",")[0].upper(), "; ".join(wanted[:limit]))
            if len(wanted) > limit:
                more("and %d more: raise --max" % (len(wanted) - limit))
        more("name a second medicine to check a pair; --level major, moderate, minor or unknown lists another grade")
    limits(con)
    rec("SOURCE", library.tag(info, 1))
    rec("CREDIT", library.credit(info, 1))
    rec("RULE", RULE)


def cmd_interact(a):
    names = list(a.names or [])
    whose = None
    if a.id:
        whose, on_file = _on_file(a)
        names += on_file
    if not names:
        die("name the medicines: interact warfarin ibuprofen (quote a name of several words), or --id for the ones on file")
    if len(names) > MAX_NAMES:
        die("that is more than %d names at once: check them in smaller groups" % MAX_NAMES)
    level = LEVELS.get((a.level or "major").strip().lower())
    if level is None:
        die("--level is one of: %s" % ", ".join(LEVELS))
    if not 1 <= a.max <= 500:
        die("--max is 1 to 500")
    con, info = library.need(STEM, WHAT)
    try:
        library.warn_if_stale(info, core.today())
        if whose:
            rec("FILE", "%s on file for %s are included" % (core.plural(len(on_file), "medicine or supplement",
                                                                         "medicines and supplements"), whose))
        found, unknown = _read(con, names)
        if not found:
            rec("NOTHING", "none of those names is in this file, so nothing was checked. That is a gap in the file, not a "
                           "finding: look it up with the tools you have and cite it, or say you have no data")
            return
        if len(names) == 1:
            _one(con, info, found, level, a.max)
            return
        if len(found) == 1:
            rec("NOTHING", "only one of the names could be read, so there is no pair to check")
            limits(con)
            return
        _report(con, info, _pairs(con, found, found))
    finally:
        con.close()


def cmd_watch(a):
    if not a.new:
        die("say what is new: watch --id self --new ibuprofen")
    whose, on_file = _on_file(a)
    con, info = library.need(STEM, WHAT)
    try:
        library.warn_if_stale(info, core.today())
        rec("WATCH", "%s against %s on file for %s" % (core.plural(len(a.new), "new name"), core.plural(
            len(on_file), "medicine or supplement", "medicines and supplements"), whose))
        if not on_file:
            more("nothing is on file to check against: ask what else they take, medicines and supplements both")
        new, _ = _read(con, a.new)
        have, _ = _read(con, on_file) if on_file else ([], [])
        again = [n[2] for n in new if n[1] in [h[1] for h in have]]
        for name in again:
            rec("SAME", "%s is on file already, under one name or another: the same substance twice is a question for the "
                        "pharmacist" % name)
        if not new:
            rec("NOTHING", "the new name is not in this file, so nothing was checked. Say that, and not \"no interactions\"")
            return
        pairs = _pairs(con, new, [h for h in have if h[1] not in [n[1] for n in new]]) + (
            _pairs(con, new, new) if len(new) > 1 else [])
        if not pairs:
            rec("NOTHING", "there was no pair to check")
            limits(con)
            return
        _report(con, info, sorted(pairs, key=_order))
        rec("SAY", "one line to the person: what was checked, against what, and what the file lists. A listed pair goes to "
                   "the pharmacist; an unlisted one is still not \"safe\"")
    finally:
        con.close()


def register(sub):
    p = command(sub, "medicines", "interact", cmd_interact,
                "known interactions between medicines, with the severity grade the source gives each pair",
                ["interact warfarin ibuprofen", 'interact paracetamol warfarin "acetylsalicylic acid"', "interact warfarin",
                 "interact warfarin --level moderate --max 10"])
    p.add_argument("names", nargs="*", help="two or more medicines to check against each other; one alone lists what is on file for it")
    p.add_argument("--id", help="add the medicines and supplements in this profile's personal file, once its gate is open")
    p.add_argument("--level", help="with one medicine: which grade to list (major by default; moderate, minor, unknown)")
    p.add_argument("--max", type=int, default=LIST_MAX, help="with one medicine: names to list (default %d)" % LIST_MAX)

    p = command(sub, "medicines", "watch", cmd_watch,
                "check something new (a medicine, a supplement) against everything in a person's file, once its gate is open",
                ["watch --id self --new ibuprofen", 'watch --id self --new "acetylsalicylic acid" --new warfarin'])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--new", action="append", metavar="NAME", help="what is new; repeat for several")
