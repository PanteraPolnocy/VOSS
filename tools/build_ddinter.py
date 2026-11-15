"""Build src/scripts/data/ddinter.db: which medicines are known to interact, and how seriously, from DDInter 2.0.

  python tools/build_ddinter.py --fetch      download what is needed into downloads/, then build
  python tools/build_ddinter.py              build from what is already in downloads/
  python tools/build_ddinter.py --files FILE [FILE ...] --names FILE --retrieved 2026-11-15

DDInter 2.0 (https://ddinter2.scbdd.com/) is a curated database of drug interactions. Its own terms page
says: "The DDInter data is made available under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International license" (read on 15 November 2026). So this database is under that licence too, in a file
of its own, with the licence text beside it. It is NOT under the licence of the code: it may be passed on
with attribution, under the same licence, and not for commercial purposes.

What DDInter lets anyone download is less than what its website shows, and the build says so wherever the
data is used:
  - pairs of medicines with a severity grade (Major, Moderate, Minor, Unknown), and nothing else. There is
    no account of why two medicines interact or what to do about it, no food or disease interactions, and
    no list of duplicated treatments. Those are on the website only, and are not taken from it.
  - only eight of the fourteen groups of the ATC classification have a download (A, B, D, H, L, P, R, V).
    A pair is in the files if at least one of its two medicines is in one of those groups. A pair of two
    medicines from the other groups (the heart and circulation, the nervous system, anti-infectives, among
    others) is not in the files at all, however well known the interaction is.

Names. DDInter calls each medicine by one name, sometimes the American one (acetaminophen) and sometimes
the international one (salbutamol). So that a medicine is found under the name a person knows, other names
for the same substance are taken from Wikidata (CC0): the labels and aliases, in English and eight more languages, of items
that carry an ATC code, matched to a DDInter name letter for letter. Where a name matches more than one
item, nothing is taken. The tool always says which DDInter entry a name was read as.

Wikidata is read through its ordinary API, a batch at a time. It keeps unnamed scripts on a short leash, so
that part is slow; it waits when told to and picks up where it stopped.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, interactions

STEM = "ddinter"
SITE = "https://ddinter2.scbdd.com"
TERMS_PAGE = SITE + "/terms/"
TERMS_FILE = "ddinter-terms.html"
DOWNLOAD_PAGE = SITE + "/download/"
FILE_RE = re.compile(r"/static/media/download/(ddinter_downloads_code_([A-Z])\.csv)")
# the terms page must still say this, or somebody reads it again before the data goes out
TERMS_WORDS = ("creative commons attribution-noncommercial-sharealike 4.0",)
LICENCE = "CC BY-NC-SA 4.0: attribution, non-commercial use only, passed on under the same licence"
CREDIT = ("DDInter 2.0 (https://ddinter2.scbdd.com/). Tian Y, Yi J, Wang N, Wu C, et al. DDInter 2.0: an enhanced drug "
          "interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic "
          "Acids Research 53(D1):D1356, doi:10.1093/nar/gkae726. CC BY-NC-SA 4.0")
HEADER = ["DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"]
LEVELS = {"Unknown": 0, "Minor": 1, "Moderate": 2, "Major": 3}
ID_RE = re.compile(r"^DDInter(\d+)$")
MIN_PAIRS, MIN_DRUGS, MIN_NAMES = 100000, 1500, 2500
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
NAMES_FILE = "drug-names.wikidata.json"
LANGUAGES = core.NAME_LANGUAGES
PACE, MAX_PACE = 0.5, 6.0
MIN_ALIAS, MAX_ALIAS = 3, 60


# ---- DDInter's files

def read_pairs(paths):
    """({drug number: name}, {(a, b): level}, [groups read], notes, {drug number: within reach or not}). a < b;
    where two files grade a pair differently the more serious grade is kept, and counted.

    Reach. Each file holds every interaction that involves a medicine of its group. So a medicine that is
    in one of those groups has all of its pairs in that one file. A medicine whose pairs are spread over
    several files, with no file holding them all, is therefore in none of the groups that have a download:
    it is out of reach, and a pair of two such medicines cannot be in the files whether or not they
    interact. That much is certain. The other way round is not: a medicine with all its pairs in one file
    may only happen to have partners in one group."""
    drugs, pairs, groups, notes, clashes = {}, {}, [], [], 0
    partners = {}
    for path in sorted(paths):
        m = re.search(r"code_([A-Z])\.csv$", os.path.basename(path))
        groups.append(m.group(1) if m else os.path.basename(path))
        group = groups[-1]
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        except (OSError, UnicodeDecodeError, csv.Error):
            sys.exit("%s cannot be read as a CSV file" % os.path.basename(path))
        if not rows or [c.strip() for c in rows[0]] != HEADER:
            sys.exit("%s does not have the columns this script knows: DDInter has changed its files. Nothing was built"
                     % os.path.basename(path))
        for n, row in enumerate(rows[1:], 2):
            if not any(c.strip() for c in row):
                continue
            if len(row) != 5:
                sys.exit("%s line %d has %d fields, not 5" % (os.path.basename(path), n, len(row)))
            id_a, name_a, id_b, name_b, level = [c.strip() for c in row]
            ma, mb = ID_RE.match(id_a), ID_RE.match(id_b)
            if not ma or not mb or level not in LEVELS or not name_a or not name_b:
                sys.exit("%s line %d is not in the shape this script knows" % (os.path.basename(path), n))
            a, b = int(ma.group(1)), int(mb.group(1))
            for number, name in ((a, name_a), (b, name_b)):
                if drugs.setdefault(number, name) != name:
                    sys.exit("%s line %d: one DDInter number under two names" % (os.path.basename(path), n))
            if a == b:
                continue
            pair = (min(a, b), max(a, b))
            grade = LEVELS[level]
            if pair in pairs and pairs[pair] != grade:
                clashes += 1
                grade = max(grade, pairs[pair])
            pairs[pair] = grade
            partners.setdefault(a, {}).setdefault(group, set()).add(b)
            partners.setdefault(b, {}).setdefault(group, set()).add(a)
    reach = {}
    for number in drugs:
        by_file = partners.get(number, {})
        everyone = set().union(*by_file.values()) if by_file else set()
        # a medicine with no pair at all proves nothing either way: it is left within reach
        reach[number] = not by_file or any(found == everyone for found in by_file.values())
    if clashes:
        notes.append("%s graded differently in two files: the more serious grade was kept" % core.plural(clashes, "pair is", "pairs are"))
    if len(pairs) < MIN_PAIRS or len(drugs) < MIN_DRUGS:
        sys.exit("only %d pairs of %d medicines were read, where some 160,000 of 1,900 are expected: these are not all of "
                 "DDInter's files" % (len(pairs), len(drugs)))
    return drugs, pairs, sorted(groups), notes, reach


def base_name(name):
    """A DDInter name without a bracket at its end: 'Abametapir (topical)' is also 'Abametapir'."""
    m = re.fullmatch(r"(.+?)\s*\([^()]*\)", name)
    return m.group(1) if m else None


# ---- other names for the same substance, from Wikidata

_pace = [PACE]


def api(params):
    """One request to Wikidata, then a breath. Each time the server asks for a pause the breath gets longer."""
    url = WIKIDATA_API + "?" + urllib.parse.urlencode(dict(params, format="json"))
    before = dbtools.pauses
    data, _ = dbtools.get(url, "application/json")
    if dbtools.pauses > before:
        _pace[0] = min(_pace[0] * 1.5, MAX_PACE)
    time.sleep(_pace[0])
    return json.loads(data.decode("utf-8"))


def fetch_names(path):
    """The labels and aliases, in the languages of core.NAME_LANGUAGES, of every Wikidata item that carries an ATC code."""
    found, more = [], {}
    while True:
        got = api(dict({"action": "query", "list": "search", "srnamespace": 0, "srlimit": 500, "srprop": "",
                        "srsearch": "haswbstatement:P267"}, **more))
        found += [row["title"] for row in got.get("query", {}).get("search", [])]
        more = got.get("continue") or {}
        if not more:
            break
    found = sorted(set(found), key=lambda q: int(q[1:]))
    if len(found) < MIN_NAMES:
        sys.exit("Wikidata named only %d items with an ATC code: something is wrong, nothing was saved" % len(found))
    partial, day, done = path + ".partial", core.today().isoformat(), {}
    try:
        with open(partial, encoding="utf-8") as f:
            kept = json.load(f)
        if kept.get("day") == day:
            done = kept["done"]
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    todo = [q for q in found if q not in done]
    say("wikidata  %d items to read, fifty at a time%s" % (len(todo), " (%d already read today)" % len(done) if done else ""))

    def keep():
        with open(partial, "w", encoding="utf-8") as f:
            json.dump({"day": day, "done": done}, f)

    try:
        for i in range(0, len(todo), 50):
            got = api({"action": "wbgetentities", "ids": "|".join(todo[i:i + 50]), "props": "labels|aliases",
                       "languages": "|".join(LANGUAGES)})
            for qid, entity in got.get("entities", {}).items():
                names = {}
                for lang in LANGUAGES:
                    label = (entity.get("labels", {}).get(lang) or {}).get("value", "")
                    aliases = [a.get("value", "") for a in entity.get("aliases", {}).get(lang, [])]
                    names[lang] = [x for x in [label] + aliases if x]
                done[qid] = names
            keep()
            if (i // 50 + 1) % 10 == 0:
                say("wikidata  %d of %d" % (min(i + 50, len(todo)), len(todo)))
    finally:
        keep()
    doc = {"what": "Labels and aliases, in %s, of the Wikidata items that carry an ATC code (property P267). " % ", ".join(LANGUAGES) +
                   "Read through the API by tools/build_ddinter.py.",
           "items": dict((q, done[q]) for q in found if q in done)}
    dbtools.save(path, (json.dumps(doc, ensure_ascii=True, indent=0) + "\n").encode("utf-8"),
                 "https://www.wikidata.org/wiki/Property:P267")
    os.remove(partial)
    say("fetched   %s (%d items)" % (os.path.basename(path), len(doc["items"])))


def read_names(path):
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)["items"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("%s is not the names file this script writes ('--fetch' makes one)" % os.path.basename(path))
    if len(items) < MIN_NAMES:
        sys.exit("only %d items are in the names file, where some 3,700 are expected: nothing was built" % len(items))
    return items


def other_names(drugs, items):
    """{drug number: [(name, language)]} taken from the one Wikidata item whose English name is the DDInter name.
    Also how many medicines found their item, and how many matched several and so got nothing."""
    by_key = {}
    for qid, names in items.items():
        for name in names.get("en") or []:
            by_key.setdefault(core.key(name), set()).add(qid)
    out, matched, unsure = {}, 0, 0
    for number, name in drugs.items():
        hits = set(by_key.get(core.key(name), ()))
        if not hits and base_name(name):
            hits = set(by_key.get(core.key(base_name(name)), ()))
        if len(hits) > 1:
            unsure += 1
            continue
        if not hits:
            continue
        matched += 1
        seen, extra = set([core.key(name)]), []
        for lang in LANGUAGES:
            for other in items[next(iter(hits))].get(lang) or []:
                other = " ".join(other.split())
                folded = core.key(other)
                if MIN_ALIAS <= len(other) <= MAX_ALIAS and len(folded) >= MIN_ALIAS and folded not in seen:
                    seen.add(folded)
                    extra.append((other, lang))
        out[number] = extra
    return out, matched, unsure


# ---- fetching

def fetch_all(folder):
    os.makedirs(folder, exist_ok=True)
    dbtools.fetch(TERMS_PAGE, TERMS_FILE, "text/html", folder=folder)
    page, _ = dbtools.get(DOWNLOAD_PAGE)
    names = sorted(set(m[0] for m in FILE_RE.findall(page.decode("utf-8", "replace"))))
    if not names:
        sys.exit("no download file is linked from %s: the page has changed" % DOWNLOAD_PAGE)
    for name in names:
        dbtools.fetch(SITE + "/static/media/download/" + name, name, folder=folder)
    fetch_names(os.path.join(folder, NAMES_FILE))


def check_terms(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = " ".join(re.sub(r"<[^>]+>", " ", f.read()).lower().split())
    except OSError:
        sys.exit("DDInter's terms page is not in the downloads folder ('--fetch' gets it): the build does not go on without it")
    missing = [w for w in TERMS_WORDS if w not in text]
    if missing:
        sys.exit("DDInter's terms page no longer says \"%s\": read %s before this data goes out, and put TERMS_WORDS, LICENCE "
                 "and the licence text in this script right" % (missing[0], TERMS_PAGE))
    return dbtools.origin(path)[1]


# ---- building

LICENCE_TEXT = """ddinter.db: what it is, and on what terms

This file holds drug-drug interactions from DDInter 2.0: which pairs of medicines are known to interact,
and the severity grade DDInter gives each pair. https://ddinter2.scbdd.com/

  Tian Y, Yi J, Wang N, Wu C, et al. DDInter 2.0: an enhanced drug interaction resource with expanded
  data coverage, new interaction types, and improved user interface. Nucleic Acids Research 53(D1):D1356.
  doi:10.1093/nar/gkae726

Licence: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)
  https://creativecommons.org/licenses/by-nc-sa/4.0/
DDInter's terms: "The DDInter data is made available under a Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International license." (https://ddinter2.scbdd.com/terms/)

This file is NOT under the licence of the code it ships with. You may copy it and pass it on, and build
on it, if you:
  - give the credit above, and say what was changed;
  - do not use it for commercial purposes. Anyone who uses this skill commercially must take this file
    out first: the tools then say that no interaction data is installed, and nothing else changes;
  - pass on anything you make from it under this same licence.

What was changed in the making of this file: DDInter's download files (one for each of eight groups of
the ATC classification) were merged into one list of pairs; a pair listed in two files is stored once;
the severity grade is stored as a number (3 Major, 2 Moderate, 1 Minor, 0 Unknown); and the pairs are
stored packed, each medicine with the numbers of the medicines it is paired with. No pair and no grade
was added, removed or altered.

What this file does not hold. DDInter's downloads carry pairs and grades only: no account of why two
medicines interact or what to do about it, and no food, disease or duplication data. They cover a pair
only if at least one of its medicines is in ATC group A, B, D, H, L, P, R or V. A pair that is not in this
file is therefore not known to be safe. DDInter's own disclaimer: "the absence of an interaction does not
necessarily mean no interactions exist."

DDInter does not endorse this skill. It is information, not advice: questions about medicines taken
together go to a pharmacist or a prescriber.

Other names for the medicines (so that "paracetamol" finds "Acetaminophen") come from Wikidata, property
P267 items, under Creative Commons CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/
They were matched by name and not checked one by one.
"""


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    files = a.files or sorted(os.path.join(a.downloads, n) for n in (os.listdir(a.downloads) if os.path.isdir(a.downloads) else [])
                              if re.fullmatch(r"ddinter_downloads_code_[A-Z]\.csv", n))
    names_path = a.names or os.path.join(a.downloads, NAMES_FILE)
    if not files or not all(os.path.isfile(p) for p in files):
        sys.exit("--files: none found. Run with --fetch, or download them by hand and name them (see the top of this script)")
    if not os.path.isfile(names_path):
        sys.exit("--names: no such file. Run with --fetch")
    days = [dbtools.origin(p, retrieved=a.retrieved)[1] for p in files]
    names_day = dbtools.origin(names_path, retrieved=a.retrieved)[1]
    terms_day = core.a_date(a.terms_read, "--terms-read") if a.terms_read else check_terms(os.path.join(a.downloads, TERMS_FILE))
    drugs, pairs, groups, notes, reach = read_pairs(files)
    extra, matched, unsure = other_names(drugs, read_names(names_path))

    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        src = dbtools.add_source(con, "DDInter 2.0: drug-drug interactions, the download files for ATC groups %s" % ", ".join(groups),
                                 DOWNLOAD_PAGE, min(days), LICENCE, CREDIT)
        src_names = dbtools.add_source(con, "Wikidata: other names for medicines (labels and aliases of items with an ATC code, P267)",
                                       "https://www.wikidata.org/wiki/Property:P267", names_day, "CC0 1.0, a public domain dedication", "")
        # reach: 0 where the files prove the medicine is in none of the groups that have a download
        con.execute("CREATE TABLE drug (id INTEGER PRIMARY KEY, name TEXT NOT NULL, reach INTEGER NOT NULL)")
        # kind: 0 for DDInter's own name, then one for each language of the other names, as interactions.NAME_KINDS has them
        con.execute("CREATE TABLE drug_name (folded TEXT NOT NULL, drug INTEGER NOT NULL, shown TEXT NOT NULL, kind INTEGER NOT NULL, "
                    "source INTEGER NOT NULL, PRIMARY KEY (folded, drug)) WITHOUT ROWID")
        # a medicine and everything it is paired with, packed: a table of the pairs is seven times the size
        con.execute("CREATE TABLE partners (drug INTEGER PRIMARY KEY, data BLOB NOT NULL)")
        added = 0
        for number in sorted(drugs):
            name = drugs[number]
            con.execute("INSERT INTO drug VALUES (?, ?, ?)", (number, name, 1 if reach[number] else 0))
            con.execute("INSERT OR IGNORE INTO drug_name VALUES (?, ?, ?, 0, ?)", (core.key(name), number, name, src))
            if base_name(name):
                con.execute("INSERT OR IGNORE INTO drug_name VALUES (?, ?, ?, 0, ?)", (core.key(base_name(name)), number, name, src))
        for number in sorted(extra):
            for other, lang in extra[number]:
                cur = con.execute("INSERT OR IGNORE INTO drug_name VALUES (?, ?, ?, ?, ?)",
                                  (core.key(other), number, other, interactions.NAME_KINDS.index("also called (%s)" % lang), src_names))
                added += cur.rowcount
        with_whom = {}
        for (first, second), level in pairs.items():
            with_whom.setdefault(first, {})[second] = level
            with_whom.setdefault(second, {})[first] = level
        con.executemany("INSERT INTO partners VALUES (?, ?)",
                        [(number, interactions.pack_partners(with_whom[number])) for number in sorted(with_whom)])
        counts = dict((word, sum(1 for v in pairs.values() if v == n)) for word, n in LEVELS.items())
        size = dbtools.finish(con, path, core.today(), facts=(
            ("format", 3), ("groups", "".join(groups)), ("drugs", len(drugs)), ("pairs", len(pairs)), ("major", counts["Major"]),
            ("moderate", counts["Moderate"]), ("minor", counts["Minor"]), ("unknown", counts["Unknown"]),
            ("named-through-wikidata", matched), ("out-of-reach", sum(1 for v in reach.values() if not v)),
            ("terms-read", terms_day.isoformat())))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE_TEXT, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d pairs of %d medicines, from the files for ATC groups %s" % (len(pairs), len(drugs), ", ".join(groups)))
    say("          graded: %d major, %d moderate, %d minor, %d with no grade given" % (
        counts["Major"], counts["Moderate"], counts["Minor"], counts["Unknown"]))
    say("          out of reach: %d medicines are in none of the groups that have a download; a pair of two of them cannot "
        "be in the file" % sum(1 for v in reach.values() if not v))
    say("          other names: %d medicines matched to one Wikidata item, %d other names taken; %d matched several and got none" % (
        matched, added, unsure))
    say("          retrieved: DDInter %s, names %s; terms page read %s" % (min(days), names_day, terms_day))
    for line in notes:
        say("          NOTE " + line)
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download everything into the downloads folder first")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--files", metavar="FILE", nargs="+", help="DDInter's download files (default: every ddinter_downloads_code_X.csv in downloads/)")
    ap.add_argument("--names", metavar="FILE", help="the names file that --fetch writes from Wikidata")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the files were downloaded, for files fetched by hand")
    ap.add_argument("--terms-read", metavar="DATE",
                    help="for a build with no terms page in downloads/: the day you read DDInter's terms yourself")
    ap.add_argument("--out", metavar="DIR", help="where to write ddinter.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads)
    a.files = [dbtools.fetch(f, os.path.basename(urllib.parse.urlparse(f).path), folder=a.downloads) if dbtools.is_url(f) else f
               for f in a.files or []] or None
    return build(a)


if __name__ == "__main__":
    main()
