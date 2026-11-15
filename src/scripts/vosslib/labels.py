"""What a medicine is, and what its label says.

'med' and 'sidefx' read labels-us.db: product labels as companies have filed them with the United States
Food and Drug Administration, one for each substance, type (prescription or over the counter) and route.
The label's words are printed as they stand, with where they came from.

Three things are said every time, because they are easy to forget:
  - it is an American label. The same medicine elsewhere may have other uses, strengths and warnings, and
    the leaflet of the product in the person's hand is the authority;
  - FDA has not verified it, and it may not be the label on the pack;
  - there is no dose in this file, on purpose.

'sidefx' looks for a symptom in a label's own list of side effects. Listed is not caused.

A medicine is never guessed from its name. The output says what a name was read as, and what part of it was
not used. A brand name that is printed on packs of different medicines ("Pain Relief") gets a list of them
and is read as none: only the active ingredient on the pack says which one it is.
"""
import re

from . import core, library, store
from .core import command, die, key, more, rec

STEM = "labels-us"
REGION = "region-pl"         # the register of the country the person lives in, where its pack is installed
WHAT = "what a medicine is and what its label says"
LABEL = "id, type, route, substances, parts, generic, brand, maker, class, application, set_id, effective, labels, source"
KINDS = ("boxed warning", "purpose", "active ingredient", "uses", "do not use", "warnings", "side effects", "interactions",
         "pregnancy and other groups", "for patients")
ALWAYS = ("boxed warning", "purpose", "active ingredient", "uses")
SYMPTOM_SECTIONS = ("boxed warning", "side effects", "warnings", "for patients")
FORMS = frozenset("mg mcg ug g kg ml l iu units unit micrograms microgram milligrams milligram grams gram percent tablet tablets "
                  "tab tabs capsule capsules caps cap pill pills inhaler puffer spray drops drop syrup solution suspension cream "
                  "ointment gel patch patches injection pen sachet sachets suppository suppositories lozenge lozenges er sr xr xl "
                  "mr cr forte retard extra regular maximum strength oral".split())
JOINERS = frozenset(("and", "with", "plus"))
PART_MIN = 3            # a typed name this short is not looked for inside brand names
MAX_WORDS = 16          # of what was typed; a name is never longer, and a box says little more
SOLD_AS = 3             # brand names shown beside a label in a list
PAGE = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=%s"
LIST_MAX = 8
PASSAGES = 6
WINDOW = 320
SECTION_CHARS = 6000
RULE = ("an American label, as the company filed it. FDA has not verified it, and it may not be the label on the pack in "
        "the person's hand: their own leaflet and their pharmacist are the authority")


def resolve(con, text):
    """The labels a typed name could mean: ([label rows], how it was read, [typed words that were not used],
    whether they are one medicine, {label: the brand names it was found under}).

    The longest run of the typed words that names something is taken, the earliest of two as long. A substance
    is looked for first, under its own name; then a brand name on an American label, whole or as part of a
    longer one ("tylenol" is in "Tylenol Extra Strength"); then a substance under another name for it. What
    is left over is a strength or a form as a rule ("500 mg tablets"), and the caller says so when it is
    anything else.

    Where the leftovers name more medicines ("acetaminophen with codeine") and there are labels that hold
    them all, those are what was meant. Failing that, a brand name that holds every typed word in some
    other order is ("robitussin dm" is "Robitussin Maximum Strength Cough plus Chest Congestion DM").

    One medicine means the labels share a substance. "Pain Relief" is printed on packs of several different
    ones, so it is not: such a name counts only when all of what was typed matched, and the caller lists what
    it found and reads it as none of them."""
    words = [w for w in key(text).split("_") if w]
    words, beyond = words[:MAX_WORDS], words[MAX_WORDS:]
    whole = _says_nothing(beyond)           # nothing that matters was typed past the words that are looked at
    brands = _Brands(words)
    found = _longest(con, brands, words)
    if found:
        rows, how, before, after, one, names = found[:6]
        unused = before + after + beyond
        if _says_nothing(unused):
            return rows, how, unused, one, names
        if one and whole:
            both = _together(con, brands, rows, how, [before, after])
            if both:
                return both[0], both[1], [], True, names
    if whole:
        rows_all, how_all, one_all, names_all = brands.with_all(con, words)
        if rows_all:
            return rows_all, how_all, [], one_all, names_all
    if not found:
        return [], "", [], True, {}
    return rows, how, unused, one, names


def _longest(con, brands, words, wide=False):
    """(rows, how, the words before the run, the words after it, whether it is one medicine, names, whether it
    was found as a substance), or None. wide: every label a brand name could mean, whether or not they are
    one medicine; that is for a second name, which only narrows down the first.

    A search says whether what it found is sure enough to stand beside words nobody can place. A substance
    is, and so is a whole brand name of one medicine. Part of a brand name is not, and neither is a name that
    several medicines carry: those count only when everything else that was typed is a strength or a form."""
    for length in range(len(words), 0, -1):
        for start in range(len(words) - length + 1):
            run = words[start:start + length]
            # "500 mg" names nothing, and neither does a run that begins or ends with "and"
            if _says_nothing(run) or run[0] in JOINERS or run[-1] in JOINERS:
                continue
            before, after = words[:start], words[start + length:]
            brand = brands.wide if wide else brands.named
            for search in (_own_name, brand, _other_name):
                rows, how, one, names, sure = search(con, "_".join(run))
                if rows and (sure or _says_nothing(before + after)):
                    return rows, how, before, after, one, names, search is not brand
    return None


def _together(con, brands, rows, how, sides):
    """More was typed than the one name. Where what is left names something too and there are labels that are
    all of it, those labels are what was meant: (rows, how). A second substance means the product with both
    in it; a brand name means the labels sold under it. None when a leftover names nothing, or no label is
    everything at once."""
    ids, with_it, sold_as = set(r[0] for r in rows), [], []
    while sides:
        words = [w for w in sides.pop(0) if w not in JOINERS]
        if _says_nothing(words):
            continue
        found = _longest(con, brands, words, wide=True)
        if not found:
            return None
        fewer = ids & set(r[0] for r in found[0])
        if not fewer:
            return None
        if fewer != ids:                    # it narrows things: not the first name said again
            ids = fewer
            (with_it if found[6] else sold_as).append(found[1])
        sides += [found[2], found[3]]
    how += " together with %s" % " and ".join(with_it) if with_it else ""
    how += ", sold as %s" % " and ".join(sold_as) if sold_as else ""
    return [r for r in rows if r[0] in ids], how


def _labels(con, where, values):
    return con.execute("SELECT DISTINCT %s FROM label l %s" % (", ".join("l." + c for c in LABEL.split(", ")), where), values).fetchall()


def _by_number(con, ids):
    rows = []
    for at in range(0, len(ids), 500):
        some = ids[at:at + 500]
        rows += _labels(con, "WHERE l.id IN (%s)" % ",".join("?" * len(some)), some)
    return rows


def _own_name(con, folded):
    """A substance under the name FDA gives it, with or without the word for its salt."""
    return _substance(con, folded, "n.kind = 'substance'")


def _other_name(con, folded):
    """A substance under another name for it, from Wikidata. It comes after the brand names on the labels:
    a brand can be one thing in the United States and another elsewhere, and these labels are American."""
    return _substance(con, folded, "n.kind <> 'substance'")


def _substance(con, folded, which):
    hits = con.execute("SELECT s.id, s.name, n.shown, n.kind FROM substance_name n JOIN substance s ON s.id = n.substance "
                       "WHERE n.folded = ? AND %s ORDER BY s.name" % which, (folded,)).fetchall()
    if not hits:
        return [], "", True, {}, True
    ids = sorted(set(h[0] for h in hits))
    rows = _labels(con, "JOIN label_substance x ON x.label = l.id WHERE x.substance IN (%s)" % ",".join("?" * len(ids)), ids)
    first = hits[0]
    how = "" if key(first[2]) == key(first[1]) else " [found under \"%s\"%s]" % (
        first[2], "" if first[3] == "substance" else ", " + first[3].replace("also called", "another name for it, from Wikidata"))
    return rows, "%s%s" % (" or ".join(sorted(set(h[1] for h in hits))[:3]), how), True, {}, True


class _Brands(object):
    """Brand names, looked for whole and as part of longer ones. The names that hold any word of what was typed
    are read once, the first time they are wanted: runs of those words are then looked for inside them."""

    def __init__(self, words):
        self.words = sorted(set(w for w in words if len(w) >= PART_MIN and not _says_nothing([w])))
        self.names = None

    def named(self, con, folded):
        """(rows, how, whether they are one medicine, {label: names}, whether that is sure) for the labels that
        carry exactly this name, and with them, where that is all one medicine, the labels whose name holds
        it. A name that only holds it counts when nothing carries it exactly, and is never sure."""
        exact, how = self._exact(con, folded)
        held, sold = self._part(con, folded)
        if exact:
            if len(held) > len(exact) and _share_a_substance(con, held):
                return held, how, True, sold, True
            one = _share_a_substance(con, exact)
            return exact, how, one, {}, one
        return held, _by_part(sold), _share_a_substance(con, held), sold, False

    def wide(self, con, folded):
        """The same, with nothing asked of the labels: every one whose name is this or holds it."""
        exact, how = self._exact(con, folded)
        held, sold = self._part(con, folded)
        return held or exact, how or _by_part(sold), True, sold, True

    def with_all(self, con, words):
        """(rows, how, whether they are one medicine, {label: names}) for the labels with a brand name that holds
        every one of these words that says anything, in whatever order."""
        want = ["_" + w + "_" for w in words if not _says_nothing([w])]
        held, sold = self._holding(con, lambda name: all(w in name for w in want)) if want else ([], {})
        return held, _by_part(sold), _share_a_substance(con, held), sold

    def _part(self, con, folded):
        """The labels whose brand name holds these words, whole and in this order. A run with no word of its own
        in it ("d 24") is not looked for: it would only be found inside a name some other word had brought up."""
        if len(folded) < PART_MIN or not any(w in self.words for w in folded.split("_")):
            return [], {}
        return self._holding(con, lambda name: "_" + folded + "_" in name)

    def _exact(self, con, folded):
        rows = _labels(con, "JOIN label_name n ON n.label = l.id WHERE n.folded = ?", (folded,))
        if not rows:
            return [], ""
        name = con.execute("SELECT shown FROM label_name WHERE folded = ? ORDER BY place, label", (folded,)).fetchone()[0]
        return rows, "%s [a brand name in the United States]" % name

    def _holding(self, con, fits):
        """The labels with a brand name that fits, and for each of them those names with their places. A name
        is handed to the test with an underscore at each end, so that a word can be told from a piece of one."""
        if not self.words:
            return [], {}
        if self.names is None:
            # an underscore means "any one character" to LIKE, so the ones that stand for a word's edge are escaped
            self.names = con.execute("SELECT folded, shown, place, label FROM label_name WHERE %s" % " OR ".join(
                ["'_' || folded || '_' LIKE ? ESCAPE '\\'"] * len(self.words)), ["%\\_" + w + "\\_%" for w in self.words]).fetchall()
        sold = {}
        for name, shown, place, label in self.names:
            if fits("_" + name + "_"):
                sold.setdefault(label, []).append((place, shown))
        for names in sold.values():
            names.sort()
        return _by_number(con, sorted(sold)), sold


def _by_part(sold):
    """How to say that brand names were found by part of them: each name once, the ones most labels carry first."""
    best = {}
    for names in sold.values():
        for place, shown in names:
            best[key(shown)] = min(best.get(key(shown), (place, shown)), (place, shown))
    shown = [name for _, name in sorted(best.values())]
    if len(shown) < 2:
        return "%s [a brand name in the United States, found by part of it]" % shown[0] if shown else ""
    return "%s%s [brand names in the United States, found by part of them]" % (
        "; ".join(shown[:SOLD_AS]), " and %d more" % (len(shown) - SOLD_AS) if len(shown) > SOLD_AS else "")


def _share_a_substance(con, rows):
    """Whether one name would find every one of these labels as a substance. A salt counts as its base, so
    ibuprofen and ibuprofen sodium are one medicine here."""
    if len(rows) < 2:
        return True
    names = {}
    ids = [r[0] for r in rows]
    for at in range(0, len(ids), 500):
        some = ids[at:at + 500]
        for label, folded in con.execute("SELECT x.label, n.folded FROM label_substance x JOIN substance_name n ON n.substance = "
                                         "x.substance WHERE n.kind = 'substance' AND x.label IN (%s)" % ",".join("?" * len(some)), some):
            names.setdefault(label, set()).add(folded)
    shared = None
    for label in ids:
        shared = names.get(label, set()) if shared is None else shared & names.get(label, set())
        if not shared:
            return False
    return True


def _says_nothing(words):
    """A strength, a form, or a word that joins two names: nothing that tells one medicine from another."""
    return all(w.isdigit() or w in FORMS or w in JOINERS or (w[:1].isdigit() and w.lstrip("0123456789") in FORMS) for w in words)


def _narrow(rows, a):
    if a.rx and a.otc:
        die("--rx or --otc, not both")
    if a.rx or a.otc:
        rows = [r for r in rows if r[1] == ("prescription" if a.rx else "over the counter")]
    if a.route:
        want = a.route.strip().lower()
        rows = [r for r in rows if want in r[2]]
    return rows


def _unused(words):
    """Says so when part of what was typed named nothing, and was more than a strength or a form."""
    if not _says_nothing(words):
        rec("CHECK", "only part of that name was used (\"%s\" was not): make sure this is the medicine meant" % " ".join(words))


def _several(rows, how, names, a, nothing_done=""):
    """The answer to a name that is on packs of different medicines: what they are and what each is sold as,
    plain substances before mixtures, and no choice among them."""
    listed = sorted(_narrow(rows, a), key=lambda r: (r[4], -len(names.get(r[0], ())), -r[12], r[0]))
    if names:
        rec("MEDICINE", "not one medicine: %s of different medicines are sold under a name with that in it%s" % (
            core.plural(len(rows), "label"), nothing_done))
    else:
        rec("MEDICINE", "not one medicine: %s of different medicines carry that name%s (read as %s)" % (
            core.plural(len(rows), "label"), nothing_done, how))
    for row in listed[:a.max]:
        sold = [shown for _, shown in names.get(row[0], ())]
        more("label %d: %s [%s; %s], %s" % (
            row[0], row[3], row[1], row[2],
            "sold as %s%s" % ("; ".join(sold[:SOLD_AS]), " and %d more" % (len(sold) - SOLD_AS) if len(sold) > SOLD_AS else "") if sold
            else "%s with FDA" % core.plural(row[12], "label on file", "labels on file")))
    if len(listed) > a.max:
        more("and %d more: raise --max, or narrow with --rx, --otc or --route" % (len(listed) - a.max))
    if not listed:
        more("none of that type or route")
    rec("RULE", "do not choose one for the person. The active ingredient is printed on the pack: read it with them, then ask "
                "again with the substance, or with 'med --id N' from this list")


def choose(rows, a):
    """(the labels to print in full, the rest). In full: for each type, the single-substance label that most
    companies have filed, or with nothing of the kind the most filed of what there is."""
    rows = sorted(_narrow(rows, a), key=lambda r: (r[4], -r[12], r[0]))
    main = []
    for kind in ("over the counter", "prescription"):
        of_kind = [r for r in rows if r[1] == kind]
        single = [r for r in of_kind if r[4] == 1]
        if single or (of_kind and not any(r[4] == 1 for r in rows)):
            main.append((single or of_kind)[0])
    return main, [r for r in rows if r not in main]


def _sections(con, label):
    return dict((kind, (block, start, length)) for kind, block, start, length in
                con.execute("SELECT kind, block, start, length FROM section WHERE label = ?", (label,)))


def _head(con, row, how=""):
    rec("MEDICINE", "%s [%s; %s] (label %d)%s" % (row[3], row[1], row[2], row[0], " - read as " + how if how else ""))
    brands = [b for (b,) in con.execute("SELECT shown FROM label_name WHERE label = ? ORDER BY place LIMIT 9", (row[0],))]
    if brands:
        rec("BRANDS", "in the United States, among others: %s%s" % ("; ".join(brands[:8]), " ..." if len(brands) > 8 else ""))
    if row[8]:
        rec("CLASS", row[8])


def _foot(con, info, row):
    rec("LABEL", "filed by %s%s; %s on file with FDA for this substance, type and route" % (
        row[7] or "a company not named", ", dated %s" % row[11] if row[11] else "",
        "the only label" if row[12] == 1 else "one of %d labels" % row[12]))
    if row[10]:
        rec("PAGE", PAGE % row[10])
    rec("SOURCE", library.tag(info, row[13]))
    rec("CREDIT", library.credit(info, row[13]))


def passages(text, words, limit=PASSAGES):
    """The places in a text where one of the words begins, each with the sentence around it: ([passages], how many
    places in all)."""
    spans = []
    for word in words:
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(word), text, re.I):
            # back to where the sentence starts and on to where it ends; a sentence that runs on too long is
            # cut at a space, never in the middle of a word
            stop, line = text.rfind(". ", 0, m.start()), text.rfind("\n", 0, m.start())
            start = max(stop + 2 if stop != -1 else 0, line + 1 if line != -1 else 0)
            if m.start() - start > WINDOW:
                start = text.find(" ", m.start() - WINDOW, m.start()) + 1 or m.start()
            end = text.find(". ", m.end())
            end = len(text) if end == -1 else end + 1
            if end - m.end() > WINDOW:
                end = text.rfind(" ", m.end(), m.end() + WINDOW)
                end = end if end > m.end() else m.end() + WINDOW
            spans.append((start, end))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:           # the same place, or the very next sentence
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    out = []
    for start, end in merged[:limit]:
        piece = " ".join(text[start:end].split())
        whole_start = start == 0 or text[start - 1] == "\n" or text[start - 2:start] == ". "
        whole_end = end >= len(text) or text[end - 1] == "."
        out.append(("" if whole_start else "... ") + piece + ("" if whole_end else " ..."))
    return out, len(merged)


def _kind(name):
    """The section a word names: 'side' is 'side effects', 'preg' is 'pregnancy and other groups'."""
    want = " ".join(str(name).lower().split())
    hits = [k for k in KINDS if k == want] or [k for k in KINDS if k.startswith(want)] or [k for k in KINDS if want in k]
    if len(hits) != 1:
        die("--section is one of: %s" % "; ".join(KINDS))
    return hits[0]


def _print_text(text, limit, everything):
    if everything or len(text) <= limit:
        print(text)
        return
    cut = text.rfind(". ", 0, limit)
    print(text[:cut + 1 if cut > limit // 2 else limit])
    more("%d more characters of this section: --all prints the whole of it, --find WORD the places that mention a word"
         % (len(text) - (cut + 1 if cut > limit // 2 else limit)))


def cmd_med(a):
    # the name on a box means what the register of the country it was sold in says it means: that comes first
    local = False
    if a.id is None and a.name and library.have(REGION):
        from . import region
        local = region.products(" ".join(a.name), a.max)
        if local and not library.have(STEM):
            return
        if local:
            print()
    con, info = library.need(STEM, WHAT)
    try:
        reader = store.Reader(con)
        library.warn_if_stale(info, core.today())
        if a.id is not None:
            row = con.execute("SELECT %s FROM label WHERE id = ?" % LABEL, (a.id,)).fetchone()
            if row is None:
                die("no label has that number: 'med NAME' finds one")
            main, rest, how, dropped = [row], [], "", []
        else:
            if not a.name:
                die("name the medicine: med metformin (or a brand name, or --id N from a list)")
            rows, how, dropped, one, names = resolve(con, " ".join(a.name))
            if not rows:
                if local:
                    rec("LABEL", "no American label is on file under that name, so there is none to set beside the register. "
                                 "Ask again with the substance's English name")
                    return
                rec("MEDICINE", "nothing on file under that name")
                rec("RULE", "that is a gap in this file, which holds American labels only: a medicine sold elsewhere under "
                            "another name may not be in it. Look it up with the tools you have and cite it, or say you have no data")
                return
            if not one:
                _several(rows, how, names, a)
                return
            main, rest = choose(rows, a)
            if not main:
                rec("MEDICINE", "%s on file for %s, and none of that type or route" % (core.plural(len(rows), "label"), how))
                return
        _unused(dropped)
        section = _kind(a.section) if a.section else None
        words = [w for w in key(" ".join(a.find or [])).split("_") if w]
        for n, row in enumerate(main):
            if n:
                print()
            _head(con, row, how)
            have = _sections(con, row[0])
            if section:
                if section not in have:
                    rec(section.upper(), "this label has no such section")
                else:
                    text = reader.text(*have[section])
                    if words:
                        found, total = passages(text, words)
                        rec(section.upper(), "%s on the label under those words%s" % (
                            core.plural(total, "place"), "" if total else ": the label may use another word for it"))
                        for line in found:
                            more(line)
                        if total > len(found):
                            more("and %d more" % (total - len(found)))
                    else:
                        rec(section.upper(), "the label's own words")
                        _print_text(text, SECTION_CHARS, a.all)
            else:
                for kind in ALWAYS:
                    if kind in have:
                        rec(kind.upper(), "the label's own words")
                        _print_text(reader.text(*have[kind]), SECTION_CHARS, a.all)
                others = [k for k in KINDS if k in have and k not in ALWAYS]
                if others:
                    rec("ALSO HERE", "%s  ('med --id %d --section NAME')" % ("; ".join(others), row[0]))
            _foot(con, info, row)
        if rest:
            rec("OTHER", "%s for the same name: other routes, and products that combine it with something else" % core.plural(
                len(rest), "more label"))
            for row in rest[:a.max]:
                more("label %d: %s [%s; %s]" % (row[0], row[3], row[1], row[2]))
            if len(rest) > a.max:
                more("and %d more: raise --max, or narrow with --rx, --otc or --route" % (len(rest) - a.max))
        rec("RULE", RULE)
        more("there is no dose in this file, on purpose: a dose comes from the label of the product itself. What a label "
             "says a medicine is for is not advice to take it")
    finally:
        con.close()


def cmd_sidefx(a):
    if not a.med:
        die("name the medicine: sidefx --med metformin --symptom nausea")
    words = [w for w in key(" ".join(a.symptom or [])).split("_") if len(w) >= 3]
    if not words:
        die("say what to look for: --symptom nausea (one word or several; a label may use a medical word for it)")
    con, info = library.need(STEM, WHAT)
    try:
        reader = store.Reader(con)
        library.warn_if_stale(info, core.today())
        rows, how, dropped, one, names = resolve(con, " ".join(a.med))
        if not rows:
            rec("MEDICINE", "nothing on file under that name, so nothing was checked")
            rec("RULE", "that is a gap in this file, not a finding. The person's own leaflet lists its side effects: read that "
                        "with them, or look it up and cite it")
            return
        if not one:
            _several(rows, how, names, a, ", so nothing was searched")
            return
        main, rest = choose(rows, a)
        if not main:
            rec("MEDICINE", "%s on file for %s, and none of that type or route" % (core.plural(len(rows), "label"), how))
            return
        _unused(dropped)
        for n, row in enumerate(main):
            if n:
                print()
            _head(con, row, how)
            have = _sections(con, row[0])
            listed = 0
            for kind in SYMPTOM_SECTIONS:
                if kind not in have:
                    continue
                found, total = passages(reader.text(*have[kind]), words, a.max)
                if not total:
                    continue
                listed += total
                rec(kind.upper(), "%s under those words" % core.plural(total, "place"))
                for line in found:
                    more(line)
                if total > len(found):
                    more("and %d more: raise --max, or 'med --id %d --section \"%s\"' for the whole section" % (
                        total - len(found), row[0], kind))
            if not listed:
                rec("NOT FOUND", "none of those words is on this label, in its side effects, its warnings or its text for "
                                 "patients. A label often uses the medical word (itching is pruritus, sleepiness is somnolence): "
                                 "try that")
                more("not on the label is not the same as not caused by the medicine")
            _foot(con, info, row)
        if rest:
            rec("OTHER", "%s not searched ('med' lists them)" % core.plural(
                len(rest), "more label for the same name was", "more labels for the same name were"))
        rec("RULE", "listed is not caused. A symptom on the label may have another cause, and one that is not on it may still "
                    "be the medicine. Triage comes first, and a red flag ends this. Never \"stop taking it\": that goes to the "
                    "prescriber or the pharmacist, today if it matters")
        more(RULE)
    finally:
        con.close()


def _common(p):
    p.add_argument("--rx", action="store_true", help="only the prescription label")
    p.add_argument("--otc", action="store_true", help="only the over-the-counter label")
    p.add_argument("--route", help="only labels for this route: oral, topical, intravenous ...")
    p.add_argument("--max", type=int, default=LIST_MAX, help="lines to list (default %d)" % LIST_MAX)


def register(sub):
    p = command(sub, "medicines", "med", cmd_med,
                "what a medicine is: its substance, its class and what its label says it is for, in the label's own words",
                ["med metformin", "med paracetamol --otc", "med advil", "med acetaminophen with codeine",
                 "med warfarin --section interactions --find aspirin", 'med ibuprofen --rx --section "side effects"', "med --id 1"])
    p.add_argument("name", nargs="*", help="a substance or a brand name, whole or in part; two substances for the product that holds both")
    p.add_argument("--id", type=int, help="one label by its number, as a list gives it")
    p.add_argument("--section", help="one section in full: %s" % "; ".join(k for k in KINDS if k not in ALWAYS))
    p.add_argument("--find", nargs="+", metavar="WORD", help="with --section: only the places that mention one of these words")
    p.add_argument("--all", action="store_true", help="print a long section whole")
    _common(p)

    p = command(sub, "medicines", "sidefx", cmd_sidefx,
                "is this symptom on the medicine's label: its side effects, warnings and text for patients, searched for a word",
                ["sidefx --med metformin --symptom nausea", "sidefx --med ibuprofen --otc --symptom stomach bleeding",
                 "sidefx --med sertraline --symptom sleepy somnolence insomnia"])
    p.add_argument("--med", nargs="+", metavar="NAME", help="the medicine: a substance or a brand name")
    p.add_argument("--symptom", nargs="+", metavar="WORD", help="what to look for; several words are looked for one by one")
    _common(p)
