"""What a medical test is, in MedlinePlus's own words.

labtests-pd.db holds the pages MedlinePlus publishes on medical tests: what a test is, what it is used for,
why someone may need it, what happens during it, how to prepare, its risks, and what results may mean. They
are printed word for word, with the credit NLM asks for.

A page says what a test is. It says nothing about one person's result: that is read against the range
printed on their own report, which is what 'labs' does with a value.
"""
from . import core, library, store
from .core import die, key, more, rec

STEM = "labtests-pd"
LIST_MAX = 8
# words a report leaves off a test's name and a page's title carries: "potassium" is the "Potassium Blood Test"
FILLER = frozenset("test tests testing blood level levels panel".split())


def find(con, query):
    """([test ids, best first], whether the first is the one the words name and no other)."""
    q = key(query)
    if not q:
        die("say which test: labs --about potassium blood test")
    hits = [t for (t,) in con.execute("SELECT DISTINCT test FROM test_name WHERE folded = ? ORDER BY kind, test", (q,))]
    if hits:
        return hits, len(hits) == 1
    words = q.split("_")
    scored = {}
    for folded, test, kind in con.execute("SELECT folded, test, kind FROM test_name"):
        have = folded.split("_")
        if all(w in have for w in words):
            extra = [h for h in have if h not in words]
            score = (len([h for h in extra if h not in FILLER]), kind, len(extra))
            if test not in scored or score < scored[test]:
                scored[test] = score
    order = sorted(scored, key=lambda t: (scored[t], t))
    whole = [t for t in order if scored[t][0] == 0]
    return order, len(whole) == 1 and order[0] == whole[0]


def _open():
    info = library.have(STEM)
    return (library.connect(info["path"]), info) if info else (None, None)


def pointer(name):
    """The line 'labs' prints about what a test measures: where to read it, or that nothing is on file."""
    con, info = _open()
    if con is None:
        return ("nothing on file for what this test measures (%s.db is not installed). Explain it from a cited lookup, or "
                "say you have no data" % STEM)
    try:
        found, sure = find(con, name)
        if not found:
            return ("nothing on file under that name. 'labs --about WORDS' looks for the test by other words; failing that, "
                    "explain it from a cited lookup, or say you have no data")
        if not sure:
            return "%s on file hold that name: 'labs --about \"%s\"' lists them" % (core.plural(len(found), "test"), name)
        title = con.execute("SELECT title FROM test WHERE id = ?", (found[0],)).fetchone()[0]
        return "'labs --about \"%s\"' prints what MedlinePlus says this test is and what it is used for [read as %s; %s.db]" % (
            name, title, STEM)
    finally:
        con.close()


def cmd_about(a):
    con, info = library.need(STEM, "what a test measures")
    try:
        library.warn_if_stale(info, core.today())
        found, sure = find(con, " ".join(a.about))
        if not found:
            rec("TEST", "nothing on file under those words")
            rec("RULE", "that is a gap in this file, not a fact about the test. Look it up with the tools you have and cite it, "
                        "or say you have no data")
            return
        if not sure and len(found) > 1:
            rec("MATCHES", "%s on file whose names hold those words" % core.plural(len(found), "test"))
            for number in found[:LIST_MAX]:
                more(con.execute("SELECT title FROM test WHERE id = ?", (number,)).fetchone()[0])
            if len(found) > LIST_MAX:
                more("and %d more: add a word to narrow it" % (len(found) - LIST_MAX))
            rec("NEXT", "say which is meant, then 'labs --about' with its title")
            rec("SOURCE", library.tag(info, 1))
            return
        title, url, block, start, length, source = con.execute(
            "SELECT title, url, block, start, length, source FROM test WHERE id = ?", (found[0],)).fetchone()
        rec("TEST", "%s [MedlinePlus medical test]" % title)
        if key(title) != key(" ".join(a.about)):
            more("that is what the words were read as: say so, and if it is not the test on the report, the page is not about it")
        other = [shown for (shown,) in con.execute("SELECT shown FROM test_name WHERE test = ? AND kind = 1 ORDER BY rowid", (found[0],))]
        if other:
            rec("ALSO", "; ".join(other))
        rec("ABOUT", "the source's own words, in full")
        print(store.Reader(con).text(block, start, length))
        rec("PAGE", url)
        rec("SOURCE", library.tag(info, source))
        credit = library.credit(info, source)
        if credit:
            rec("CREDIT", credit)
        rec("RULE", "these are the source's words about the test, written for readers in the United States. They are not about "
                    "the person's result: a value is read against the range printed on their own report ('labs --test ... "
                    "--value ... --range ...'), and nothing here is a diagnosis")
    finally:
        con.close()
