"""Build src/scripts/data/firstaid-sa.db: what Wikipedia says about first aid, section by section, in its own words.

  python tools/build_firstaid.py --fetch     download the revisions named below into downloads/, then build
  python tools/build_firstaid.py             build from what is already in downloads/
  python tools/build_firstaid.py --show      print every passage as it would be stored, and build nothing
  python tools/build_firstaid.py --fetch --latest --show
                                             the same from today's revisions, to read before they are trusted

Wikipedia's text is under CC BY-SA 4.0: it may be copied and passed on with a link to the page and the name of
the licence, and whatever is made from it has to carry the same licence. That is why it sits in a file of its
own, apart from everything else ("sa" stands for share-alike).

No published first-aid guideline was found whose terms allow it to be passed on, so this is an encyclopaedia's
account of the guidelines and not a guideline. Two things follow, and they are the reason this script is strict:

  The revisions are pinned. READ names the revision of each article that somebody read, passage by passage,
  before it went in. Anyone can edit Wikipedia, so a newer revision is fetched only with --latest, and has to be
  read in full (--show) before its number is written into READ.

  Not every section is taken. A section is left out where it is not first aid, or where it says something no
  first-aid body teaches: the article on choking, as read, suggests reaching into an unconscious person's throat
  with kitchen tools. UNSOUND holds words that stop the build if they ever turn up in a passage.

What this script changes: HTML becomes plain text (paragraphs, "- " list items), footnote marks are dropped, and
curly quotes and long dashes become straight ones. No wording is changed. Where only the opening paragraphs of
a section are taken, the passage's title says so.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from html.parser import HTMLParser

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, desk

STEM = "firstaid-sa"
API = "https://en.wikipedia.org/w/api.php"
PAGE = "https://en.wikipedia.org/w/index.php?title=%s&oldid=%d"
LICENCE_NAME = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
TERMS_TITLE = "Wikipedia:Reusing Wikipedia content"
TERMS_FILE = "wikipedia-reusing-content.json"
TERMS_WORDS = ("creative commons attribution share-alike license", "attribution-share-alike license 4.0")
# the revision of each article that was read before it went in
READ = {
    "Cardiopulmonary resuscitation": 1382701468,
    "Recovery position": 1316139441,
    "Emergency bleeding control": 1372598793,
    "Burn": 1385540835,
    "Choking": 1384678935,
}
LEAD = ""
# topic, article, section ('' is the opening of the article), how much of it, and words it is known by.
# 'paragraphs' takes that many from the top; 'whole' takes the section with what is under it; 'top' stops at
# the first heading under it
PASSAGES = (
    ("cpr", "Cardiopulmonary resuscitation", "Order of CPR in a first aid sequence", "whole",
     ("Calling by phone for emergency medical services",)),
    ("cpr", "Cardiopulmonary resuscitation", "Compressions with rescue breaths", "whole", ("30:2", "at least 100 compressions per minute")),
    ("cpr", "Cardiopulmonary resuscitation", "Compression only", "whole", ("compression-only CPR",)),
    ("recovery", "Recovery position", LEAD, 1, ("unconscious but breathing",)),
    ("recovery", "Recovery position", "Purpose", "whole", ("six key principles",)),
    ("bleeding", "Emergency bleeding control", "Direct pressure", "whole", ("Direct pressure is the common method",)),
    ("bleeding", "Emergency bleeding control", "Tourniquet", "whole", ("Improvised tourniquets",)),
    ("burns", "Burn", "Wound care", 2, ("cool water", "20 minutes of cool running water")),
    ("choking", "Choking", 'General strategy: "five and five"', "whole", ("five and five",)),
    ("choking", "Choking", "Cough", "whole", ("continue coughing",)),
    ("choking", "Choking", "Back blows (back slaps)", "whole", ("between the shoulder blades",)),
    ("choking", "Choking", "Abdominal thrusts (Heimlich maneuver)", "whole", ("between the chest and the belly button",)),
    ("choking", "Choking", "Chest thrusts", "whole", ("lower half of the chest bone",)),
    ("choking", "Choking", "Infants (babies under 1 year-old)", "top", ("five back blows and five chest compressions",)),
)
UNSOUND = ("toothpick", "kitchen tweezers", "forks and spoons")
PACE = 1.0

LICENCE = """firstaid-sa.db: where its contents come from, and on what terms

Passages on first aid from the English Wikipedia: cardiopulmonary resuscitation, the recovery position,
bleeding, burns and choking. Each passage is a section of an article, or the opening paragraphs of one, in
the article's own words, from the one revision the file names for it.

Licence: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
https://creativecommons.org/licenses/by-sa/4.0/

What that asks of anyone who passes this file on, or anything made from it:
- Credit. Each passage carries the address of the page and revision it was taken from, which is the credit
  Wikipedia asks for: "a hyperlink (where possible) or URL to the page or pages you are re-using"
  (https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content). Keep it with the passage.
- The same licence. This file, and anything adapted from it, may only be passed on under CC BY-SA 4.0 or a
  later version of it. That condition belongs to this file. It does not reach the code or the other
  databases, which sit beside it under their own terms.
- Changes are named. Changed in the making of this file: HTML turned into plain text, footnote marks dropped,
  curly quotes and long dashes made straight. No wording was changed. Where only the opening paragraphs of a
  section were taken, the passage's title says so.

The authors are Wikipedia's contributors; each article's history lists them. Neither they nor the Wikimedia
Foundation endorse this skill.

This is an encyclopaedia's account of first-aid guidelines. It is not a guideline, anyone can edit the
articles, and the file is as old as the revisions it names. The instructions of an emergency operator, and
a current guideline of a first-aid body, both come before it.
"""


# ---- an article's HTML as plain text

class Plain(HTMLParser):
    """A section of an article as text: paragraphs, '## ' headings, '- ' list items. Footnote marks, pictures,
    tables, notes in boxes and the links for editing are left out."""
    VOID = ("br", "img", "hr", "input", "meta", "link", "wbr", "source", "track", "area", "col", "embed", "param", "base")
    HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
    OUT_TAGS = ("style", "script", "figure", "table")
    OUT_CLASSES = ("reference", "mw-editsection", "hatnote", "thumb", "reflist", "mw-references-wrap", "navbox", "metadata",
                   "ambox", "infobox", "gallery", "noprint", "mw-empty-elt", "shortdescription", "sidebar", "Inline-Template",
                   "mw-cite-backlink", "citation-needed-content")

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag not in self.VOID:
                self.skip += 1
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag in self.OUT_TAGS or any(c in self.OUT_CLASSES for c in classes):
            if tag not in self.VOID:
                self.skip = 1
            return
        if tag in self.HEADINGS:
            self.out.append("\n\n## ")
        elif tag in ("p", "ul", "ol", "dl", "blockquote"):
            self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("br", "dt", "dd"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in self.VOID:
                self.skip -= 1
            return
        if tag in self.HEADINGS or tag in ("p", "ul", "ol", "dl", "blockquote"):
            self.out.append("\n\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def plain(html):
    parser = Plain()
    parser.feed(html or "")
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.out).split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return desk.fix_text(text)


# ---- Wikipedia, through its API

def api(params):
    url = API + "?" + urllib.parse.urlencode(dict(params, format="json", formatversion="2"))
    data, _ = dbtools.get(url, "application/json")
    time.sleep(PACE)
    return json.loads(data.decode("utf-8"))


def file_of(article):
    return "wikipedia-%s.json" % core.key(article)


def fetch_article(folder, article, revision):
    """One article at one revision: its sections' HTML, saved as one file with a note of the day."""
    if revision is None:
        page = api({"action": "query", "prop": "revisions", "titles": article, "rvprop": "ids|timestamp"})["query"]["pages"][0]
    else:
        page = api({"action": "query", "prop": "revisions", "revids": revision, "rvprop": "ids|timestamp"})["query"]["pages"][0]
    if page.get("title") != article or not page.get("revisions"):
        sys.exit("Wikipedia has no such revision of \"%s\"" % article)
    revision, stamp = page["revisions"][0]["revid"], page["revisions"][0]["timestamp"]
    listed = api({"action": "parse", "oldid": revision, "prop": "sections"})["parse"]["sections"]
    index = dict((re.sub(r"<[^>]+>", "", s["line"]).strip(), s["index"]) for s in listed)
    wanted = sorted(set(section for _, name, section, _, _ in PASSAGES if name == article))
    sections = {}
    for section in wanted:
        number = "0" if section == LEAD else index.get(section)
        if number is None:
            sys.exit("\"%s\" has no section \"%s\" at revision %d: the article has changed. Read it again" % (article, section, revision))
        got = api({"action": "parse", "oldid": revision, "section": number, "prop": "text", "disableeditsection": "1",
                   "disabletoc": "1", "disablelimitreport": "1"})
        sections[section] = got["parse"]["text"]
    doc = {"title": article, "revision": revision, "timestamp": stamp, "sections": sections}
    dbtools.save(os.path.join(folder, file_of(article)), (json.dumps(doc, ensure_ascii=True, indent=1) + "\n").encode("utf-8"),
                 PAGE % (urllib.parse.quote(article.replace(" ", "_")), revision))
    say("fetched   %s, revision %d of %s" % (article, revision, stamp[:10]))


def fetch_all(folder, latest):
    os.makedirs(folder, exist_ok=True)
    got = api({"action": "parse", "page": TERMS_TITLE, "prop": "text", "disableeditsection": "1"})
    dbtools.save(os.path.join(folder, TERMS_FILE), (json.dumps(got["parse"], ensure_ascii=True) + "\n").encode("utf-8"),
                 "https://en.wikipedia.org/wiki/" + TERMS_TITLE.replace(" ", "_"))
    for article in READ:
        fetch_article(folder, article, None if latest else READ[article])


def check_terms(folder):
    try:
        with open(os.path.join(folder, TERMS_FILE), encoding="utf-8") as f:
            text = " ".join(plain(json.load(f)["text"]).lower().split())
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("Wikipedia's page on reusing its content is not in the downloads folder ('--fetch' gets it)")
    for words in TERMS_WORDS:
        if words not in text:
            sys.exit("Wikipedia's page on reusing its content no longer says \"%s\": read it again before anything is passed on" % words)


# ---- cutting the passages

def read_article(folder, article):
    try:
        with open(os.path.join(folder, file_of(article)), encoding="utf-8") as f:
            doc = json.load(f)
        doc["revision"], doc["timestamp"], doc["sections"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("\"%s\" is not in the downloads folder ('--fetch' gets it)" % article)
    return doc


def passage(doc, section, how):
    """(the title to store, the text): a section whole, down to its first heading, or its opening paragraphs."""
    if section not in doc["sections"]:
        sys.exit("the download of \"%s\" has no section \"%s\": fetch it again" % (doc["title"], section))
    lines = plain(doc["sections"][section]).split("\n")
    if section != LEAD and lines and lines[0].startswith("## "):
        lines = lines[1:]                               # the section's own heading is its title
    if how == "top":
        cut = next((n for n, line in enumerate(lines) if line.startswith("## ")), len(lines))
        lines = lines[:cut]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    title = section or "%s (the opening of the article)" % doc["title"]
    if isinstance(how, int):
        blocks = [b for b in text.split("\n\n") if b.strip()]
        text = "\n\n".join(blocks[:how])
        title = "%s (the opening of the article)" % doc["title"] if section == LEAD else (
            "%s (its first %s)" % (section, "paragraph" if how == 1 else "%d paragraphs" % how))
    return title, text


def read_passages(folder, latest):
    """[(topic, article, title, text)] and the articles as read from the downloads."""
    docs, out = {}, []
    for topic, article, section, how, known in PASSAGES:
        if article not in docs:
            docs[article] = read_article(folder, article)
            if not latest and docs[article]["revision"] != READ[article]:
                sys.exit("the download of \"%s\" is revision %s, and the one that was read is %d. Fetch again, or read the "
                         "new one in full (--latest --show) and put its number into READ" % (
                             article, docs[article]["revision"], READ[article]))
        title, text = passage(docs[article], section, how)
        what = "\"%s\", \"%s\"" % (article, section or "the opening")
        if not text:
            sys.exit("%s: nothing is there any more" % what)
        for words in known:
            if words not in text:
                sys.exit("%s: the passage does not hold \"%s\". The article has changed: read it again" % (what, words))
        for words in UNSOUND:
            if words in text.lower():
                sys.exit("%s: the passage holds \"%s\", which no first-aid body teaches. It stays out" % (what, words))
        if "\ufffd" in text:
            sys.exit("%s: the passage holds a character that could not be read" % what)
        out.append((topic, article, title, text))
    return out, docs


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    check_terms(a.downloads)
    found, docs = read_passages(a.downloads, a.latest)
    if a.show:
        for topic, article, title, text in found:
            print("=== %s | %s, revision %s | %s\n%s\n" % (topic, article, docs[article]["revision"], title, text))
        return None
    if a.latest:
        sys.exit("--latest is for reading (--show): a revision goes into the file once it has been read and its number is in READ")
    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        sources, pages = {}, {}
        for article in READ:
            doc = docs[article]
            pages[article] = PAGE % (urllib.parse.quote(article.replace(" ", "_")), doc["revision"])
            _, day = dbtools.origin(os.path.join(a.downloads, file_of(article)), retrieved=a.retrieved)
            sources[article] = dbtools.add_source(
                con, "Wikipedia: \"%s\", revision %d of %s" % (article, doc["revision"], doc["timestamp"][:10]), pages[article], day,
                LICENCE_NAME, "Wikipedia contributors, \"%s\" (%s). %s (%s). An excerpt, as plain text; no wording changed" % (
                    article, pages[article], LICENCE_NAME, LICENCE_URL))
        con.execute("CREATE TABLE passage (id INTEGER PRIMARY KEY, topic TEXT NOT NULL, part INTEGER NOT NULL, title TEXT NOT NULL, "
                    "text TEXT NOT NULL, url TEXT NOT NULL, dated TEXT NOT NULL, source INTEGER NOT NULL)")
        for part, (topic, article, title, text) in enumerate(found, 1):
            con.execute("INSERT INTO passage (topic, part, title, text, url, dated, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (topic, part, title, text, pages[article], docs[article]["timestamp"][:10], sources[article]))
        con.execute("CREATE INDEX passage_topic ON passage (topic, part)")
        import vosslib
        size = dbtools.finish(con, path, core.today(), facts=(("format", 1), ("toolkit", vosslib.VERSION), ("passages", len(found))))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d passages on %s" % (len(found), ", ".join(sorted(set(t for t, _, _, _ in found)))))
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download the articles and Wikipedia's terms into the downloads folder first")
    ap.add_argument("--latest", action="store_true", help="with --fetch and --show: today's revisions, to read before they are trusted")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the articles were downloaded, for files fetched by hand")
    ap.add_argument("--show", action="store_true", help="print every passage as it would be stored, and build nothing")
    ap.add_argument("--out", metavar="DIR", help="where to write firstaid-sa.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads, a.latest)
    return build(a)


if __name__ == "__main__":
    main()
