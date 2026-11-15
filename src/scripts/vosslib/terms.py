"""A medical word in plain English.

'term' reads core-pd.db: the health topic summaries and the short definitions of health terms that
MedlinePlus publishes, word for word, each with its credit line and the day it was retrieved. It looks a
word up by its name, by what else it is called, and by the medical heading it is filed under; failing
that it says which entries hold all the words, and failing that which summaries mention them.

It explains what a thing is. It knows nothing about the person asking, and it is not a diagnosis.
"""
import difflib
import re

from . import core, library, store
from .core import command, die, key, more, rec

STEM = "core-pd"
KINDS = {"title": 0, "also called": 1, "see reference": 2, "MeSH": 3}
STOP = frozenset("a about an and are can do does explain for i in is it me mean means of on or please tell the to what "
                 "whats which".split())
LIST_MAX = 8
BRIEF_CHARS = 160
ENTRY = "id, kind, title, url, origin, brief, block, start, length, source"


def _has(word, have):
    """True if one of a name's words is this word, or begins with it, or is its singular."""
    for h in have:
        if h == word or (len(word) >= 4 and h.startswith(word)) or (
                len(h) >= 4 and word.startswith(h) and word[len(h):] in ("s", "es")):
            return True
    return False


def _best_first(hits):
    """Entries from (entry, kind of name) pairs: each once, the one found by its title first."""
    best = {}
    for entry, kind in hits:
        rank = KINDS.get(kind, 9)
        if entry not in best or rank < best[entry]:
            best[entry] = rank
    return [e for e, _ in sorted(best.items(), key=lambda kv: (kv[1], kv[0]))]


def find(con, reader, query):
    """(how they were found, [entry ids, best first]). How: 'exact', 'words', 'close', 'text' or 'nothing'."""
    q = key(query)
    if not q:
        die("say which word or topic: term \"atrial fibrillation\"")
    hits = con.execute("SELECT entry, kind FROM name WHERE folded = ?", (q,)).fetchall()
    names = con.execute("SELECT folded, entry, kind FROM name").fetchall()
    if not hits:
        # 'afib' is 'a-fib': the same letters, written together
        run = q.replace("_", "")
        hits = [(e, k) for f, e, k in names if f.replace("_", "") == run]
    if hits:
        return "exact", _best_first(hits)
    words = [w for w in q.split("_") if w not in STOP] or q.split("_")
    scored = {}
    for folded, entry, kind in names:
        have = folded.split("_")
        if all(_has(w, have) for w in words):
            score = (max(len(have) - len(words), 0), KINDS.get(kind, 9))
            if entry not in scored or score < scored[entry]:
                scored[entry] = score
    if scored:
        whole = [e for e, s in scored.items() if s[0] == 0]
        if whole:                       # the words are the whole of a name, give or take a plural
            return "exact", sorted(whole, key=lambda e: (scored[e], e))
        return "words", sorted(scored, key=lambda e: (scored[e], e))
    close = difflib.get_close_matches(q, sorted(set(f for f, _, _ in names)), n=LIST_MAX, cutoff=0.8)
    if close:
        order = []
        for name in close:
            order += [e for e in _best_first([(e, k) for f, e, k in names if f == name]) if e not in order]
        return "close", order
    patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(w)) for w in words]
    counted = []
    for entry, block, start, length in con.execute("SELECT id, block, start, length FROM entry ORDER BY block, start"):
        low = reader.text(block, start, length).lower()
        counts = [len(p.findall(low)) for p in patterns]
        if all(counts):
            counted.append((-sum(counts), entry))
    if counted:
        return "text", [e for _, e in sorted(counted)]
    return "nothing", []


def _row(con, entry):
    return con.execute("SELECT %s FROM entry WHERE id = ?" % ENTRY, (entry,)).fetchone()


def _label(kind, entry):
    return "health topic, id %d" % entry if kind == "topic" else "definition"


def show(con, info, reader, entry, brief=False):
    """One entry in full: its names, the source's own words, and where they came from."""
    eid, kind, title, url, origin, short, block, start, length, source = _row(con, entry)
    rec("TERM", "%s [%s]" % (title, _label(kind, eid)))
    also, mesh, seen = [], [], set([key(title)])
    for name_kind, shown in con.execute("SELECT kind, shown FROM name WHERE entry = ? ORDER BY rowid", (eid,)):
        if key(shown) in seen:
            continue
        seen.add(key(shown))
        (mesh if name_kind == "MeSH" else also).append(shown)
    if also:
        rec("ALSO", "; ".join(also))
    if mesh:
        rec("MESH", "%s [Medical Subject Headings, National Library of Medicine]" % "; ".join(mesh))
    text = reader.text(block, start, length)
    if kind == "topic":
        groups = [g for (g,) in con.execute("SELECT name FROM grouping WHERE entry = ? ORDER BY name", (eid,))]
        if groups:
            rec("GROUP", "; ".join(groups))
        if brief or not text:
            rec("BRIEF", short or "the source gives this topic no summary")
            if text:
                more("'term --id %d' prints the whole summary" % eid)
        else:
            rec("SUMMARY", "the source's own words, in full")
            print(text)
        related = [t for (t,) in con.execute(
            "SELECT e.title FROM related r JOIN entry e ON e.id = r.other WHERE r.entry = ? ORDER BY e.title", (eid,))]
        if related:
            rec("SEE ALSO", "; ".join(related))
    else:
        rec("MEANS", text)
        if origin or short:
            rec("FROM", "; ".join(x for x in (origin, short) if x))
    if url:
        rec("PAGE", url)
    rec("SOURCE", library.tag(info, source))
    credit = library.credit(info, source)
    if credit:
        rec("CREDIT", credit)


def listing(con, reader, entries, limit):
    for entry in entries[:limit]:
        eid, kind, title, _url, _origin, short, block, start, length, _source = _row(con, entry)
        if kind != "topic":
            short = " ".join(reader.text(block, start, length).split())
        if len(short) > BRIEF_CHARS:
            short = short[:BRIEF_CHARS].rsplit(" ", 1)[0] + " ..."
        more("%s [%s]%s" % (title, _label(kind, eid), ": " + short if short else ""))
    if len(entries) > limit:
        more("and %d more: add a word to narrow it" % (len(entries) - limit))


def cmd_term(a):
    con, info = library.need(STEM, "medical words and health topics")
    try:
        reader = store.Reader(con)
        library.warn_if_stale(info, core.today())
        if a.id is not None:
            if a.words:
                die("give the id or the words, not both")
            if _row(con, a.id) is None:
                die("no entry has that id: 'term WORDS' finds one by name")
            how, entries = "exact", [a.id]
        else:
            how, entries = find(con, reader, " ".join(a.words or []))
        if not 1 <= a.max <= 50:
            die("--max is 1 to 50")
        if how == "nothing":
            rec("TERM", "nothing on file under those words, in any name or in any summary")
            rec("RULE", "that is a gap in this file, not a fact about the word. Look it up with the tools you have and cite it, "
                        "or say you have no data")
            return
        full = not a.list and (how == "exact" and len(entries) <= 3 or how in ("words", "close") and len(entries) == 1)
        if full:
            if how == "words":
                rec("NEAREST", "no entry has exactly that name; this one holds every word of it")
            elif how == "close":
                rec("NEAREST", "nothing is on file under that spelling; this is the nearest name. Say which you took it for")
            for n, entry in enumerate(entries):
                if n:
                    print()
                show(con, info, reader, entry, brief=a.brief)
            rec("RULE", "these are the source's words, about the thing and not about the person: nothing here is a diagnosis. "
                        "It was written for readers in the United States, so where it names 911 or an American service, give the "
                        "person's own ('triage --country')")
            more("a figure in a summary is general: a lab value is still read against the range printed on the person's own report")
            return
        head = {"exact": "%s on file under that name", "words": "%s whose names hold those words",
                "close": "nothing under that spelling; %s with a name close to it",
                "text": "no entry is named that; %s whose summaries mention those words"}[how]
        rec("MATCHES", head % core.plural(len(entries), "entry", "entries"))
        listing(con, reader, entries, a.max)
        rec("NEXT", "say which is meant, then 'term' with its title, or 'term --id N' for a health topic")
        rec("SOURCE", library.tag(info, 1))
    finally:
        con.close()


def register(sub):
    p = command(sub, "clinic", "term", cmd_term,
                "a medical word or health topic in plain English, in the source's own words, with its credit",
                ['term "heart attack"', "term afib --brief", "term antioxidants", "term kidney --list", "term --id 5"])
    p.add_argument("words", nargs="*", help="the word, the abbreviation or the topic")
    p.add_argument("--id", type=int, help="a health topic by its number, as a list of matches gives it")
    p.add_argument("--brief", action="store_true", help="the source's one-line description in place of the whole summary")
    p.add_argument("--list", action="store_true", help="only list what matches, one line each")
    p.add_argument("--max", type=int, default=LIST_MAX, help="entries to list (default %d)" % LIST_MAX)
