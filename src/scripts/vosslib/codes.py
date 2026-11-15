"""What an ICD-11 code means.

'code' reads icd11.db: ICD-11 for Mortality and Morbidity Statistics, as the World Health Organization
publishes it. A code and its title are printed exactly as they stand in the release, with the entry's URI
and WHO's citation, and that is all this module does with them. It does not reword or translate a title,
and it does not map a code to any other code system: WHO's licence allows neither, which is why there is
no ICD-10 here and no table between the two.

A title is read out of WHO's own record every time. The database keeps no second copy of it.

A code names a category. It says nothing about any one person.
"""
import re

from . import core, library, store
from .core import command, die, key, more, rec

STEM = "icd11"
WHAT = "ICD-11 codes"
KINDS = ("chapter", "block", "category")        # as the file numbers them
ROW = ("id, code, block_id, CASE kind WHEN 0 THEN 'chapter' WHEN 1 THEN 'block' ELSE 'category' END, residual, leaf, chapter, "
       "parent, block, start, length, source")
ID, CODE, BLOCK_ID, KIND, RESIDUAL, LEAF, CHAPTER, PARENT, BLOCK, START, LENGTH, SOURCE = range(12)
LIST_MAX = 15
STOP = frozenset("a an and are code codes for icd icd11 in is of or the to what which with".split())
ICD10_RE = re.compile(r"^[A-Z]\d{2}(?:\.\d{1,2})?$")
LINK_RE = re.compile(r'https?://[^"\s]+')
DEPTH_RE = re.compile(r"(?:- )*")
RULE = ("code and title are WHO's, character for character: pass them on as printed. Do not reword or translate a "
        "title, and do not turn a code into one of another code system: WHO's licence allows neither")


def _unquote(field):
    if len(field) >= 2 and field[0] == field[-1] == '"':
        return field[1:-1].replace('""', '"')
    return field


def title_of(record):
    """The title in one record of WHO's file, as it reads: without the quoting the file puts round it and the
    "- " marks it uses to show depth. Not a character of the title itself is touched."""
    fields = record.split("\t")
    title = _unquote(fields[4]) if len(fields) > 4 else ""
    return title[DEPTH_RE.match(title).end():]


def _title(reader, row):
    return title_of(reader.text(row[BLOCK], row[START], row[LENGTH]))


def _label(row):
    """How an entry is named in a list: its code, its block id, or its chapter number."""
    return row[CODE] or row[BLOCK_ID] or "chapter %s" % row[CHAPTER]


def _kind(row):
    if row[KIND] == "category":
        words = "category" + (", a residual one (other specified or unspecified)" if row[RESIDUAL] else "")
        return words + (", with no subdivisions" if row[LEAF] else ", with subdivisions")
    return "%s, a grouping without a code of its own" % row[KIND]


def _row(con, where, value):
    return con.execute("SELECT %s FROM entity WHERE %s" % (ROW, where), (value,)).fetchone()


def _children(con, row):
    return con.execute("SELECT %s FROM entity WHERE parent = ? ORDER BY id" % ROW, (row[ID],)).fetchall()


def _ancestors(con, row):
    """From the chapter down to the entry's parent."""
    out, seen = [], set()
    while row[PARENT] is not None and row[PARENT] not in seen:
        seen.add(row[PARENT])
        row = _row(con, "id = ?", row[PARENT])
        if row is None:
            break
        out.append(row)
    return out[::-1]


def show(con, info, reader, row, limit):
    """One entry: code, title and URI as WHO has them, where it sits, and what is under it."""
    record = reader.text(row[BLOCK], row[START], row[LENGTH])
    fields = record.split("\t")
    release = (con.execute("SELECT value FROM build WHERE key = 'release'").fetchone() or [""])[0]
    rec("CODE", "%s [ICD-11 MMS, release %s]" % (_label(row), release))
    rec("TITLE", title_of(record))
    rec("KIND", _kind(row))
    for n, up in enumerate(_ancestors(con, row)):
        (more if n else lambda text: rec("IN", text))("%s  %s" % (_label(up), _title(reader, up)))
    if len(fields) > 17 and fields[17].strip():
        rec("NOTE", " ".join(_unquote(fields[17]).split()))
        more("WHO's coding note for this entry, as it stands in the release")
    below = _children(con, row)
    if below:
        rec("UNDER IT", core.plural(len(below), "entry", "entries"))
        for child in below[:limit]:
            more("%s  %s" % (_label(child), _title(reader, child)))
        if len(below) > limit:
            again = "--chapter %s" % row[CHAPTER] if row[KIND] == "chapter" else _label(row)
            more("and %d more: 'code %s --max %d' lists them all" % (len(below) - limit, again, len(below)))
    rec("URI", fields[1] + ("  (foundation: %s)" % fields[0] if fields[0] else ""))
    link = LINK_RE.search(fields[9]) if len(fields) > 9 else None
    if link:
        rec("BROWSE", link.group(0))
    rec("SOURCE", library.tag(info, row[SOURCE]))
    rec("CREDIT", library.credit(info, row[SOURCE]))


def lookup(con, text):
    """The entry a code or a block id names, or None."""
    want = "".join(str(text).split())
    row = _row(con, "code = ?", want.upper())
    if row is None and "." not in want and len(want) > 4:
        row = _row(con, "code = ?", (want[:4] + "." + want[4:]).upper())      # BA410 for BA41.0
    if row is None:
        row = _row(con, "block_id = ? COLLATE NOCASE", want)
    return row


def nearest(con, text):
    """The entry whose code this one would sit under, if the code itself is not in the release."""
    want = "".join(str(text).split()).upper()
    for cut in range(len(want) - 1, 3, -1):
        row = _row(con, "code = ?", want[:cut].rstrip("."))
        if row is not None:
            return row
    return None


def find(con, reader, words):
    """Entries whose titles hold every word, the shortest titles first: [(row, title)].

    The titles are in WHO's records and nowhere else, so every record is looked at. A record that does not hold
    the words as plain letters is passed over without being taken apart; only if nothing turns up that way is
    each title read folded, since an accent in a title hides it from a plain search."""
    want = [w for w in key(" ".join(words)).split("_") if w and w not in STOP]
    if not want:
        die("say which words to look for in the titles: code --find type 2 diabetes")
    places = con.execute("SELECT id, block, start, length FROM entity ORDER BY id").fetchall()
    needles = [w.encode("utf-8") for w in want]
    for plain in (True, False):
        likely, number, low, skip = [], None, b"", False
        for ident, block, start, length in places:
            if plain:
                if block != number:
                    number, low = block, reader.block(block).lower()
                    skip = not all(n in low for n in needles)       # a block without the words holds no such title
                if skip or not all(n in low[start:start + length] for n in needles):
                    continue
            likely.append(ident)
        hits = []
        for at in range(0, len(likely), 500):
            some = likely[at:at + 500]
            for row in con.execute("SELECT %s FROM entity WHERE id IN (%s)" % (ROW, ",".join("?" * len(some))), some):
                title = _title(reader, row)
                have = key(title).split("_")
                if all(any(h == w or (len(w) >= 4 and h.startswith(w)) for h in have) for w in want):
                    hits.append((len(have), 0 if row[KIND] == "category" else 1, row[ID], row, title))
        if hits:
            break
    return [(h[3], h[4]) for h in sorted(hits, key=lambda h: h[:3])]


def cmd_code(a):
    con, info = library.need(STEM, WHAT)
    try:
        reader = store.Reader(con)
        library.warn_if_stale(info, core.today())
        if not 1 <= a.max <= 2000:
            die("--max is 1 to 2000")
        if a.find:
            if a.codes or a.chapter:
                die("--find looks through the titles: leave out the code and --chapter")
            rows = find(con, reader, a.find)
            if not rows:
                rec("CODE", "no title in this release holds those words")
                rec("RULE", "that is a gap in the search, not in medicine: WHO's wording may differ from the words given. Try "
                            "another word for it, or look it up in WHO's own browser and cite it")
                return
            rec("MATCHES", "%s whose titles hold those words" % core.plural(len(rows), "entry", "entries"))
            for row, title in rows[:a.max]:
                more("%s  %s" % (_label(row), title))
            if len(rows) > a.max:
                more("and %d more: add a word, or raise --max" % (len(rows) - a.max))
            rec("NEXT", "'code CODE' prints one entry in full, with its URI. A title that matches some words is not a diagnosis")
            rec("SOURCE", library.tag(info, rows[0][0][SOURCE]))
            rec("CREDIT", library.credit(info, rows[0][0][SOURCE]))
            rec("RULE", RULE)
            return
        wanted = []
        if a.chapter:
            number = a.chapter.strip().upper()
            row = _row(con, "kind = 0 AND chapter = ?", number.zfill(2) if number.isdigit() else number)
            if row is None:
                die("there is no such chapter: they run 01 to 26, then V and X")
            wanted.append((a.chapter, row))
        for given in a.codes or []:
            # a cluster joins codes with '&' or '/': each part is looked up by itself, and the join is not read
            for part in [p for p in re.split(r"[&/]", given) if p.strip()]:
                wanted.append((part, lookup(con, part)))
        if not wanted:
            die("give a code (code BA41.0), a chapter (--chapter 11) or words to look for (--find heart attack)")
        shown = 0
        for given, row in wanted:
            if shown:
                print()
            shown += 1
            if row is not None:
                show(con, info, reader, row, a.max)
                continue
            shape = "".join(str(given).split()).upper()
            rec("CODE", "not in this release of ICD-11")
            if ICD10_RE.match(shape):
                more("it has the shape of an ICD-10 code. This file holds ICD-11 only, and no table between the two: WHO keeps "
                     "such tables for a written agreement. Much paperwork still uses ICD-10: look that code up and cite the "
                     "source, or go by what the document says in words")
            else:
                near = nearest(con, given)
                if near is not None:
                    more("the nearest entry above it: %s  %s" % (_label(near), _title(reader, near)))
                more("check the code against the document it came from; 'code --find WORDS' looks through the titles")
        if any(row is not None for _, row in wanted):
            rec("RULE", RULE)
            more("a code names a category. It is not a diagnosis of anyone, and WHO does not endorse this tool")
    finally:
        con.close()


def register(sub):
    p = command(sub, "clinic", "code", cmd_code,
                "what an ICD-11 code means, word for word from WHO's classification; or the codes whose titles hold some words",
                ["code BA41.0", "code 5A11 1A00", "code --chapter 11", "code --find type 2 diabetes", "code BlockL1-1A0 --max 30"])
    p.add_argument("codes", nargs="*", help="one or more ICD-11 codes, or block ids")
    p.add_argument("--chapter", help="a chapter by its number: 01 to 26, V or X")
    p.add_argument("--find", nargs="+", metavar="WORD", help="look through the titles for entries that hold all these words")
    p.add_argument("--max", type=int, default=LIST_MAX, help="entries to list (default %d)" % LIST_MAX)
