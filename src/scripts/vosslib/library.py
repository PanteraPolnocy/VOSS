"""The databases Voss answers from: where they are, what each says about itself, and how old it is.

Every database is one SQLite file in scripts/data/, opened read-only, with its licence text beside it as
LICENSE-<name>.txt. It carries a 'meta' table with a row for each source (source, url, retrieved, licence,
and optionally the credit line the licence asks for) and a 'build' table of key and value that holds the
day it was built. A file that cannot say where its rows came from is not answered from. Nothing here
fetches anything.
"""
import os
import sqlite3
from pathlib import Path

from . import core
from .core import DATA, command, die, more, parse_date, rec

# stem, what it holds, months before a warning (None: no fixed age), and the limit in words, as SOURCES.md lists it
EXPECTED = (
    ("core-pd", "MedlinePlus health topic summaries and emergency numbers", 6, "6 months"),
    ("icd11", "ICD-11 codes and titles, verbatim", None, "when WHO publishes a new annual release"),
    ("ddinter", "DDInter 2.0 interactions", 12, "12 months, or when a new DDInter release appears"),
    ("labels-us", "product labels of medicines sold in the United States", 6, "6 months"),
)
REGION_PREFIX = "region-"
REGION_LIMIT = (1, "1 month")
META_COLUMNS = ("source", "url", "retrieved", "licence")
LIMIT_TAG = "[pending]"


def folder():
    """Where the databases are: scripts/data/, unless VOSS_DATA names another folder."""
    return os.environ.get("VOSS_DATA") or DATA


def files():
    """Every database file in the folder, by name."""
    where = folder()
    try:
        names = sorted(n for n in os.listdir(where) if n.lower().endswith(".db"))
    except OSError:
        return []
    return [os.path.join(where, n) for n in names if os.path.isfile(os.path.join(where, n))]


def limit_for(stem):
    """(months or None, the limit in words, what the file holds or None if this version does not know it)."""
    for name, what, months, words in EXPECTED:
        if name == stem:
            return months, words, what
    if stem.startswith(REGION_PREFIX):
        return REGION_LIMIT[0], REGION_LIMIT[1], "region pack: registers, services and numbers for one country"
    return None, "", None


def connect(path):
    """Open a database read-only. Raises sqlite3.Error if it cannot be opened."""
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def read(path):
    """What one database file says about itself. Never raises: what is wrong goes in 'problems'."""
    stem = os.path.splitext(os.path.basename(path))[0]
    info = {"stem": stem, "path": path, "sources": [], "built": None, "problems": [], "size": 0,
            "licence_file": os.path.isfile(os.path.join(os.path.dirname(path), "LICENSE-%s.txt" % stem))}
    try:
        info["size"] = os.path.getsize(path)
        con = connect(path)
    except (OSError, sqlite3.Error):
        info["problems"].append("cannot be opened")
        return info
    try:
        columns = [row[1] for row in con.execute("PRAGMA table_info(meta)")]
        if not all(c in columns for c in META_COLUMNS):
            info["problems"].append("has no meta table with source, url, retrieved and licence")
        else:
            if "credit" in columns:
                rows = con.execute("SELECT source, url, retrieved, licence, credit FROM meta ORDER BY rowid").fetchall()
            else:
                rows = [r + ("",) for r in con.execute("SELECT source, url, retrieved, licence FROM meta ORDER BY rowid")]
            for source, url, retrieved, licence, credit in rows:
                day = parse_date(retrieved or "")
                if not (source and licence and day):
                    info["problems"].append("has a source row without a name, a licence or a retrieval date")
                    continue
                info["sources"].append({"source": str(source), "url": str(url or ""), "retrieved": day,
                                        "licence": str(licence), "credit": str(credit or "")})
            if not rows:
                info["problems"].append("names no source")
        row = None
        if any(r[1] == "key" for r in con.execute("PRAGMA table_info(build)")):
            row = con.execute("SELECT value FROM build WHERE key = ?", ("built",)).fetchone()
        info["built"] = parse_date(row[0]) if row and row[0] else None
        if info["built"] is None:
            info["problems"].append("does not say when it was built")
    except sqlite3.Error:
        info["problems"].append("cannot be read as a database")
    finally:
        con.close()
    if not info["licence_file"]:
        info["problems"].append("has no LICENSE-%s.txt beside it" % stem)
    return info


def installed():
    return [read(p) for p in files()]


def have(stem):
    """What one database says about itself, if it is installed and can be answered from; else None."""
    path = os.path.join(folder(), stem + ".db")
    if not os.path.isfile(path):
        return None
    info = read(path)
    return None if info["problems"] else info


def need(stem, what):
    """Open the database a command answers from: (connection, what the file says about itself). A file that
    is missing, or cannot say where its rows came from, stops the command with one plain line."""
    path = os.path.join(folder(), stem + ".db")
    if not os.path.isfile(path):
        die("%s.db is not installed, so there is nothing on file for %s. Look it up with the tools you have and cite "
            "it, or say you have no data" % (stem, what))
    info = read(path)
    if info["problems"]:
        die("%s.db cannot be answered from: it %s ('sources' has the rest). Until that is put right this is a cited "
            "lookup, or \"I have no data\"" % (stem, info["problems"][0]))
    try:
        return connect(path), info
    except sqlite3.Error:
        die("%s.db cannot be opened" % stem)


def _source(info, number):
    if not isinstance(number, int) or not 1 <= number <= len(info["sources"]):
        die("%s.db points at a source it does not name: rebuild or replace the file" % info["stem"])
    return info["sources"][number - 1]


def tag(info, number):
    """What goes with anything taken from one source of a database: the source, the day it was read, and the
    file with the day it was built."""
    s = _source(info, number)
    return "%s, retrieved %s [sourced: %s.db, built %s]" % (
        s["source"], s["retrieved"].isoformat(), info["stem"], info["built"].isoformat())


def credit(info, number):
    """The credit line the source asks for, or '' where it asks for none."""
    return _source(info, number)["credit"]


def warn_if_stale(info, today):
    """Doctrine 5: a file past its limit says so before the answer."""
    stale, note = age_note(info, today)
    if stale:
        rec("STALE", "%s.db: %s" % (info["stem"], note))


def usable(infos):
    return [i for i in infos if not i["problems"]]


def data_date(info):
    """The day the data is as old as: the earliest retrieval among its sources."""
    days = [s["retrieved"] for s in info["sources"]]
    return min(days) if days else info["built"]


def age_note(info, today):
    """(stale or not, a line about the file's age against its limit)."""
    months, words, known = limit_for(info["stem"])
    day = data_date(info)
    if day is None:
        return False, "age unknown"
    days = (today - day).days
    age = "retrieved %s, %s ago" % (day.isoformat(), core.plural(max(days, 0), "day"))
    if known is None:
        return False, "%s; no limit is set for this file" % age
    if months is None:
        return False, "%s; replace it %s %s (the tool cannot see that from here)" % (age, words, LIMIT_TAG)
    stale = core.add_months(day, months) < today
    if stale:
        return True, "%s: STALE, the limit is %s %s. Say so before any answer from it" % (age, words, LIMIT_TAG)
    return False, "%s; warn after %s %s" % (age, words, LIMIT_TAG)


def status(infos):
    """The words after 'data:' in the banner: 'not installed', or the build date of the oldest usable file."""
    days = [i["built"] for i in usable(infos)]
    return min(days).isoformat() if days else "not installed"


def _size(n):
    """A file's size as the build counts it: megabytes of a million bytes."""
    if n >= 100000:
        return "%.1f MB" % (n / 1e6)
    return "%d KB" % max(1, n // 1000)


def cmd_sources(a):
    today = core.today()
    infos = installed()
    where = folder() if os.environ.get("VOSS_DATA") else "scripts/data"
    if not infos:
        rec("SOURCES", "no database installed (looked in %s)" % where)
    else:
        rec("SOURCES", "%s in %s; banner status: %s" % (core.plural(len(infos), "database"), where, status(infos)))
    seen = set()
    for info in infos:
        seen.add(info["stem"])
        _, _, known = limit_for(info["stem"])
        rec("FILE", "%s.db (%s)%s%s" % (info["stem"], _size(info["size"]),
                                         ", built %s" % info["built"].isoformat() if info["built"] else "",
                                         "" if known else "; not a file this version knows"))
        for s in info["sources"]:
            more("source: %s | licence: %s | retrieved %s" % (s["source"], s["licence"], s["retrieved"].isoformat()))
            if s["url"]:
                more("  from %s" % s["url"])
            if s["credit"]:
                more("  credit, to be kept with every answer from it: %s" % s["credit"])
        if info["problems"]:
            for problem in info["problems"]:
                more("NOT USABLE: it %s" % problem)
            more("do not answer from this file until that is put right")
        else:
            more("licence text: LICENSE-%s.txt" % info["stem"])
            more("age: %s" % age_note(info, today)[1])
    for stem, what, _, words in EXPECTED:
        if stem not in seen:
            rec("NOT HERE", "%s.db: %s (limit: %s %s)" % (stem, what, words, LIMIT_TAG))
    if not any(s.startswith(REGION_PREFIX) for s in seen):
        rec("NOT HERE", "no region pack (%sXX.db): no registers, services or numbers for any country" % REGION_PREFIX)
    rec("BUILT IN", "the triage levels and red flags, the visit lists and the personal file's field list are written "
                    "for this skill: scripts/data/SOURCES.md says where each comes from")
    rec("RULE", "nothing is fetched while the tools run. An answer that needs a source the files do not hold is a "
                "cited lookup, or \"I have no data\"")


def register(sub):
    command(sub, "desk", "sources", cmd_sources,
            "what data is installed, from where, under which licence, and how old each file is",
            ["sources"])
