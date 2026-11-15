"""What an ICD-11 code means.

'code' reads icd11.db: ICD-11 for Mortality and Morbidity Statistics, as the World Health Organization
publishes it. A code and its title are printed exactly as they stand in the release, with the entry's URI
and WHO's citation, and that is all this module does with them. It does not reword or translate a title,
and it does not map a code to any other code system: WHO's licence allows neither, which is why there is
no ICD-10 here and no table between the two.

A code names a category. It says nothing about any one person.
"""
import re

from . import core, library, store
from .core import command, die, key, more, rec

STEM = "icd11"
WHAT = "ICD-11 codes"
ROW = "id, code, block_id, title, kind, residual, leaf, chapter, parent, block, start, length, source"
LIST_MAX = 15
STOP = frozenset("a an and are code codes for icd icd11 in is of or the to what which with".split())
ICD10_RE = re.compile(r"^[A-Z]\d{2}(?:\.\d{1,2})?$")
LINK_RE = re.compile(r'https?://[^"\s]+')
RULE = ("code and title are WHO's, character for character: pass them on as printed. Do not reword or translate a "
        "title, and do not turn a code into one of another code system: WHO's licence allows neither")


def _unquote(field):
    if len(field) >= 2 and field[0] == field[-1] == '"':
        return field[1:-1].replace('""', '"')
    return field


def _label(row):
    """How an entry is named in a list: its code, its block id, or its chapter number."""
    return row[1] or row[2] or "chapter %s" % row[7]


def _kind(row):
    if row[4] == "category":
        words = "category" + (", a residual one (other specified or unspecified)" if row[5] else "")
        return words + (", with no subdivisions" if row[6] else ", with subdivisions")
    return "%s, a grouping without a code of its own" % row[4]


def _row(con, where, value):
    return con.execute("SELECT %s FROM entity WHERE %s" % (ROW, where), (value,)).fetchone()


def _children(con, row):
    return con.execute("SELECT %s FROM entity WHERE parent = ? ORDER BY id" % ROW, (row[0],)).fetchall()


def _ancestors(con, row):
    """From the chapter down to the entry's parent."""
    out, seen = [], set()
    while row[8] is not None and row[8] not in seen:
        seen.add(row[8])
        row = _row(con, "id = ?", row[8])
        if row is None:
            break
        out.append(row)
    return out[::-1]


def show(con, info, reader, row, limit):
    """One entry: code, title and URI as WHO has them, where it sits, and what is under it."""
    fields = reader.text(row[9], row[10], row[11]).split("\t")
    release = (con.execute("SELECT value FROM build WHERE key = 'release'").fetchone() or [""])[0]
    rec("CODE", "%s [ICD-11 MMS, release %s]" % (_label(row), release))
    rec("TITLE", row[3])
    rec("KIND", _kind(row))
    for n, up in enumerate(_ancestors(con, row)):
        (more if n else lambda text: rec("IN", text))("%s  %s" % (_label(up), up[3]))
    if len(fields) > 17 and fields[17].strip():
        rec("NOTE", " ".join(_unquote(fields[17]).split()))
        more("WHO's coding note for this entry, as it stands in the release")
    below = _children(con, row)
    if below:
        rec("UNDER IT", core.plural(len(below), "entry", "entries"))
        for child in below[:limit]:
            more("%s  %s" % (_label(child), child[3]))
        if len(below) > limit:
            again = "--chapter %s" % row[7] if row[4] == "chapter" else _label(row)
            more("and %d more: 'code %s --max %d' lists them all" % (len(below) - limit, again, len(below)))
    rec("URI", fields[1] + ("  (foundation: %s)" % fields[0] if fields[0] else ""))
    link = LINK_RE.search(fields[9]) if len(fields) > 9 else None
    if link:
        rec("BROWSE", link.group(0))
    rec("SOURCE", library.tag(info, row[12]))
    rec("CREDIT", library.credit(info, row[12]))


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


def find(con, words):
    """Entries whose titles hold every word, the shortest titles first: [rows]."""
    want = [w for w in key(" ".join(words)).split("_") if w and w not in STOP]
    if not want:
        die("say which words to look for in the titles: code --find type 2 diabetes")
    sql = "SELECT %s FROM entity WHERE %s" % (ROW, " AND ".join("title LIKE ?" for _ in want))
    rows = con.execute(sql, tuple("%" + w + "%" for w in want)).fetchall()
    if not rows:
        # an accent in a title hides it from a plain search: look through them all, folded
        rows = con.execute("SELECT %s FROM entity" % ROW).fetchall()
    hits = []
    for row in rows:
        have = key(row[3]).split("_")
        if all(any(h == w or (len(w) >= 4 and h.startswith(w)) for h in have) for w in want):
            hits.append((len(have), 0 if row[4] == "category" else 1, row[0], row))
    return [h[3] for h in sorted(hits, key=lambda h: h[:3])]


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
            rows = find(con, a.find)
            if not rows:
                rec("CODE", "no title in this release holds those words")
                rec("RULE", "that is a gap in the search, not in medicine: WHO's wording may differ from the words given. Try "
                            "another word for it, or look it up in WHO's own browser and cite it")
                return
            rec("MATCHES", "%s whose titles hold those words" % core.plural(len(rows), "entry", "entries"))
            for row in rows[:a.max]:
                more("%s  %s" % (_label(row), row[3]))
            if len(rows) > a.max:
                more("and %d more: add a word, or raise --max" % (len(rows) - a.max))
            rec("NEXT", "'code CODE' prints one entry in full, with its URI. A title that matches some words is not a diagnosis")
            rec("SOURCE", library.tag(info, rows[0][12]))
            rec("CREDIT", library.credit(info, rows[0][12]))
            rec("RULE", RULE)
            return
        wanted = []
        if a.chapter:
            number = a.chapter.strip().upper()
            row = _row(con, "kind = 'chapter' AND chapter = ?", number.zfill(2) if number.isdigit() else number)
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
                    more("the nearest entry above it: %s  %s" % (_label(near), near[3]))
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
