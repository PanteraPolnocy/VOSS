"""What the database builders share: fetching a file, packing text small, and the two tables every database
carries.

Used by tools/build_*.py only. Nothing here is part of the skill, so this is the one place where the
network is touched: the tools Voss runs never fetch anything.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "scripts"))

from vosslib import core, store  # noqa: E402

DOWNLOADS = os.path.join(ROOT, "downloads")
DATA = os.path.join(ROOT, "src", "scripts", "data")
# A plain client name on purpose: nothing about this project or its owner goes out with a request. Some
# services (Wikidata is one) ask a script to say who runs it and how to reach them, and are slow with one
# that does not. Whoever builds can put such a line of their own in VOSS_BUILD_AGENT; nothing is put there
# for them.
AGENT = os.environ.get("VOSS_BUILD_AGENT") or "offline-data-build/1.0"
MAX_WAIT = 120
pauses = 0                      # how often a server has asked for a pause, so a caller can slow down
NOTE = ".from.json"
# big enough for a block's pieces to share their words, small enough that reading one piece stays a matter of
# milliseconds. Measured on the MedlinePlus summaries: about 4.3 times smaller, some 15 ms to read
BLOCK_BYTES = 1 << 19
MAX_FILE_BYTES = 49 * 1000 * 1000


def say(text):
    print(text)
    sys.stdout.flush()


# ---- fetching

def is_url(text):
    return str(text).lower().startswith(("http://", "https://"))


def get(url, accept="*/*", tries=5, missing_ok=False):
    """The bytes at a URL, and its Last-Modified header. A server that says "too many requests" is given the
    pause it asks for, up to two minutes at a time; after five tries it gives up. With missing_ok, a page
    that is not there gives (None, '') in place of an error."""
    global pauses
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.headers.get("Last-Modified") or ""
        except urllib.error.HTTPError as e:
            if e.code == 404 and missing_ok:
                return None, ""
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries:
                sys.exit("could not fetch %s: HTTP %s %s" % (url, e.code, e.reason))
            asked = e.headers.get("Retry-After") or ""
            wait = min(max(int(asked) if asked.isdigit() else 0, 15 * attempt), MAX_WAIT)
            pauses += 1
            say("          the server asks for a pause (HTTP %s): waiting %d seconds" % (e.code, wait))
            time.sleep(wait)
        except (urllib.error.URLError, OSError) as e:
            if attempt == tries:
                sys.exit("could not fetch %s: %s" % (url, e))
            time.sleep(5 * attempt)


def fetch(url, name, accept="*/*", folder=None):
    """Download a URL into downloads/NAME, with a note beside it of where it came from and on which day.
    Returns the path."""
    folder = folder or DOWNLOADS
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    data, modified = get(url, accept)
    save(path, data, url, modified)
    say("fetched   %s (%s)" % (name, size_words(len(data))))
    return path


def save(path, data, url, modified=""):
    """Write a download and its note. The file appears whole or not at all."""
    part = path + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, path)
    with open(path + NOTE, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"url": url, "retrieved": core.today().isoformat(), "last_modified": modified}, f, indent=1)
        f.write("\n")


def origin(path, url="", retrieved=None):
    """(url, retrieval date) for a file to build from: what was given on the command line, else the note
    that 'fetch' left beside it. A file with neither cannot say how old it is, and the build stops."""
    note = {}
    try:
        with open(path + NOTE, encoding="utf-8") as f:
            note = json.load(f)
    except (OSError, ValueError):
        pass
    day = core.parse_date(retrieved or note.get("retrieved") or "")
    if day is None:
        sys.exit("%s has no note of when it was downloaded: pass --retrieved YYYY-MM-DD, the day you fetched it"
                 % os.path.basename(path))
    if day > core.today():
        sys.exit("--retrieved is in the future")
    return url or note.get("url") or "", day


def newest(folder, start, endings):
    """The newest file in a folder whose name starts and ends as given, or None. Names carry their date."""
    try:
        names = sorted(n for n in os.listdir(folder) if n.startswith(start) and n.lower().endswith(endings))
    except OSError:
        return None
    return os.path.join(folder, names[-1]) if names else None


def size_words(n):
    return "%.1f MB" % (n / 1e6) if n >= 100000 else "%d KB" % max(1, n // 1000)


# ---- packing text

class Texts:
    """Packs many pieces of text into a few compressed blocks, so that a database stays small.

    A piece is found again by (block, start, length). Add pieces that are alike one after the other: a
    block squeezes better when its neighbours repeat each other. The same text added twice is stored once.
    """

    def __init__(self, con, codec=None, block_bytes=BLOCK_BYTES):
        self.con = con
        self.codec = codec or store.SMALLEST
        if self.codec != store.SMALLEST and self.codec not in store.available():
            sys.exit("--codec is one of: %s, %s" % (store.SMALLEST, ", ".join(store.available())))
        self.block_bytes = block_bytes
        self.used = {}
        self.number, self.parts, self.size = 1, [], 0
        self.seen = {}
        self.raw_total = self.packed_total = 0
        con.execute("CREATE TABLE %s (id INTEGER PRIMARY KEY, codec TEXT NOT NULL, data BLOB NOT NULL)" % store.TABLE)

    def add(self, text):
        """Store one piece; returns (block, start, length). Empty text has no address: (None, 0, 0)."""
        raw = str(text).encode("utf-8")
        if not raw:
            return None, 0, 0
        key = hashlib.sha1(raw).digest()
        if key in self.seen:
            return self.seen[key]
        if self.size and self.size + len(raw) > self.block_bytes:
            self.flush()
        where = (self.number, self.size, len(raw))
        self.parts.append(raw)
        self.size += len(raw)
        self.seen[key] = where
        return where

    def flush(self):
        if not self.parts:
            return
        raw = b"".join(self.parts)
        codec, packed = store.pack(raw, self.codec)
        self.con.execute("INSERT INTO %s (id, codec, data) VALUES (?, ?, ?)" % store.TABLE, (self.number, codec, packed))
        self.used[codec] = self.used.get(codec, 0) + 1
        self.raw_total += len(raw)
        self.packed_total += len(packed)
        self.number, self.parts, self.size = self.number + 1, [], 0

    def close(self):
        self.flush()
        return self.raw_total, self.packed_total


# ---- the tables every database carries

def create(path):
    """A new, empty database at path + '.part'. 'finish' moves it into place once it is whole."""
    part = path + ".part"
    if os.path.exists(part):
        os.remove(part)
    con = sqlite3.connect(part)
    con.execute("PRAGMA page_size = 4096")
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    con.execute("CREATE TABLE meta (source TEXT NOT NULL, url TEXT NOT NULL, retrieved TEXT NOT NULL, "
                "licence TEXT NOT NULL, credit TEXT NOT NULL)")
    con.execute("CREATE TABLE build (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return con


def add_source(con, source, url, retrieved, licence, credit=""):
    """One row of 'meta'; returns its number, which the rows that came from it carry."""
    cur = con.execute("INSERT INTO meta (source, url, retrieved, licence, credit) VALUES (?, ?, ?, ?, ?)",
                      (source, url, retrieved.isoformat(), licence, credit))
    return cur.lastrowid


def finish(con, path, built=None, facts=()):
    """Stamp the build day, tidy the file, check it reads back, and move it into place. Returns its size."""
    day = built or core.today()
    con.execute("INSERT INTO build (key, value) VALUES (?, ?)", ("built", day.isoformat()))
    for key, value in facts:
        con.execute("INSERT INTO build (key, value) VALUES (?, ?)", (key, str(value)))
    con.commit()
    con.execute("VACUUM")
    con.commit()
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    part = path + ".part"
    if ok != "ok":
        os.remove(part)
        sys.exit("the new database failed its own integrity check: %s" % ok)
    size = os.path.getsize(part)
    if size > MAX_FILE_BYTES:
        os.remove(part)
        sys.exit("%s would be %s: no file in the repository may be over %d MB. Nothing was written: it has to be cut "
                 "into parts, or shipped another way" % (os.path.basename(path), size_words(size), MAX_FILE_BYTES // 1000000))
    os.replace(part, path)
    return size


def discard(con, path):
    """Throw away a database that was not finished, so that no half of one is left lying in the data folder."""
    try:
        con.close()
    except sqlite3.Error:
        pass
    if os.path.exists(path + ".part"):
        os.remove(path + ".part")


def write_licence(stem, text, folder=None):
    """The licence text that sits beside a database, as LICENSE-<stem>.txt."""
    path = os.path.join(folder or DATA, "LICENSE-%s.txt" % stem)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.strip() + "\n")
    return path
