"""Where the person lives: the region pack.

A region pack holds what is true of one country and nowhere else. One is known so far, for Poland
(region-pl.db). It carries two things.

Facts about getting care: who to call, where to go at night, what a patient is owed, where old medicines go.
'find' reads them. A fact is in this skill's own words, and under it stands what it rests on: the law, word
for word, with the article; or the official page it was read on, with the day. Where the law's words were read
by a person and not checked by the build, the line says so.

The country's register of medicines: what a product sold there is. 'med' asks it before it reads an American
label out, because the name on a Polish box means what the Polish register says it means.

The register names a substance in Latin, as it stands in the register. It is printed as it is and never
turned into English by a rule: a medicine is not guessed from its name.
"""
from . import core, library
from .core import command, die, key, more, rec

PACKS = {"PL": ("region-pl", "Poland")}
STEM = "region-pl"
WHAT = "where to get care in Poland, and what a medicine sold there is"
LIST_MAX = 8
NAMES_MAX = 12
SUBSTANCE_MIN = 5           # a typed name this short is not looked for at the start of a substance's name
# words after a product's name that say how much or in what form, and not which product
STRENGTH = frozenset("mg mcg ug g kg ml l iu j m jm tabl tab tabletki tabletka kaps kapsulki kapsulka czopki syrop zel krem "
                     "masc krople plastry aerozol saszetki amp fiol szt tablets tablet capsules capsule".split())
PRODUCT = ("p.id, p.name, c.text, p.strength, f.text, r.text, p.atc, h.text, p.sale, p.parts, p.leaflet, p.imported, p.source "
           "FROM product p JOIN word c ON c.id = p.common JOIN word f ON f.id = p.form JOIN word r ON r.id = p.route "
           "JOIN word h ON h.id = p.holder")
RULE = ("the register says what a product is and how it may be sold. It gives no dose and no advice: the leaflet in the "
        "pack and the pharmacist are the authority")


def installed():
    """What the pack says about itself, if it is there and can be answered from; else None."""
    return library.have(STEM)


def _says_nothing(words):
    return all(w.isdigit() or w in STRENGTH or (w[:1].isdigit() and w.lstrip("0123456789") in STRENGTH) for w in words)


# ---- the register of medicines

def products(text, limit=LIST_MAX):
    """What the country's register says about a name: a product sold under it, or failing that the products
    that hold a substance whose name begins with it. Prints what it finds and returns True; prints nothing and
    returns False when the register has nothing under that name."""
    con, info = library.need(STEM, WHAT)
    try:
        words = [w for w in key(text).split("_") if w]
        for end in range(len(words), 0, -1):
            if _says_nothing(words[:end]):
                break
            rows = con.execute("SELECT %s JOIN product_name n ON n.product = p.id WHERE n.folded = ? ORDER BY p.id" % PRODUCT,
                               ("_".join(words[:end]),)).fetchall()
            if rows:
                library.warn_if_stale(info, core.today())
                _product(con, info, rows, "_".join(words[:end]), words[end:], limit)
                return True
        # not a product's name: perhaps the start of a substance's, as the register writes it
        name = [w for w in words if not _says_nothing([w])]
        if len(name) == 1 and len(name[0]) >= SUBSTANCE_MIN:
            rows = con.execute("SELECT %s WHERE c.text LIKE ? ESCAPE '\\' ORDER BY p.id" % PRODUCT, (name[0] + "%",)).fetchall()
            if rows:
                library.warn_if_stale(info, core.today())
                _substance(con, info, rows, limit)
                return True
        return False
    finally:
        con.close()


def _sale(con, codes):
    """'Rp (on prescription)': a pack's sale category with what it means; one the pack does not explain stands alone."""
    means = dict(con.execute("SELECT code, means FROM sale"))
    return "; ".join("%s (%s)" % (c, means[c]) if c in means else c for c in codes.split("; ") if c) or "sale category not given"


def _foot(con, info, row):
    rec("SOURCE", library.tag(info, row[12]))
    rec("CREDIT", library.credit(info, row[12]))
    rec("RULE", RULE)
    more("for what a label says about the substance, ask 'med' again with its English name; the register gives it in Latin")


def _product(con, info, rows, folded, unused, limit):
    if not _says_nothing(unused):
        rec("CHECK", "only part of that name was used (\"%s\" was not): make sure this is the product meant" % " ".join(unused))
    # one name can stand for more than one composition: each is shown under its own substance
    by_substance = {}
    for row in rows:
        by_substance.setdefault((row[2], row[6]), []).append(row)
    for (common, atc), group in sorted(by_substance.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rec("REGISTER", "%s [a medicine in Poland's register]: %s%s; %s" % (
            group[0][1], "%s [the substance, as the register names it]" % common if common else "no substance name given",
            "; ATC %s" % atc if atc else "", core.plural(len(group), "entry", "entries")))
        kinds = {}
        for row in group:
            kinds.setdefault((row[3], row[4], row[5], row[8]), []).append(row)
        for n, ((strength, form, route, sale), same) in enumerate(sorted(kinds.items(), key=lambda kv: (-len(kv[1]), kv[0]))):
            if n == limit:
                more("and %d more strengths and forms" % (len(kinds) - limit))
                break
            holders = sorted(set(r[7] for r in same if not r[11])) or sorted(set(r[7] for r in same))
            more("%s - %s - %s%s" % (
                ", ".join(x for x in (strength, form, route) if x), _sale(con, sale), holders[0] if holders else "holder not given",
                " and %s" % core.plural(len(holders) - 1, "more holder") if len(holders) > 1 else ""))
        parts = sorted(set(r[9] for r in group if r[9]))
        if parts:
            more("in it, as the register spells it out: %s%s" % (parts[0], " (and %d other compositions)" % (len(parts) - 1) if len(parts) > 1 else ""))
    longer = [n for (n,) in con.execute("SELECT DISTINCT p.name FROM product_name n JOIN product p ON p.id = n.product "
                                        "WHERE n.folded > ? AND n.folded < ? ORDER BY p.name LIMIT ?",
                                        (folded + "_", folded + "`", NAMES_MAX + 1))]
    if longer:
        rec("ALSO", "other products whose name begins the same, each a product of its own: %s%s" % (
            "; ".join(longer[:NAMES_MAX]), " ..." if len(longer) > NAMES_MAX else ""))
    _leaflet(con, rows)
    _foot(con, info, rows[0])


def _substance(con, info, rows, limit):
    by_substance = {}
    for row in rows:
        by_substance.setdefault((row[2], row[6][:5]), []).append(row)
    listed = sorted(by_substance.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for n, ((common, atc), group) in enumerate(listed):
        if n == limit:
            rec("MORE", "%d other substances and mixtures in the register begin with that name" % (len(listed) - limit))
            break
        # the names most entries carry first
        counts = {}
        for row in group:
            counts[row[1]] = counts.get(row[1], 0) + 1
        names = sorted(counts, key=lambda name: (-counts[name], key(name)))
        rec("REGISTER", "%s [a substance in Poland's register, as the register names it]%s; %s" % (
            common, "; ATC %s" % group[0][6] if group[0][6] else "", core.plural(len(group), "entry", "entries")))
        more("sold as: %s%s" % ("; ".join(names[:NAMES_MAX]), " and %s" % core.plural(len(names) - NAMES_MAX, "more name") if len(names) > NAMES_MAX else ""))
        sales = {}
        for row in group:
            for code in row[8].split("; "):
                if code:
                    sales[code] = sales.get(code, 0) + 1
        more("; ".join("%s: %s" % (_sale(con, code), core.plural(count, "entry", "entries")) for code, count in sorted(sales.items())))
    _foot(con, info, rows[0])


def _leaflet(con, rows):
    """The address of the product's Polish leaflet in the register: a link, never the text."""
    for imported in (0, 1):
        for row in rows:
            if row[10] is not None and row[11] == imported:
                url = con.execute("SELECT value FROM build WHERE key = ?", ("leaflet-url-import" if imported else "leaflet-url",)).fetchone()
                if url:
                    rec("LEAFLET", "the Polish leaflet, from the register%s: %s" % (
                        " (a parallel import's)" if imported else "", url[0] % row[10]))
                return


def lookup(text):
    """The register's entries for a product's name, the longest start of what was typed that is one; [] where
    there is none, and None where no register is installed."""
    info = installed()
    if not info:
        return None
    con = library.connect(info["path"])
    try:
        words = [w for w in key(text).split("_") if w]
        for end in range(len(words), 0, -1):
            rows = con.execute("SELECT %s JOIN product_name n ON n.product = p.id WHERE n.folded = ? ORDER BY p.id" % PRODUCT,
                               ("_".join(words[:end]),)).fetchall()
            if rows:
                return rows
        return []
    finally:
        con.close()


def same_substance(names):
    """For each name that is a product in the register, the substances the register gives it: {typed name:
    set of substance names}. For telling two boxes of the same medicine apart from two medicines."""
    out = {}
    info = installed()
    if not info:
        return out
    con = library.connect(info["path"])
    try:
        for name in names:
            words = [w for w in key(name).split("_") if w]
            for end in range(len(words), 0, -1):
                found = set(c for (c,) in con.execute(
                    "SELECT DISTINCT c.text FROM product_name n JOIN product p ON p.id = n.product JOIN word c ON c.id = p.common "
                    "WHERE n.folded = ?", ("_".join(words[:end]),)) if c)
                if found:
                    out[name] = found
                    break
    finally:
        con.close()
    return out


# ---- the facts

def _fact(con, info, row):
    fact_key, topic, title, says = row
    rec("FACT", "%s [%s; '%s']" % (title, topic, fact_key))
    more(says)
    more("the wording is this skill's. What it rests on:")
    numbers = con.execute("SELECT number, what FROM number WHERE fact = ? ORDER BY position", (fact_key,)).fetchall()
    if numbers:
        rec("NUMBERS", "; ".join("%s [%s]" % (n, w) for n, w in numbers))
    used = []
    for kind, name, place, url, quote, read, how, source in con.execute(
            "SELECT kind, name, place, url, quote, read, how, source FROM fact_source WHERE fact = ? ORDER BY position", (fact_key,)):
        if kind == "law":
            rec("LAW", "%s, %s: \"%s\" [%s]" % (name, place, quote, "read by hand on %s" % read if how == "by hand"
                                                     else "found in the act on %s" % read))
        else:
            rec("PAGE", "%s: %s [stated there on %s; no words of the page are quoted]" % (name, url, read))
        if source not in used:
            used.append(source)
    for n, source in enumerate(used):
        (more if n else lambda text: rec("SOURCE", text))(library.tag(info, source))


def say(fact_key, heading):
    """One fact of the pack, for another command to print under a heading of its own. Returns False, and prints
    nothing, where the pack is not installed or has no such fact."""
    info = installed()
    if not info:
        return False
    con = library.connect(info["path"])
    try:
        row = con.execute("SELECT says FROM fact WHERE key = ?", (fact_key,)).fetchone()
        if not row:
            return False
        rec(heading, row[0])
        for kind, name, place, read, how in con.execute(
                "SELECT kind, name, place, read, how FROM fact_source WHERE fact = ? ORDER BY position", (fact_key,)):
            more("rests on: %s%s [%s %s]" % (name, ", %s" % place if place else "",
                                            "read by hand on" if how == "by hand" else "found in the act on" if kind == "law" else "stated there on",
                                            read))
        more("the wording is this skill's; 'find %s' has the law's own words [sourced: %s.db, built %s]" % (
            fact_key, info["stem"], info["built"].isoformat()))
        return True
    finally:
        con.close()


def _matching(rows, words):
    """The facts that hold every word. A fact whose name holds them comes before one that only mentions them, and
    a whole word before the start of one: the first of those four that finds anything is the answer."""
    def held(text, starts):
        parts = key(text).split("_")
        return all(any(p.startswith(w) if starts else p == w for p in parts) for w in words)
    exact = [r for r in rows if key(r[0]) == "_".join(words)]
    if exact:
        return exact
    def name(row):                  # its key and its title, not the subject it is filed under
        return "%s %s" % (row[0], row[2])
    for text, starts in ((name, False), (name, True), (" ".join, False), (" ".join, True)):
        found = [r for r in rows if held(text(r), starts)]
        if found:
            return found
    return []


def cmd_find(a):
    con, info = library.need(STEM, WHAT)
    try:
        library.warn_if_stale(info, core.today())
        rows = con.execute("SELECT key, topic, title, says FROM fact ORDER BY position").fetchall()
        words = [w for w in key(" ".join(a.words or [])).split("_") if w]
        if a.topic:
            topics = sorted(set(r[1] for r in rows))
            if a.topic.strip().lower() not in topics:
                die("--topic is one of: %s" % ", ".join(topics))
            rows = [r for r in rows if r[1] == a.topic.strip().lower()]
        if not words and not a.topic:
            rec("FIND", "%s on file for Poland. Ask with a word or two, or with --topic" % core.plural(len(rows), "fact"))
            for fact_key, topic, title, _ in rows:
                more("%s [%s; '%s']" % (title, topic, fact_key))
            rec("RULE", "these are facts about how care is organised, each with its source. Which service a person needs "
                        "now is a triage question, and comes first")
            return
        if words:
            rows = _matching(rows, words)
        if not rows:
            rec("FIND", "nothing on file under those words")
            more("'find' alone lists what there is. Anything else is a cited lookup, or \"I have no data\"")
            return
        for n, row in enumerate(rows[:a.max]):
            if n:
                print()
            _fact(con, info, row)
        if len(rows) > a.max:
            rec("MORE", "%s: narrow it down, or raise --max" % core.plural(len(rows) - a.max, "more fact"))
        rec("RULE", "a fact here says how things are arranged in Poland, as its source had it on the day named. It is not "
                    "advice for this person, and where it matters the source is the one to check")
    finally:
        con.close()


def numbers(code):
    """The country's own numbers, with what each is for, when its pack is installed. Prints nothing otherwise."""
    pack = PACKS.get(str(code).upper())
    info = library.have(pack[0]) if pack else None
    if not info:
        return
    con = library.connect(info["path"])
    try:
        listed = con.execute("SELECT number, what FROM number WHERE code = ? ORDER BY position", (str(code).upper(),)).fetchall()
        if not listed:
            return
        rec("REGION", "%s's own, from its numbering plan and its health fund: %s" % (
            pack[1], "; ".join("%s [%s]" % (n, w) for n, w in listed)))
        more("'find emergency numbers' and 'find helpline' say what each rests on [sourced: %s.db, built %s]" % (
            info["stem"], info["built"].isoformat()))
    finally:
        con.close()


def register(sub):
    p = command(sub, "clinic", "find", cmd_find,
                "where to get care in the person's country, and what a patient is owed: the region pack's facts, each with its source",
                ["find", "find night care", "find emergency numbers", "find --topic rights", "find old medicines"])
    p.add_argument("words", nargs="*", help="a word or two of what is wanted: night, helpline, rights, kit ...")
    p.add_argument("--topic", help="every fact on one subject: care, emergency, rights, medicines, kit, paperwork")
    p.add_argument("--max", type=int, default=3, help="facts to print in full (default 3)")

