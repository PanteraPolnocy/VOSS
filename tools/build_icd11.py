"""Build src/scripts/data/icd11.db: ICD-11, the codes and their titles, exactly as the World Health
Organization publishes them.

  python tools/build_icd11.py --fetch      download the release file and WHO's licence, then build
  python tools/build_icd11.py              build from what is already in downloads/
  python tools/build_icd11.py --tabulation FILE --release 2026-01 --retrieved 2026-11-15
  python tools/build_icd11.py --verify     put WHO's file back together from the database and compare the two

The source is the "Simple Tabulation" of ICD-11 for Mortality and Morbidity Statistics (MMS), which WHO
publishes with each yearly release and which needs no account:
  https://icdcdn.who.int/static/releasefiles/<release>/SimpleTabulation-ICD-11-MMS-en.zip

The licence is CC BY-ND 3.0 IGO, with WHO's own terms of use on top
(https://icd.who.int/en/docs/icd11-license.pdf, read on 15 November 2026). What they come to, for a file
like this one:
  - no adaptations. Building the classification into software is not one, WHO says, as long as it keeps its
    name and its attribution, and every entry keeps its code, its title and its URI;
  - no translations and no tables between ICD-11 and any other code system: those need a written agreement
    with WHO. There are none here, and none may be added;
  - anything added to an entry must be marked as not coming from WHO;
  - WHO's name is used to say where the classification comes from and for nothing else, and nothing may
    suggest that WHO endorses this skill.

So this script changes nothing. Every record of WHO's file goes into the database whole, character for
character, and '--verify' proves it by putting the file back together. The table beside the records (a
record's position, its parent's position, and its code, kind and chapter copied out so that it can be
found) adds no content, and the licence text beside the database says it is not WHO's. A title is not
copied anywhere: it is read from the record each time.

WHO is preparing an updated licence. The build therefore checks that the licence document is still the
one that was read, by its checksum, and stops if it is not: read the new one before the data goes out.
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import codes, core, store

STEM = "icd11"
RELEASE_URL = "https://icdcdn.who.int/static/releasefiles/%s/SimpleTabulation-ICD-11-MMS-en.zip"
RELEASE_RE = re.compile(r"^\d{4}-\d{2}$")
LICENCE_URL = "https://icd.who.int/en/docs/icd11-license.pdf"
LICENCE_FILE = "icd11-license.pdf"
# the licence document as it was read on 15 November 2026 (dated 7 October 2025 inside)
LICENCE_SHA256 = "bc73f6bc49775511222caa2c166414b21670d0b51d83458e7c3c164decd28891"
LICENCE_READ = "2026-11-15"
LICENCE = "CC BY-ND 3.0 IGO, with WHO's terms of use: unchanged, every entry with its code, title and URI; no translation, no mapping"
# WHO's own wording for the citation (clause 1.3 of its terms of use)
CITATION = ("International Classification of Diseases, Eleventh Revision (ICD-11), World Health Organization (WHO) 2019 "
            "https://icd.who.int/browse11. Licensed under the Creative Commons Attribution-NoDerivatives 3.0 IGO licence "
            "(CC BY-ND 3.0 IGO).")
COLUMNS = ("Foundation URI", "Linearization URI", "Code", "BlockId", "Title", "ClassKind", "DepthInKind", "IsResidual",
           "ChapterNo", "BrowserLink", "isLeaf", "Primary tabulation", "Grouping1", "Grouping2", "Grouping3", "Grouping4",
           "Grouping5", "CodingNote", "Parent")
KINDS = codes.KINDS
MIN_RECORDS = 30000
END = "\r\n"


# ---- reading WHO's file

def read_tabulation(path):
    """(header line, [records], checksum of the file, its size). Records are split where the file ends them, on
    CR LF: some coding notes have a bare line feed inside, which belongs to the note."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".txt") and "readme" not in n.lower()]
            if len(names) != 1:
                sys.exit("%s should hold exactly one tabulation .txt" % os.path.basename(path))
            raw = z.read(names[0])
    else:
        with open(path, "rb") as f:
            raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        sys.exit("the tabulation is not UTF-8 text: this is not the file this script knows")
    lines = text.split(END)
    if lines[-1] != "":
        sys.exit("the tabulation does not end with a line end: it is cut short")
    return lines[0], lines[1:-1], hashlib.sha256(raw).hexdigest(), len(raw)


def parse(header, records):
    """Check the file is the shape this script knows, and pick out what a lookup needs: [dict], one per record."""
    names = header.lstrip("\ufeff").split("\t")
    if tuple(names[:len(COLUMNS)]) != COLUMNS:
        sys.exit("the tabulation's columns are not the ones this script knows: WHO has changed the file. Nothing was built")
    if len(records) < MIN_RECORDS:
        sys.exit("only %d records were read, where some 37,000 are expected: this is not the whole tabulation" % len(records))
    rows, by_uri, used = [], {}, set()
    for n, record in enumerate(records, 1):
        f = record.split("\t")
        if len(f) != len(COLUMNS):
            sys.exit("record %d has %d fields, not %d: the file is not the shape this script knows" % (n, len(f), len(COLUMNS)))
        row = {"id": n, "foundation": f[0], "uri": f[1], "code": f[2], "block_id": f[3], "title": codes.title_of(record),
               "kind": f[5], "residual": f[7] == "True", "chapter": f[8], "leaf": f[10] == "True", "parent_uri": f[18]}
        if row["kind"] not in KINDS or not row["uri"] or not row["title"]:
            sys.exit("record %d has no URI, no title or an unknown kind: the file is not the shape this script knows" % n)
        if row["kind"] == "category":
            if not row["code"] or row["code"] in used:
                sys.exit("record %d: a category without a code, or a code used twice" % n)
            used.add(row["code"])
        if row["foundation"]:
            by_uri[row["foundation"]] = n
        rows.append(row)
    for row in rows:
        row["parent"] = by_uri.get(row["parent_uri"]) if row["parent_uri"] else None
        if row["parent_uri"] and row["parent"] is None:
            sys.exit("record %d names a parent that is not in the file" % row["id"])
        if row["kind"] != "chapter" and row["parent"] is None:
            sys.exit("record %d is not a chapter and has no parent" % row["id"])
    return rows


def version_stamp(header):
    m = re.search(r"Version:\s*(.+)$", header)
    return m.group(1).strip() if m else ""


# ---- fetching

def fetch_all(folder, release=None):
    os.makedirs(folder, exist_ok=True)
    data, modified = dbtools.get(LICENCE_URL)
    dbtools.save(os.path.join(folder, LICENCE_FILE), data, LICENCE_URL, modified)
    say("fetched   %s (%s)" % (LICENCE_FILE, dbtools.size_words(len(data))))
    year = core.today().year
    for candidate in ([release] if release else ["%d-01" % y for y in (year + 1, year, year - 1)]):
        data, modified = dbtools.get(RELEASE_URL % candidate, missing_ok=True)
        if data is not None:
            name = "SimpleTabulation-ICD-11-MMS-en-%s.zip" % candidate
            dbtools.save(os.path.join(folder, name), data, RELEASE_URL % candidate, modified)
            say("fetched   %s (%s), release %s" % (name, dbtools.size_words(len(data)), candidate))
            return
    sys.exit("no release file was found at %s: say which release with --release, as WHO names it (2026-01)" % (RELEASE_URL % "<release>"))


def check_licence(folder):
    """The licence document must be the one that was read. A new one is read by a person before anything ships."""
    path = os.path.join(folder, LICENCE_FILE)
    try:
        with open(path, "rb") as f:
            found = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        sys.exit("WHO's licence document is not in the downloads folder ('--fetch' gets it): the build does not go on without it")
    if found != LICENCE_SHA256:
        sys.exit("WHO's licence document has changed since it was read on %s. Read the new one (%s). If it still allows "
                 "this file to be passed on, put its checksum in LICENCE_SHA256 and the day in LICENCE_READ, and write what "
                 "you found into SOURCES.md. Its checksum is %s" % (LICENCE_READ, LICENCE_URL, found))
    return dbtools.origin(path)[1]


# ---- building

LICENCE_TEXT = """icd11.db: what it is, and on what terms

This file holds ICD-11 for Mortality and Morbidity Statistics (MMS), release %(release)s, as the World
Health Organization publishes it in its "Simple Tabulation" file: every record, whole and unchanged.

  %(citation)s

Licence: Creative Commons Attribution-NoDerivatives 3.0 IGO
  https://creativecommons.org/licenses/by-nd/3.0/igo/
with WHO's terms of use for the classifications: https://icd.who.int/en/docs/icd11-license.pdf

This file is NOT under the licence of the code it ships with. It may be copied and passed on, unchanged,
with the citation above. Under WHO's terms:
  - it may not be adapted. Nothing in it has been: the classification was not reworded, shortened,
    re-ordered or renamed, and every entry keeps its code, its title and its URI. What was done is a change
    of file format, which the licence allows.
  - it may not be translated, and no table between ICD-11 and another code system may be made from it or
    added to it, without a written agreement with WHO. There is no translation and no such table here.
  - it is not to be used to develop or promote a different standard.
  - WHO's name appears here to say where the classification comes from, and for nothing else. WHO does not
    endorse this skill, its author or anything it says, and is not affiliated with it.

Not from WHO: the table "entity", which exists so that a record can be found. It holds each record's
position in WHO's file, the position of its parent, and where the record sits in the packed text, with
copies of its code, its block id, its chapter number, its kind (as a number) and two of its flags. They
add nothing to the classification and change nothing in it. No title is copied: a title is always read
from WHO's own record.

The records can be put back together into WHO's file, byte for byte: "python tools/build_icd11.py --verify"
does so and compares the result with the download. The checksum of WHO's file is in the table "build".

Source file: %(url)s
"""


def paths(a):
    tabulation = a.tabulation or dbtools.newest(a.downloads, "SimpleTabulation-ICD-11-MMS-en", (".zip", ".txt"))
    if not tabulation or not os.path.isfile(tabulation):
        sys.exit("--tabulation: no such file. Run with --fetch, or download it by hand and name it (see the top of this script)")
    url, day = dbtools.origin(tabulation, retrieved=a.retrieved)
    release = a.release
    if not release:
        m = re.search(r"/releasefiles/(\d{4}-\d{2})/", url) or re.search(r"(\d{4}-\d{2})\.(?:zip|txt)$", tabulation)
        release = m.group(1) if m else None
    if not release or not RELEASE_RE.match(release):
        sys.exit("say which release the file is, as WHO names it: --release 2026-01")
    return tabulation, url or RELEASE_URL % release, day, release


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    tabulation, url, day, release = paths(a)
    licence_day = check_licence(a.downloads) if not a.licence_read else core.a_date(a.licence_read, "--licence-read")
    header, records, checksum, size = read_tabulation(tabulation)
    rows = parse(header, records)
    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        source = dbtools.add_source(
            con, "ICD-11 for Mortality and Morbidity Statistics (MMS), release %s: the Simple Tabulation, World Health "
                 "Organization" % release, url, day, LICENCE, CITATION)
        # kind: its place in codes.KINDS. There is no column for the title on purpose: it is in the record
        con.execute("CREATE TABLE entity (id INTEGER PRIMARY KEY, code TEXT NOT NULL, block_id TEXT NOT NULL, kind INTEGER NOT NULL, "
                    "residual INTEGER NOT NULL, leaf INTEGER NOT NULL, chapter TEXT NOT NULL, parent INTEGER, "
                    "block INTEGER NOT NULL, start INTEGER NOT NULL, length INTEGER NOT NULL, source INTEGER NOT NULL)")
        # records are kept in the file's own order, so the pieces of one block are neighbours and squeeze well;
        # nothing is stored once for two records, because each has its own URI
        texts = dbtools.Texts(con, a.codec)
        for row, record in zip(rows, records):
            block, start, length = texts.add(record)
            con.execute("INSERT INTO entity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (row["id"], row["code"], row["block_id"], KINDS.index(row["kind"]), int(row["residual"]),
                         int(row["leaf"]), row["chapter"], row["parent"], block, start, length, source))
        raw, packed = texts.close()
        con.execute("CREATE INDEX entity_code ON entity (code) WHERE code != ''")
        con.execute("CREATE INDEX entity_block ON entity (block_id) WHERE block_id != ''")
        con.execute("CREATE INDEX entity_parent ON entity (parent)")
        counts = dict((k, sum(1 for r in rows if r["kind"] == k)) for k in KINDS)
        file_size = dbtools.finish(con, path, core.today(), facts=(
            ("format", 2), ("release", release), ("version-stamp", version_stamp(header)), ("header", header),
            ("tabulation-sha256", checksum), ("tabulation-bytes", size), ("records", len(rows)),
            ("chapters", counts["chapter"]), ("blocks", counts["block"]), ("categories", counts["category"]),
            ("licence-read", licence_day.isoformat()), ("licence-sha256", LICENCE_SHA256)))
    except BaseException:
        dbtools.discard(con, path)
        raise
    problem = verify(path, tabulation)
    if problem:
        os.remove(path)
        sys.exit("the database does not give WHO's file back unchanged (%s): it was deleted, and nothing ships" % problem)
    dbtools.write_licence(STEM, LICENCE_TEXT % {"release": release, "citation": CITATION, "url": url}, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(file_size)))
    say("          release %s (%s): %d chapters, %d blocks, %d categories" % (
        release, version_stamp(header) or "no version stamp", counts["chapter"], counts["block"], counts["category"]))
    say("          records: %s packed into %s (%.1f times smaller; blocks: %s)" % (
        dbtools.size_words(raw), dbtools.size_words(packed), raw / float(max(packed, 1)),
        ", ".join("%d %s" % (n, c) for c, n in sorted(texts.used.items()))))
    say("          checked: the records in the database put WHO's file back together, byte for byte")
    say("          retrieved %s; licence document read %s" % (day, licence_day))
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def rebuilt(con):
    """WHO's file, put back together from the database: bytes."""
    header = con.execute("SELECT value FROM build WHERE key = 'header'").fetchone()[0]
    reader = store.Reader(con)
    parts = [header]
    for block, start, length in con.execute("SELECT block, start, length FROM entity ORDER BY id"):
        parts.append(reader.text(block, start, length))
    return (END.join(parts) + END).encode("utf-8")


def verify(path, tabulation=None):
    """'' if the database gives WHO's file back unchanged, else what is wrong. With the download to hand the
    two are compared outright; without it, the rebuilt file is held against the checksum taken at the build."""
    from vosslib import library
    con = library.connect(path)
    try:
        again = rebuilt(con)
        recorded = con.execute("SELECT value FROM build WHERE key = 'tabulation-sha256'").fetchone()[0]
    finally:
        con.close()
    if hashlib.sha256(again).hexdigest() != recorded:
        return "the records no longer add up to the checksum taken when the file was built"
    if tabulation:
        _, _, checksum, _ = read_tabulation(tabulation)
        if checksum != recorded:
            return "the download is not the file the database was built from"
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download the release file and WHO's licence document first")
    ap.add_argument("--verify", action="store_true", help="put WHO's file back together from the database and compare; builds nothing")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--tabulation", metavar="FILE", help="the Simple Tabulation, .zip or .txt (default: the newest in downloads/)")
    ap.add_argument("--release", metavar="YYYY-MM", help="the release, as WHO names it (default: read from where the file came from)")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the file was downloaded, for a file fetched by hand")
    ap.add_argument("--licence-read", metavar="DATE",
                    help="for a build with no licence document in downloads/: the day you read WHO's terms yourself")
    ap.add_argument("--codec", help="how to pack the records: smallest (default), or one of %s" % ", ".join(store.CODECS))
    ap.add_argument("--out", metavar="DIR", help="where to write icd11.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.release and not RELEASE_RE.match(a.release):
        sys.exit("--release looks like 2026-01")
    if a.fetch:
        fetch_all(a.downloads, a.release)
    if a.tabulation and dbtools.is_url(a.tabulation):
        a.tabulation = dbtools.fetch(a.tabulation, os.path.basename(a.tabulation.split("?")[0]), folder=a.downloads)
    if a.verify:
        path = os.path.join(a.out or DATA, STEM + ".db")
        if not os.path.isfile(path):
            sys.exit("there is no icd11.db to verify")
        tabulation = a.tabulation or dbtools.newest(a.downloads, "SimpleTabulation-ICD-11-MMS-en", (".zip", ".txt"))
        problem = verify(path, tabulation if tabulation and os.path.isfile(tabulation) else None)
        if problem:
            sys.exit("NOT VERIFIED: " + problem)
        say("verified  the records in icd11.db put WHO's file back together, byte for byte%s" % (
            "" if tabulation and os.path.isfile(tabulation) else " (against the checksum taken at the build: the download is not here)"))
        return path
    return build(a)


if __name__ == "__main__":
    main()
