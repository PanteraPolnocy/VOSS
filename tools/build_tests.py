"""Build src/scripts/data/labtests-pd.db: what a medical test is, what it is for and what happens during it, in
MedlinePlus's own words.

  python tools/build_tests.py --fetch     download the test pages into downloads/ (some three hundred small
                                          requests, a few minutes), then build
  python tools/build_tests.py             build from what is already in downloads/

MedlinePlus publishes its health topics as a file, and its medical tests as pages only, so the pages are read
one by one, from the list on https://medlineplus.gov/lab-tests/.

Public domain, which is what "pd" stands for. NLM's page on using its content lists "Medical test information"
among what is not copyrighted, and asks to be named as the source
(https://medlineplus.gov/about/using/usingcontent/). That page is downloaded with the rest, and the build stops
if it no longer says so.

What is taken from a page: its title, the other names it gives for the test, and its text from the first
heading down to the references. What is left out: the references, the links to other pages, and the pictures.

What this script changes: HTML becomes plain text (paragraphs, "## " headings, "- " list items), and curly
quotes and long dashes become straight ones. No wording is changed.
"""
import argparse
import json
import os
import re
import sys
import time

import dbtools
from build_core import plain, tidy
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, store

STEM = "labtests-pd"
INDEX = "https://medlineplus.gov/lab-tests/"
TERMS_PAGE = "https://medlineplus.gov/about/using/usingcontent/"
TERMS_FILE = "mplus-usingcontent.html"
TERMS_WORDS = ("works produced by the federal government are not copyrighted under u.s. law", "medical test information")
PAGES_FILE = "mplus-labtests.json"
LINK_RE = re.compile(r'href="(https://medlineplus\.gov/lab-tests/[a-z0-9-]+/)"')
CREDIT = "Source: MedlinePlus, National Library of Medicine"
PD = "public domain: a work of the United States government, not copyrighted. MedlinePlus asks to be named as the source"
MIN_TESTS = 200
PACE = 0.5

LICENCE = """labtests-pd.db: where its contents come from, and on what terms

MedlinePlus medical tests: what a test is, what it is used for, why someone may need it, what happens during
it, how to prepare, its risks, and what results may mean, in MedlinePlus's own words.
National Library of Medicine (NLM), United States. https://medlineplus.gov/lab-tests/

Public domain. NLM's own words: "Works produced by the federal government are not copyrighted under U.S. law.
You may reproduce, redistribute, and link freely to non-copyrighted content", and among the content that is
in the public domain it lists "Medical test information".
(https://medlineplus.gov/about/using/usingcontent/)

Credit, to be kept with every answer drawn from it: Source: MedlinePlus, National Library of Medicine
NLM does not endorse this skill. The file holds the pages as they stood on the day they were retrieved
('sources' prints the day): it is not the current MedlinePlus, and MedlinePlus is.

Not in this file: the references at the foot of each page, the links to other pages, and the pictures.
Changed in the making of this file: HTML turned into plain text; curly quotes and long dashes made straight.
No wording was changed.

The pages were written for readers in the United States. They say what a test is; they say nothing about
any one person's result, which is read against the range printed on that person's own report.
"""


def fetch_all(folder):
    os.makedirs(folder, exist_ok=True)
    dbtools.fetch(TERMS_PAGE, TERMS_FILE, "text/html", folder=folder)
    index, _ = dbtools.get(INDEX, "text/html")
    links = sorted(set(LINK_RE.findall(index.decode("utf-8", "replace"))))
    if len(links) < MIN_TESTS:
        sys.exit("only %d test pages are linked from %s: the page has changed, nothing was saved" % (len(links), INDEX))
    path = os.path.join(folder, PAGES_FILE)
    partial, day, done = path + ".partial", core.today().isoformat(), {}
    try:
        with open(partial, encoding="utf-8") as f:
            kept = json.load(f)
        if kept.get("day") == day:
            done = kept["done"]
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    todo = [u for u in links if u not in done]
    say("medline   %d test pages to read%s: this takes a few minutes" % (len(todo), " (%d already read today)" % len(done) if done else ""))

    def keep():
        with open(partial, "w", encoding="utf-8") as f:
            json.dump({"day": day, "done": done}, f)

    try:
        for n, url in enumerate(todo, 1):
            data, _ = dbtools.get(url, "text/html")
            done[url] = data.decode("utf-8", "replace")
            time.sleep(PACE)
            if n % 25 == 0:
                keep()
                say("medline   %d of %d" % (n, len(todo)))
    finally:
        keep()
    doc = {"what": "MedlinePlus medical test pages, as fetched one by one by tools/build_tests.py.",
           "pages": dict((u, done[u]) for u in links)}
    dbtools.save(path, (json.dumps(doc, ensure_ascii=True) + "\n").encode("utf-8"), INDEX)
    os.remove(partial)
    say("fetched   %s (%d pages)" % (PAGES_FILE, len(links)))


def check_terms(folder):
    try:
        with open(os.path.join(folder, TERMS_FILE), encoding="utf-8", errors="replace") as f:
            text = " ".join(re.sub(r"<[^>]+>", " ", f.read()).lower().split())
    except OSError:
        sys.exit("NLM's page on using its content is not in the downloads folder ('--fetch' gets it)")
    for words in TERMS_WORDS:
        if words not in text:
            sys.exit("NLM's page on using its content no longer says \"%s\": read %s again before anything is passed on" % (words, TERMS_PAGE))


def read_page(html):
    """(title, [other names], text) of one test page, or None for a page that is not one."""
    head = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    start = html.find('<div class="main">')
    if not head or start < 0:
        return None
    body = html[start:]
    end = re.search(r"(?is)<h2[^>]*>\s*References\s*</h2>", body)
    stop = body.find("</article>")
    body = body[:end.start()] if end else body[:stop] if stop > 0 else body
    text = plain(body)
    if "## " not in text:
        return None
    names = []
    m = re.search(r"(?m)^Other names?: (.+)$", text)
    if m:
        names = [tidy(x) for x in re.split(r"[,;]", m.group(1)) if 2 <= len(tidy(x)) <= 80]
    return tidy(re.sub(r"<[^>]+>", "", head.group(1))), names, text


def read_pages(path):
    try:
        with open(path, encoding="utf-8") as f:
            pages = json.load(f)["pages"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("%s is not the file of test pages this script writes ('--fetch' makes one)" % os.path.basename(path))
    out, skipped = [], []
    for url in sorted(pages):
        got = read_page(pages[url])
        if got is None:
            skipped.append(url)
            continue
        out.append((got[0], url, got[1], got[2]))
    if len(out) < MIN_TESTS:
        sys.exit("only %d test pages could be read, where about three hundred are expected: nothing was built" % len(out))
    out.sort(key=lambda t: (core.key(t[0]), t[1]))
    return out, skipped


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    check_terms(a.downloads)
    pages_path = os.path.join(a.downloads, PAGES_FILE)
    tests, skipped = read_pages(pages_path)
    url, day = dbtools.origin(pages_path, retrieved=a.retrieved)
    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        source = dbtools.add_source(con, "MedlinePlus medical tests, National Library of Medicine", url or INDEX, day, PD, CREDIT)
        con.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, block INTEGER, "
                    "start INTEGER NOT NULL, length INTEGER NOT NULL, source INTEGER NOT NULL)")
        con.execute("CREATE TABLE test_name (folded TEXT NOT NULL, test INTEGER NOT NULL, kind INTEGER NOT NULL, shown TEXT NOT NULL)")
        texts = dbtools.Texts(con, a.codec)
        for number, (title, page, names, text) in enumerate(tests, 1):
            block, start, length = texts.add(text)
            con.execute("INSERT INTO test VALUES (?, ?, ?, ?, ?, ?, ?)", (number, title, page, block, start, length, source))
            seen = set()
            for kind, shown in [(0, title)] + [(1, n) for n in names]:
                folded = core.key(shown)
                if folded and folded not in seen:
                    seen.add(folded)
                    con.execute("INSERT INTO test_name VALUES (?, ?, ?, ?)", (folded, number, kind, shown))
        raw, packed = texts.close()
        con.execute("CREATE INDEX test_name_folded ON test_name (folded)")
        import vosslib
        size = dbtools.finish(con, path, core.today(), facts=(("format", 1), ("toolkit", vosslib.VERSION), ("tests", len(tests))))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d tests; text: %s packed into %s" % (len(tests), dbtools.size_words(raw), dbtools.size_words(packed)))
    for page in skipped:
        say("          NOTE not a test page in the shape this script knows, left out: %s" % page)
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download the test pages and NLM's terms into the downloads folder first")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the pages were downloaded, for a file fetched by hand")
    ap.add_argument("--codec", help="how to pack the text: smallest (default), or one of %s" % ", ".join(store.CODECS))
    ap.add_argument("--out", metavar="DIR", help="where to write labtests-pd.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads)
    return build(a)


if __name__ == "__main__":
    main()
