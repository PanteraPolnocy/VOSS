"""Tests for the Voss toolkit. Standard library only.

Run:  python tests/test_voss.py            (from the repository root)
      python tests/test_voss.py -v

The clock is pinned with VOSS_NOW, and made-up patients (tests/fixtures/personal.test.json) stand in for
the personal file, so results do not depend on the day or on anyone's real data. Files the tools write
(calendar files, rebuilt personal files, packages) go to a temporary folder that is removed afterwards.

Most tests run with no database at all: VOSS_DATA points at an empty folder, so nothing depends on what
data happens to ship. The tests of 'term' and of the emergency numbers build a small database of their own
from the made-up files in tests/fixtures/core, with the real builder. A few at the end look at the
databases that ship, and are skipped where there are none.
"""
import atexit
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
SCRIPTS = os.path.join(SRC, "scripts")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
FIXTURE = os.path.join(FIXTURES, "personal.test.json")
HOUSEHOLD = os.path.join(FIXTURES, "household.example.md")
OUTPUTS = tempfile.mkdtemp(prefix="voss-tests-")
atexit.register(shutil.rmtree, OUTPUTS, True)
sys.dont_write_bytecode = True
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
NOW = "2026-11-15T10:30"
os.environ["VOSS_NOW"] = NOW
os.environ["VOSS_PERSONAL"] = FIXTURE
os.environ["VOSS_OUTPUTS"] = OUTPUTS
NO_DATA = os.path.join(OUTPUTS, "no-data")
os.makedirs(NO_DATA)
os.environ["VOSS_DATA"] = NO_DATA
os.environ.pop("VOSS_HOUSEHOLD", None)
os.environ.pop("VOSS_BUILD_AGENT", None)

import voss  # noqa: E402
import vosslib  # noqa: E402
from vosslib import clinic, core, desk, doses, gate, ical, index, labels, library, personal, record, store, terms  # noqa: E402

import build  # noqa: E402
import build_core  # noqa: E402
import build_ddinter  # noqa: E402
import build_icd11  # noqa: E402
import build_labels  # noqa: E402
import build_index  # noqa: E402
import dbtools  # noqa: E402

CORE = os.path.join(FIXTURES, "core")
REAL_DATA = os.path.join(SCRIPTS, "data")

ANSWERS = ("kittiwake", "pendle", "bottle", "butelkowa", "cello")
UNCHOSEN = ("travel", "secondopinion", "opinion", "logbook", "casebook", "screening", "booster", "sleep", "sleepdiary")


def use_personal(path):
    """Switch the personal file (None: no file at all) and forget the copy already read."""
    if path:
        os.environ["VOSS_PERSONAL"] = path
    else:
        os.environ["VOSS_PERSONAL"] = os.path.join(OUTPUTS, "no-such-personal.json")
    personal.reset()


def clock(text=NOW):
    os.environ["VOSS_NOW"] = text


def run(*args):
    """Run a command; return (exit code, stdout, stderr)."""
    personal.reset()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = voss.main([str(a) for a in args])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def ok(*args):
    code, out, err = run(*args)
    assert code == 0, "voss.py %s -> exit %s\n%s%s" % (" ".join(map(str, args)), code, out, err)
    return out


def fails(*args):
    """Run a command that must end in an ERROR line; return that line."""
    code, out, err = run(*args)
    assert code == 2 and err.startswith("ERROR "), "voss.py %s -> exit %s\n%s%s" % (" ".join(map(str, args)), code, out, err)
    return err


def field(out, key):
    for line in out.splitlines():
        if line.startswith(key + " ") or line == key:
            return line[len(key):].strip()
    raise AssertionError("no %s line in:\n%s" % (key, out))


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def copy_fixture(change=None):
    """A copy of the made-up patients in the temp folder, optionally changed, as the personal file in use."""
    data = load_json(FIXTURE)
    if change:
        change(data)
    folder = tempfile.mkdtemp(dir=OUTPUTS)
    path = os.path.join(folder, "personal.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f)
    use_personal(path)
    return path


def make_db(folder, stem, built="2026-11-10", retrieved="2026-11-09", meta=True, licence=True, source="A made-up source"):
    """A tiny database in the shape the tools expect, for the tests only."""
    path = os.path.join(folder, stem + ".db")
    con = sqlite3.connect(path)
    if meta:
        con.execute("CREATE TABLE meta (source TEXT, url TEXT, retrieved TEXT, licence TEXT, credit TEXT)")
        con.execute("INSERT INTO meta VALUES (?, ?, ?, ?, ?)",
                    (source, "https://example.org/data", retrieved, "public domain", "Source: a made-up source"))
    con.execute("CREATE TABLE build (key TEXT PRIMARY KEY, value TEXT)")
    if built:
        con.execute("INSERT INTO build VALUES (?, ?)", ("built", built))
    con.commit()
    con.close()
    if licence:
        with open(os.path.join(folder, "LICENSE-%s.txt" % stem), "w", encoding="utf-8") as f:
            f.write("Made up for the tests.\n")
    return path


@contextlib.contextmanager
def small_samples():
    """The builder refuses a topic file with a handful of topics in it, as a download cut short. The made-up
    files are a handful on purpose, so that guard is lowered while they are read."""
    keep = build_core.MIN_TOPICS, build_core.MIN_COUNTRIES
    build_core.MIN_TOPICS, build_core.MIN_COUNTRIES = 3, 3
    try:
        yield
    finally:
        build_core.MIN_TOPICS, build_core.MIN_COUNTRIES = keep


def build_sample(out, *extra, **files):
    """Run the real builder on the made-up files in tests/fixtures/core; returns what it printed."""
    named = {"topics": "mplus_topics_sample.xml", "definitions": "sampledefinitions.xml", "numbers": "emergency.sample.json",
             "eu-page": "eu-112.sample.html"}
    named.update(files)
    args = []
    for option, name in sorted(named.items()):
        args += ["--" + option, name if os.path.isabs(name) or dbtools.is_url(name) else os.path.join(CORE, name)]
    said = io.StringIO()
    with small_samples(), contextlib.redirect_stdout(said):
        build_core.main(args + ["--out", out] + list(extra))
    return said.getvalue()


_sample = {}


def sample_data():
    """The folder that holds the small core database, built once for the whole run."""
    if "folder" not in _sample:
        folder = os.path.join(OUTPUTS, "sample-data")
        os.makedirs(folder)
        clock()
        _sample["said"] = build_sample(folder, "--retrieved", "2026-11-10")
        _sample["folder"] = folder
    return _sample["folder"]


ICD_HEAD = "\ufeff" + "\t".join(build_icd11.COLUMNS + ("Version:2026 Jan 01 - 00:00 UTC",))


def icd_record(number, code="", block="", title="", kind="category", depth=1, residual=False, chapter="01", leaf=True,
               note="", parent=None, tail=""):
    """One record in the shape of WHO's tabulation, about something that does not exist."""
    entity = "" if residual else "http://id.example.org/icd/entity/%d" % number
    uri = "http://id.example.org/icd/release/11/mms/%s" % (tail or number)
    link = '"=hyperlink(""https://example.org/browse#%s"",""browser"")"' % (tail or number)
    return "\t".join([entity, uri, code, block, '"%s"' % title.replace('"', '""'), kind, str(depth), str(residual), chapter, link,
                      str(leaf), "", "", "", "", "", "", note, "http://id.example.org/icd/entity/%d" % parent if parent else ""])


ICD_RECORDS = [
    icd_record(1, title="Made-up conditions of the tests", kind="chapter", leaf=False),
    icd_record(2, block="BlockL1-ZA0", title="- Wobbles", kind="block", leaf=False, parent=1),
    icd_record(3, code="ZA00", title="- - Wobbly knee", leaf=False, parent=2),
    icd_record(4, code="ZA00.0", title="- - - Wobbly knee, left", depth=2, parent=3,
               note='"Code also the ""cause"", if known\nand the side it is on"'),
    icd_record(3, code="ZA00.Y", title="- - - Other specified wobbly knee", depth=2, residual=True, parent=3, tail="3/other"),
    icd_record(3, code="ZA00.Z", title="- - - Wobbly knee, unspecified", depth=2, residual=True, parent=3, tail="3/unspecified"),
    icd_record(5, code="ZA01", title="- - Creaky elbow", parent=2),
    icd_record(6, code="ZA02", title="- - Sj\u00f6gren-like dryness \u2013 of the tests", parent=2),
    icd_record(9, title="Extension codes of the tests", kind="chapter", chapter="X", leaf=False),
    icd_record(10, code="XZ01", title="- Left", chapter="X", parent=9),
]


def icd_file(records=None, head=ICD_HEAD, name="SimpleTabulation-sample.txt"):
    """A made-up tabulation on disk, with the line ends and the byte order mark WHO's file has."""
    path = os.path.join(tempfile.mkdtemp(dir=OUTPUTS), name)
    with open(path, "wb") as f:
        f.write(("\r\n".join([head] + list(ICD_RECORDS if records is None else records)) + "\r\n").encode("utf-8"))
    return path


def build_icd(out, tabulation, *extra):
    """Run the real ICD-11 builder on a made-up tabulation; returns what it printed."""
    keep = build_icd11.MIN_RECORDS
    build_icd11.MIN_RECORDS = 5
    said = io.StringIO()
    try:
        with contextlib.redirect_stdout(said):
            build_icd11.main(["--tabulation", tabulation, "--out", out, "--downloads", NO_DATA] + list(extra))
    finally:
        build_icd11.MIN_RECORDS = keep
    return said.getvalue()


def sample_icd():
    """The folder that holds the small ICD database, built once for the whole run."""
    if "icd" not in _sample:
        folder = os.path.join(OUTPUTS, "sample-icd")
        os.makedirs(folder)
        clock()
        _sample["icd-file"] = icd_file()
        _sample["icd-said"] = build_icd(folder, _sample["icd-file"], "--release", "2026-01", "--retrieved", "2026-11-10",
                                        "--licence-read", "2026-11-10")
        _sample["icd"] = folder
    return _sample["icd"]


# Interaction files in the shape of DDInter's, about medicines that do not exist.
DDI_FILES = {
    "A": [("DDInter1", "Wobblol", "DDInter2", "Creakazine", "Major"),
          ("DDInter1", "Wobblol", "DDInter3", "Kneeprofen", "Moderate"),
          ("DDInter4", "Sniffex", "DDInter1", "Wobblol", "Minor"),
          ("DDInter5", "Sniffex (topical)", "DDInter1", "Wobblol", "Unknown"),
          ("DDInter7", "Mopezil", "DDInter1", "Wobblol", "Moderate"),
          ("DDInter8", "Dozapine", "DDInter1", "Wobblol", "Major")],
    "B": [("DDInter2", "Creakazine", "DDInter1", "Wobblol", "Moderate"),
          ("DDInter2", "Creakazine", "DDInter6", "Elbowmycin", "Unknown"),
          ("DDInter3", "Kneeprofen", "DDInter3", "Kneeprofen", "Minor"),
          ("DDInter2", "Creakazine", "DDInter7", "Mopezil", "Minor"),
          ("DDInter2", "Creakazine", "DDInter8", "Dozapine", "Unknown")],
}
# Wobblol is the group-A medicine and Creakazine the group-B one: every pair of theirs is in their own file.
# Mopezil and Dozapine have a pair in each file and all their pairs in neither, so they are in neither group.
DDI_NAMES = {"items": {
    "Q1": {"en": ["wobblol", "WBL-1"], "pl": ["wobblol", "woblol"]},
    "Q2": {"en": ["Creakazine", "creaksine", "CZ", "a name that is far too long to be a name anybody would ever type in"],
           "pl": ["kreakazyna"]},
    "Q3": {"en": ["Kneeprofen"], "pl": []},
    "Q4": {"en": ["kneeprofen", "something else"], "pl": []},
}}


def ddi_files(files=None, names=None, header=None):
    """Made-up download files and a made-up names file on disk; returns ([csv paths], names path)."""
    import csv
    folder = tempfile.mkdtemp(dir=OUTPUTS)
    paths = []
    for letter, rows in sorted((DDI_FILES if files is None else files).items()):
        path = os.path.join(folder, "ddinter_downloads_code_%s.csv" % letter)
        with open(path, "w", encoding="utf-8", newline="") as f:
            out = csv.writer(f)
            out.writerow(header or build_ddinter.HEADER)
            out.writerows(rows)
        paths.append(path)
    names_path = os.path.join(folder, "drug-names.sample.json")
    with open(names_path, "w", encoding="utf-8") as f:
        json.dump(DDI_NAMES if names is None else names, f)
    return paths, names_path


def build_ddi(out, paths, names_path, *extra):
    """Run the real interaction builder on made-up files; returns what it printed."""
    keep = build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES
    build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES = 3, 3, 2
    said = io.StringIO()
    try:
        with contextlib.redirect_stdout(said):
            build_ddinter.main(["--files"] + list(paths) + ["--names", names_path, "--out", out, "--downloads", NO_DATA] + list(extra))
    finally:
        build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES = keep
    return said.getvalue()


def sample_ddi():
    """The folder that holds the small interaction database, built once for the whole run."""
    if "ddi" not in _sample:
        folder = os.path.join(OUTPUTS, "sample-ddi")
        os.makedirs(folder)
        clock()
        paths, names_path = ddi_files()
        _sample["ddi-said"] = build_ddi(folder, paths, names_path, "--retrieved", "2026-11-10", "--terms-read", "2026-11-10")
        _sample["ddi"] = folder
    return _sample["ddi"]


# Product labels in the shape of openFDA's, for medicines that do not exist.
def _fda(kind, substances, generic, brands, maker, route, application, **more):
    block = {"product_type": [kind], "substance_name": substances, "generic_name": [generic], "brand_name": brands,
             "manufacturer_name": [maker], "route": [route], "application_number": [application]}
    block.update(more)
    return block


LABELS = {"meta": {"disclaimer": "made up for the tests", "results": {"skip": 0, "limit": 9, "total": 9}}, "results": [
    {"set_id": "set-1", "effective_time": "20250101",
     "openfda": _fda("HUMAN PRESCRIPTION DRUG", ["WOBBLOL HYDROCHLORIDE"], "WOBBLOL HYDROCHLORIDE", ["Wobblol Hydrochloride"], "Copycat Ltd",
                     "ORAL", "ANDA000001", pharm_class_epc=["Knee Steadier [EPC]"]),
     "indications_and_usage": ["1 INDICATIONS Wobblol is for wobbly knees. This is the copy's label."],
     "adverse_reactions": ["6 ADVERSE REACTIONS Dizziness."]},
    {"set_id": "set-2", "effective_time": "20260301",
     "openfda": _fda("HUMAN PRESCRIPTION DRUG", ["WOBBLOL HYDROCHLORIDE"], "WOBBLOL HYDROCHLORIDE", ["Steadyknee"], "Original Pharma Inc",
                     "ORAL", "NDA000002", pharm_class_epc=["Knee Steadier [EPC]"], is_original_packager=[True]),
     "boxed_warning": ["WARNING: A MADE-UP RISK Wobblol can make the tests fail."],
     "indications_and_usage": ["1 INDICATIONS AND USAGE Wobblol is indicated for wobbly knees in adults.   It isn\u2019t a real medicine."],
     "contraindications": ["4 CONTRAINDICATIONS Do not use in patients with creaky elbows."],
     "warnings_and_cautions": ["5 WARNINGS AND PRECAUTIONS 5.1 Sniffles Monitor for sniffles."],
     "adverse_reactions": ["6 ADVERSE REACTIONS The most common adverse reactions (incidence 5% or more) are nausea, pruritus and "
                           "somnolence. Nausea led to discontinuation in 2% of patients. 6.2 Postmarketing Experience Headache has "
                           "been reported."],
     "drug_interactions": ["7 DRUG INTERACTIONS 7.1 Creakazine Increased wobbling. Avoid the combination. 7.2 Elbowmycin No effect."],
     "pregnancy": ["8.1 Pregnancy There are no data in pregnant women."],
     "dosage_and_administration": ["2 DOSAGE AND ADMINISTRATION Take 5 mg once daily."],
     "spl_medguide": ["MEDICATION GUIDE What is the most important information I should know? Wobblol may cause nausea."]},
    {"set_id": "set-3", "effective_time": "20260201",
     "openfda": _fda("HUMAN OTC DRUG", ["WOBBLOL"], "WOBBLOL", ["Kneeze Gel", "Shopwise Wobblol Gel", "Knee Relief", "Wobblol Gel 1%"],
                     "Shelf Goods LLC", "TOPICAL", "M017"),
     "purpose": ["Purpose Knee steadier"], "active_ingredient": ["Active ingredient Wobblol 1%"],
     "indications_and_usage": ["Uses temporarily steadies a wobbly knee"], "warnings": ["Warnings For external use only."],
     "stop_use": ["Stop use and ask a doctor if a rash appears"], "dosage_and_administration": ["Directions apply thinly twice a day"]},
    {"set_id": "set-4", "effective_time": "20260110",
     "openfda": _fda("HUMAN PRESCRIPTION DRUG", ["CREAKAZINE", "WOBBLOL HYDROCHLORIDE"], "WOBBLOL AND CREAKAZINE", ["Duoknee"],
                     "Original Pharma Inc", "ORAL", "NDA000004"),
     "indications_and_usage": ["1 INDICATIONS AND USAGE Duoknee is indicated for knees and elbows at once."],
     "adverse_reactions": ["6 ADVERSE REACTIONS Nausea."]},
    {"set_id": "set-5", "effective_time": "20260101", "indications_and_usage": ["A label FDA has not matched to a product."]},
    {"set_id": "set-6", "effective_time": "20260101", "openfda": {"product_type": ["PLASMA DERIVATIVE"], "substance_name": ["PLASMOL"]},
     "indications_and_usage": ["Not a kind of product that is kept."]},
    # another medicine altogether, sold under a name the wobblol gel also carries
    {"set_id": "set-7", "effective_time": "20260105",
     "openfda": _fda("HUMAN OTC DRUG", ["ZIPPERINE"], "ZIPPERINE", ["Knee Relief", "Zippo Warming Rub"], "Shelf Goods LLC", "TOPICAL", "M018"),
     "purpose": ["Purpose Knee warmer"], "indications_and_usage": ["Uses warms a cold knee"],
     "warnings": ["Warnings For external use only. Stop use if a rash appears."]},
    # two labels FDA lists no substances for: one whose generic name reads as a list of them, one that does not
    {"set_id": "set-8", "effective_time": "20250601",
     "openfda": _fda("HUMAN PRESCRIPTION DRUG", [], "Wobblol HCl and Creakazine Tablets", ["Duoknee Starter Pack"], "Copycat Ltd", "",
                     "ANDA000008"),
     "indications_and_usage": ["1 INDICATIONS The starter pack is for knees and elbows. This is the pack's label."]},
    {"set_id": "set-9", "effective_time": "20250601",
     "openfda": _fda("HUMAN PRESCRIPTION DRUG", [], "Knee tonic compound", ["Tonique"], "Copycat Ltd", "ORAL", "ANDA000009"),
     "indications_and_usage": ["1 INDICATIONS A tonic nobody can place."]},
]}


def label_files(doc=None, indent=1):
    """A made-up label file and the made-up names file on disk; returns ([label path], names path)."""
    folder = tempfile.mkdtemp(dir=OUTPUTS)
    path = os.path.join(folder, "drug-label-0001-of-0001.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(LABELS if doc is None else doc, f, indent=indent)
    names_path = os.path.join(folder, "drug-names.sample.json")
    with open(names_path, "w", encoding="utf-8") as f:
        json.dump(DDI_NAMES, f)
    return [path], names_path


def build_labels_db(out, paths, names_path, *extra):
    """Run the real label builder on made-up files; returns what it printed."""
    keep = build_labels.MIN_LABELS, build_labels.MIN_NAMES
    build_labels.MIN_LABELS, build_labels.MIN_NAMES = 2, 2
    said = io.StringIO()
    try:
        with contextlib.redirect_stdout(said):
            build_labels.main(["--files"] + list(paths) + ["--names", names_path, "--out", out, "--downloads", NO_DATA] + list(extra))
    finally:
        build_labels.MIN_LABELS, build_labels.MIN_NAMES = keep
    return said.getvalue()


def sample_labels():
    """The folder that holds the small label database, built once for the whole run."""
    if "labels" not in _sample:
        folder = os.path.join(OUTPUTS, "sample-labels")
        os.makedirs(folder)
        clock()
        paths, names_path = label_files()
        _sample["labels-said"] = build_labels_db(folder, paths, names_path, "--retrieved", "2026-11-10", "--terms-read", "2026-11-10")
        _sample["labels"] = folder
    return _sample["labels"]


class Base(unittest.TestCase):
    def setUp(self):
        clock()
        use_personal(FIXTURE)
        os.environ["VOSS_DATA"] = NO_DATA
        os.environ.pop("VOSS_HOUSEHOLD", None)

    tearDown = setUp


class BootTests(Base):
    def test_banner_data_and_people(self):
        out = ok("boot", "--seed", "1")
        self.assertEqual(field(out, "BANNER"), "VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: not installed")
        self.assertIn("DATA       not installed", out)
        self.assertIn("TODAY      2026-11-15 Sun 10:30", out)
        self.assertIn("PERSONAL   2 profiles and 1 dependant on file: self, rowan, pip", out)
        self.assertIn("last changed 2026-11-02. If the person saved something later than that, an older copy", out)
        self.assertIn("an emergency answer carries [mood: serious] [voss-serious.webp] and no look", out)
        self.assertIn("still gets your full care and knowledge, only without the file", out)
        self.assertIn("self: on, 4 questions [every new conversation]", out)
        self.assertIn("rowan: off, no questions on file", out)
        self.assertIn("pip: on, 4 questions [every new conversation], by the gate of self", out)
        self.assertIn("ask who you are speaking with", out)
        self.assertIn("moods: composed, focused, sceptical, exasperated, pleased, concerned, amused, proud, flustered, serious", out)
        self.assertIn("looks: on-duty, baking", out)

    def test_one_profile_is_dealt_a_question(self):
        def only_self(data):
            data["profiles"] = data["profiles"][:1]
            data["dependants"] = []
        copy_fixture(only_self)
        out = ok("boot", "--seed", "5")
        first = int(re.search(r"ask: .+\?  \(profile self, question (\d)\)", out).group(1))
        later = [int(x) for x in re.findall(r"--q (\d)", out.split("if missed")[1].split("\n")[0])]
        self.assertEqual(len(set([first] + later)), 3)
        seen = set(re.search(r"question (\d)\)", ok("boot")).group(1) for _ in range(60))
        self.assertEqual(seen, set("1234"))

    def test_no_file_and_a_broken_file(self):
        use_personal(None)
        self.assertIn("PERSONAL   no personal file (VOSS_PERSONAL names one that is not there yet): general mode", ok("boot"))
        self.assertIn("there is no personal file here", fails("profile", "--id", "self"))
        path = os.path.join(tempfile.mkdtemp(dir=OUTPUTS), "personal.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"profiles": [{"id": "self", "call_me": "Secret Name",]}')
        use_personal(path)
        out = ok("boot")
        self.assertIn("the personal file cannot be used", out)
        self.assertIn("general mode", out)
        self.assertNotIn("Secret Name", out)
        code, out, _ = run("selftest")
        self.assertEqual(code, 1)
        self.assertNotIn("Secret Name", out)

    def test_theatre(self):
        out = ok("theatre")
        self.assertEqual(field(out, "BANNER"), "VOSS-01 | PROJECT ASCLEPIUS | THEATRE | data: not installed")
        self.assertIn("real drugs and real doses keep their real rules", out)
        self.assertIn("nothing from Theatre goes into the personal file", out)
        self.assertEqual(field(ok("theatre", "--off"), "BANNER"), "VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: not installed")

    def test_selftest(self):
        out = ok("selftest")
        self.assertIn("SELFTEST   15 of 15 passed; data: not installed", out)
        self.assertNotIn("FAIL", out)


class SourcesTests(Base):
    def data_folder(self):
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        os.environ["VOSS_DATA"] = folder
        return folder

    def test_nothing_installed(self):
        out = ok("sources")
        self.assertIn("SOURCES    no database installed (looked in ", out)
        for stem in ("core-pd", "icd11", "ddinter", "labels-us"):
            self.assertIn("NOT HERE   %s.db" % stem, out)
        self.assertIn("nothing is fetched while the tools run", out)

    def test_a_database_says_where_it_came_from(self):
        folder = self.data_folder()
        make_db(folder, "core-pd")
        make_db(folder, "icd11", built="2026-10-01", retrieved="2026-09-30")
        out = ok("sources")
        self.assertIn("SOURCES    2 databases", out)
        self.assertIn("banner status: 2026-10-01", out)
        self.assertIn("core-pd.db (", out)
        self.assertIn("source: A made-up source | licence: public domain | retrieved 2026-11-09", out)
        self.assertIn("credit, to be kept with every answer from it: Source: a made-up source", out)
        self.assertIn("age: retrieved 2026-11-09, 6 days ago; warn after 6 months [pending]", out)
        self.assertIn("when WHO publishes a new annual release", out)
        self.assertEqual(field(ok("boot"), "BANNER"), "VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: 2026-10-01")
        self.assertIn("2 databases to answer from; the oldest was built 2026-10-01", ok("boot"))

    def test_stale_data_gets_a_warning(self):
        folder = self.data_folder()
        make_db(folder, "core-pd", built="2026-11-10", retrieved="2026-05-14")
        make_db(folder, "region-pl", built="2026-11-10", retrieved="2026-10-14")
        make_db(folder, "ddinter", built="2026-11-10", retrieved="2025-11-16")
        out = ok("sources")
        self.assertIn("retrieved 2026-05-14, 185 days ago: STALE, the limit is 6 months", out)
        self.assertIn("retrieved 2026-10-14, 32 days ago: STALE, the limit is 1 month", out)
        self.assertIn("retrieved 2025-11-16, 364 days ago; warn after 12 months", out)
        boot = ok("boot")
        self.assertIn("core-pd.db: retrieved 2026-05-14", boot)
        self.assertIn("region-pl.db: retrieved 2026-10-14", boot)
        self.assertNotIn("ddinter.db: retrieved", boot)

    def test_a_file_that_cannot_account_for_itself_is_not_used(self):
        folder = self.data_folder()
        make_db(folder, "core-pd", meta=False)
        make_db(folder, "icd11", licence=False)
        make_db(folder, "ddinter", built=None)
        with open(os.path.join(folder, "region-pl.db"), "wb") as f:
            f.write(b"this is not a database at all")
        out = ok("sources")
        self.assertIn("NOT USABLE: it has no meta table with source, url, retrieved and licence", out)
        self.assertIn("NOT USABLE: it has no LICENSE-icd11.txt beside it", out)
        self.assertIn("NOT USABLE: it does not say when it was built", out)
        self.assertIn("NOT USABLE: it cannot be read as a database", out)
        boot = ok("boot")
        self.assertIn("data: not installed", boot)
        self.assertIn("core-pd.db cannot be answered from", boot)
        self.assertEqual(run("selftest")[0], 1)

    def test_databases_are_opened_read_only(self):
        folder = self.data_folder()
        path = make_db(folder, "core-pd")
        con = library.connect(path)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("INSERT INTO build VALUES (?, ?)", ("x", "y"))
        con.close()


class ClinicTests(Base):
    def test_triage_is_the_clinical_rules_word_for_word(self):
        with open(os.path.join(SRC, "references", "clinical-rules.md"), encoding="utf-8") as f:
            rules = f.read()
        data = core.load_data("triage")
        levels = re.findall(r"(?m)^\d\. (.+)$", rules.split("## Triage levels")[1].split("##")[0])
        self.assertEqual(data["levels"], levels)
        flags = re.findall(r"(?m)^- (.+)$", rules.split("## Red flags: emergency now")[1].split("##")[0])
        self.assertEqual(data["red_flags"], flags)
        self.assertIn(data["rule"], rules)
        self.assertIn(data["flags_note"], rules)
        out = ok("triage")
        for line in levels + flags:
            self.assertIn(line, out)
        self.assertIn("LEVEL 1    Emergency now: call the emergency number.", out)
        self.assertIn("no wit and no ears", out)
        self.assertIn("The marker is [mood: serious] [voss-serious.webp]", out)
        self.assertIn("NUMBERS    none on file: core-pd.db is not installed", out)

    def test_triage_options(self):
        out = ok("triage", "--level", "2")
        self.assertIn("LEVEL 2    Urgent today", out)
        self.assertNotIn("RED FLAGS", out)
        self.assertNotIn("LEVEL 1", ok("triage", "--flags"))
        self.assertIn("--level is 1 to 4", fails("triage", "--level", "9"))

    def test_visit(self):
        out = ok("visit", "--reason", "the cough that will not go", "--on", "2026-12-01", "--diary-days", "3")
        self.assertIn("VISIT      getting ready: the cough that will not go", out)
        self.assertIn("WHEN       2026-12-01 Tue, in 16 days [derived]", out)
        self.assertIn("DIARY      one line a day: date | what | severity 0 to 10 | what helped | notes", out)
        self.assertIn("2026-11-15 Sun |  |  |  |", out)
        self.assertIn("2026-11-17 Tue |  |  |  |", out)
        self.assertNotIn("2026-11-18", out)
        self.assertIn("[general]", out)
        self.assertIn("in the past", fails("visit", "--on", "2026-11-14"))
        self.assertIn("today", ok("visit", "--on", "today"))
        self.assertEqual(run("visit", "--diary-days", "61")[0], 2)

    def reading(self, *args):
        return field(ok("labs", "--test", "A test", *args), "READING")

    def test_labs_reads_a_value_against_the_printed_range_only(self):
        self.assertEqual(self.reading("--value", "72", "--range", ">=60"), "inside the printed range [derived]")
        self.assertEqual(self.reading("--value", "5,4", "--unit", "mmol/L", "--range", "3.5-5.1"),
                         "above the printed range by 0.3 mmol/L [derived]")
        self.assertEqual(self.reading("--value", "3.2", "--range", "3,5 - 5,1"), "below the printed range by 0.3 [derived]")
        self.assertEqual(self.reading("--value", "5.10", "--range", "3.5 to 5.1"),
                         "on the upper limit, which the printed range includes [derived]")
        self.assertEqual(self.reading("--value", "5.0", "--range", "<5.0"),
                         "on the upper limit, which the range as printed does not include [derived]")
        self.assertEqual(self.reading("--value", "60", "--range", "60 or above"),
                         "on the lower limit, which the printed range includes [derived]")
        self.assertEqual(self.reading("--value", "18", "--low", "30", "--high", "50"), "below the printed range by 12 [derived]")
        self.assertEqual(self.reading("--value", "-1.5", "--range", "-2-3"), "inside the printed range [derived]")
        self.assertEqual(self.reading("--value", "4.9", "--range", "\u2264 5.0"), "inside the printed range [derived]")
        self.assertEqual(self.reading("--value", "0.1", "--range", "0.2\u20132.0"), "below the printed range by 0.1 [derived]")

    def test_labs_values_the_lab_printed_with_a_sign(self):
        self.assertIn("which is inside the printed range", self.reading("--value", "<0.5", "--range", "<5.0"))
        self.assertIn("which is below the printed range", self.reading("--value", "<0.2", "--range", "0.2-2.0"))
        self.assertIn("cannot be placed against this range", self.reading("--value", "<0.5", "--range", "0.2-2.0"))
        self.assertIn("which is above the printed range", self.reading("--value", ">100", "--range", "10-90"))
        self.assertIn("cannot be placed", self.reading("--value", ">50", "--range", "10-90"))

    def test_labs_never_brings_a_range_of_its_own(self):
        out = ok("labs", "--test", "Ferritin", "--value", "12")
        self.assertIn("RANGE      none given", out)
        self.assertIn("never against one remembered", out)
        self.assertIn("MEASURES   nothing on file yet", out)
        self.assertIn("It is not a diagnosis", out)

    def test_labs_repeats_the_labs_flag_and_adds_none(self):
        out = ok("labs", "--test", "Potassium", "--value", "5.4", "--range", "3.5-5.1", "--flag", "H")
        self.assertIn("FLAG       H [the lab's own, as printed: repeat it, add none]", out)
        self.assertNotIn("CHECK", out)
        out = ok("labs", "--test", "Potassium", "--value", "4.4", "--range", "3.5-5.1", "--flag", "H")
        self.assertIn("CHECK      the flag and the printed range do not agree", out)
        self.assertIn("FLAG       none given", ok("labs", "--test", "Potassium", "--value", "5.4", "--range", "3.5-5.1"))

    def test_labs_errors_keep_the_value_to_themselves(self):
        for args in (("--value", "12abc34"), ("--value", "7", "--range", "nonsense77"), ("--value", "1,234.5"),
                     ("--value", "5", "--range", "9-3"), ("--value", "5", "--range", "3-9", "--low", "1")):
            err = fails("labs", "--test", "A test", *args)
            for secret in ("12abc34", "nonsense77", "1,234.5"):
                self.assertNotIn(secret, err)


class DosesTests(Base):
    def test_dose_lines(self):
        d = doses.parse_entry("08:00", "t")
        self.assertEqual((d.hour, d.minute, d.units, d.days, d.every), (8, 0, 1, None, None))
        self.assertEqual(doses.parse_entry("20:00 x2", "t").units, 2)
        self.assertEqual(doses.parse_entry("8.30 x0,5", "t").units, Fraction(1, 2))
        self.assertEqual(doses.parse_entry("21:30 x1/2", "t").units, Fraction(1, 2))
        self.assertEqual(doses.parse_entry("Mon Thu 08:00", "t").days, frozenset([0, 3]))
        self.assertEqual(doses.parse_entry("monday/friday 08:00 x 3", "t").days, frozenset([0, 4]))
        e = doses.parse_entry("every 2 days from 2026-11-01 08:00", "t")
        self.assertEqual((e.every, e.anchor), (2, date(2026, 11, 1)))
        self.assertEqual(doses.parse_entry("every other day 07:15", "t").every, 2)
        self.assertIsNone(doses.parse_entry("every 1 days 07:15", "t").every)
        self.assertEqual(doses.parse_entry("mon 08:00 x6", "t").words(), "08:00 on Mon, 6 each time")
        self.assertEqual(doses.parse_entry("mon wed fri 08:00", "t").words(), "08:00 on Mon, Wed and Fri")
        for bad in ("", "x2", "25:00", "08:00 x0", "noon", "mon tueday 08:00", "every 0 days 08:00", "08:00 x2000",
                    "every 2 days from 31.02.2026 08:00"):
            with self.assertRaises(core.VossError):
                doses.parse_entry(bad, "t")
        with self.assertRaises(core.VossError):
            doses.parse_doses(["08:00", "08:00"], "t")
        self.assertEqual(doses.parse_med("Vitamin B12:08:00")["name"], "Vitamin B12")
        self.assertEqual(len(doses.parse_med("Co-codamol 30/500: 08:00, 14:00, 20:00 x2")["doses"]), 3)

    def test_schedule_is_read_back_before_anything_is_written(self):
        out = ok("schedule", "--med", "Metformin 500 mg: 08:00, 20:00")
        self.assertIn("SCHEDULE   1 medicine from 2026-11-15 Sun [as given: this repeats a schedule, it does not set one]", out)
        self.assertIn("MEDICINE   Metformin 500 mg", out)
        self.assertIn("08:00 every day; first on 2026-11-15 Sun", out)
        self.assertIn("the prescription label and the pharmacist come first", out)
        self.assertIn("NEXT       read it back to the person", out)
        self.assertNotIn("CALENDAR", out)
        self.assertEqual(os.listdir(OUTPUTS), [n for n in os.listdir(OUTPUTS) if not n.endswith(".ics")])

    def calendar(self, out):
        path = field(out, "CALENDAR")
        with open(path, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b"BEGIN:VCALENDAR\r\n") and raw.endswith(b"END:VCALENDAR\r\n"), path)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "every line must end CRLF")
        self.assertTrue(all(len(line) <= 75 for line in raw.split(b"\r\n")), "a line is longer than 75 octets")
        text = raw.decode("utf-8")
        self.assertEqual(text.count("BEGIN:VEVENT"), text.count("UID:"))
        self.assertEqual(len(set(re.findall(r"UID:(\S+)", text))), text.count("UID:"))
        for stamp in re.findall(r"DTSTART:(\S+)", text):
            self.assertRegex(stamp, r"^\d{8}T\d{6}$", "a dose time carries no zone")
        return path, text, text.replace("\r\n ", "")

    def test_schedule_calendar(self):
        with tempfile.TemporaryDirectory() as d:
            out = ok("schedule", "--med", "Metformin 500 mg: 08:00, 20:00", "--med", "Methotrexate 2.5 mg: mon 08:00 x6",
                     "--med", "Patch: every 3 days from 2026-11-14 09:00", "--ics", d)
            path, text, flat = self.calendar(out)
            self.assertEqual(os.path.basename(path), "voss-medicines-2026-11-15.ics")
            self.assertEqual(text.count("BEGIN:VEVENT"), 4)
            self.assertIn("DTSTART:20261115T080000\r\nRRULE:FREQ=DAILY\r\nSUMMARY:Take: Metformin 500 mg", text)
            self.assertIn("DTSTART:20261115T200000\r\nRRULE:FREQ=DAILY\r\n", text)
            self.assertIn("DTSTART:20261116T080000\r\nRRULE:FREQ=WEEKLY;BYDAY=MO\r\nSUMMARY:Take 6: Methotrexate 2.5 mg", text)
            self.assertIn("DTSTART:20261117T090000\r\nRRULE:FREQ=DAILY;INTERVAL=3\r\nSUMMARY:Take: Patch", text)
            self.assertEqual(text.count("TRIGGER:PT0M"), 4)
            self.assertIn("If the label\\, the prescription or the pharmacist says otherwise\\, they are right.", flat)
            self.assertIn("times carry no zone", out)
            self.assertIn("lock screen", out)
            named = os.path.join(d, "course.ics")
            out = ok("schedule", "--med", "Amoxicillin 500 mg: 07:00, 15:00, 23:00", "--from", "2026-11-16", "--days", "7",
                     "--alarm", "10", "--discreet", "--ics", named)
            _, text, flat = self.calendar(out)
            self.assertEqual(field(out, "CALENDAR"), named)
            self.assertEqual(text.count("RRULE:FREQ=DAILY;UNTIL=20261122T235959"), 3)
            self.assertEqual(text.count("TRIGGER:-PT10M"), 3)
            self.assertNotIn("Amoxicillin", text)
            self.assertIn("SUMMARY:Medicine 1", text)
            out = ok("schedule", "--med", "Metformin 500 mg: 08:00", "--no-alarm", "--ics", d)
            self.assertNotIn("VALARM", self.calendar(out)[1])
        self.assertEqual(run("schedule", "--med", "Metformin 500 mg: 08:00", "--ics", os.path.join(ROOT, "no-such-folder"))[0], 2)

    def test_a_calendar_is_never_written_into_a_repository_or_the_skill(self):
        med = ["schedule", "--med", "Metformin 500 mg: 08:00"]
        self.assertIn("inside a git repository", fails(*(med + ["--ics", os.path.join(ROOT, "docs")])))
        self.assertIn("inside a git repository", fails(*(med + ["--ics", os.path.join(ROOT, "docs", "mine.ics")])))
        self.assertIn("inside the package Voss is running from", fails(*(med + ["--ics", os.path.join(SRC, "images")])))
        self.assertIn("inside a git repository", fails("refill", "--med", "A: 08:00", "--left", "9", "--ics", ROOT))
        self.assertFalse([n for n in os.listdir(os.path.join(ROOT, "docs")) if n.endswith(".ics")])
        # 'auto', with nowhere named: the current folder is this repository, so it goes on to the Downloads folder
        home = tempfile.mkdtemp(dir=OUTPUTS)
        os.makedirs(os.path.join(home, "Downloads"))
        keep = dict((k, os.environ.get(k)) for k in ("VOSS_OUTPUTS", "HOME", "USERPROFILE"))
        here = os.getcwd()
        try:
            os.environ.pop("VOSS_OUTPUTS")
            os.environ["HOME"] = os.environ["USERPROFILE"] = home
            os.chdir(ROOT)
            out = ok(*(med + ["--ics", "auto"]))
            self.assertEqual(os.path.dirname(field(out, "CALENDAR")), os.path.join(home, "Downloads"))
            shutil.rmtree(os.path.join(home, "Downloads"))
            self.assertEqual(os.path.dirname(field(ok(*(med + ["--ics", "auto"])), "CALENDAR")), home)
            with open(os.path.join(home, ".git"), "w") as f:
                f.write("gitdir: elsewhere\n")
            self.assertIn("nowhere fit for the calendar file", fails(*(med + ["--ics", "auto"])))
            self.assertIn("nowhere fit to write a private file",
                          fails("forget", "--id", "self", "--field", "allergies", "--confirm",
                                field(ok("forget", "--id", "self", "--field", "allergies"), "CONFIRM")))
        finally:
            os.chdir(here)
            for key, value in keep.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("*.ics", f.read().split())

    def test_schedule_refuses_what_it_was_not_given(self):
        self.assertIn("no medicine was given", fails("schedule"))
        self.assertIn("no dose times were given", fails("schedule", "--med", "Ibuprofen 200 mg:"))
        self.assertIn("--med looks like", fails("schedule", "--med", "08:00, 20:00"))
        self.assertIn("--until is before the first day", fails("schedule", "--med", "A: 08:00", "--until", "2026-11-01"))
        self.assertIn("give the end once", fails("schedule", "--med", "A: 08:00", "--until", "2026-12-01", "--days", "3"))
        err = fails("schedule", "--med", "Secretol 5 mg: 08:00, half past nine")
        self.assertNotIn("half past nine", err)
        out = ok("schedule", "--med", "A: every 2 days 08:00")
        self.assertIn("NOTE       A: 'every 2 days' is counted from 2026-11-15", out)

    def test_schedule_from_the_file(self):
        out = ok("schedule", "--id", "self")
        self.assertIn("SCHEDULE   2 medicines", out)
        self.assertIn("MEDICINE   Metformin 500 mg", out)
        self.assertIn("08:00 on Mon, 6 each time; first on 2026-11-16 Mon", out)
        self.assertIn("LEFT OUT   Salbutamol inhaler 100 micrograms: no dose times on file", out)
        self.assertIn("LEFT OUT   Ibuprofen 200 mg", out)
        self.assertNotIn("Vitamin D", out)
        self.assertIn("MEDICINE   Vitamin D 25 micrograms", ok("schedule", "--id", "self", "--supplements"))
        with tempfile.TemporaryDirectory() as d:
            _, text, flat = self.calendar(ok("schedule", "--id", "self", "--ics", d))
            self.assertIn("DESCRIPTION:one tablet with food. The schedule as it was given on 2026-11-15.", flat)

    def test_refill_counts_exactly(self):
        out = ok("refill", "--med", "Metformin 500 mg: 08:00, 20:00", "--pack", "60", "--opened", "2026-11-01")
        self.assertIn("CLOCK      2026-11-15 Sun 10:30 [this machine's clock", out)
        self.assertIn("PACK       60, opened 2026-11-01 Sun", out)
        self.assertIn("USED       29 in 29 doses up to now [derived: every scheduled dose counted as taken, the opening day included]", out)
        self.assertIn("LEFT       31 [derived]", out)
        self.assertIn("LAST DOSE  2026-11-30 Mon 20:00 is the last this pack covers [derived]", out)
        self.assertIn("RUNS OUT   2026-12-01 Tue 08:00, the first dose it cannot cover; 16 days from today [derived]", out)
        self.assertIn("REMIND     2026-11-24 Tue, 7 days before it runs out", out)
        self.assertIn("It knows nothing of missed or extra doses", out)
        out = ok("refill", "--med", "Metformin 500 mg: 08:00, 20:00", "--pack", "60", "--opened", "2026-11-01", "--now", "2026-11-15 07:59")
        self.assertIn("USED       28 in 28 doses", out)
        self.assertIn("[as given with --now]", out)
        self.assertIn("RUNS OUT   2026-12-01 Tue 08:00", out)

    def test_refill_other_shapes(self):
        out = ok("refill", "--med", "Levothyroxine 50 mcg: 07:00", "--left", "12", "--lead", "10")
        self.assertIn("LEFT       12 [counted by the person, as of 2026-11-15 Sun 10:30]", out)
        self.assertIn("LAST DOSE  2026-11-27 Fri 07:00", out)
        self.assertIn("RUNS OUT   2026-11-28 Sat 07:00, the first dose it cannot cover; 13 days from today", out)
        self.assertIn("REMIND     2026-11-18 Wed, 10 days before it runs out", out)
        out = ok("refill", "--med", "Methotrexate 2.5 mg: mon 08:00 x6", "--pack", "24", "--opened", "2026-11-02")
        self.assertIn("USED       12 in 2 doses", out)
        self.assertIn("LAST DOSE  2026-11-23 Mon 08:00", out)
        self.assertIn("RUNS OUT   2026-11-30 Mon 08:00", out)
        out = ok("refill", "--med", "Halves: 08:00 x0.5", "--pack", "10", "--opened", "2026-11-01")
        self.assertIn("USED       7.5 in 15 doses", out)
        self.assertIn("LEFT       2.5 [derived]", out)
        self.assertIn("RUNS OUT   2026-11-21 Sat 08:00", out)
        out = ok("refill", "--med", "Odd: 08:00 x2", "--left", "5")
        self.assertIn("1 will be left over, less than that dose needs", out)
        out = ok("refill", "--med", "Soon: 08:00, 20:00", "--left", "3")
        self.assertIn("REMIND     now: the pack runs out inside the 7-day lead", out)
        out = ok("refill", "--med", "Empty: 08:00", "--left", "0")
        self.assertIn("RUNS OUT   now: what is left does not cover the next dose, at 2026-11-16 Mon 08:00", out)

    def test_refill_says_when_the_sums_do_not_fit(self):
        out = ok("refill", "--med", "Metformin 500 mg: 08:00, 20:00", "--pack", "10", "--opened", "2026-11-01")
        self.assertIn("RAN OUT    by this schedule the pack could not cover the dose of 2026-11-06 Fri 08:00 [derived]", out)
        self.assertIn("Ask which: do not guess", out)
        self.assertNotIn("REMIND", out)
        self.assertIn("needs its first day", fails("refill", "--med", "A: every 2 days 08:00", "--left", "9"))
        self.assertIn("in the future", fails("refill", "--med", "A: 08:00", "--pack", "9", "--opened", "2026-11-16"))
        self.assertIn("go together", fails("refill", "--med", "A: 08:00", "--pack", "9"))
        self.assertIn("not both", fails("refill", "--med", "A: 08:00", "--pack", "9", "--opened", "2026-11-01", "--left", "3"))
        self.assertIn("more than ten years", fails("refill", "--med", "A: mon 08:00 x0.01", "--left", "99000"))
        self.assertIn("--lead", fails("refill", "--med", "A: 08:00", "--left", "3", "--lead", "400"))

    def test_refill_from_the_file_and_its_reminder(self):
        with tempfile.TemporaryDirectory() as d:
            out = ok("refill", "--id", "self", "--ics", d)
            self.assertIn("REFILL     Metformin 500 mg", out)
            self.assertIn("REFILL     Methotrexate 2.5 mg", out)
            self.assertIn("LEFT OUT   Ibuprofen 200 mg: no dose times on file", out)
            path = field(out, "CALENDAR")
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            self.assertEqual(text.count("BEGIN:VEVENT"), 2)
            self.assertIn("DTSTART;VALUE=DATE:20261124\r\nDTEND;VALUE=DATE:20261125\r\nSUMMARY:Refill: Metformin 500 mg", text)
            self.assertIn("DTSTART;VALUE=DATE:20261123\r\n", text)
            out = ok("refill", "--id", "self", "--name", "metformin", "--discreet", "--ics", d)
            self.assertNotIn("Methotrexate", out)
            with open(field(out, "CALENDAR"), encoding="utf-8", newline="") as f:
                self.assertNotIn("Metformin", f.read())


class GateTests(Base):
    def test_no_answer_is_ever_shown(self):
        outputs = [ok("boot") for _ in range(6)] + [ok("ignition")] + [ok("ignition", "--id", "self")]
        outputs += [ok("ignition", "--id", "self", "--q", str(n)) for n in (1, 2, 3, 4)]
        outputs += [ok("ignition", "--id", "self", "--q", "2", "--answer", "the", "Malverns"),
                    ok("ignition", "--id", "self", "--q", "3", "--answer", "green"),
                    ok("profile", "--id", "self"), ok("intake", "--id", "self", "--full"), ok("selftest"), ok("sources"),
                    ok("forget", "--id", "self", "--all", "--with-dependants")]
        outputs.append(fails("profile", "--id", "self", "--field", "ignition"))
        for out in outputs:
            for word in ANSWERS:
                self.assertNotIn(word, out.lower())

    def test_replies_are_judged_loosely(self):
        def verdict(q, *said):
            return ok("ignition", "--id", "self", "--q", str(q), "--answer", *said).split()[0]
        self.assertEqual(verdict(1, "Kittiwake"), "PASS")
        self.assertEqual(verdict(1, "the", "kitiwake,", "of", "course"), "PASS")
        self.assertEqual(verdict(1, "no", "idea"), "FAIL")
        self.assertEqual(verdict(2, "pendle", "hill,", "I", "think"), "PASS")
        self.assertEqual(verdict(2, "the", "Malverns"), "FAIL")
        self.assertEqual(verdict(3, "a", "sort", "of", "green"), "CLOSE")
        self.assertEqual(verdict(3, "GREEN,", "bottle"), "PASS")
        self.assertEqual(verdict(3, "butelkowa", "ziele\u0144"), "PASS")
        self.assertEqual(verdict(4, "a", "chello"), "PASS")
        self.assertEqual(verdict(4, "piano,", "cello,", "or", "the", "flute"), "CLOSE")
        self.assertEqual(run("ignition", "--id", "self", "--q", "9")[0], 2)
        self.assertIn("What was the name of the first boat?", ok("ignition", "--id", "self", "--q", "1"))
        self.assertIn("say which question", fails("ignition", "--id", "self", "--answer", "x"))

    def test_open_is_open(self):
        out = ok("ignition", "--id", "self", "--q", "1", "--answer", "kittiwake")
        self.assertEqual(out.strip(), "PASS       the gate is open for self, and it stays open for this conversation. Say so in your own words")
        # the tool judges and nothing more: no key to carry about, and no second door round the gate
        self.assertIn("PROFILE    self [profile]", ok("profile", "--id", "self"))
        for extra in (["--pass", "anything"], ["--emergency"]):
            self.assertEqual(run("profile", "--id", "self", *extra)[0], 2, extra)
        self.assertEqual(run("ignition", "--id", "self", "--vouched-by", "Beacon")[0], 2)

    def test_nobody_is_turned_away(self):
        out = ok("ignition", "--id", "self", "--q", "1", "--answer", "no", "idea")
        self.assertIn("after three misses the file stays shut: use nothing from it", out)
        self.assertIn("they still get your full care and everything you know, only without the file", out)
        self.assertIn("Emergency help is never held back", out)

    def test_a_dependant_is_guarded_by_the_carers_gate(self):
        out = ok("ignition", "--id", "pip", "--seed", "1")
        self.assertIn("pip is in the care of self: it is their gate that opens this record", out)
        self.assertRegex(out, r"ASK        .+\?  \(profile self, question \d\)")
        self.assertIn("PROFILE    pip [dependant]", ok("profile", "--id", "pip"))
        self.assertIn("pip: on, 4 questions [every new conversation], by the gate of self", ok("profile", "--id", "pip"))

        def orphan(data):
            data["dependants"][0]["carer"] = "nobody"
        copy_fixture(orphan)
        self.assertIn("the carer it names is not on file, so nothing guards it", fails("ignition", "--id", "pip"))
        self.assertIn("pip: the carer it names is not on file", ok("ignition"))
        self.assertIn("pip: the carer it names is not on file", ok("boot"))

    def test_no_questions_means_no_gate_and_it_says_so(self):
        out = ok("profile", "--id", "rowan")
        self.assertIn("GATE       rowan: off, no questions on file; questions and answers are never shown", out)
        self.assertIn("call_me    Rowan", out)
        self.assertIn("date_of_birth 1961; aged 64 or 65 [derived: only the year is on file]", out)
        self.assertIn("no questions on file, so the gate is off: anyone with this package could ask about the file",
                      ok("ignition", "--id", "rowan"))

        def off(data):
            data["profiles"][0]["ignition"]["setting"] = "off"
        copy_fixture(off)
        self.assertIn("self: switched off in the file (4 questions on file)", ok("profile", "--id", "self"))
        self.assertIn("switched off in the file", ok("ignition", "--id", "self"))
        self.assertIn("self: switched off in the file", ok("boot"))


class ProfileTests(Base):
    def test_read_back(self):
        out = ok("profile", "--id", "self")
        self.assertIn("PROFILE    self [profile]; on file since 2026-10-01, last changed 2026-11-02", out)
        self.assertIn("date_of_birth 1988-02-29; aged 38 [derived, today 2026-11-15]", out)
        self.assertIn("medical_reference human [the data is human medicine", out)
        self.assertIn("sex_assigned_at_birth declined (not asked again)", out)
        self.assertIn("weight_kg  value 68.5; measured 2025-09-30", out)
        self.assertIn("STALE      pregnancy: recorded more than 30 days ago, so it has expired", out)
        self.assertIn("STALE      medicines: 1 entry was told over a year ago", out)
        self.assertIn("STALE      recent_travel: 1 trip ended over three months ago", out)
        self.assertNotIn("the whole profile", out)
        self.assertNotIn("implants_devices", out)
        self.assertIn("in the care of self; consent: note their parent agreed", ok("profile", "--id", "pip"))
        self.assertIn("date_of_birth 2020-05-17; aged 6", ok("profile", "--id", "pip"))

    def test_a_profile_left_alone_for_a_year_is_asked_about_as_a_whole(self):
        def old(data):
            data["profiles"][0]["updated"] = "2025-11-14"
        copy_fixture(old)
        out = ok("profile", "--id", "self")
        self.assertIn("STALE      the whole profile: last changed 2025-11-14, over a year ago. Ask whether it still stands, "
                      "the weight first", out)
        self.assertIn("last changed 2026-10-20.", ok("boot"))

        def a_year_to_the_day(data):
            data["profiles"][0]["updated"] = "2025-11-15"
        copy_fixture(a_year_to_the_day)
        self.assertNotIn("the whole profile", ok("profile", "--id", "self"))

    def test_ages(self):
        self.assertEqual(record.age_words("2000-02-29", date(2026, 2, 28)), "aged 25 [derived, today 2026-02-28]")
        self.assertEqual(record.age_words("2000-02-29", date(2026, 3, 1)), "aged 26 [derived, today 2026-03-01]")
        self.assertEqual(record.age_words("2026-01-31", date(2026, 11, 15)), "aged 9 months [derived, today 2026-11-15]")
        self.assertEqual(record.age_words("2025-03-20", date(2026, 11, 15)), "aged 19 months [derived, today 2026-11-15]")
        self.assertEqual(record.age_words("1961", date(2026, 11, 15)), "aged 64 or 65 [derived: only the year is on file]")
        self.assertIn("cannot be read", record.age_words("2027-01-01", date(2026, 11, 15)))

    def test_parts_of_a_file(self):
        out = ok("profile", "--id", "self", "--section", "medicines")
        self.assertIn("MEDICINES", out)
        self.assertNotIn("WHO THEY ARE", out)
        self.assertEqual(ok("profile", "--id", "self", "--field", "allergies").strip(),
                         "allergies  substance penicillin; reaction a rash; told 2026-10-01")
        self.assertIn("nothing on file", ok("profile", "--id", "self", "--field", "intolerances"))
        self.assertIn("never shown", fails("profile", "--id", "self", "--field", "ignition"))
        self.assertIn("did you mean allergies?", fails("profile", "--id", "self", "--field", "alergies"))
        self.assertIn("--section is one of", fails("profile", "--id", "self", "--section", "everything"))
        self.assertIn("no profile with that id", fails("profile", "--id", "nobody"))
        self.assertIn("say whose file", fails("profile"))


class FileShapeTests(Base):
    def test_the_field_list_is_the_reference_word_for_word(self):
        with open(os.path.join(SRC, "references", "personal-file.md"), encoding="utf-8") as f:
            text = f.read()
        rows = {}
        for names, what, why in re.findall(r"(?m)^\| (`[a-z_`, ]+`) \| (.+?) \| (.+?) \|$", text):
            for name in re.findall(r"`([a-z_]+)`", names):
                rows[name] = (what, why)
        schema = personal.schema()
        listed = dict((f["name"], (f["what"], f["why"])) for f in schema["fields"] + schema["household"])
        self.assertEqual(listed, rows)
        with open(os.path.join(SCRIPTS, "data", "personal.template.json"), encoding="utf-8") as f:
            template = json.load(f)
        own = set(template["profiles"][0]) - set(personal.ENTRY_KEYS)
        self.assertEqual(own, set(f["name"] for f in schema["fields"]))
        self.assertEqual(set(template) - {"_about", "version", "profiles"}, set(f["name"] for f in schema["household"]))
        for spec in schema["fields"]:
            if spec["type"] in ("object", "objects", "records"):
                shape = template["profiles"][0][spec["name"]]
                shape = shape[0] if isinstance(shape, list) else shape
                self.assertEqual(set(shape), set(spec["keys"]), spec["name"])
        asked = schema["ask_first"] + schema["ask_routine"] + schema["ask_last"] + schema["ask_when_needed"] + schema["ask_on_request"]
        self.assertEqual(len(asked), len(set(asked)))
        self.assertEqual(set(asked), set(f["name"] for f in schema["fields"]) - {"medical_reference", "ignition", "symptom_diary", "lab_results"})
        self.assertEqual(personal.check(template, date(2026, 11, 15)), [])

    def test_a_file_is_checked_in_one_pass_and_nothing_in_it_is_quoted(self):
        self.assertEqual(personal.check(load_json(FIXTURE), date(2026, 11, 15)), [])
        bad = {
            "version": 3,
            "profiles": [
                {"id": "Bad Id", "call_me": 7},
                {"id": "ok", "weight_kg": {"value": "seventy", "measured": "last spring"}, "units": "stones",
                 "date_of_birth": "2031-01-01", "region": "Atlantis", "medical_reference": "dragon",
                 "medicines": [{"name": "Secretol", "schedule": ["whenever"]}], "favourite_colour": "teal",
                 "conditions": "none", "care_wishes": "card 4111 1111 1111 1111",
                 "ignition": {"setting": "sometimes", "questions": [{"q": "", "a": []}], "hint": "starts with K"}},
                {"id": "ok"},
            ],
            "dependants": [{"id": "kid", "carer": "nobody"}],
            "pets": "a cat",
        }
        found = personal.check(bad, date(2026, 11, 15))
        where = [w for _, w, _ in found]
        for place in ("profiles.1.id", "profiles.ok.weight_kg.value", "profiles.ok.weight_kg.measured", "profiles.ok.units",
                      "profiles.ok.date_of_birth", "profiles.ok.region", "profiles.ok.medical_reference",
                      "profiles.ok.medicines.1.schedule", "profiles.ok.favourite_colour", "profiles.ok.conditions",
                      "profiles.ok.care_wishes", "profiles.ok.ignition.setting", "profiles.ok.ignition.questions.1",
                      "profiles.ok.ignition.hint", "profiles.3.id", "dependants.kid.carer", "pets"):
            self.assertIn(place, where)
        said = " ".join(what for _, _, what in found)
        for secret in ("seventy", "last spring", "stones", "Atlantis", "Secretol", "whenever", "teal", "4111", "sometimes"):
            self.assertNotIn(secret, said)

    def test_numbers_that_are_never_kept(self):
        body = "9001010012"
        made_up = body + str((10 - sum(w * int(d) for w, d in zip((1, 3, 7, 9, 1, 3, 7, 9, 1, 3), body)) % 10) % 10)
        self.assertEqual(personal.never_stored("my number is %s" % made_up), "a national identity number")
        self.assertEqual(personal.never_stored("4111 1111 1111 1111"), "a payment card number")
        self.assertEqual(personal.never_stored("4111-1111-1111-1111"), "a payment card number")
        self.assertEqual(personal.never_stored("943 476 5919"), "a health service number")
        self.assertEqual(personal.never_stored("078-05-1120"), "a social security number")
        self.assertEqual(personal.never_stored("GB82 WEST 1234 5698 7654 32"), "a bank account number")
        self.assertEqual(personal.never_stored("passport XK1234567"), "an identity, insurance, bank or password detail")
        self.assertEqual(personal.never_stored("my password is hunter2"), "an identity, insurance, bank or password detail")
        self.assertEqual(personal.never_stored("gb82 west 1234 5698 7654 32"), "a bank account number")
        for fine in ("took 2 tablets at 08:00 on 2026-11-15", "asthma since 1999", "500 mg twice a day", "blood pressure 120/80",
                     "the passport office was shut", "4111 1111 1111 1112", "weighed 68.5 kg", "from 2026-11-15 10 ml a day",
                     "renewed my passport in 2025", "on 14.03.2019 1200 units, then 2026-11-15 08:00 again", "2026-11-15 2026-11-16 2026"):
            self.assertIsNone(personal.never_stored(fine), fine)
        self.assertIsNone(personal.never_stored("+44 20 7946 0123", "phone"))
        self.assertIsNone(personal.never_stored("Dr Hale, 020 7946 0123", "contact"))
        self.assertIsNone(personal.never_stored("943 476 5919", "contact"))


class IntakeTests(Base):
    def test_it_asks_little_and_says_why(self):
        out = ok("intake", "--id", "self")
        self.assertIn("NOTHING    nothing to ask just now", out)
        out = ok("intake", "--id", "self", "--full")
        asked = re.findall(r"(?m)^ASK\s+([a-z_]+):", out)
        self.assertEqual(asked, ["communication_needs", "intolerances"])
        self.assertIn("why a doctor asks: so he can actually be understood", out)
        self.assertIn('to store the answer: --add "intolerances: substance=...; what_happens=..."', out)
        self.assertIn("sex_assigned_at_birth, screening_organs, menstrual, substance_use", out)
        out = ok("intake", "--id", "self", "--full", "--have", "communication_needs,intolerances")
        self.assertEqual(re.findall(r"(?m)^ASK\s+([a-z_]+):", out), ["baseline_vitals", "implants_devices"])
        out = ok("intake", "--id", "self", "--needs", "menstrual")
        self.assertIn("ASK        menstrual: last period, cycle notes", out)
        self.assertIn("why a doctor asks: timing of symptoms, pregnancy questions, some labels", out)
        out = ok("intake", "--id", "self", "--needs", "sex_assigned_at_birth")
        self.assertIn("ON FILE    sex_assigned_at_birth is answered already", out)
        self.assertNotIn("ASK ", out)
        out = ok("intake", "--id", "rowan", "--full")
        self.assertEqual(re.findall(r"(?m)^ASK\s+([a-z_]+):", out), ["title", "species"])
        self.assertIn("call_me", ok("intake", "--fields"))
        use_personal(None)
        out = ok("intake", "--id", "self")
        self.assertIn("there is no personal file yet", out)
        self.assertIn("plain JSON", out)

    def changes(self):
        return ["--set", "communication_needs=short answers, please", "--set", "weight_kg: value=70,5; measured=yesterday",
                "--add", "intolerances: substance=lactose; what_happens=bloating", "--add", "sensory_aids=reading glasses",
                "--set", "care_contacts: pharmacy=the one on Mill Lane; emergency_contact.phone=+44 20 7946 0999",
                "--set", "settings: weekly_round=yes; wellbeing_checkin.on=yes; wellbeing_checkin.how_often=monthly",
                "--decline", "contraception"]

    def test_read_back_then_saved_exactly(self):
        out = ok("intake", "--id", "self", *self.changes())
        self.assertIn("READ BACK  for self. Nothing is saved yet", out)
        self.assertIn("SET        communication_needs: short answers, please", out)
        self.assertIn("SET        weight_kg: value 70.5; measured 2026-11-14", out)
        self.assertIn("ADD        intolerances: substance lactose; what_happens bloating; told 2026-11-15", out)
        self.assertIn("DECLINED   contraception", out)
        code = field(out, "CONFIRM")
        self.assertRegex(code, r"^[0-9a-f]{8}$")
        self.assertIn("nothing is saved without the read-back", fails("rebuild", "--id", "self", *self.changes()))
        self.assertIn("does not match", fails("rebuild", "--id", "self", "--confirm", "00000000", *self.changes()))
        other = self.changes()[:-2]
        self.assertIn("does not match", fails("rebuild", "--id", "self", "--confirm", code, *other))
        clock("2026-11-16T09:00")
        self.assertIn("does not match", fails("rebuild", "--id", "self", "--confirm", code, *self.changes()))
        clock()
        with tempfile.TemporaryDirectory() as d:
            out = ok("rebuild", "--id", "self", "--confirm", code, "--out", d, *self.changes())
            path = field(out, "PERSONAL")
            self.assertEqual(path, os.path.join(d, "personal.json"))
            self.assertIn("PRIVATE    it holds health information", out)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        me = data["profiles"][0]
        self.assertEqual(me["communication_needs"], "short answers, please")
        self.assertEqual(me["weight_kg"], {"value": 70.5, "measured": "2026-11-14"})
        self.assertEqual(me["intolerances"], [{"substance": "lactose", "what_happens": "bloating", "told": "2026-11-15"}])
        self.assertEqual(me["sensory_aids"], ["reading glasses"])
        self.assertEqual(me["care_contacts"]["pharmacy"], "the one on Mill Lane")
        self.assertEqual(me["care_contacts"]["doctor"], "Dr Hale, the Elm Street surgery")
        self.assertEqual(me["care_contacts"]["emergency_contact"], {"name": "Sorrel", "relation": "sister", "phone": "+44 20 7946 0999"})
        self.assertEqual(me["settings"]["wellbeing_checkin"], {"on": True, "how_often": "monthly"})
        self.assertTrue(me["settings"]["weekly_round"] and me["settings"]["desk_notices"])
        self.assertEqual(me["contraception"], "declined")
        self.assertEqual(me["updated"], "2026-11-15")
        self.assertEqual(me["ignition"], load_json(FIXTURE)["profiles"][0]["ignition"])
        self.assertEqual(data["profiles"][1], load_json(FIXTURE)["profiles"][1])
        self.assertEqual(personal.check(data, date(2026, 11, 15)), [])

    def test_a_list_entry_under_the_same_name_is_replaced(self):
        out = ok("intake", "--id", "self", "--add",
                 "medicines: name=metformin; strength=850 mg; schedule=08:00|20:00 x2; pack_size=90; pack_opened=2026-11-10")
        self.assertIn("(replaces the entry on file under the same name)", out)
        self.assertIn("schedule 08:00 | 20:00 x2", out)
        new, _ = record.apply(personal.load(), "self", [("add", "medicines", {"name": "metformin", "strength": "850 mg"})], date(2026, 11, 15))
        names = [m["name"] for m in new["profiles"][0]["medicines"]]
        self.assertEqual(names, ["Salbutamol inhaler", "Ibuprofen", "Methotrexate", "metformin"])
        self.assertIn("that is on file already", fails("intake", "--id", "rowan", "--add", "sensory_aids=x", "--add", "sensory_aids=X"))

    def test_what_it_will_not_store(self):
        cases = (
            (["--set", "care_wishes=my card is 4111 1111 1111 1111"], "a payment card number", "4111"),
            (["--add", "conditions: in_their_words=passport XK1234567"], "password detail", "XK1234567"),
            (["--set", "care_contacts: emergency_contact.phone=call me maybe"], "must be a phone number", "maybe"),
            (["--set", "medical_reference=dragon"], "the medical reference is human", "dragon!"),
            (["--set", "date_of_birth=31.02.1990"], "must be a full date", "31.02"),
            (["--set", "date_of_birth=2030-01-01"], "in the future", "2030"),
            (["--set", "region=Atlantis"], "two-letter country code", "Atlantis"),
            (["--set", "units=stones"], "must be one of: metric, imperial", "stones"),
            (["--set", "weight_kg: value=seventy"], "must be a plain number", "seventy"),
            (["--set", "weight_kg: value=70; measured=2027-01-01"], "in the future", "2027"),
            (["--set", "weight_kg: kilos=70"], "has no part 'kilos'", None),
            (["--set", "weight_kg=70"], "has parts", None),
            (["--set", "allergies: substance=x"], "is a list", None),
            (["--add", "allergies: reaction=a rash"], "needs its 'substance' part", "rash"),
            (["--add", "medicines: name=Secretol; schedule=whenever I remember"], "has no clock time", "remember"),
            (["--set", "ignition=x"], "types their own gate questions", None),
            (["--set", "lab_results=x"], "not built yet", None),
            (["--set", "shoe_size=9"], "not a field of the personal file", None),
            (["--decline", "ignition"], "not something a person declines", None),
            (["--gate", "sometimes"], "--gate is one of", None),
            (["--set", "no equals sign here"], "was not understood", None),
        )
        for args, expect, secret in cases:
            err = fails("intake", "--id", "self", *args)
            self.assertIn(expect, err, args)
            if secret:
                self.assertNotIn(secret, err, args)

    def test_new_profiles_and_dependants(self):
        out = ok("intake", "--id", "robin", "--new", "--set", "call_me=Robin", "--set", "pronouns=they/them")
        self.assertIn("NEW        profile robin", out)
        new, _ = record.apply(personal.load(), "robin", [("set", "call_me", "Robin")], date(2026, 11, 15), new=True)
        entry = new["profiles"][-1]
        self.assertEqual((entry["id"], entry["medical_reference"], entry["created"]), ("robin", "human", "2026-11-15"))
        self.assertIn("on file already", fails("intake", "--id", "self", "--new", "--set", "call_me=X"))
        self.assertIn("not the place for a name", fails("intake", "--id", "Robin Smith", "--new"))
        self.assertIn("add --new", fails("intake", "--id", "robin", "--set", "call_me=Robin"))
        self.assertIn("needs a word on consent", fails("intake", "--id", "kit", "--new", "--carer", "self"))
        self.assertIn("must be the id of a profile", fails("intake", "--id", "kit", "--new", "--carer", "pip", "--consent", "x"))
        out = ok("intake", "--id", "kit", "--new", "--carer", "self", "--consent", "his mother agreed for him",
                 "--set", "weight_kg: value=14; measured=today")
        self.assertIn("NEW        record kit, in the care of self; consent: his mother agreed for him", out)
        use_personal(None)
        out = ok("intake", "--id", "self", "--new", "--set", "call_me=First")
        code = field(out, "CONFIRM")
        with tempfile.TemporaryDirectory() as d:
            path = field(ok("rebuild", "--id", "self", "--new", "--set", "call_me=First", "--confirm", code, "--json", "--out", d), "PERSONAL")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(data["version"], 3)
        self.assertEqual([p["id"] for p in data["profiles"]], ["self"])
        self.assertIn("PRIVATE", data["_about"])


class RebuildTests(Base):
    def saved(self, *extra):
        change = ["--id", "self", "--gate", "when it matters"]
        code = field(ok("intake", *change), "CONFIRM")
        return ["rebuild"] + change + ["--confirm", code] + list(extra)

    def test_a_package_that_runs_with_the_change_in_it(self):
        with tempfile.TemporaryDirectory() as d:
            out = ok(*self.saved("--package", "--out", d))
            path = field(out, "PACKAGE").split(" (")[0]
            self.assertEqual(os.path.basename(path), "voss-private.zip")
            self.assertIn("still runs the old copy", out)
            self.assertIn("that file was not changed", out)
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                data = json.loads(z.read("scripts/data/personal.json").decode("utf-8"))
                z.extractall(os.path.join(d, "unpacked"))
            for must in ("SKILL.md", "scripts/voss.py", "scripts/vosslib/core.py", "references/clinical-rules.md", "images/manifest.json"):
                self.assertIn(must, names)
            self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
            self.assertEqual(data["profiles"][0]["ignition"]["setting"], "when it matters")
            self.assertEqual(len(data["profiles"][0]["ignition"]["questions"]), 4)
            env = dict((k, v) for k, v in os.environ.items() if not k.startswith("VOSS_"))
            env["VOSS_NOW"] = NOW
            done = subprocess.run([sys.executable, "-I", "-B", os.path.join(d, "unpacked", "scripts", "voss.py"), "selftest"],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("personal file: reads, and nothing in it needs fixing", done.stdout)
            boot = subprocess.run([sys.executable, "-I", "-B", os.path.join(d, "unpacked", "scripts", "voss.py"), "boot"],
                                  capture_output=True, text=True, env=env)
            self.assertIn("self: on, 4 questions [when it matters]", boot.stdout)

    def test_where_it_will_not_write(self):
        self.assertIn("inside a git repository", fails(*self.saved("--out", ROOT)))
        self.assertIn("inside the package Voss is running from", fails(*self.saved("--out", os.path.join(SRC, "references"))))
        self.assertIn("no such folder", fails(*self.saved("--out", os.path.join(OUTPUTS, "no-such-folder"))))
        path = copy_fixture()
        self.assertIn("that is the file this copy reads", fails(*self.saved("--out", path)))
        self.assertEqual(load_json(path)["profiles"][0]["ignition"]["setting"], "every new conversation")
        out = ok(*self.saved("--out", path, "--replace"))
        self.assertIn("the file in use was replaced, as the person asked", out)
        self.assertEqual(load_json(path)["profiles"][0]["ignition"]["setting"], "when it matters")
        self.assertFalse(os.path.exists(path + ".part"))
        self.assertIn("REBUILD    nothing to change was given", ok("rebuild", "--id", "self"))


class ForgetTests(Base):
    def forget(self, *what):
        """Read back, confirm, write; return (read-back, final output, the new file as text)."""
        args = ["forget", "--id", "self"] + list(what)
        back = ok(*args)
        self.assertIn("Nothing is removed yet", back)
        with tempfile.TemporaryDirectory() as d:
            out = ok(*(args + ["--confirm", field(back, "CONFIRM"), "--json", "--out", d]))
            with open(field(out, "PERSONAL"), encoding="utf-8") as f:
                return back, out, f.read()

    def test_a_field_goes_without_a_trace(self):
        back, out, text = self.forget("--field", "recent_travel")
        self.assertIn("REMOVE     recent_travel (1 entry)", back)
        self.assertIn("REMOVED    recent_travel (1 entry)", out)
        self.assertIn("FORGOTTEN  gone from the new file", out)
        self.assertIn("OLD COPIES", out)
        self.assertNotIn("Lisbon", text)
        self.assertNotIn("recent_travel", text)
        self.assertEqual(personal.check(json.loads(text), date(2026, 11, 15)), [])
        self.assertEqual(json.loads(text)["profiles"][0]["updated"], "2026-11-15")

    def test_one_entry_or_one_part(self):
        back, _, text = self.forget("--field", "medicines", "--match", "ibuprofen")
        self.assertIn("REMOVE     one entry from medicines: Ibuprofen", back)
        self.assertNotIn("Ibuprofen", text)
        self.assertIn("Metformin", text)
        _, _, text = self.forget("--field", "care_contacts.emergency_contact.phone")
        self.assertNotIn("7946", text)
        self.assertEqual(json.loads(text)["profiles"][0]["care_contacts"]["emergency_contact"], {"name": "Sorrel", "relation": "sister", "phone": ""})
        _, _, text = self.forget("--field", "allergies", "--match", "penicillin")
        self.assertNotIn("allergies", json.loads(text)["profiles"][0])
        _, _, text = self.forget("--field", "blood_type", "--field", "care_wishes", "--field", "sex_assigned_at_birth")
        for gone in ("blood_type", "care_wishes", "sex_assigned_at_birth", "donor"):
            self.assertNotIn(gone, text)

    def test_forget_me(self):
        self.assertIn("1 record is in this person's care", fails("forget", "--id", "self", "--all"))
        back, out, text = self.forget("--all", "--with-dependants")
        self.assertIn("REMOVE     the whole profile self, its gate included", back)
        self.assertIn("REMOVE     1 dependant's record in their care", back)
        self.assertIn("REMOVE     1 cabinet entry that belonged to them", back)
        data = json.loads(text)
        self.assertEqual([p["id"] for p in data["profiles"]], ["rowan"])
        self.assertEqual(data["dependants"], [])
        self.assertEqual(data["cabinet"], [])
        for gone in ("Wren", "Pip", "penicillin", "peanuts", "Kittiwake", "Paracetamol", "Sorrel", "squirrel"):
            self.assertNotIn(gone, text)
        back = ok("forget", "--id", "pip", "--all")
        self.assertIn("REMOVE     the whole record pip, its gate included", back)

    def test_what_it_refuses(self):
        base = ["forget", "--id", "self"]
        self.assertIn("say what to forget", fails(*base))
        self.assertIn("the person's own to edit", fails(*(base + ["--field", "ignition"])))
        self.assertIn("nothing is on file under intolerances", fails(*(base + ["--field", "intolerances"])))
        self.assertIn("--match fits nothing", fails(*(base + ["--field", "medicines", "--match", "aspirin"])))
        self.assertIn("more than one entry", fails(*(base + ["--field", "medicines", "--match", "met"])))
        self.assertIn("a single --field", fails(*(base + ["--field", "medicines", "--field", "allergies", "--match", "x"])))
        self.assertIn("leave out --field", fails(*(base + ["--all", "--field", "allergies"])))
        self.assertIn("does not match", fails(*(base + ["--field", "allergies", "--confirm", "00000000"])))
        self.assertIn("nothing is on file under care_contacts.pharmacy", fails(*(base + ["--field", "care_contacts.pharmacy"])))


class CheckTests(Base):
    def test_typography(self):
        code, out, _ = run("check", "--text", "He said \u201chello\u201d \u2014 it\u2019s fine")
        self.assertEqual(code, 1)
        self.assertIn("4 to fix", out)
        self.assertIn("clean", ok("check", "--text", "Plain text - with 'straight' quotes. Za\u017c\u00f3\u0142\u0107."))
        self.assertEqual(run("check", "--code", "--text", "x = 1 // za\u017c\u00f3\u0142\u0107")[0], 1)
        self.assertEqual(ok("check", "--fix", "--text", "\u201cA\u201d \u2013 B\u2026").strip(), '"A" - B...')

    def reply(self, *lines, **kw):
        args = ["check", "--reply"] + (["--emergency"] if kw.get("emergency") else []) + ["--mode", kw.get("mode", "clinic"), "--text"]
        return run(*(args + list(lines)))

    def test_a_clean_reply(self):
        code, out, _ = self.reply("It measures how well your kidneys filter. *ears perk*", "[mood: composed] [voss-composed.webp]")
        self.assertEqual(code, 0, out)
        self.assertIn("REPLY      clean as a clinic reply", out)
        self.assertIn("this checks form only", out)
        code, out, _ = self.reply("Flour first.", "[mood: pleased] [voss-pleased.webp] [look: baking] [voss-baking.webp]")
        self.assertEqual(code, 0, out)
        code, out, _ = self.reply("VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: not installed", "Good evening.",
                                  "[mood: composed] [voss-composed.webp]")
        self.assertEqual(code, 0, out)

    def test_the_marker_line(self):
        cases = (
            (["No marker here."], "no marker line"),
            (["Hm.", "[mood: smug] [voss-smug.webp]"], "mood 'smug' is not one of"),
            (["Hm.", "[mood: amused] [voss-smirk.webp]"], "the file for mood 'amused' is voss-amused.webp"),
            (["Hm.", "[mood: amused] [voss-amused.webp] [look: gardening] [voss-gardening.webp]"], "look 'gardening' is not one of"),
            (["[mood: amused] [voss-amused.webp]", "And another thing."], "not the last line"),
            (["Hm.", "[mood: amused] [voss-amused.webp]", "[mood: proud] [voss-proud.webp]"], "2 marker lines"),
            (["Hm.", "[Mood: Amused]"], "not a marker line as written"),
            (["```", "KEY value", "[mood: amused] [voss-amused.webp]", "```"], "inside a code or record block"),
            (["```", "KEY value", "[mood: amused] [voss-amused.webp]"], "opened and never closed"),
        )
        for lines, expect in cases:
            code, out, _ = self.reply(*lines)
            self.assertEqual(code, 1, lines)
            self.assertIn(expect, out, lines)

    def test_ears_and_stage_business(self):
        mark = "[mood: composed] [voss-composed.webp]"
        code, out, _ = self.reply("Well. *ears flatten*", "Really. *ears droop*", mark)
        self.assertEqual(code, 1)
        self.assertIn("2 ear cues: at most one per message in Clinic", out)
        code, out, _ = self.reply("```", "TEST x *ears perk*", "```", mark)
        self.assertIn("an ear cue inside a record block", out)
        code, out, _ = self.reply("*snaps on gloves* Let us begin.", mark)
        self.assertEqual(code, 0)
        self.assertIn("reads like an action line", out)
        code, out, _ = self.reply("*snaps on gloves* Wings first. *ears perk* *sighs*", mark, mode="theatre")
        self.assertEqual(code, 0)
        self.assertIn("clean as a theatre reply", out)
        code, out, _ = self.reply("**Bold is not an action.**", mark)
        self.assertNotIn("action line", out)

    def test_things_never_said(self):
        mark = "[mood: composed] [voss-composed.webp]"
        code, out, _ = self.reply("It's probably nothing.", mark)
        self.assertEqual(code, 1)
        self.assertIn('"probably nothing" is never said', out)
        code, out, _ = self.reply("I would stop taking it for a week.", mark)
        self.assertEqual(code, 0)
        self.assertIn("starting, stopping or changing a dose", out)
        code, out, _ = self.reply("No interaction on file, so it is safe.", mark)
        self.assertIn("absence is not safety", out)
        code, out, _ = self.reply("It\u2019s nothing.", mark)
        self.assertIn("reads like a verdict", out)
        code, out, _ = self.reply(*(["Line of talk."] * 13 + [mark]))
        self.assertIn("13 lines of prose", out)
        code, out, _ = self.reply("VOSS-01 | Project Asclepius | clinic", "Good evening.", mark)
        self.assertEqual(code, 1)
        self.assertIn("not the banner as 'boot' prints it", out)

    def test_an_emergency_answer(self):
        serious = "[mood: serious] [voss-serious.webp]"
        code, out, _ = self.reply("Call 112 now.", "Stay with me and I will tell you what to do while you wait.", serious, emergency=True)
        self.assertEqual(code, 0, out)
        self.assertIn("clean as an emergency answer: typography, the number first, no ears, the serious face", out)
        code, out, _ = self.reply("Call the emergency number now.", serious, emergency=True)
        self.assertEqual(code, 0, out)
        code, out, _ = self.reply("Call the emergency number now.", emergency=True)
        self.assertEqual(code, 1)
        self.assertIn("no marker line: every reply ends with one, and an emergency answer with [mood: serious] [voss-serious.webp]", out)
        code, out, _ = self.reply("That does sound unpleasant.", "You should call 112.", serious, emergency=True)
        self.assertEqual(code, 1)
        self.assertIn("leads with the number", out)
        code, out, _ = self.reply("Call 999 now. *ears flatten*", serious, emergency=True)
        self.assertEqual(code, 1)
        self.assertIn("no ears and no stage business in an emergency answer", out)
        self.assertNotIn("marker", out)
        code, out, _ = self.reply("Call 999 now.", "[mood: concerned] [voss-concerned.webp]", emergency=True)
        self.assertEqual(code, 1)
        self.assertIn("an emergency answer carries the serious face and no other: [mood: serious] [voss-serious.webp]", out)
        code, out, _ = self.reply("Call 999 now.", serious + " [look: on-duty] [voss-on-duty.webp]", emergency=True)
        self.assertEqual(code, 1)
        self.assertIn("no look in an emergency answer", out)
        # a long emergency answer is not told to be short: the steps while help comes take the room they need
        code, out, _ = self.reply(*(["Call 112 now."] + ["Press hard on the wound."] * 14 + [serious]), emergency=True)
        self.assertEqual(code, 0, out)

    def test_a_package_without_pictures_carries_no_marker(self):
        self.assertEqual(desk.reply_findings("Fine.", None), [])
        found = desk.reply_findings("Fine.\n[mood: composed] [voss-composed.webp]", None)
        self.assertEqual([f[0] for f in found], ["FIX"])
        self.assertIn("leave the marker line out", found[0][2])


class CalendarTests(Base):
    def test_format(self):
        stamp = datetime(2026, 11, 15, tzinfo=timezone.utc)
        long_title = "A, long; title \\ with every character that needs escaping, and enough words to run well past the limit"
        ev = ical.event(long_title, datetime(2026, 11, 16, 8, 0), rule="FREQ=DAILY", description="one\ntwo", alarm=timedelta(minutes=30))
        text = ical.build([ev], stamp=stamp)
        flat = text.replace("\r\n ", "")
        self.assertIn("SUMMARY:A\\, long\\; title \\\\ with every character", flat)
        self.assertIn("DESCRIPTION:one\\ntwo", flat)
        self.assertIn("DTSTAMP:20261115T000000Z", text)
        self.assertIn("DTSTART:20261116T080000\r\nRRULE:FREQ=DAILY", text)
        self.assertIn("TRIGGER:-PT30M", text)
        self.assertEqual(text, ical.build([ev], stamp=stamp))
        accents = ical.build([ical.event("\u017b\u00f3\u0142\u0107 " * 30, datetime(2026, 11, 16, 8, 0))], stamp=stamp)
        for line in accents.encode("utf-8").split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
            line.decode("utf-8")
        self.assertIn("\u017b\u00f3\u0142\u0107 " * 29, accents.replace("\r\n ", ""))
        self.assertNotIn("VALARM", accents)
        day = ical.build([ical.event("Refill", date(2027, 3, 14), alarm=timedelta(days=2))], stamp=stamp)
        self.assertIn("DTSTART;VALUE=DATE:20270314\r\nDTEND;VALUE=DATE:20270315", day)
        self.assertIn("TRIGGER:-P2D", day)
        same = ical.build([ical.event("Twin", datetime(2026, 11, 16, 8, 0)), ical.event("Twin", datetime(2026, 11, 16, 8, 0))], stamp=stamp)
        self.assertEqual(len(set(re.findall(r"UID:(\S+)", same))), 2)
        with self.assertRaises(core.VossError):
            ical.event("zoned", datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc))
        with self.assertRaises(core.VossError):
            ical.event("all day, repeating", date(2026, 11, 16), rule="FREQ=DAILY")


class BuildTests(Base):
    def tree(self):
        """A copy of the repository in the temp folder: enough of it to build from."""
        root = tempfile.mkdtemp(dir=OUTPUTS)
        skip = shutil.ignore_patterns("__pycache__", "*.pyc", "household.md", "personal.json", "private")
        shutil.copytree(SRC, os.path.join(root, "src"), ignore=skip)
        shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(root, "tools"), ignore=skip)
        for name in (".gitignore", "LICENSE", "README.md"):
            if os.path.exists(os.path.join(ROOT, name)):
                shutil.copyfile(os.path.join(ROOT, name), os.path.join(root, name))
        return root

    def household(self, root):
        """The made-up household file, kept in the copied repository as the real fixture is kept in this one."""
        folder = os.path.join(root, "tests", "fixtures")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "household.example.md")
        shutil.copyfile(HOUSEHOLD, path)
        os.environ["VOSS_HOUSEHOLD"] = path
        return path

    def quiet(self, func, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            problems = func(*args)
        return problems, out.getvalue()

    def test_leak_words_are_read_from_the_household_file(self):
        with open(HOUSEHOLD, encoding="utf-8") as f:
            self.assertEqual(build.leak_words(f.read()), ["Mira", "Quillfeather", "Lantern", "Axle", "Brackenford", "workshop"])
        self.assertEqual(build.leak_words("# x\n\n## Leak words\n\nSome words.\n\n- One\n- Two words\n* Three\n\n## After\n\n- Not this\n"),
                         ["One", "Two words", "Three"])
        self.assertIsNone(build.leak_words("# nothing of the kind\n"))
        self.assertEqual(build.leak_words("## Leak words\n\n```\n```\n"), [])

    def test_a_leak_word_is_a_whole_word_in_any_case(self):
        rx = build.leak_pattern("Axle")
        for hit in ("Axle said so", "ask AXLE.", "the axle's turn", "(axle)", "axle"):
            self.assertTrue(rx.search(hit), hit)
        for miss in ("axles", "Praxle", "ax le", "axle_grease", "axle2"):
            self.assertFalse(rx.search(miss), miss)
        phrase = build.leak_pattern("Maple Hollow")
        self.assertTrue(phrase.search("in maple\n  hollow, of all places"))
        self.assertFalse(phrase.search("maple, hollow"))
        self.assertTrue(build.leak_pattern("P\u00f3\u0142noc").search("z p\u00f3\u0142noc, i tyle"))
        self.assertFalse(build.leak_pattern("P\u00f3\u0142noc").search("p\u00f3\u0142nocny"))

    def test_the_public_build(self):
        root = self.tree()
        self.household(root)
        problems, said = self.quiet(build.build_public, root)
        self.assertEqual(problems, [])
        self.assertIn("LEAK CHECK passed: 6 words and phrases against", said)
        path = os.path.join(root, "dist", "voss.zip")
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        for must in ("SKILL.md", "CHANGELOG.md", "scripts/voss.py", "scripts/data/personal.template.json", "scripts/data/commands.json",
                     "images/manifest.json", "images/voss-composed.webp", "references/clinical-rules.md", "playbooks/theatre.md"):
            self.assertIn(must, names)
        self.assertFalse([n for n in names if build.is_private(n) or "__pycache__" in n])
        with open(path, "rb") as f:
            first = f.read()
        self.assertEqual(self.quiet(build.build_public, root)[0], [])
        with open(path, "rb") as f:
            self.assertEqual(first, f.read(), "on one machine, the same source must pack to the same bytes")

    def test_private_files_never_reach_the_public_build(self):
        root = self.tree()
        src = os.path.join(root, "src")
        shutil.copyfile(HOUSEHOLD, os.path.join(src, "references", "household.md"))
        shutil.copyfile(FIXTURE, os.path.join(src, "scripts", "data", "personal.json"))
        os.makedirs(os.path.join(src, "images", "private"))
        shutil.copyfile(os.path.join(SRC, "images", "voss-proud.webp"), os.path.join(src, "images", "private", "scene.webp"))
        problems, said = self.quiet(build.build_public, root)
        self.assertEqual(problems, [])
        self.assertIn("left out, as always: images/private/scene.webp, references/household.md, scripts/data/personal.json", said)
        self.assertIn("LEAK CHECK passed", said)
        with zipfile.ZipFile(os.path.join(root, "dist", "voss.zip")) as z:
            names = z.namelist()
            everything = b"".join(z.read(n) for n in names)
        self.assertFalse([n for n in names if "household" in n or n.endswith("personal.json") or "private" in n])
        for word in (b"Quillfeather", b"Brackenford", b"Kittiwake", b"Wren", b"Sorrel", b"Lisbon"):
            self.assertNotIn(word, everything, word)

    def test_one_leak_word_and_nothing_is_packed(self):
        root = self.tree()
        self.household(root)
        with open(os.path.join(root, "src", "references", "voss-self.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\nBuilt in the Workshop, as it happens.\n")
        problems, _ = self.quiet(build.build_public, root)
        self.assertEqual(len([p for p in problems if p.startswith("leak word in src/references/voss-self.md line ")]), 1)
        self.assertFalse(any("orkshop" in p for p in problems), "the word itself is not printed unless asked for")
        self.assertFalse(os.path.exists(os.path.join(root, "dist", "voss.zip")))
        build.SHOW_WORDS = True
        try:
            problems, _ = self.quiet(build.build_public, root)
        finally:
            build.SHOW_WORDS = False
        self.assertTrue(any(p.endswith(": workshop") for p in problems))

    def test_leaks_outside_the_package_and_in_odd_places(self):
        root = self.tree()
        self.household(root)
        shutil.copyfile(HOUSEHOLD, os.path.join(root, "tests", "a-stray-copy.md"))
        os.makedirs(os.path.join(root, "docs"))
        with open(os.path.join(root, "docs", "notes.md"), "w", encoding="utf-8") as f:
            f.write("line one\nline two mentions LANTERN\n")
        with open(os.path.join(root, "tools", "axle.txt"), "w", encoding="utf-8") as f:
            f.write("nothing here\n")
        exif = b"made by Mira Quillfeather"
        body = b"WEBP" + b"VP8 " + struct.pack("<I", 4) + b"\0\0\0\0" + b"EXIF" + struct.pack("<I", len(exif)) + exif + b"\0"
        with open(os.path.join(root, "src", "images", "voss-serious.webp"), "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
        with open(os.path.join(root, "LICENSE"), "a", encoding="utf-8") as f:
            f.write("Copyright (c) Mira Quillfeather\n")
        problems, _ = self.quiet(build.build_public, root)
        self.assertIn("leak word in docs/notes.md line 2", problems)
        self.assertIn("leak word in tools/axle.txt, in the file's name", problems)
        self.assertIn("leak word in src/images/voss-serious.webp line 1", problems)
        self.assertFalse(any("LICENSE" in p for p in problems), "the licence carries its holder's name")
        self.assertFalse(any("household.example.md" in p for p in problems), "the list of words is not itself a leak")
        self.assertTrue(any("tests/a-stray-copy.md" in p for p in problems), "but a second copy of it somewhere public is")

    def test_the_author_may_sign_the_credit_line_and_nothing_else(self):
        root = self.tree()
        self.household(root)
        credit = "- Voss, the VOSS-01 design and the pictures: Mira Quillfeather.\n"
        readme = os.path.join(root, "README.md")
        with open(readme, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + credit)
        self.assertEqual(self.quiet(build.build_public, root)[0], [])
        with open(readme, "a", encoding="utf-8", newline="\n") as f:
            f.write("With thanks to Mira.\n")
        with open(os.path.join(root, "tools", "notes.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(credit)
        problems, _ = self.quiet(build.build_public, root)
        self.assertEqual(len([p for p in problems if p.startswith("leak word in README.md line ")]), 1)
        self.assertEqual(len([p for p in problems if p.startswith("leak word in tools/notes.md line 1")]), 2,
                         "the same line in any other file is still a leak")

    def test_no_household_file_skips_only_the_leak_check(self):
        root = self.tree()
        problems, said = self.quiet(build.build_public, root)
        self.assertEqual(problems, [])
        self.assertIn("LEAK CHECK skipped", said)
        with open(os.path.join(root, "src", "references", "household.md"), "w", encoding="utf-8") as f:
            f.write("# The household\n\nNo list at all.\n")
        problems, _ = self.quiet(build.build_public, root)
        self.assertEqual(problems, ["the household file has no 'Leak words' section: the leak check cannot run"])

    def test_what_else_stops_a_build(self):
        root = self.tree()
        src = os.path.join(root, "src")

        def edit(rel, old, new):
            path = os.path.join(root, *rel.split("/"))
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn(old, text, rel)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text.replace(old, new, 1))

        edit("src/images/manifest.json", '"version": "%s"' % vosslib.VERSION, '"version": "9.9.9"')
        edit("src/scripts/data/personal.template.json", '"call_me": ""', '"call_me": "Somebody"')
        edit(".gitignore", "src/references/household.md\n", "")
        edit("src/references/features.md", "# Features", "# Features \u2014 all of them")
        edit("src/SKILL.md", "| references/voss-self.md |", "| see `references/no-such-file.md` |")
        shutil.copyfile(os.path.join(SRC, "images", "voss-proud.webp"), os.path.join(src, "images", "voss-smug.webp"))
        os.remove(os.path.join(src, "images", "voss-baking.webp"))
        with open(os.path.join(src, "scripts", "vosslib", "extra.py"), "w", encoding="utf-8") as f:
            f.write("# caf\u00e9\n")
        make_db(os.path.join(src, "scripts", "data"), "region-zz", licence=False)
        with open(os.path.join(src, "scripts", "data", "half-built.db.part"), "wb") as f:
            f.write(b"left behind by a build that stopped")
        problems, _ = self.quiet(build.build_public, root)
        text = "\n".join(problems)
        for expect in ("versions disagree", "personal.template.json has 'call_me' filled in", ".gitignore does not list src/references/household.md",
                       "references/features.md line 1 col", "SKILL.md points at references/no-such-file.md",
                       "images/voss-smug.webp is not in images/manifest.json", "names voss-baking.webp, which is not in images/",
                       "scripts/vosslib/extra.py has non-ASCII bytes", "scripts/data/region-zz.db has no LICENSE-region-zz.txt beside it",
                       "scripts/data/SOURCES.md does not list region-zz.db among the files that are installed",
                       "scripts/data/half-built.db.part is a half-built database", "selftest failed in the public build"):
            self.assertIn(expect, text)
        self.assertFalse(os.path.exists(os.path.join(root, "dist", "voss.zip")))

    def test_the_private_build(self):
        root = self.tree()
        os.environ["VOSS_HOUSEHOLD"] = HOUSEHOLD
        os.environ["VOSS_PERSONAL"] = FIXTURE
        self.assertIn("never written inside a git repository", self.quiet(build.build_private, root, os.path.join(root, "dist"))[0][0])
        self.assertIn("never written inside a git repository", self.quiet(build.build_private, root, ROOT)[0][0])
        out_dir = tempfile.mkdtemp(dir=OUTPUTS)
        problems, said = self.quiet(build.build_private, root, out_dir)
        self.assertEqual(problems, [])
        self.assertIn("with the household file and the personal file", said)
        with zipfile.ZipFile(os.path.join(out_dir, "voss-private.zip")) as z:
            names = z.namelist()
            self.assertIn(b"Quillfeather", z.read("references/household.md"))
            self.assertEqual(json.loads(z.read("scripts/data/personal.json").decode("utf-8"))["profiles"][0]["call_me"], "Wren")
        self.assertIn("SKILL.md", names)
        self.assertFalse(os.path.exists(os.path.join(root, "src", "references", "household.md")), "nothing private is written into the repository")
        os.environ.pop("VOSS_PERSONAL")
        problems, said = self.quiet(build.build_private, root, out_dir)
        self.assertEqual(problems, [])
        self.assertIn("without a personal file", said)
        os.environ.pop("VOSS_HOUSEHOLD")
        self.assertIn("nothing private to add", self.quiet(build.build_private, root, out_dir)[0][0])


class PackageTests(Base):
    def test_every_example_in_the_help_runs(self):
        voss.build_parser()
        registry = list(core.REGISTRY)
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with open(os.path.join(folder, "reply.txt"), "w", encoding="utf-8") as f:
            f.write("*snaps on gloves* Wings first, then the tail.\n[mood: amused] [voss-amused.webp]\n")
        with open(os.path.join(folder, "draft.txt"), "w", encoding="utf-8") as f:
            f.write("A \u201cdraft\u201d \u2013 with the wrong quotes.\n")
        here = os.getcwd()
        os.chdir(folder)
        # the examples name real topics and real countries, so they run against the data that ships
        shipped = os.path.isfile(os.path.join(REAL_DATA, "core-pd.db"))
        if shipped:
            os.environ.pop("VOSS_DATA")
        try:
            for group, name, summary, examples in registry:
                self.assertTrue(summary and not summary.endswith(".") and len(summary) <= 125, name)
                self.assertTrue(examples, "%s has no examples" % name)
                for ex in examples:
                    args = shlex.split(ex)
                    if (not shipped and (name == "term" or "--country" in args)) or (
                            name == "code" and not os.path.isfile(os.path.join(REAL_DATA, "icd11.db"))) or (
                            name in ("interact", "watch") and not os.path.isfile(os.path.join(REAL_DATA, "ddinter.db"))) or (
                            name in ("med", "sidefx") and not os.path.isfile(os.path.join(REAL_DATA, "labels-us.db"))):
                        continue
                    if "CODE" in args:
                        probe = [a for a in args if a not in ("--json", "--package")]
                        at = probe.index("--confirm")
                        del probe[at:at + 2]
                        probe[0] = "intake" if probe[0] == "rebuild" else probe[0]
                        args[args.index("CODE")] = field(ok(*probe), "CONFIRM")
                    code, out, err = run(*args)
                    self.assertEqual(code, 0, "example failed: voss.py %s\n%s%s" % (ex, out, err))
                    self.assertTrue(out.strip(), ex)
        finally:
            os.chdir(here)

    def test_output_obeys_the_typography_rule(self):
        samples = [("boot", "--seed", "1"), ("theatre",), ("theatre", "--off"), ("sources",), ("selftest",), ("tools",),
                   ("tools", "--examples"), ("triage",), ("visit", "--diary-days", "3"), ("intake", "--fields"),
                   ("labs", "--test", "CRP", "--value", "<0.5", "--range", "<5.0", "--flag", "H"),
                   ("schedule", "--med", "Metformin 500 mg: 08:00, 20:00 x2"), ("refill", "--med", "A: 08:00", "--left", "9"),
                   ("ignition",), ("ignition", "--id", "self", "--seed", "1"), ("profile", "--id", "self"),
                   ("ignition", "--id", "self", "--q", "1", "--answer", "no idea"), ("intake", "--id", "self", "--full"),
                   ("forget", "--id", "self", "--field", "allergies")]
        for args in samples:
            self.assertEqual(desk.check_text(ok(*args)), [], args)
            self.assertFalse([ln for ln in ok(*args).splitlines() if ln != ln.rstrip()], args)

    def test_sources_are_plain_ascii(self):
        for root in (SCRIPTS, os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
            for folder, _, files in os.walk(root):
                for f in files:
                    if f.endswith(".py"):
                        with open(os.path.join(folder, f), "rb") as fh:
                            data = fh.read()
                        self.assertTrue(all(b < 128 for b in data), "%s has non-ASCII bytes" % f)
                        self.assertNotIn(b"\t", data, f)
                        self.assertNotIn(b"\r", data, f)

    def test_every_text_file_obeys_the_typography_rule(self):
        checked = 0
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "dist", "private")]
            for f in files:
                if not f.endswith((".md", ".py", ".json", ".txt", ".gitignore", ".gitattributes")) and f != "LICENSE":
                    continue
                path = os.path.join(folder, f)
                rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                if rel in ("src/references/household.md", "src/scripts/data/personal.json"):
                    continue
                with open(path, encoding="utf-8") as fh:
                    found = desk.check_text(fh.read())
                self.assertEqual([(ln, col, what) for ln, col, _, what, _ in found], [], rel)
                checked += 1
        self.assertGreater(checked, 30)

    def test_nothing_reaches_for_the_network(self):
        banned = re.compile(r"^\s*(?:import|from)\s+(socket|urllib|http|ftplib|smtplib|ssl|requests|asyncio|telnetlib|xmlrpc)\b", re.M)
        for folder, _, files in os.walk(SCRIPTS):
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        self.assertIsNone(banned.search(fh.read()), "%s imports a network module" % f)

    def test_only_the_chosen_commands_exist(self):
        names = [c["name"] for c in index.load()["commands"]]
        self.assertEqual(sorted(names), sorted(["boot", "theatre", "sources", "check", "selftest", "tools", "triage", "visit", "labs",
                                                "term", "code", "schedule", "refill", "interact", "watch", "med", "sidefx", "ignition",
                                                "profile", "intake", "rebuild", "forget"]))
        for name in names:
            for word in UNCHOSEN:
                self.assertNotIn(word, name)

    def test_the_versions_agree(self):
        with open(os.path.join(SRC, "SKILL.md"), encoding="utf-8") as f:
            fm = build.frontmatter(f.read())
        with open(os.path.join(SRC, "images", "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        with open(os.path.join(SRC, "CHANGELOG.md"), encoding="utf-8") as f:
            newest = re.search(r"(?m)^## (\d+\.\d+\.\d+)\b", f.read()).group(1)
        self.assertEqual({fm["version"], manifest["version"], vosslib.VERSION, newest}, {vosslib.VERSION})
        self.assertEqual(fm["name"], "voss")
        self.assertTrue(50 <= len(fm["description"]) <= 1024)
        self.assertNotIn("''", fm["description"])

    def test_the_pictures_and_their_list_agree(self):
        problems, manifest = build.check_images(SRC)
        self.assertEqual(problems, [])
        self.assertEqual([m["key"] for m in manifest["moods"]],
                         ["composed", "focused", "sceptical", "exasperated", "pleased", "concerned", "amused", "proud", "flustered", "serious"])
        self.assertEqual([m["key"] for m in manifest["looks"]], ["on-duty", "baking"])

    def test_broken_pipe_is_quiet(self):
        class Closed(io.StringIO):
            def write(self, s):
                raise BrokenPipeError()
        err = io.StringIO()
        with contextlib.redirect_stdout(Closed()), contextlib.redirect_stderr(err):
            code = voss.main(["tools"])
            self.assertEqual(getattr(sys.stdout, "name", None), os.devnull)
            sys.stdout.close()          # main() left stdout on the null device; in a test nothing else closes it
        sys.stdout = sys.__stdout__
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")

    def test_a_value_that_starts_with_a_minus_is_not_an_option(self):
        self.assertEqual(voss.protect(["labs", "--range", "-2-3", "--value", "-1.5"]), ["labs", "--range=-2-3", "--value", "-1.5"])
        self.assertEqual(voss.protect(["labs", "--range=-2-3"]), ["labs", "--range=-2-3"])


class IndexTests(Base):
    def test_the_index_on_file_is_what_the_commands_say(self):
        self.assertEqual(build_index.current(), build_index.render(SCRIPTS), "run  python tools/build_index.py")

    def test_every_command_has_a_module_and_everyday_words(self):
        data = index.load()
        names = [c["name"] for c in data["commands"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(index.ALSO), set(names))
        self.assertEqual(index.module_of("refill"), "doses")
        self.assertEqual(index.module_of("tools"), "index")
        self.assertIsNone(index.module_of("no_such_command"))
        for c in data["commands"]:
            self.assertIn(c["module"], vosslib.MODULES, c["name"])
            self.assertIn(c["group"], [g for g, _ in core.GROUPS], c["name"])

    def test_a_call_loads_only_the_module_it_needs(self):
        code = ("import sys; sys.path.insert(0, %r); import voss; voss.main(['triage', '--level', '1']); "
                "print('LOADED', ' '.join(sorted(m for m in sys.modules if m.startswith('vosslib.'))))" % SCRIPTS)
        out = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        loaded = out.stdout.split("LOADED ")[1].split()
        self.assertEqual(loaded, ["vosslib.clinic", "vosslib.core", "vosslib.index"])

    def test_a_missing_index_only_costs_time(self):
        kept, path = index._index, index.INDEX_FILE
        try:
            index._index, index.INDEX_FILE = None, os.path.join(OUTPUTS, "no-such-index.json")
            rebuilt = index.load()
            self.assertEqual([c["name"] for c in rebuilt["commands"]], [c["name"] for c in build_index_names()])
            self.assertIn("LEVEL 1", ok("triage"))
        finally:
            index._index, index.INDEX_FILE = kept, path

    def test_an_unknown_command_is_an_ordinary_error(self):
        code, out, err = run("frobnicate")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_find(self):
        for question, first in (("when do the tablets run out", "refill"), ("get ready for the doctor", "visit"),
                                ("is this an emergency", "triage"), ("blood test result", "labs"),
                                ("calendar for my medicines", "schedule"), ("what do you know about me", "profile"),
                                ("forget me", "forget"), ("which licence", "sources"), ("roleplay scene", "theatre"),
                                ("who is speaking", "ignition")):
            got = ok("tools", "--find", *question.split()).splitlines()[1].split()[0]
            self.assertEqual(got, first, question)
        for question, first in (("what does this word mean", "term"), ("which number do I call abroad", "triage"),
                                ("the icd code on my discharge letter", "code"), ("can I take these two tablets together", "interact"),
                                ("the doctor prescribed something new", "watch"), ("what is this pill for", "med"),
                                ("could this be a side effect", "sidefx")):
            self.assertEqual(ok("tools", "--find", *question.split()).splitlines()[1].split()[0], first, question)
        self.assertIn("no command answers that", ok("tools", "--find", "zzzzqq"))
        self.assertEqual(run("tools", "--find", "time", "--limit", "0")[0], 2)
        self.assertIn("CLINIC", ok("tools", "--group", "clinic"))
        self.assertEqual(run("tools", "--group", "nonsense")[0], 2)
        self.assertIn("22 commands.", ok("tools"))

    def test_compiled_files_go_to_the_temp_folder_only_when_the_skill_is_read_only(self):
        kept = (sys.dont_write_bytecode, sys.pycache_prefix, os.access, dict(os.environ))
        try:
            sys.pycache_prefix = None
            sys.dont_write_bytecode = True
            self.assertIsNone(voss.cache_elsewhere(SCRIPTS))            # Python was told not to write them
            sys.dont_write_bytecode = False
            self.assertIsNone(voss.cache_elsewhere(SCRIPTS))            # the folder can be written to: leave Python alone
            self.assertIsNone(sys.pycache_prefix)
            os.access = lambda path, mode: False
            for name in ("TMPDIR", "TEMP", "TMP"):
                os.environ[name] = OUTPUTS
            os.environ["VOSS_NO_CACHE"] = "1"
            self.assertIsNone(voss.cache_elsewhere(SCRIPTS))
            del os.environ["VOSS_NO_CACHE"]
            path = voss.cache_elsewhere(SCRIPTS)
            self.assertTrue(path and os.path.isdir(path) and os.path.dirname(path) == OUTPUTS, path)
            self.assertEqual(sys.pycache_prefix, path)
            self.assertIsNone(voss.cache_elsewhere(SCRIPTS))            # already set: not ours to change
        finally:
            sys.dont_write_bytecode, sys.pycache_prefix, os.access = kept[0], kept[1], kept[2]
            os.environ.clear()
            os.environ.update(kept[3])


def build_index_names():
    return json.loads(build_index.render(SCRIPTS))["commands"]


class SmallThingsTests(Base):
    def test_dates_and_numbers(self):
        self.assertEqual(core.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(core.add_months(date(2025, 12, 15), 2), date(2026, 2, 15))
        self.assertEqual(core.add_months(date(2026, 3, 31), -1), date(2026, 2, 28))
        self.assertEqual(core.parse_date("08.11.2026"), date(2026, 11, 8))
        self.assertEqual(core.parse_date("tomorrow", date(2026, 11, 15)), date(2026, 11, 16))
        self.assertIsNone(core.parse_date("2026-02-30"))
        self.assertIsNone(core.parse_date("tomorrow"))
        self.assertEqual(core.parse_clock("0830"), (8, 30))
        self.assertEqual(core.decimal_of("5,40", "x"), Decimal("5.40"))
        self.assertEqual(core.plain(Decimal("5.40") - Decimal("5.1")), "0.3")
        self.assertEqual(core.plain(Decimal("100")), "100")
        self.assertEqual(core.show_amount(Fraction(7, 3)), "2 1/3")
        self.assertEqual(core.show_amount(Fraction(15, 2)), "7.5")
        self.assertEqual(core.fold("Wis\u0142a  Krak\u00f3w"), "wisla_krakow")
        for bad in ("1,234.5", "five", "1e3", ""):
            with self.assertRaises(core.VossError):
                core.decimal_of(bad, "x")
        self.assertEqual(personal.part_date("2019-3"), "2019-03")
        self.assertEqual(personal.part_date("14.03.2019"), "2019-03-14")
        self.assertIsNone(personal.part_date("spring 2019"))
        self.assertEqual(personal.when_text("2026-12-01T9:05"), "2026-12-01 09:05")
        self.assertTrue(core.same_path(ROOT.upper(), ROOT.lower()) or os.name != "nt")
        self.assertTrue(core.within(SCRIPTS, SRC) and not core.within(SRC, SCRIPTS))
        self.assertTrue(core.inside_repository(SCRIPTS))
        self.assertFalse(core.inside_repository(OUTPUTS))


class StoreTests(Base):
    def test_text_goes_in_and_comes_out_the_same(self):
        raw = ("Plain prose squeezes well, and the same words come round again. " * 300).encode("utf-8")
        self.assertIn(store.ZLIB, store.available())
        for codec in store.available():
            used, packed = store.pack(raw, codec)
            self.assertEqual(used, codec)
            self.assertEqual(store.unpack(packed, used), raw, codec)
            if codec != store.RAW:
                self.assertLess(len(packed), len(raw) // 10, codec)
        used, packed = store.pack(raw, store.SMALLEST)
        self.assertEqual(len(packed), min(len(store.pack(raw, c)[1]) for c in store.available()))
        self.assertEqual(store.unpack(packed, used), raw)
        self.assertEqual(store.pack(b"ab", store.ZLIB), (store.RAW, b"ab"), "what does not shrink is kept as it is")

    def test_a_piece_is_found_again_by_its_address(self):
        con = sqlite3.connect(":memory:")
        texts = dbtools.Texts(con, block_bytes=100)
        first = texts.add("alpha " * 5)
        second = texts.add("z\u00f3\u0142\u0107 " * 5)
        again = texts.add("alpha " * 5)
        third = texts.add("gamma " * 20)
        raw, packed = texts.close()
        self.assertEqual(first, (1, 0, 30))
        self.assertEqual(second, (1, 30, 40))
        self.assertEqual(again, first, "the same text is stored once")
        self.assertEqual(third, (2, 0, 120))
        self.assertEqual(texts.add(""), (None, 0, 0))
        self.assertEqual(raw, 190)
        reader = store.Reader(con)
        self.assertEqual(reader.text(*first), "alpha " * 5)
        self.assertEqual(reader.text(*second), "z\u00f3\u0142\u0107 " * 5)
        self.assertEqual(reader.text(*third), "gamma " * 20)
        self.assertEqual(reader.text(None, 0, 0), "")
        self.assertEqual(sum(len(block) for _, block in reader.everything()), raw)
        for bad in ((99, 0, 5), (1, 60, 500)):
            with self.assertRaises(core.VossError):
                reader.text(*bad)
        con.close()

    def test_a_damaged_or_unknown_block_says_so(self):
        for codec in store.available():
            if codec == store.RAW:
                continue
            with self.assertRaises(core.VossError) as caught:
                store.unpack(b"this is not packed text", codec)
            self.assertIn("damaged", str(caught.exception))
        with self.assertRaises(core.VossError) as caught:
            store.unpack(b"x", "a codec nobody has heard of")
        self.assertIn("newer toolkit", str(caught.exception))
        kept = store.lzma
        try:
            store.lzma = None
            with self.assertRaises(core.VossError) as caught:
                store.unpack(b"x", store.LZMA)
            self.assertIn("which this Python was built without", str(caught.exception))
            self.assertNotIn(store.LZMA, store.available())
        finally:
            store.lzma = kept


class CoreBuildTests(Base):
    """tools/build_core.py, run on the made-up files in tests/fixtures/core."""

    SUMMARY = "\n".join([
        "## What is a wobbly knee?", "",
        "A wobbly knee is a made-up condition that the tests use. It isn't real - nothing here is advice, and it says \"so\" itself.", "",
        "## What are the signs?", "",
        "- A knee that wobbles", "- Trouble on stairs:", "  - going up", "  - going down", "",
        "If the knee gives way completely, call 911.", "",
        "Grade | Wobble", "1 | a little", "2 | a lot", "",
        "NIH: National Institute of Made-Up Things"])

    def test_a_summary_becomes_plain_text_and_nothing_else_is_taken(self):
        with small_samples():
            topics, generated = build_core.read_topics(os.path.join(CORE, "mplus_topics_sample.xml"))
        self.assertEqual(generated, "2026-11-10")
        self.assertEqual([t["id"] for t in topics], [16, 13, 14, 15, 11], "English topics only, by title")
        knee = topics[-1]
        self.assertEqual(knee["text"], self.SUMMARY)
        self.assertEqual((knee["title"], knee["created"], knee["institute"]),
                         ("Wobbly Knee", "2001-03-04", "National Institute of Made-Up Things"))
        self.assertEqual((knee["also"], knee["see"], knee["mesh"]), (["WK", "Knee wobble"], ["Knee Instability"], ["Knee Instability"]))
        self.assertEqual(knee["groups"], ["Bones, Joints and Muscles", "Made-Up Conditions"])
        self.assertEqual(knee["related"], [13, 999])
        self.assertEqual(topics[0]["text"], "")
        everything = json.dumps(topics)
        for left_out in ("picture", "Somebody", "Other people", "Rodilla", "example.org/made-up"):
            self.assertNotIn(left_out, everything)
        self.assertEqual(build_core.plain("<p>one<br>two</p><ol><li>a</li></ol><script>x()</script>"), "one\ntwo\n\n- a")
        self.assertEqual(build_core.iso_date("1/2/2015"), "2015-01-02")
        self.assertEqual(build_core.iso_date("yesterday"), "")

    def test_definitions(self):
        got = build_core.read_definitions([os.path.join(CORE, "sampledefinitions.xml")])
        self.assertEqual([(d["title"], d["origin"]) for d in got],
                         [("Wobble Index (WI)", "National Institute of Made-Up Things"), ("Wobbly Knee", "NIH Made-Up")])
        self.assertEqual(got[0]["text"], "The wobble index says how much a made-up knee wobbles. It is not real.")
        self.assertEqual(got[1]["page"], "Definitions of Health Terms: Made-Up Things")

    def test_numbers_are_put_in_the_order_to_say_them(self):
        with small_samples():
            countries, left = build_core.read_numbers(os.path.join(CORE, "emergency.sample.json"))
        ems, fire = "emergency medical services", "fire department"
        self.assertEqual(sorted(countries), ["AU", "CN", "FR", "NZ", "PL", "US"])
        self.assertEqual(countries["PL"][1], [("112", "", False), ("999", ems, False), ("997", "police", False), ("998", fire, False)])
        self.assertEqual(countries["FR"][1], [("112", "", True), ("15", ems, False), ("17", "police", False)],
                         "a member state of the EU has 112, whether or not the source lists it")
        self.assertEqual(countries["AU"][1], [("000", "", False), ("112", "alternative", False), ("106", "teleprinter", False)])
        self.assertEqual(countries["CN"][1], [("120", ems, False), ("119", fire, False), ("110", "police", False)])
        self.assertEqual((countries["CN"][0], countries["CN"][2]), ("China", "People's Republic of China"))
        self.assertEqual(countries["US"][0], "United States")
        self.assertEqual(left, ["ZQ: a number without digits, left out"])

    def test_the_database_it_writes(self):
        folder = sample_data()
        said = _sample["said"]
        for line in ("5 health topics, 2 definitions, 6 countries with emergency numbers",
                     "retrieved: topics 2026-11-10 (file generated 2026-11-10), definitions 2026-11-10, numbers 2026-11-10",
                     "112 added from the EU page, where Wikidata does not list it: FR", "NOTE ZQ: a number without digits, left out"):
            self.assertIn(line, said)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE-core-pd.txt", "core-pd.db"])
        info = library.read(os.path.join(folder, "core-pd.db"))
        self.assertEqual(info["problems"], [])
        self.assertEqual(info["built"], date(2026, 11, 15))
        self.assertEqual([s["retrieved"] for s in info["sources"]], [date(2026, 11, 10)] * 4)
        self.assertEqual([s["credit"] for s in info["sources"]], [build_core.CREDIT, build_core.CREDIT, "", ""])
        with open(os.path.join(folder, "LICENSE-core-pd.txt"), encoding="utf-8") as f:
            licence = f.read()
        for must in ("Source: MedlinePlus, National Library of Medicine", "CC0 1.0", "not verified one by one", "A.D.A.M."):
            self.assertIn(must, licence)
        con = library.connect(os.path.join(folder, "core-pd.db"))
        try:
            self.assertEqual(dict(con.execute("SELECT key, value FROM build"))["topics"], "5")
            names = set(con.execute("SELECT folded, kind FROM name WHERE entry = 13"))
            self.assertEqual(names, {("creaky_elbow", "title"), ("ce_creak", "also called"), ("a_creak", "also called")},
                             "brackets that are not an abbreviation are not split into names of their own")
            self.assertEqual(set(f for (f,) in con.execute("SELECT folded FROM name WHERE entry > 1000 AND kind = 'title'")),
                             {"wobble_index_wi", "wobble_index", "wi", "wobbly_knee"})
            self.assertEqual(con.execute("SELECT other FROM related WHERE entry = 11").fetchall(), [(13,)])
            reader = store.Reader(con)
            block, start, length = con.execute("SELECT block, start, length FROM entry WHERE id = 11").fetchone()
            self.assertEqual(reader.text(block, start, length), self.SUMMARY)
            everything = b"".join(raw for _, raw in reader.everything()).decode("utf-8")
            for left_out in ("Rodilla", "Esto no se guarda", "Other people's words", "picture"):
                self.assertNotIn(left_out, everything)
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("DELETE FROM entry")
        finally:
            con.close()

    def stops(self, *extra, **files):
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught:
            build_sample(folder, *extra, **files)
        self.assertEqual(os.listdir(folder), [], "a build that stops leaves nothing behind")
        return str(caught.exception)

    def test_what_stops_a_build(self):
        self.assertIn("has no note of when it was downloaded", self.stops())
        self.assertIn("--retrieved is in the future", self.stops("--retrieved", "2026-11-16"))
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with open(os.path.join(CORE, "mplus_topics_sample.xml"), encoding="utf-8") as f:
            text = f.read()
        short = os.path.join(folder, "short.xml")
        with open(short, "w", encoding="utf-8") as f:
            f.write(text.replace('total="6"', 'total="9"'))
        self.assertIn("says it holds 9 topics and 6 were read", self.stops("--retrieved", "2026-11-10", topics=short))
        page = os.path.join(folder, "page.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write("<p>112 is a number.</p>")
        self.assertIn("no longer says", self.stops("--retrieved", "2026-11-10", **{"eu-page": page}))
        self.assertIn("no such file", self.stops("--retrieved", "2026-11-10", numbers=os.path.join(folder, "nothing.json")))
        self.assertIn("--numbers is a file", self.stops("--retrieved", "2026-11-10", numbers="https://example.org/numbers.json"))
        out = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            build_core.main(["--topics", os.path.join(CORE, "mplus_topics_sample.xml"), "--definitions",
                             os.path.join(CORE, "sampledefinitions.xml"), "--numbers", os.path.join(CORE, "emergency.sample.json"),
                             "--eu-page", os.path.join(CORE, "eu-112.sample.html"), "--retrieved", "2026-11-10", "--out", out])
        self.assertIn("only 5 English topics were read", str(caught.exception))

    def test_reading_wikidata_request_by_request(self):
        """The fetch, with the network stood in for: what is asked for, what is kept, and how it picks up again."""
        asked = []
        claims = {
            ("Q36", "P297"): [{"mainsnak": {"datavalue": {"value": "pl"}}, "rank": "normal"}],
            ("Q36", "P2852"): [
                {"mainsnak": {"datavalue": {"value": {"id": "Q100"}}}, "rank": "normal"},
                {"mainsnak": {"datavalue": {"value": {"id": "Q101"}}}, "rank": "normal",
                 "qualifiers": {"P366": [{"datavalue": {"value": {"id": "Q200"}}}], "P582": [{"datavalue": {"value": {"time": "+2020"}}}]}},
                {"mainsnak": {"snaktype": "somevalue"}, "rank": "normal"}],
            ("Q30", "P297"): [{"mainsnak": {"datavalue": {"value": "US"}}, "rank": "normal"},
                              {"mainsnak": {"datavalue": {"value": "XX"}}, "rank": "deprecated"}],
            ("Q30", "P2852"): [{"mainsnak": {"datavalue": {"value": {"id": "Q102"}}}, "rank": "preferred",
                                "qualifiers": {"P1535": [{"datavalue": {"value": {"id": "Q201"}}}]}}],
        }
        labels = {"Q36": "Poland", "Q30": "United States of America", "Q100": "112", "Q101": "985", "Q102": "a helpline",
                  "Q200": "mountain rescue", "Q201": "teleprinter"}

        def fake(params):
            asked.append(params)
            if params["action"] == "query":
                if "sroffset" not in params:
                    return {"query": {"search": [{"title": "Q36"}]}, "continue": {"sroffset": 1, "continue": "-||"}}
                return {"query": {"search": [{"title": "Q30"}, {"title": "Q36"}]}}
            if params["action"] == "wbgetclaims":
                if params["entity"] == "Q36" and params["property"] == "P2852" and fake.fail:
                    fake.fail = False
                    raise SystemExit("could not fetch")
                return {"claims": {params["property"]: claims[(params["entity"], params["property"])]}}
            out = {}
            for qid in params["ids"].split("|"):
                out[qid] = {"labels": {"en": {"value": labels[qid]}}}
                if qid == "Q102" and "claims" in params["props"]:
                    out[qid]["claims"] = {"P1329": [{"mainsnak": {"datavalue": {"value": "911"}}}]}
            return {"entities": out}

        fake.fail = True
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        path = os.path.join(folder, "emergency.wikidata.json")
        kept = build_core.api
        build_core.api = fake
        try:
            with small_samples(), contextlib.redirect_stdout(io.StringIO()):
                build_core.MIN_COUNTRIES = 2
                with self.assertRaises(SystemExit):
                    build_core.fetch_numbers(path)
                self.assertFalse(os.path.exists(path))
                self.assertEqual(sorted(load_json(path + ".partial")["done"]), ["Q30"], "what was read is kept")
                before = len(asked)
                build_core.fetch_numbers(path)
        finally:
            build_core.api = kept
        again = [p for p in asked[before:] if p["action"] == "wbgetclaims"]
        self.assertEqual([(p["entity"], p["property"]) for p in again], [("Q36", "P297"), ("Q36", "P2852")], "and not read twice")
        self.assertFalse(os.path.exists(path + ".partial"))
        doc = load_json(path)
        self.assertEqual([c["item"] for c in doc["countries"]], ["Q30", "Q36"])
        usa, poland = doc["countries"]
        self.assertEqual((usa["codes"], usa["name"]), (["US"], "United States of America"))
        self.assertEqual(usa["numbers"], [{"item": "Q102", "rank": "preferred", "use": [], "notes": ["teleprinter"], "ended": False,
                                           "number": "911"}])
        self.assertEqual(poland["codes"], ["PL"])
        self.assertEqual([(n["number"], n["use"], n["ended"]) for n in poland["numbers"]],
                         [("112", [], False), ("985", ["mountain rescue"], True)])
        self.assertEqual(load_json(path + dbtools.NOTE)["retrieved"], "2026-11-15")
        self.assertNotIn("VOSS", dbtools.AGENT.upper(), "nothing about the project goes out with a request")


class CoreData(Base):
    """Tests that run against the small database built from the made-up files."""

    def setUp(self):
        Base.setUp(self)
        os.environ["VOSS_DATA"] = sample_data()


class TermTests(CoreData):
    def test_a_topic_in_the_sources_own_words(self):
        out = ok("term", "wobbly", "knee")
        topic, definition = out.split("\n\n" + "TERM ", 1) if "\n\nTERM " in out else (out, "")
        for line in ("TERM       Wobbly Knee [health topic, id 11]", "ALSO       WK; Knee wobble; Knee Instability",
                     "GROUP      Bones, Joints and Muscles; Made-Up Conditions", "SUMMARY    the source's own words, in full",
                     "SEE ALSO   Creaky Elbow", "PAGE       https://example.org/wobblyknee.html",
                     "SOURCE     MedlinePlus health topics, National Library of Medicine, retrieved 2026-11-10 "
                     "[sourced: core-pd.db, built 2026-11-15]",
                     "CREDIT     Source: MedlinePlus, National Library of Medicine"):
            self.assertIn(line, topic)
        self.assertIn(CoreBuildTests.SUMMARY, topic)
        self.assertNotIn("MESH", topic, "a heading that only repeats a name already shown is not said twice")
        for line in ("Wobbly Knee [definition]", "MEANS      A knee that wobbles, in the tests only.",
                     "FROM       NIH Made-Up; Definitions of Health Terms: Made-Up Things", "PAGE       https://example.org/knee.html",
                     "SOURCE     MedlinePlus definitions of health terms, National Library of Medicine, retrieved 2026-11-10"):
            self.assertIn(line, definition)
        self.assertIn("RULE       these are the source's words, about the thing and not about the person: nothing here is a diagnosis", out)
        self.assertIn("where it names 911 or an American service, give the person's own ('triage --country')", out)
        self.assertIn("a lab value is still read against the range printed on the person's own report", out)

    def test_names_it_is_found_under(self):
        def title(*words):
            return field(ok("term", *words), "TERM")
        self.assertEqual(title("WK"), "Wobbly Knee [health topic, id 11]")
        self.assertEqual(title("knee", "instability"), "Wobbly Knee [health topic, id 11]")
        self.assertEqual(title("wi"), "Wobble Index (WI) [definition]")
        self.assertEqual(title("wobble", "index"), "Wobble Index (WI) [definition]")
        self.assertEqual(title("CE"), "Creaky Elbow [health topic, id 13]")
        self.assertEqual(title("acreak"), "Creaky Elbow [health topic, id 13]", "written together or apart")
        self.assertEqual(title("what", "is", "a", "creaky", "elbow"), "Creaky Elbow [health topic, id 13]")
        self.assertEqual(title("Creaky", "elbows"), "Creaky Elbow [health topic, id 13]", "a plural is the same word")
        self.assertEqual(title("knee"), "Knee Tests [health topic, id 14]", "found by its medical heading")
        self.assertIn("MESH       Knee [Medical Subject Headings, National Library of Medicine]", ok("term", "knee"))
        self.assertEqual(title("--id", "15"), "Summer Sniffles [health topic, id 15]")

    def test_near_misses_are_listed_not_guessed(self):
        out = ok("term", "wobbl")
        self.assertIn("MATCHES    3 entries whose names hold those words", out)
        self.assertIn("Wobbly Knee [health topic, id 11]: A made-up topic for the tests: what a wobbly knee is", out)
        self.assertIn("Wobble Index (WI) [definition]: The wobble index says how much", out)
        self.assertIn("NEXT       say which is meant", out)
        self.assertNotIn("SUMMARY", out)
        out = ok("term", "wobly", "knee")
        self.assertIn("MATCHES    nothing under that spelling; 2 entries with a name close to it", out)
        out = ok("term", "sumer", "sniffles")
        self.assertIn("NEAREST    nothing is on file under that spelling; this is the nearest name", out)
        self.assertIn("TERM       Summer Sniffles [health topic, id 15]", out)
        out = ok("term", "creaky", "--list")
        self.assertIn("MATCHES    1 entry whose names hold those words", out)
        out = ok("term", "pollen")
        self.assertIn("MATCHES    no entry is named that; 2 entries whose summaries mention those words", out)
        self.assertLess(out.index("Summer Sniffles"), out.index("Creaky Elbow"), "the one that says it most comes first")
        self.assertIn("and 1 more: add a word to narrow it", ok("term", "wobbl", "--max", "2"))

    def test_nothing_on_file_is_said_as_such(self):
        out = ok("term", "zygomorphic")
        self.assertIn("TERM       nothing on file under those words, in any name or in any summary", out)
        self.assertIn("that is a gap in this file, not a fact about the word", out)
        self.assertIn("say which word or topic", fails("term"))
        self.assertIn("no entry has that id", fails("term", "--id", "999"))
        self.assertIn("not both", fails("term", "--id", "11", "knee"))
        self.assertIn("--max is 1 to 50", fails("term", "knee", "--max", "0"))

    def test_brief_and_a_topic_with_no_summary(self):
        out = ok("term", "--id", "15", "--brief")
        self.assertIn("BRIEF      A made-up topic for the tests: sneezing in the summer.", out)
        self.assertIn("'term --id 15' prints the whole summary", out)
        self.assertNotIn("pollen", out)
        self.assertIn("BRIEF      the source gives this topic no summary", ok("term", "--id", "16"))

    def test_output_obeys_the_typography_rule(self):
        for args in (("term", "wobbly", "knee"), ("term", "wobbl"), ("term", "pollen"), ("triage", "--country", "FR"), ("sources",)):
            out = ok(*args)
            self.assertEqual(desk.check_text(out), [], args)
            self.assertFalse([ln for ln in out.splitlines() if ln != ln.rstrip()], args)

    def test_without_the_database_it_says_so(self):
        os.environ["VOSS_DATA"] = NO_DATA
        err = fails("term", "knee")
        self.assertIn("core-pd.db is not installed, so there is nothing on file for medical words and health topics", err)
        self.assertIn("or say you have no data", err)
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        shutil.copyfile(os.path.join(sample_data(), "core-pd.db"), os.path.join(folder, "core-pd.db"))
        os.environ["VOSS_DATA"] = folder
        self.assertIn("cannot be answered from: it has no LICENSE-core-pd.txt beside it", fails("term", "knee"))

    def test_stale_data_says_so_before_the_answer(self):
        clock("2027-05-11T09:00")
        out = ok("term", "wk")
        self.assertTrue(out.startswith("STALE      core-pd.db: retrieved 2026-11-10, 182 days ago: STALE, the limit is 6 months"), out)
        self.assertTrue(ok("triage", "--country", "PL").startswith("STALE      core-pd.db"))
        clock("2027-05-10T09:00")
        self.assertTrue(ok("term", "wk").startswith("TERM "))


class NumbersTests(CoreData):
    def test_a_countrys_numbers_with_their_source(self):
        out = ok("triage", "--country", "PL")
        self.assertIn("NUMBERS    Poland (PL): 112; 999 [emergency medical services]; 997 [police]; 998 [fire department]", out)
        self.assertIn("the first is the one to lead with", out)
        self.assertIn("EU         112 is the European emergency number: free of charge, and it reaches an ambulance, the fire brigade "
                      "or the police anywhere in the European Union", out)
        self.assertIn("SOURCE     Wikidata: emergency telephone numbers by country (property P2852), retrieved 2026-11-10 "
                      "[sourced: core-pd.db, built 2026-11-15]", out)
        self.assertIn("European Commission: 112, the EU's emergency phone number, retrieved 2026-11-10", out)
        self.assertIn("were not verified one by one", out)
        self.assertIn("ANSWER     a red flag ends the guessing. Lead with the number", out)
        self.assertNotIn("LEVEL", out)
        self.assertNotIn("984", out, "a number the source has withdrawn is not passed on")
        self.assertNotIn("985", out, "nor one that has ended")

    def test_by_code_or_by_name(self):
        def listed(*words):
            return field(ok("triage", "--country", *words), "NUMBERS")
        self.assertEqual(listed("fr"), "France (FR): 112; 15 [emergency medical services]; 17 [police]")
        self.assertEqual(listed("new zealand"), "New Zealand (NZ): 111")
        self.assertEqual(listed("USA"), "United States (US): 911")
        self.assertEqual(listed("United States of America"), "United States (US): 911")
        self.assertEqual(listed("china"), "China (CN): 120 [emergency medical services]; 119 [fire department]; 110 [police]")
        self.assertEqual(listed("Australia"), "Australia (AU): 000; 112 [alternative]; 106 [teleprinter]")
        self.assertNotIn("EU  ", ok("triage", "--country", "AU"))
        out = ok("triage", "--country", "Narnia")
        self.assertIn("NUMBERS    nothing on file for that country", out)
        self.assertIn("tell them to call their local emergency number", out)
        self.assertIn("did you mean Poland?", ok("triage", "--country", "Polnad"))
        self.assertIn("nothing on file for that country", ok("triage", "--country", "ZQ"))

    def test_it_sits_with_the_rest_of_triage(self):
        out = ok("triage")
        self.assertIn("NUMBERS    by country: 'triage --country PL'", out)
        out = ok("triage", "--flags", "--country", "AU")
        self.assertIn("RED FLAGS", out)
        self.assertIn("Australia (AU): 000", out)
        out = ok("triage", "--level", "1", "--country", "US")
        self.assertIn("LEVEL 1    Emergency now", out)
        self.assertIn("United States (US): 911", out)
        os.environ["VOSS_DATA"] = NO_DATA
        self.assertIn("core-pd.db is not installed, so there is nothing on file for emergency numbers", fails("triage", "--country", "PL"))

    def test_boot_sources_and_selftest_see_the_database(self):
        self.assertEqual(field(ok("boot"), "BANNER"), "VOSS-01 | PROJECT ASCLEPIUS | CLINIC | data: 2026-11-15")
        out = ok("sources")
        self.assertIn("core-pd.db (", out)
        self.assertIn("credit, to be kept with every answer from it: Source: MedlinePlus, National Library of Medicine", out)
        self.assertIn("licence: CC0 1.0, a public domain dedication", out)
        out = ok("selftest")
        self.assertIn("PASS       data: core-pd.db says where it came from and when it was built", out)
        self.assertIn("PASS       data: the text in core-pd.db unpacks on this Python", out)
        self.assertIn("SELFTEST   17 of 17 passed; data: 2026-11-15", out)


class IcdBuildTests(Base):
    """tools/build_icd11.py, run on a made-up tabulation in the shape of WHO's."""

    def test_the_file_goes_in_whole_and_comes_out_the_same(self):
        folder = sample_icd()
        said = _sample["icd-said"]
        for line in ("release 2026-01 (2026 Jan 01 - 00:00 UTC): 2 chapters, 1 blocks, 7 categories",
                     "checked: the records in the database put WHO's file back together, byte for byte",
                     "retrieved 2026-11-10; licence document read 2026-11-10"):
            self.assertIn(line, said)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE-icd11.txt", "icd11.db"])
        path = os.path.join(folder, "icd11.db")
        with open(_sample["icd-file"], "rb") as f:
            original = f.read()
        con = library.connect(path)
        try:
            self.assertEqual(build_icd11.rebuilt(con), original, "every byte of the source file, the byte order mark included")
            facts = dict(con.execute("SELECT key, value FROM build"))
            self.assertEqual((facts["release"], facts["records"], facts["licence-read"]), ("2026-01", "10", "2026-11-10"))
            self.assertEqual(con.execute("SELECT title, parent, residual FROM entity WHERE code = 'ZA00.Y'").fetchone(),
                             ("Other specified wobbly knee", 3, 1))
            self.assertEqual(con.execute("SELECT title FROM entity WHERE code = 'ZA02'").fetchone()[0],
                             "Sj\u00f6gren-like dryness \u2013 of the tests", "not a character of a title is touched")
        finally:
            con.close()
        self.assertEqual(build_icd11.verify(path, _sample["icd-file"]), "")
        self.assertEqual(build_icd11.verify(path), "")
        info = library.read(path)
        self.assertEqual(info["problems"], [])
        self.assertEqual(info["sources"][0]["credit"], build_icd11.CITATION)
        self.assertIn("CC BY-ND 3.0 IGO", info["sources"][0]["licence"])
        with open(os.path.join(folder, "LICENSE-icd11.txt"), encoding="utf-8") as f:
            licence = f.read()
        for must in (build_icd11.CITATION, "https://creativecommons.org/licenses/by-nd/3.0/igo/", "NOT under the licence of the code",
                     "There is no translation and no such table here", "WHO does not", "Not from WHO: three helper columns"):
            self.assertIn(must, licence)

    def test_a_record_out_of_place_is_caught(self):
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        path = os.path.join(folder, "icd11.db")
        shutil.copyfile(os.path.join(sample_icd(), "icd11.db"), path)
        con = sqlite3.connect(path)
        first, second = con.execute("SELECT start, length FROM entity WHERE id IN (3, 7) ORDER BY id").fetchall()
        con.execute("UPDATE entity SET start = ?, length = ? WHERE id = 3", second)
        con.execute("UPDATE entity SET start = ?, length = ? WHERE id = 7", first)
        con.commit()
        con.close()
        self.assertIn("no longer add up to the checksum", build_icd11.verify(path))
        other = icd_file(ICD_RECORDS[:-1])
        self.assertIn("not the file the database was built from", build_icd11.verify(os.path.join(sample_icd(), "icd11.db"), other))

    def stops(self, tabulation, *extra):
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught:
            build_icd(folder, tabulation, *extra)
        self.assertEqual(os.listdir(folder), [], "a build that stops leaves nothing behind")
        return str(caught.exception)

    def test_what_stops_a_build(self):
        good = ("--release", "2026-01", "--retrieved", "2026-11-10", "--licence-read", "2026-11-10")
        sample = icd_file()
        self.assertIn("say which release", self.stops(sample, "--retrieved", "2026-11-10", "--licence-read", "2026-11-10"))
        self.assertIn("has no note of when it was downloaded", self.stops(sample, "--release", "2026-01", "--licence-read", "2026-11-10"))
        self.assertIn("WHO's licence document is not in the downloads folder", self.stops(sample, "--release", "2026-01", "--retrieved", "2026-11-10"))
        self.assertIn("--release looks like 2026-01", self.stops(sample, "--release", "eleven"))
        self.assertIn("columns are not the ones this script knows", self.stops(icd_file(head=ICD_HEAD.replace("Title", "Name")), *good))
        self.assertIn("has 18 fields, not 19", self.stops(icd_file(ICD_RECORDS + [ICD_RECORDS[-1].rsplit("\t", 1)[0]]), *good))
        twice = ICD_RECORDS + [icd_record(11, code="ZA01", title="- - A second entry under one code", parent=2)]
        self.assertIn("a code used twice", self.stops(icd_file(twice), *good))
        orphan = ICD_RECORDS + [icd_record(12, code="ZA09", title="- - An entry with no such parent", parent=77)]
        self.assertIn("names a parent that is not in the file", self.stops(icd_file(orphan), *good))
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            build_icd11.main(["--tabulation", sample, "--out", folder, "--downloads", NO_DATA] + list(good))
        self.assertIn("only 10 records were read", str(caught.exception))
        # the licence document must be the one that was read
        downloads = tempfile.mkdtemp(dir=OUTPUTS)
        dbtools.save(os.path.join(downloads, build_icd11.LICENCE_FILE), b"a licence that somebody has rewritten", build_icd11.LICENCE_URL)
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            build_icd11.main(["--tabulation", sample, "--out", folder, "--downloads", downloads, "--release", "2026-01",
                              "--retrieved", "2026-11-10"])
        self.assertIn("WHO's licence document has changed since it was read", str(caught.exception))
        self.assertEqual(os.listdir(folder), [])


class CodeTests(Base):
    def setUp(self):
        Base.setUp(self)
        os.environ["VOSS_DATA"] = sample_icd()

    def test_a_code_word_for_word(self):
        out = ok("code", "ZA00.0")
        for line in ("CODE       ZA00.0 [ICD-11 MMS, release 2026-01]", "TITLE      Wobbly knee, left", "KIND       category, with no subdivisions",
                     "IN         chapter 01  Made-up conditions of the tests", "BlockL1-ZA0  Wobbles", "ZA00  Wobbly knee",
                     "NOTE       Code also the \"cause\", if known and the side it is on",
                     "URI        http://id.example.org/icd/release/11/mms/4  (foundation: http://id.example.org/icd/entity/4)",
                     "BROWSE     https://example.org/browse#4",
                     "SOURCE     ICD-11 for Mortality and Morbidity Statistics (MMS), release 2026-01: the Simple Tabulation, World Health "
                     "Organization, retrieved 2026-11-10 [sourced: icd11.db, built 2026-11-15]",
                     "CREDIT     " + build_icd11.CITATION,
                     "RULE       code and title are WHO's, character for character: pass them on as printed",
                     "do not turn a code into one of another code system", "It is not a diagnosis of anyone, and WHO does not endorse this tool"):
            self.assertIn(line, out)
        self.assertEqual(desk.check_text(out), [])
        self.assertFalse([ln for ln in out.splitlines() if ln != ln.rstrip()])

    def test_what_is_under_it_and_over_it(self):
        out = ok("code", "za00")
        self.assertIn("KIND       category, with subdivisions", out)
        self.assertIn("UNDER IT   3 entries", out)
        for child in ("ZA00.0  Wobbly knee, left", "ZA00.Y  Other specified wobbly knee", "ZA00.Z  Wobbly knee, unspecified"):
            self.assertIn(child, out)
        out = ok("code", "ZA00.Y")
        self.assertIn("KIND       category, a residual one (other specified or unspecified), with no subdivisions", out)
        self.assertIn("URI        http://id.example.org/icd/release/11/mms/3/other", out)
        self.assertNotIn("foundation", out)
        self.assertIn("TITLE      Wobbly knee, left", ok("code", "ZA000"), "a code typed without its dot")
        out = ok("code", "blockl1-za0", "--max", "2")
        self.assertIn("CODE       BlockL1-ZA0 [ICD-11 MMS, release 2026-01]", out)
        self.assertIn("KIND       block, a grouping without a code of its own", out)
        self.assertIn("and 1 more: 'code BlockL1-ZA0 --max 3' lists them all", out)
        out = ok("code", "--chapter", "1")
        self.assertIn("CODE       chapter 01 [ICD-11 MMS, release 2026-01]", out)
        self.assertIn("TITLE      Made-up conditions of the tests", out)
        self.assertIn("TITLE      Extension codes of the tests", ok("code", "--chapter", "x"))
        self.assertIn("there is no such chapter", fails("code", "--chapter", "99"))

    def test_a_title_is_never_altered(self):
        out = ok("code", "ZA02")
        self.assertIn("TITLE      Sj\u00f6gren-like dryness \u2013 of the tests", out, "WHO's dash and WHO's accent, untouched")

    def test_several_codes_and_a_cluster(self):
        out = ok("code", "ZA01", "ZA00.0&XZ01")
        self.assertEqual(re.findall(r"(?m)^TITLE\s+(.+)$", out), ["Creaky elbow", "Wobbly knee, left", "Left"])
        self.assertEqual(out.count("RULE "), 1)

    def test_a_code_that_is_not_there(self):
        out = ok("code", "I21")
        self.assertIn("CODE       not in this release of ICD-11", out)
        self.assertIn("it has the shape of an ICD-10 code. This file holds ICD-11 only, and no table between the two", out)
        self.assertNotIn("RULE", out)
        out = ok("code", "ZA00.7")
        self.assertIn("the nearest entry above it: ZA00  Wobbly knee", out)
        out = ok("code", "QQ99")
        self.assertIn("CODE       not in this release of ICD-11", out)
        self.assertNotIn("nearest", out)
        self.assertIn("check the code against the document it came from", out)

    def test_looking_through_the_titles(self):
        out = ok("code", "--find", "wobbly", "knee")
        self.assertIn("MATCHES    4 entries whose titles hold those words", out)
        listed = re.findall(r"(?m)^\s+(ZA\S+)  ", out)
        self.assertEqual(listed, ["ZA00", "ZA00.0", "ZA00.Z", "ZA00.Y"], "the shortest title first")
        self.assertIn("A title that matches some words is not a diagnosis", out)
        self.assertIn("CREDIT     " + build_icd11.CITATION, out)
        self.assertIn("and 2 more", ok("code", "--find", "wobbly", "--max", "2"))
        self.assertIn("ZA02  Sj\u00f6gren-like dryness", ok("code", "--find", "sjogren"), "found with or without the accent")
        self.assertIn("ZA01  Creaky elbow", ok("code", "--find", "what", "is", "the", "code", "for", "creaky", "elbow"))
        out = ok("code", "--find", "zygomorphic")
        self.assertIn("CODE       no title in this release holds those words", out)
        self.assertIn("WHO's wording may differ from the words given", out)

    def test_what_it_refuses(self):
        self.assertIn("give a code", fails("code"))
        self.assertIn("leave out the code and --chapter", fails("code", "ZA00", "--find", "knee"))
        self.assertIn("--max is 1 to 2000", fails("code", "ZA00", "--max", "0"))
        self.assertIn("say which words to look for", fails("code", "--find", "the", "of"))
        os.environ["VOSS_DATA"] = NO_DATA
        self.assertIn("icd11.db is not installed, so there is nothing on file for ICD-11 codes", fails("code", "ZA00"))


class InteractionBuildTests(Base):
    """tools/build_ddinter.py, run on made-up files in the shape of DDInter's."""

    def test_the_database_it_writes(self):
        folder = sample_ddi()
        said = _sample["ddi-said"]
        for line in ("9 pairs of 8 medicines, from the files for ATC groups A, B",
                     "graded: 2 major, 2 moderate, 2 minor, 3 with no grade given",
                     "out of reach: 2 medicines are in none of the groups that have a download",
                     "other names: 2 medicines matched to one Wikidata item, 4 other names taken; 1 matched several and got none",
                     "NOTE 1 pair is graded differently in two files: the more serious grade was kept",
                     "retrieved: DDInter 2026-11-10, names 2026-11-10; terms page read 2026-11-10"):
            self.assertIn(line, said)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE-ddinter.txt", "ddinter.db"])
        info = library.read(os.path.join(folder, "ddinter.db"))
        self.assertEqual(info["problems"], [])
        self.assertIn("CC BY-NC-SA 4.0", info["sources"][0]["licence"])
        self.assertEqual(info["sources"][0]["credit"], build_ddinter.CREDIT)
        self.assertEqual(info["sources"][1]["credit"], "")
        with open(os.path.join(folder, "LICENSE-ddinter.txt"), encoding="utf-8") as f:
            licence = f.read()
        for must in ("https://creativecommons.org/licenses/by-nc-sa/4.0/", "NOT under the licence of the code", "doi:10.1093/nar/gkae726",
                     "do not use it for commercial purposes", "under this same licence", "is therefore not known to be safe",
                     "https://creativecommons.org/publicdomain/zero/1.0/"):
            self.assertIn(must, licence)
        con = library.connect(os.path.join(folder, "ddinter.db"))
        try:
            self.assertEqual(con.execute("SELECT a, b, level FROM pair ORDER BY a, b").fetchall(),
                             [(1, 2, 3), (1, 3, 2), (1, 4, 1), (1, 5, 0), (1, 7, 2), (1, 8, 3), (2, 6, 0), (2, 7, 1), (2, 8, 0)],
                             "each pair once, the more serious grade kept")
            self.assertEqual([n for (n,) in con.execute("SELECT name FROM drug WHERE reach = 0 ORDER BY name")], ["Dozapine", "Mopezil"],
                             "a medicine with no file that holds all its pairs is in none of the groups the files cover")
            names = set(con.execute("SELECT folded, drug, kind FROM drug_name"))
            for row in (("wobblol", 1, "name"), ("wbl_1", 1, "also called (en)"), ("woblol", 1, "also called (pl)"),
                        ("kreakazyna", 2, "also called (pl)"), ("sniffex", 4, "name"), ("sniffex", 5, "name"), ("sniffex_topical", 5, "name")):
                self.assertIn(row, names)
            self.assertFalse([n for n in names if n[0] in ("cz", "something_else") or n[0].startswith("a_name_that")],
                             "nothing from a name that fits two items, and nothing too short or too long to be a name")
            self.assertEqual(dict(con.execute("SELECT key, value FROM build"))["groups"], "AB")
        finally:
            con.close()

    def stops(self, *extra, **what):
        paths, names_path = ddi_files(**what)
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught:
            build_ddi(folder, paths, names_path, *extra)
        self.assertEqual(os.listdir(folder), [], "a build that stops leaves nothing behind")
        return str(caught.exception)

    def test_what_stops_a_build(self):
        good = ("--retrieved", "2026-11-10", "--terms-read", "2026-11-10")
        self.assertIn("has no note of when it was downloaded", self.stops("--terms-read", "2026-11-10"))
        self.assertIn("DDInter's terms page is not in the downloads folder", self.stops("--retrieved", "2026-11-10"))
        self.assertIn("does not have the columns this script knows", self.stops(*good, header=["A", "B", "C", "D", "E"]))
        self.assertIn("is not in the shape this script knows",
                      self.stops(*good, files={"A": DDI_FILES["A"] + [("DDInter7", "Odd", "DDInter8", "Odder", "Catastrophic")]}))
        self.assertIn("one DDInter number under two names",
                      self.stops(*good, files={"A": DDI_FILES["A"] + [("DDInter1", "Wobblol forte", "DDInter2", "Creakazine", "Minor")]}))
        self.assertIn("is not the names file this script writes", self.stops(*good, names={"nothing": "of the kind"}))
        paths, names_path = ddi_files()
        folder = tempfile.mkdtemp(dir=OUTPUTS)
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            build_ddinter.main(["--files"] + paths + ["--names", names_path, "--out", folder, "--downloads", NO_DATA] + list(good))
        self.assertIn("only 9 pairs of 8 medicines were read", str(caught.exception))
        downloads = tempfile.mkdtemp(dir=OUTPUTS)
        dbtools.save(os.path.join(downloads, build_ddinter.TERMS_FILE), b"<p>All rights reserved. Ask before you copy.</p>",
                     build_ddinter.TERMS_PAGE)
        keep = build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES
        build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES = 3, 3, 2
        try:
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
                build_ddinter.main(["--files"] + paths + ["--names", names_path, "--out", folder, "--downloads", downloads,
                                                           "--retrieved", "2026-11-10"])
        finally:
            build_ddinter.MIN_PAIRS, build_ddinter.MIN_DRUGS, build_ddinter.MIN_NAMES = keep
        self.assertIn("DDInter's terms page no longer says", str(caught.exception))
        self.assertEqual(os.listdir(folder), [])


def made_up_medicines(data):
    """Put the medicines that do not exist into the first made-up patient's file."""
    me = data["profiles"][0]
    me["medicines"] = [{"name": "Wobblol", "strength": "5 mg", "schedule": [], "told": "2026-11-01"},
                       {"name": "Mysterol", "strength": "", "schedule": [], "told": "2026-11-01"}]
    me["supplements"] = [{"name": "Sniffex", "strength": "", "schedule": [], "told": "2026-11-01"}]


class InteractTests(Base):
    def setUp(self):
        Base.setUp(self)
        os.environ["VOSS_DATA"] = sample_ddi()

    def test_a_pair_and_its_grade(self):
        out = ok("interact", "wobblol", "creakazine")
        for line in ("READ AS    wobblol -> Wobblol", "creakazine -> Creakazine", "PAIR       Wobblol + Creakazine: Major [DDInter's grade]",
                     "PARTIAL    this file holds pairs and grades only, and only pairs with at least one medicine in ATC group A, B",
                     "N (the nervous system)", "C (the heart and circulation)",
                     "the absence of an interaction does not necessarily mean no interactions exist",
                     "SOURCE     DDInter 2.0: drug-drug interactions, the download files for ATC groups A, B, retrieved 2026-11-10 "
                     "[sourced: ddinter.db, built 2026-11-15]",
                     "CREDIT     " + build_ddinter.CREDIT,
                     "RULE       a grade is DDInter's, about the two substances: it is not a verdict on this person",
                     "Never tell anyone to start, stop or change a medicine"):
            self.assertIn(line, out)
        self.assertEqual(desk.check_text(out), [])
        self.assertFalse([ln for ln in out.splitlines() if ln != ln.rstrip()])

    def test_not_listed_is_never_safe(self):
        out = ok("interact", "kneeprofen", "creakazine", "elbowmycin")
        self.assertIn("PAIR       Creakazine + Elbowmycin: listed, with no grade given [DDInter lists the pair]", out)
        self.assertIn("NOT LISTED Kneeprofen + Creakazine: no interaction between these two is in this file. That is not \"safe\"", out)
        self.assertIn("NOT LISTED Kneeprofen + Elbowmycin", out)
        self.assertLess(out.index("PAIR "), out.index("NOT LISTED"), "what is listed comes first")
        self.assertNotIn("no interaction between these two is known", out)

    def test_a_pair_the_file_could_not_hold_is_said_to_be_out_of_reach(self):
        out = ok("interact", "mopezil", "dozapine", "wobblol")
        self.assertIn("PAIR       Dozapine + Wobblol: Major [DDInter's grade]", out)
        self.assertIn("OUT OF REACH Mopezil + Dozapine: neither is in a group this file covers, so the pair could not be in it whether or "
                      "not the two interact", out)
        self.assertNotIn("NOT LISTED", out)
        self.assertIn("this medicine is in none of the groups the file covers", ok("interact", "mopezil"))
        self.assertNotIn("none of the groups", ok("interact", "wobblol"))
        self.assertIn("NOT LISTED Mopezil + Kneeprofen", ok("interact", "mopezil", "kneeprofen"), "one of the two may be covered: only unlisted")

    def test_a_medicine_is_found_under_its_other_names(self):
        out = ok("interact", "woblol", "Kreakazyna 5 mg")
        self.assertIn("woblol -> Wobblol [found under \"woblol\", another name for it, from Wikidata (pl)]", out)
        self.assertIn("Kreakazyna 5 mg -> Creakazine [found under \"kreakazyna\", another name for it, from Wikidata (pl)]", out)
        self.assertIn("PAIR       Wobblol + Creakazine: Major", out)
        self.assertNotIn("only the start", out, "a strength after the name changes nothing")
        out = ok("interact", "wobblol carbonate", "creakazine tablets")
        self.assertIn("only the start of that name matched (\"carbonate\" was left off): make sure this is the medicine meant", out)
        self.assertEqual(out.count("only the start"), 1)

    def test_a_name_with_two_forms_is_checked_as_both(self):
        out = ok("interact", "sniffex", "wobblol")
        self.assertIn("that name fits 2 entries: each is checked, under DDInter's own name for it", out)
        self.assertIn("PAIR       Sniffex + Wobblol: Minor [DDInter's grade]", out)
        self.assertIn("PAIR       Sniffex (topical) + Wobblol: listed, with no grade given", out)
        self.assertNotIn("Sniffex + Sniffex (topical)", out)
        self.assertNotIn("Sniffex (topical) + Sniffex", out)

    def test_a_name_it_does_not_have(self):
        out = ok("interact", "wobblol", "mysterol")
        self.assertIn("UNKNOWN    \"mysterol\": nothing in this file under that name. It was not checked against anything: say so", out)
        self.assertIn("NOTHING    only one of the names could be read, so there is no pair to check", out)
        self.assertIn("did you mean Creakazine?", ok("interact", "wobblol", "creakazin"))
        out = ok("interact", "mysterol", "zygomorphine")
        self.assertIn("NOTHING    none of those names is in this file, so nothing was checked", out)
        self.assertNotIn("PAIR", out)

    def test_one_medicine_alone(self):
        out = ok("interact", "wobblol")
        self.assertIn("MEDICINE   Wobblol: 6 interactions on file (2 major, 2 moderate, 1 minor, 1 with no grade)", out)
        self.assertIn("MAJOR      Creakazine; Dozapine", out)
        self.assertIn("PARTIAL", out)
        self.assertIn("LISTED     Sniffex (topical)", ok("interact", "wobblol", "--level", "unknown"))
        self.assertIn("MODERATE   Kneeprofen; Mopezil", ok("interact", "wobblol", "--level", "Moderate"))
        self.assertIn("and 1 more: raise --max", ok("interact", "wobblol", "--max", "1"))
        self.assertIn("--level is one of", fails("interact", "wobblol", "--level", "deadly"))

    def test_what_it_refuses(self):
        self.assertIn("name the medicines", fails("interact"))
        self.assertIn("more than 25 names at once", fails("interact", *["wobblol"] * 26))
        self.assertIn("--max is 1 to 500", fails("interact", "wobblol", "--max", "0"))
        self.assertIn("say what is new", fails("watch", "--id", "self"))
        os.environ["VOSS_DATA"] = NO_DATA
        self.assertIn("ddinter.db is not installed, so there is nothing on file for interactions between medicines",
                      fails("interact", "wobblol", "creakazine"))

    def test_with_the_medicines_on_file(self):
        copy_fixture(made_up_medicines)
        out = ok("interact", "--id", "self", "creakazine")
        self.assertIn("FILE       3 medicines and supplements on file for self are included", out)
        self.assertIn("PAIR       Creakazine + Wobblol: Major", out)
        self.assertIn("UNKNOWN    \"Mysterol\"", out)
        self.assertIn("PAIR       Wobblol + Sniffex: Minor", out)

    def test_watch_checks_something_new_against_the_file(self):
        copy_fixture(made_up_medicines)
        out = ok("watch", "--id", "self", "--new", "creakazine")
        for line in ("WATCH      1 new name against 3 medicines and supplements on file for self",
                     "PAIR       Creakazine + Wobblol: Major [DDInter's grade]", "UNKNOWN    \"Mysterol\"",
                     "NOT LISTED Creakazine + Sniffex: no interaction between these two is in this file",
                     "SAY        one line to the person", "an unlisted one is still not \"safe\""):
            self.assertIn(line, out)
        self.assertNotIn("Wobblol + Sniffex", out, "only the new one is checked: the rest was there before")
        out = ok("watch", "--id", "self", "--new", "woblol")
        self.assertIn("SAME       Wobblol is on file already, under one name or another", out)
        self.assertIn("PAIR       Wobblol + Sniffex: Minor", out)
        out = ok("watch", "--id", "self", "--new", "mysterol")
        self.assertIn("NOTHING    the new name is not in this file, so nothing was checked", out)
        use_personal(None)
        self.assertIn("there is no personal file here", fails("watch", "--new", "wobblol"))

    def test_stale_data_says_so_first(self):
        clock("2027-11-11T09:00")
        self.assertTrue(ok("interact", "wobblol", "creakazine").startswith("STALE      ddinter.db: retrieved 2026-11-10"))


class LabelBuildTests(Base):
    """tools/build_labels.py, run on a made-up file in the shape of openFDA's."""

    def test_the_database_it_writes(self):
        folder = sample_labels()
        said = _sample["labels-said"]
        for line in ("4 labels kept of 9 read: 2 prescription, 2 over the counter; 4 substances",
                     "brand names: 8; left out: 1 label that FDA lists no substances for, and whose generic name does not read as a list of them",
                     "other names: 3 substances matched to one Wikidata item",
                     "retrieved: labels 2026-11-10, names 2026-11-10; terms page read 2026-11-10"):
            self.assertIn(line, said)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE-labels-us.txt", "labels-us.db"])
        info = library.read(os.path.join(folder, "labels-us.db"))
        self.assertEqual(info["problems"], [])
        self.assertEqual(info["sources"][0]["credit"], build_labels.CREDIT)
        self.assertIn("CC0 1.0", info["sources"][0]["licence"])
        with open(os.path.join(folder, "LICENSE-labels-us.txt"), encoding="utf-8") as f:
            licence = f.read()
        for must in ("https://creativecommons.org/publicdomain/zero/1.0/", "Data provided by the U.S. Food and Drug Administration",
                     "neither been altered nor verified by FDA", "The dose is left out on purpose", "FDA does not endorse this skill"):
            self.assertIn(must, licence)
        con = library.connect(os.path.join(folder, "labels-us.db"))
        try:
            rows = con.execute("SELECT id, type, route, substances, brand, maker, application, effective, labels, class FROM label").fetchall()
            self.assertEqual([r[:4] for r in rows], [(1, "prescription", "oral", "CREAKAZINE; WOBBLOL HYDROCHLORIDE"),
                                                     (2, "over the counter", "topical", "WOBBLOL"),
                                                     (3, "prescription", "oral", "WOBBLOL HYDROCHLORIDE"),
                                                     (4, "over the counter", "topical", "ZIPPERINE")])
            self.assertEqual(rows[2][4:], ("Steadyknee", "Original Pharma Inc", "NDA000002", "2026-03-01", 2, "Knee Steadier [EPC]"),
                             "of two labels for one medicine, the original maker's and the newer is kept")
            self.assertEqual(rows[0][4:9], ("Duoknee", "Original Pharma Inc", "NDA000004", "2026-01-10", 2),
                             "a label with no list of substances and no route is counted with the product its generic name spells out")
            kinds = [k for (k,) in con.execute("SELECT kind FROM section WHERE label = 3")]
            self.assertEqual(sorted(kinds), sorted(["boxed warning", "uses", "do not use", "warnings", "side effects", "interactions",
                                                    "pregnancy and other groups", "for patients"]))
            reader = store.Reader(con)
            everything = b"".join(raw for _, raw in reader.everything()).decode("utf-8")
            for left_out in ("5 mg once daily", "apply thinly", "copy's label", "not matched to a product", "kind of product",
                             "pack's label", "nobody can place"):
                self.assertNotIn(left_out, everything)
            self.assertIn("It isn't a real medicine.", everything, "tidied, and in this skill's typography")
            self.assertIn("Stop use and ask a doctor if a rash appears", everything)
            self.assertEqual(set(con.execute("SELECT folded, label FROM label_name")),
                             {("steadyknee", 3), ("kneeze_gel", 2), ("shopwise_wobblol_gel", 2), ("knee_relief", 2), ("duoknee", 1),
                              ("duoknee_starter_pack", 1), ("knee_relief", 4), ("zippo_warming_rub", 4)},
                             "every brand name is kept but the ones that say no more than the substance: 'Wobblol Hydrochloride', 'Wobblol Gel 1%'")
            self.assertEqual([n for (n,) in con.execute("SELECT shown FROM label_name WHERE label = 1 ORDER BY place")],
                             ["Duoknee", "Duoknee Starter Pack"])
            names = set(con.execute("SELECT n.folded, s.name, n.kind FROM substance_name n JOIN substance s ON s.id = n.substance"))
            for row in (("wobblol", "WOBBLOL", "substance"), ("wobblol", "WOBBLOL HYDROCHLORIDE", "substance"),
                        ("woblol", "WOBBLOL HYDROCHLORIDE", "also called (pl)"), ("kreakazyna", "CREAKAZINE", "also called (pl)")):
                self.assertIn(row, names)
        finally:
            con.close()

    def test_a_big_file_is_read_a_piece_at_a_time(self):
        paths, _ = label_files(indent=None)
        whole = [x["set_id"] for x in build_labels.labels(paths[0])]
        self.assertEqual(whole, ["set-%d" % n for n in range(1, 10)])
        keep = build_labels.CHUNK
        try:
            for size in (1, 7, 64, 1000):
                build_labels.CHUNK = size
                for indent in (None, 2):
                    paths, _ = label_files(indent=indent)
                    self.assertEqual([x["set_id"] for x in build_labels.labels(paths[0])], whole, (size, indent))
            build_labels.CHUNK = 50
            short = os.path.join(tempfile.mkdtemp(dir=OUTPUTS), "short.json")
            with open(paths[0], encoding="utf-8") as f, open(short, "w", encoding="utf-8") as out:
                out.write(f.read()[:900])
            with self.assertRaises(SystemExit) as caught:
                list(build_labels.labels(short))
            self.assertIn("cut short", str(caught.exception))
            with open(short, "w", encoding="utf-8") as out:
                out.write('{"meta": {}, "labels": []}')
            with self.assertRaises(SystemExit) as caught:
                list(build_labels.labels(short))
            self.assertIn("no list of results", str(caught.exception))
        finally:
            build_labels.CHUNK = keep
        self.assertEqual(build_labels.base_name("METFORMIN HYDROCHLORIDE"), "METFORMIN")
        self.assertIsNone(build_labels.base_name("IBUPROFEN"))
        self.assertIsNone(build_labels.base_name("SODIUM CHLORIDE"), "a salt that is all salt keeps its name")

    def test_a_generic_name_read_as_a_list(self):
        read = build_labels.parts_of
        self.assertEqual(read(["Norgestimate and Ethinyl Estradiol Tablets USP"]), ["NORGESTIMATE", "ETHINYL ESTRADIOL"])
        self.assertEqual(read(["Acetaminophen, Dextromethorphan HBr, Phenylephrine HCl"]),
                         ["ACETAMINOPHEN", "DEXTROMETHORPHAN HYDROBROMIDE", "PHENYLEPHRINE HYDROCHLORIDE"])
        self.assertEqual(read(["acetaminophen/caffeine", "Caffeine"]), ["ACETAMINOPHEN", "CAFFEINE"])
        self.assertEqual(read(["Acetaminophen Dextromethorphan"]), ["ACETAMINOPHEN DEXTROMETHORPHAN"], "run together, it is not taken apart")
        self.assertEqual(read(["Kit"]), [])
        known = {"acetaminophen", "ethinyl_estradiol", "dextromethorphan"}
        for name, is_one in (("ACETAMINOPHEN", True), ("DEXTROMETHORPHAN HYDROBROMIDE", True), ("ACETAMINOPHEN DEXTROMETHORPHAN", False),
                             ("NORGESTIMATE", False)):
            self.assertEqual(build_labels.is_known(name, known), is_one, name)

        def made_of(*labels_in):
            doc = {"meta": {}, "results": [{"set_id": "s%d" % n, "effective_time": "20260101", "openfda": block,
                                            "indications_and_usage": ["Uses of pack %d." % n]} for n, block in enumerate(labels_in)]}
            keep = build_labels.say
            build_labels.say = lambda *a, **k: None
            try:
                best, seen, left_out = build_labels.pick(label_files(doc)[0], frozenset(["wikidol"]))
            finally:
                build_labels.say = keep
            return sorted((key, entry[4]) for key, entry in best.items()), left_out

        def pack(generic, application, route="", kind="HUMAN PRESCRIPTION DRUG"):
            return _fda(kind, [], generic, ["A Pack"], "Copycat Ltd", route, application)
        plain = _fda("HUMAN PRESCRIPTION DRUG", ["WOBBLOL"], "WOBBLOL", ["Steadyknee"], "Original Pharma Inc", "ORAL", "NDA000001")
        rx = "prescription"
        # a name no list has: three separate approvals agree on it, two do not
        groups, left_out = made_of(plain, pack("Mysterol and Wobblol", "ANDA000001"), pack("Mysterol and Wobblol", "ANDA000002"),
                                   pack("Wobblol and Mysterol", "ANDA000003", "ORAL"))
        self.assertEqual(groups, [((rx, ("MYSTEROL", "WOBBLOL"), "oral"), 3), ((rx, ("WOBBLOL",), "oral"), 1)],
                         "and the two that give no route are counted with the one that does")
        self.assertEqual(left_out, [])
        groups, left_out = made_of(plain, pack("Mysterol and Wobblol", "ANDA000001"), pack("Mysterol and Wobblol", "ANDA000002"),
                                   pack("Mysterol and Wobblol", "ANDA000002"), pack("Mysterol and Wobblol", "M012"))
        self.assertEqual(groups, [((rx, ("WOBBLOL",), "oral"), 1)])
        self.assertEqual(left_out, ["Mysterol and Wobblol"] * 4)
        # a name Wikidata has is enough; and with no word anywhere on how a pack is taken, the label says so
        groups, left_out = made_of(plain, pack("Wikidol; wobblol HCl", ""), pack("Wobblol", "", "", "HUMAN OTC DRUG"))
        self.assertEqual(groups, [(("over the counter", ("WOBBLOL",), "route not given"), 1), ((rx, ("WIKIDOL", "WOBBLOL HYDROCHLORIDE"), "route not given"), 1),
                                  ((rx, ("WOBBLOL",), "oral"), 1)])
        says_more = build_labels.says_more
        own = {"ibuprofen", "sodium"}
        for name in ("ibuprofen", "ibuprofen_tablets_200_mg", "ibuprofen_sodium_200mg", "ibuprofen_and_ibuprofen_usp", "extra_strength_ibuprofen"):
            self.assertFalse(says_more(name, own), name)
        for name in ("motrin_ib", "childrens_ibuprofen", "ibuprofen_pm", "equate_ibuprofen"):
            self.assertTrue(says_more(name, own), name)

    def test_what_stops_a_build(self):
        paths, names_path = label_files()
        folder = tempfile.mkdtemp(dir=OUTPUTS)

        def stops(*extra):
            with self.assertRaises(SystemExit) as caught:
                build_labels_db(folder, paths, names_path, *extra)
            self.assertEqual(os.listdir(folder), [], "a build that stops leaves nothing behind")
            return str(caught.exception)
        self.assertIn("has no note of when it was downloaded", stops("--terms-read", "2026-11-10"))
        self.assertIn("openFDA's terms page is not in the downloads folder", stops("--retrieved", "2026-11-10"))
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            build_labels.main(["--files"] + paths + ["--names", names_path, "--out", folder, "--downloads", NO_DATA,
                                                      "--retrieved", "2026-11-10", "--terms-read", "2026-11-10"])
        self.assertIn("only 4 items are in the names file", str(caught.exception))
        self.assertEqual(os.listdir(folder), [])


class MedTests(Base):
    def setUp(self):
        Base.setUp(self)
        os.environ["VOSS_DATA"] = sample_labels()

    def test_what_a_medicine_is(self):
        out = ok("med", "wobblol")
        over, rx = out.split("\n\n", 1)
        for line in ("MEDICINE   WOBBLOL [over the counter; topical] (label 2) - read as WOBBLOL or WOBBLOL HYDROCHLORIDE",
                     "BRANDS     in the United States, among others: Knee Relief; Kneeze Gel; Shopwise Wobblol Gel",
                     "PURPOSE    the label's own words", "Purpose Knee steadier",
                     "Active ingredient Wobblol 1%", "Uses temporarily steadies a wobbly knee", "ALSO HERE  warnings  ('med --id 2 --section NAME')",
                     "LABEL      filed by Shelf Goods LLC, dated 2026-02-01; the only label on file with FDA for this substance, type and route",
                     "PAGE       https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=set-3"):
            self.assertIn(line, over)
        for line in ("MEDICINE   WOBBLOL HYDROCHLORIDE [prescription; oral] (label 3)", "BRANDS     in the United States, among others: Steadyknee",
                     "CLASS      Knee Steadier [EPC]", "BOXED WARNING the label's own words", "WARNING: A MADE-UP RISK Wobblol can make the tests fail.",
                     "1 INDICATIONS AND USAGE Wobblol is indicated for wobbly knees in adults. It isn't a real medicine.",
                     "ALSO HERE  do not use; warnings; side effects; interactions; pregnancy and other groups; for patients",
                     "LABEL      filed by Original Pharma Inc, dated 2026-03-01; one of 2 labels on file with FDA",
                     "SOURCE     openFDA drug labels: product labelling as companies have filed it with the United States Food and Drug "
                     "Administration, retrieved 2026-11-10 [sourced: labels-us.db, built 2026-11-15]",
                     "CREDIT     Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)",
                     "OTHER      1 more label for the same name", "label 1: CREAKAZINE; WOBBLOL HYDROCHLORIDE [prescription; oral]",
                     "RULE       an American label, as the company filed it. FDA has not verified it",
                     "there is no dose in this file, on purpose"):
            self.assertIn(line, rx)
        self.assertNotIn("5 mg", out)
        self.assertEqual(desk.check_text(out), [])
        self.assertFalse([ln for ln in out.splitlines() if ln != ln.rstrip()])

    def test_names_it_is_found_under(self):
        def first(*words):
            return field(ok("med", *words), "MEDICINE")
        self.assertIn("(label 3) - read as Steadyknee [a brand name in the United States]", first("steadyknee"))
        self.assertIn("(label 2) - read as Kneeze Gel [a brand name in the United States]", first("Kneeze", "gel"))
        self.assertIn("read as WOBBLOL or WOBBLOL HYDROCHLORIDE [found under \"woblol\", another name for it, from Wikidata (pl)]", first("woblol"))
        self.assertIn("CREAKAZINE; WOBBLOL HYDROCHLORIDE [prescription; oral] (label 1) - read as CREAKAZINE", first("kreakazyna"))
        self.assertIn("(label 3)", first("wobblol", "hydrochloride"))
        self.assertNotIn("CHECK", ok("med", "Wobblol 5 mg tablets"))
        self.assertNotIn("CHECK", ok("med", "extra strength steadyknee 5mg"))
        self.assertIn("CHECK      only part of that name was used (\"carbonate\" was not)", ok("med", "wobblol", "carbonate"))
        out = ok("med", "childrens", "wobblol")
        self.assertIn("read as WOBBLOL or WOBBLOL HYDROCHLORIDE", field(out, "MEDICINE"))
        self.assertIn("CHECK      only part of that name was used (\"childrens\" was not): make sure this is the medicine meant", out)
        self.assertEqual(field(ok("med", "--id", "1"), "MEDICINE"), "CREAKAZINE; WOBBLOL HYDROCHLORIDE [prescription; oral] (label 1)")
        out = ok("med", "mysterol")
        self.assertIn("MEDICINE   nothing on file under that name", out)
        self.assertIn("which holds American labels only", out)
        for nothing in (["500", "mg"], ["extra", "strength"], ["and"], ["x"]):
            self.assertIn("nothing on file under that name", ok("med", *nothing), nothing)

    def test_a_brand_by_part_of_its_name(self):
        def first(*words):
            return field(ok("med", *words), "MEDICINE")
        self.assertIn("(label 2) - read as Kneeze Gel [a brand name in the United States, found by part of it]", first("kneeze"))
        self.assertIn("(label 2) - read as Shopwise Wobblol Gel [a brand name in the United States, found by part of it]", first("shopwise"))
        self.assertIn("(label 1) - read as Duoknee [a brand name in the United States]", first("duoknee"))
        self.assertIn("(label 1) - read as Duoknee Starter Pack [a brand name in the United States]", first("Duoknee", "starter", "pack"))
        self.assertIn("(label 1) - read as Duoknee Starter Pack [a brand name in the United States, found by part of it]", first("starter", "pack"))
        self.assertIn("nothing on file", first("duo"), "a piece of a word is not a word")
        self.assertIn("nothing on file", first("ze"))
        con = library.connect(os.path.join(sample_labels(), "labels-us.db"))
        try:
            rows, how, unused, one, names = labels.resolve(con, "rub zippo 2%")
            self.assertEqual(([r[0] for r in rows], unused, one), ([4], [], True), "every word is in the one name, in another order")
            self.assertEqual(how, "Zippo Warming Rub [a brand name in the United States, found by part of it]")
            self.assertEqual(names, {4: [(2, "Zippo Warming Rub")]})
            self.assertEqual(labels.resolve(con, "zippo relief")[0], [], "two words from two names of one label are not a name")
            self.assertEqual(labels.resolve(con, "kneeze mysterol")[0], [], "part of a name is not trusted beside a word nobody can place")
            self.assertEqual([r[0] for r in labels.resolve(con, "kneeze 10 g")[0]], [2])
            rows, how, unused, one, names = labels.resolve(con, "steadyknee mysterol")
            self.assertEqual(([r[0] for r in rows], unused), ([3], ["mysterol"]), "a whole name is, and the word is reported")
            rows, how, unused, one, names = labels.resolve(con, "duoknee pack 28 tablets")
            self.assertEqual(([r[0] for r in rows], how, unused), ([1], "Duoknee [a brand name in the United States]", []),
                             "a word from a longer name of the same label is no surprise")
            rows, how, unused, one, names = labels.resolve(con, "steadyknee wobblol 5 mg")
            self.assertEqual(([r[0] for r in rows], how, unused, names), ([3], "Steadyknee [a brand name in the United States]", [], {}),
                             "a brand with its own substance after it")
            self.assertEqual(labels.resolve(con, ""), ([], "", [], True, {}))
            self.assertEqual(labels.resolve(con, " ".join(["mysterol"] * 40))[0], [], "a long line of nothing is still nothing")
            unused = labels.resolve(con, " ".join(["wobblol"] + ["mysterol"] * 14))[2]
            self.assertEqual(len(unused), 14, "what was typed beyond the name is reported, all of it")
        finally:
            con.close()

    def test_a_name_on_packs_of_different_medicines(self):
        out = ok("med", "knee", "relief")
        for line in ("MEDICINE   not one medicine: 2 labels of different medicines carry that name (read as Knee Relief [a brand name in "
                     "the United States])",
                     "label 2: WOBBLOL [over the counter; topical], 1 label on file with FDA",
                     "label 4: ZIPPERINE [over the counter; topical], 1 label on file with FDA",
                     "RULE       do not choose one for the person. The active ingredient is printed on the pack"):
            self.assertIn(line, out)
        for never in ("PURPOSE", "USES", "Knee steadier", "Knee warmer", "SOURCE"):
            self.assertNotIn(never, out, "none of them is read out")
        self.assertEqual(desk.check_text(out), [])
        self.assertIn("none of that type or route", ok("med", "knee", "relief", "--rx"))
        self.assertIn("nothing on file", ok("med", "knee", "relief", "mysterol"), "such a name counts only when all of it matched")
        self.assertIn("MEDICINE   not one medicine", ok("med", "knee", "relief", "gel", "10", "g"), "a strength or a form changes nothing")
        out = ok("sidefx", "--med", "knee", "relief", "--symptom", "rash")
        self.assertIn("carry that name, so nothing was searched (read as Knee Relief", out)
        self.assertNotIn("WARNINGS", out)
        self.assertIn("(label 4) - read as Zippo Warming Rub [a brand name in the United States, found by part of it]",
                      field(ok("sidefx", "--med", "zippo", "rub", "--symptom", "rash"), "MEDICINE"))

    def test_two_substances_in_one_product(self):
        for words in (["wobblol", "with", "creakazine"], ["creakazine", "and", "wobblol"], ["wobblol/creakazine"], ["Wobblol", "creakazine", "5", "mg"],
                      ["kreakazyna", "plus", "woblol"]):
            out = ok("med", *words)
            self.assertIn("CREAKAZINE; WOBBLOL HYDROCHLORIDE [prescription; oral] (label 1) - read as", field(out, "MEDICINE"), words)
            self.assertNotIn("CHECK", out, words)
            self.assertEqual(out.count("MEDICINE "), 1, words)
        self.assertIn("read as WOBBLOL or WOBBLOL HYDROCHLORIDE together with CREAKAZINE",
                      field(ok("med", "wobblol", "with", "creakazine"), "MEDICINE"))
        self.assertIn("(label 1) - read as CREAKAZINE", field(ok("med", "creakazine", "and", "wobblol"), "MEDICINE"))
        self.assertNotIn("together", ok("med", "creakazine", "and", "wobblol"), "creakazine is only sold with it: nothing was narrowed")
        out = ok("med", "wobblol", "and", "zipperine")
        self.assertIn("read as WOBBLOL or WOBBLOL HYDROCHLORIDE", field(out, "MEDICINE"))
        self.assertNotIn("together", out)
        self.assertIn("CHECK      only part of that name was used (\"and zipperine\" was not)", out, "no label holds both, and none is made up")
        out = ok("med", "steadyknee", "and", "creakazine")
        self.assertIn("(label 3) - read as Steadyknee [a brand name in the United States]", field(out, "MEDICINE"))
        self.assertIn("CHECK      only part of that name was used (\"and creakazine\" was not)", out, "two products are not turned into a third")
        out = ok("med", "wobblol", "knee", "relief")
        self.assertIn("WOBBLOL [over the counter; topical] (label 2) - read as WOBBLOL or WOBBLOL HYDROCHLORIDE, sold as Knee Relief "
                      "[a brand name in the United States]", field(out, "MEDICINE"), "the substance says which of the two Knee Reliefs")
        self.assertNotIn("CHECK", out)
        self.assertEqual(out.count("MEDICINE "), 1)
        out = ok("med", "knee", "relief", "zipperine")
        self.assertTrue(field(out, "MEDICINE").endswith("(label 4) - read as ZIPPERINE"), "zipperine has the one label: the name narrows nothing")
        self.assertNotIn("CHECK", out)

    def test_choosing_a_label_and_a_section(self):
        self.assertEqual(ok("med", "wobblol", "--rx").count("MEDICINE "), 1)
        self.assertIn("(label 2)", field(ok("med", "wobblol", "--otc"), "MEDICINE"))
        self.assertIn("(label 2)", field(ok("med", "wobblol", "--route", "topical"), "MEDICINE"))
        self.assertIn("and none of that type or route", ok("med", "wobblol", "--route", "rectal"))
        out = ok("med", "wobblol", "--rx", "--section", "side")
        self.assertIn("SIDE EFFECTS the label's own words", out)
        self.assertIn("are nausea, pruritus and somnolence", out)
        self.assertNotIn("INDICATIONS", out)
        self.assertIn("SIDE EFFECTS this label has no such section", ok("med", "wobblol", "--otc", "--section", "side effects"))
        out = ok("med", "wobblol", "--rx", "--section", "interactions", "--find", "creakazine")
        self.assertIn("INTERACTIONS 1 place on the label under those words", out)
        self.assertIn("7.1 Creakazine Increased wobbling.", out)
        self.assertNotIn("Elbowmycin", out)
        self.assertIn("0 places on the label under those words: the label may use another word for it",
                      ok("med", "wobblol", "--rx", "--section", "warn", "--find", "liver"))
        self.assertIn("--section is one of", fails("med", "wobblol", "--section", "dose"))
        self.assertIn("--rx or --otc, not both", fails("med", "wobblol", "--rx", "--otc"))
        self.assertIn("no label has that number", fails("med", "--id", "99"))
        self.assertIn("name the medicine", fails("med"))
        os.environ["VOSS_DATA"] = NO_DATA
        self.assertIn("labels-us.db is not installed", fails("med", "wobblol"))

    def test_a_long_section_is_cut_and_says_so(self):
        text = "A sentence about the knee. " * 400
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            labels._print_text(text, 500, False)
        said = out.getvalue()
        self.assertLess(len(said.splitlines()[0]), 520)
        self.assertTrue(said.splitlines()[0].endswith("knee."))
        self.assertIn("more characters of this section: --all prints the whole of it", said)

    def test_is_this_symptom_on_the_label(self):
        out = ok("sidefx", "--med", "wobblol", "--rx", "--symptom", "nausea")
        for line in ("MEDICINE   WOBBLOL HYDROCHLORIDE [prescription; oral] (label 3)", "SIDE EFFECTS 1 place under those words",
                     "are nausea, pruritus and somnolence. Nausea led to discontinuation in 2% of patients.",
                     "FOR PATIENTS 1 place under those words", "Wobblol may cause nausea.",
                     "RULE       listed is not caused. A symptom on the label may have another cause",
                     "Never \"stop taking it\": that goes to the prescriber or the pharmacist, today if it matters",
                     "an American label, as the company filed it"):
            self.assertIn(line, out)
        self.assertNotIn("Headache", out, "only the sentences that mention it")
        out = ok("sidefx", "--med", "wobblol", "--rx", "--symptom", "itching")
        self.assertIn("NOT FOUND  none of those words is on this label", out)
        self.assertIn("itching is pruritus", out)
        self.assertIn("not on the label is not the same as not caused by the medicine", out)
        self.assertIn("pruritus and somnolence", ok("sidefx", "--med", "wobblol", "--rx", "--symptom", "itching", "pruritus"))
        out = ok("sidefx", "--med", "wobblol", "--symptom", "rash")
        self.assertIn("WARNINGS   1 place under those words", out)
        self.assertIn("Stop use and ask a doctor if a rash appears", out)
        self.assertIn("OTHER      1 more label for the same name was not searched", out)
        self.assertEqual(labels.passages("One two three. Four five six. Seven eight nine.", ["five"]), (["Four five six."], 1))
        long = "word " * 200 + "needle " + "word " * 200
        found, total = labels.passages(long, ["needle"])
        self.assertTrue(found[0].startswith("... word") and found[0].endswith("word ..."), "a long run is cut at a space, and says so")
        self.assertLess(len(found[0]), 2 * labels.WINDOW + 30)
        self.assertIn("nothing on file under that name, so nothing was checked", ok("sidefx", "--med", "mysterol", "--symptom", "nausea"))
        self.assertIn("name the medicine", fails("sidefx", "--symptom", "nausea"))
        self.assertIn("say what to look for", fails("sidefx", "--med", "wobblol"))
        self.assertEqual(desk.check_text(ok("sidefx", "--med", "wobblol", "--symptom", "nausea")), [])


class ShippedDataTests(Base):
    """A look at the databases that ship with the skill. Skipped in a copy that carries none."""

    def setUp(self):
        Base.setUp(self)
        self.files = sorted(n for n in os.listdir(REAL_DATA) if n.endswith(".db"))
        if not self.files:
            self.skipTest("no database ships in this copy")
        os.environ.pop("VOSS_DATA")
        clock(datetime.now().strftime("%Y-%m-%dT%H:%M"))

    def test_every_database_accounts_for_itself_and_fits(self):
        with open(os.path.join(REAL_DATA, "SOURCES.md"), encoding="utf-8") as f:
            listed = f.read().split("## Databases to come")[0]
        for name in self.files:
            info = library.read(os.path.join(REAL_DATA, name))
            self.assertEqual(info["problems"], [], name)
            self.assertLessEqual(info["size"], build.MAX_FILE_BYTES, "%s is over the limit for one file" % name)
            self.assertIn("`%s`" % name, listed, "%s is not in SOURCES.md" % name)
            self.assertTrue(desk._unpacks(os.path.join(REAL_DATA, name))[0], name)
        self.assertFalse([n for n in os.listdir(REAL_DATA) if n.endswith(".part")])
        code, out, _ = run("selftest")
        self.assertEqual(code, 0, out)

    def test_the_core_data(self):
        if "core-pd.db" not in self.files:
            self.skipTest("core-pd.db does not ship in this copy")
        out = ok("term", "heart", "attack")
        self.assertIn("TERM       Heart Attack [health topic, id 5]", out)
        self.assertIn("CREDIT     Source: MedlinePlus, National Library of Medicine", out)
        self.assertEqual(desk.check_text(out), [], "the source's text is in this skill's typography")
        self.assertIn("Atrial Fibrillation [health topic", field(ok("term", "afib", "--brief"), "TERM"))
        self.assertIn("[definition]", ok("term", "antioxidants"))
        con = library.connect(os.path.join(REAL_DATA, "core-pd.db"))
        try:
            counts = dict(con.execute("SELECT kind, COUNT(*) FROM entry GROUP BY kind"))
            self.assertGreater(counts["topic"], 900)
            self.assertGreater(counts["definition"], 50)
            self.assertGreater(con.execute("SELECT COUNT(*) FROM country").fetchone()[0], 150)
            first = dict(con.execute("SELECT code, number FROM emergency WHERE position = 1"))
            for code in sorted(build_core.EU):
                self.assertEqual(first.get(code), "112", code)
            for code, number in (("US", "911"), ("CA", "911"), ("AU", "000")):
                self.assertEqual(first.get(code), number, code)
            self.assertIn("999", [n for (n,) in con.execute("SELECT number FROM emergency WHERE code = 'GB'")])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM entry WHERE url LIKE '%/spanish/%'").fetchone()[0], 0)
        finally:
            con.close()
        self.assertIn("Poland (PL): 112", field(ok("triage", "--country", "poland"), "NUMBERS"))

    def test_the_label_data(self):
        if "labels-us.db" not in self.files:
            self.skipTest("labels-us.db does not ship in this copy")
        con = library.connect(os.path.join(REAL_DATA, "labels-us.db"))
        try:
            counts = dict(con.execute("SELECT type, COUNT(*) FROM label GROUP BY type"))
            self.assertGreater(counts["prescription"], 2000)
            self.assertGreater(counts["over the counter"], 2000)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM section WHERE kind NOT IN (%s)" % ",".join("?" * len(labels.KINDS)),
                                         labels.KINDS).fetchone()[0], 0, "no section but the ones the tool knows, and so no dose")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM label l WHERE NOT EXISTS (SELECT 1 FROM section s WHERE s.label = l.id)")
                             .fetchone()[0], 0)
        finally:
            con.close()
        out = ok("med", "metformin", "--rx")
        self.assertIn("METFORMIN HYDROCHLORIDE [prescription; oral]", out)
        self.assertIn("BOXED WARNING", out)
        self.assertIn("CREDIT     " + build_labels.CREDIT, out)
        self.assertIn("read as ACETAMINOPHEN [found under", field(ok("med", "paracetamol", "--otc"), "MEDICINE"))
        first = field(ok("med", "advil", "200", "mg"), "MEDICINE")
        self.assertIn("IBUPROFEN [over the counter; oral]", first)
        self.assertIn("read as Advil [a brand name in the United States]", first)
        # a name that is on more than one medicine is never read as one of them, whatever the day's file holds
        out = ok("med", "tylenol", "--max", "40")
        self.assertIn("ACETAMINOPHEN [over the counter; oral]", out)
        if "not one medicine" in out:
            self.assertNotIn("USES", out)
            self.assertIn("RULE       do not choose one for the person", out)
        self.assertIn("not one medicine", field(ok("med", "pain", "relief"), "MEDICINE"))
        self.assertIn("ACETAMINOPHEN; CODEINE PHOSPHATE [prescription; oral]", field(ok("med", "acetaminophen", "with", "codeine"), "MEDICINE"))
        self.assertIn("ETHINYL ESTRADIOL", field(ok("med", "norgestimate"), "MEDICINE"), "a pill FDA lists no substances for is in all the same")
        self.assertIn("nothing on file under that name", ok("med", "lorem", "ipsum", "dolor", "sit", "amet"))
        self.assertRegex(ok("sidefx", "--med", "metformin", "--rx", "--symptom", "diarrhea"), r"SIDE EFFECTS \d+ places? under those words")
        with open(os.path.join(REAL_DATA, "LICENSE-labels-us.txt"), encoding="utf-8") as f:
            self.assertIn("https://creativecommons.org/publicdomain/zero/1.0/", f.read())

    def test_the_interaction_data(self):
        if "ddinter.db" not in self.files:
            self.skipTest("ddinter.db does not ship in this copy")
        con = library.connect(os.path.join(REAL_DATA, "ddinter.db"))
        try:
            self.assertGreater(con.execute("SELECT COUNT(*) FROM pair").fetchone()[0], 100000)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM pair WHERE a >= b OR level NOT IN (0, 1, 2, 3)").fetchone()[0], 0)
            self.assertGreater(con.execute("SELECT COUNT(*) FROM drug").fetchone()[0], 1500)
        finally:
            con.close()
        out = ok("interact", "warfarin", "ibuprofen")
        self.assertRegex(out, r"PAIR       Warfarin \+ Ibuprofen: (Major|Moderate|Minor)")
        self.assertIn("PARTIAL", out)
        self.assertIn("CREDIT     " + build_ddinter.CREDIT, out)
        self.assertIn("paracetamol -> Acetaminophen [found under", ok("interact", "paracetamol", "warfarin"))
        with open(os.path.join(REAL_DATA, "LICENSE-ddinter.txt"), encoding="utf-8") as f:
            self.assertIn("https://creativecommons.org/licenses/by-nc-sa/4.0/", f.read())

    def test_the_icd11_data(self):
        if "icd11.db" not in self.files:
            self.skipTest("icd11.db does not ship in this copy")
        path = os.path.join(REAL_DATA, "icd11.db")
        self.assertEqual(build_icd11.verify(path), "", "the records must still add up to WHO's file")
        con = library.connect(path)
        try:
            counts = dict(con.execute("SELECT kind, COUNT(*) FROM entity GROUP BY kind"))
            self.assertGreater(counts["category"], 30000)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM entity WHERE block IS NULL OR title = ''").fetchone()[0], 0)
            facts = dict(con.execute("SELECT key, value FROM build"))
            self.assertRegex(facts["release"], r"^\d{4}-\d{2}$")
            self.assertEqual(facts["licence-sha256"], build_icd11.LICENCE_SHA256)
        finally:
            con.close()
        out = ok("code", "1A00")
        self.assertIn("TITLE      Cholera", out)
        self.assertIn("URI        http://id.who.int/icd/release/11/mms/", out)
        self.assertIn("CREDIT     " + build_icd11.CITATION, out)
        self.assertIn("the shape of an ICD-10 code", ok("code", "I21"))
        with open(os.path.join(REAL_DATA, "LICENSE-icd11.txt"), encoding="utf-8") as f:
            self.assertIn("https://creativecommons.org/licenses/by-nd/3.0/igo/", f.read())


if __name__ == "__main__":
    unittest.main()
