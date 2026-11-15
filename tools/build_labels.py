"""Build src/scripts/data/labels-us.db: what a medicine is and what its label says, from the product labels
that companies file with the United States Food and Drug Administration.

  python tools/build_labels.py --fetch      download the label files (about 1.8 GB) into downloads/, then build
  python tools/build_labels.py              build from what is already in downloads/
  python tools/build_labels.py --files FILE [FILE ...] --names FILE --retrieved 2026-11-15

The source is openFDA's drug label download (https://open.fda.gov/apis/drug/label/download/), fourteen
files of some 20,000 labels each. openFDA's terms (https://open.fda.gov/terms/, read on 15 November 2026):
"Unless otherwise noted, the content, data, documentation, code, and related materials on openFDA is public
domain and made available with a Creative Commons CC0 1.0 Universal dedication." The label data set carries
no note to the contrary. FDA asks, without requiring it, for the credit "Data provided by the U.S. Food and
Drug Administration (https://open.fda.gov)", and that nobody imply its endorsement.

What a label is, in FDA's own words: "the most recent drug listing information companies have submitted",
whose "content has neither been altered nor verified by FDA", and which "may not be the labeling on
currently distributed products or identical to the labeling that is approved". The tools repeat that.

What is kept. A quarter of a million labels would be gigabytes, and most of them are the same medicine
from another company. So:
  - only labels that FDA has matched to a product (those are the ones with names, a type and a class),
    and only human prescription and over-the-counter medicines;
  - one label for each combination of substance, type and route: the fullest one, an original
    manufacturer's before a copy, the newer before the older. Brand names are collected from all of them,
    and every one is kept that says more than the substance does;
  - what is in a product is FDA's own list of substances. For some 1,700 labels FDA gives none
    (a pack of two kinds of tablet, such as a contraceptive pill, is the usual case). Such a label is kept
    when its generic name reads as a list ("NORGESTIMATE AND ETHINYL ESTRADIOL") and every part of it is
    a substance FDA lists for another label, a medicine Wikidata knows by that name, or a name used under
    at least three separate approvals. Otherwise it is left out, and counted: nothing is guessed. Where
    such a label gives no route either, it is counted with the labels of the same substances that do,
    if those all give the same one;
  - the sections a person asks about: what it is for, the boxed warning, who must not take it, warnings,
    side effects, interactions, pregnancy and the like, and the texts written for patients. NOT the dose:
    a dose comes from the label of the product in the person's hand, never from this file.

Nothing is reworded. Curly quotes and long dashes become straight ones, as everywhere in this skill.

Other names for a substance (in English and eight more languages) come from the same Wikidata file the interaction data
uses (CC0), so that "paracetamol" finds "ACETAMINOPHEN".
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
import zlib

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, desk, store
from vosslib.labels import ALWAYS, FORMS, JOINERS, NAME_KINDS, SYMPTOM_SECTIONS
from vosslib.labels import KINDS as KNOWN_KINDS
from vosslib.labels import TYPES as TYPE_NAMES

STEM = "labels-us"
INDEX_URL = "https://api.fda.gov/download.json"
INDEX_FILE = "openfda-download.json"
TERMS_URL = "https://open.fda.gov/terms/"
TERMS_FILE = "openfda-terms.html"
TERMS_WORDS = ("creative commons cc0 1.0 universal dedication",)
NAMES_FILE = "drug-names.wikidata.json"
LICENCE = "CC0 1.0, a public domain dedication (openFDA's terms); FDA asks for the credit and that no endorsement be implied"
CREDIT = "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)"
TYPES = {"HUMAN PRESCRIPTION DRUG": "prescription", "HUMAN OTC DRUG": "over the counter"}
# openFDA's field -> the name a section goes by here. Fields that say the same thing in older and newer
# labels share a name, and are stored one after the other under it.
SECTIONS = (
    ("boxed_warning", "boxed warning"),
    ("purpose", "purpose"),
    ("active_ingredient", "active ingredient"),
    ("indications_and_usage", "uses"),
    ("contraindications", "do not use"),
    ("do_not_use", "do not use"),
    ("warnings_and_cautions", "warnings"),
    ("warnings", "warnings"),
    ("precautions", "warnings"),
    ("general_precautions", "warnings"),
    ("ask_doctor", "warnings"),
    ("ask_doctor_or_pharmacist", "warnings"),
    ("when_using", "warnings"),
    ("stop_use", "warnings"),
    ("keep_out_of_reach_of_children", "warnings"),
    ("adverse_reactions", "side effects"),
    ("drug_interactions", "interactions"),
    ("use_in_specific_populations", "pregnancy and other groups"),
    ("pregnancy", "pregnancy and other groups"),
    ("pregnancy_or_breast_feeding", "pregnancy and other groups"),
    ("nursing_mothers", "pregnancy and other groups"),
    ("pediatric_use", "pregnancy and other groups"),
    ("geriatric_use", "pregnancy and other groups"),
    ("information_for_patients", "for patients"),
    ("spl_medguide", "for patients"),
    ("spl_patient_package_insert", "for patients"),
)
KINDS = []
for _field, _kind in SECTIONS:
    if _kind not in KINDS:
        KINDS.append(_kind)
# a section is stored under its number in the reader's list, so the two lists have to be one list
if tuple(KINDS) != tuple(KNOWN_KINDS):
    sys.exit("the sections this script keeps are not the ones vosslib/labels.py knows: put the two lists right")
# how the text is packed. What 'med' prints unasked goes label by label into small blocks, and what 'sidefx'
# searches goes label by label into middling ones, so each of those answers opens one block. The sections that
# are only read when asked for go kind by kind into large blocks, where a text sits beside a hundred like it
HEAD_BLOCK = 1 << 20
SEARCHED_BLOCK = 1 << 22
BODY_BLOCK = 1 << 23
SEARCHED = tuple(k for k in SYMPTOM_SECTIONS if k not in ALWAYS)
SET_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# words that say which salt or form a substance is in, and not which substance
SALTS = frozenset("""acetate acetonide anhydrous aspartate benzoate besylate bitartrate bromide butyrate calcium carbonate chloride
citrate decanoate dihydrate dihydrochloride dimesylate dipropionate disodium edisylate esylate fumarate furoate gluconate
hemihydrate hydrate hydrobromide hydrochloride hydroxide lactate magnesium malate maleate mesylate monohydrate mononitrate
nitrate oxalate palmitate pamoate phosphate potassium propionate salicylate sodium stearate succinate sulfate tartrate
tosylate trihydrate valerate zinc""".split())
MIN_LABELS, MIN_NAMES = 2000, 2500
# where a generic name is read as a list: what parts one substance from the next, and the short ways of
# writing a salt
LIST = re.compile(r"\s*(?:[,;/&+]|\bAND\b|\bWITH\b|\bPLUS\b)\s*")
SHORT = {"HCL": "HYDROCHLORIDE", "HCI": "HYDROCHLORIDE", "HBR": "HYDROBROMIDE"}
# words that add nothing to a name, beside the forms and strengths the reader already knows
FILLER = JOINERS | frozenset(("hcl", "hbr", "usp", "nf", "kit"))
APPROVED = ("NDA", "ANDA", "BLA")       # how the number of an approved application begins
AGREED = 3                             # separate approvals that must use a name no list has
NO_ROUTE = "route not given"
START = re.compile(r'"results"\s*:\s*\[')
GAP = re.compile(r"[\s,]*")
CHUNK = 1 << 20                 # characters read at a time


# ---- reading openFDA's files

def labels(path):
    """Each label in one of openFDA's files, one at a time. A file is a single JSON object, hundreds of megabytes
    unpacked, with every label in a list called "results": it is read a piece at a time and never held whole."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".json")]
            if len(names) != 1:
                sys.exit("%s should hold exactly one JSON file" % os.path.basename(path))
            with z.open(names[0]) as raw:
                for label in _labels(io.TextIOWrapper(raw, encoding="utf-8")):
                    yield label
    else:
        with open(path, encoding="utf-8") as f:
            for label in _labels(f):
                yield label


def _labels(reader):
    decode = json.JSONDecoder().raw_decode
    buffer, pos, started = "", 0, False
    while True:
        chunk = reader.read(CHUNK)
        if not started:
            buffer += chunk
            m = START.search(buffer)
            if m:
                buffer, started = buffer[m.end():], True
            elif not chunk:
                sys.exit("a label file has no list of results in it: it is not one of openFDA's")
            else:
                buffer = buffer[-32:]          # the marker may straddle two pieces
                continue
        else:
            buffer = buffer[pos:] + chunk
        pos = 0
        while True:
            pos = GAP.match(buffer, pos).end()
            if pos >= len(buffer):
                break
            if buffer[pos] == "]":
                return
            try:
                label, pos = decode(buffer, pos)
            except ValueError:
                break                          # the label runs on into the next piece
            yield label
        if not chunk:
            sys.exit("a label file ends in the middle of a label: it is cut short")


def base_name(name):
    """A substance without the words for its salt or form: 'METFORMIN HYDROCHLORIDE' is 'METFORMIN'."""
    words = [w for w in re.split(r"[\s,]+", name.strip()) if w]
    kept = [w for w in words if w.lower() not in SALTS]
    return " ".join(kept) if kept and len(kept) < len(words) else None


def text_of(label, field):
    return desk.fix_text("\n\n".join(" ".join(str(x).split()) for x in label.get(field) or [] if str(x).strip()))


def pick(files, also_known=frozenset()):
    """Go through every file once and keep, for each substance, type and route, the best label and every brand
    name seen. also_known: folded names of medicines that count as substances though no label lists them.
    Returns ({key: [score, facts, packed sections, brand names, labels seen, class]}, how many labels were
    read, [the generic names of the labels left out because nothing says what is in them])."""
    best, aside, seen = {}, [], 0
    for path in files:
        for label in labels(path):
            seen += 1
            fda = label.get("openfda") or {}
            kind = TYPES.get((fda.get("product_type") or [""])[0])
            substances = sorted(set(" ".join(str(s).upper().split()) for s in fda.get("substance_name") or []))
            generic = [" ".join(str(g).split()) for g in fda.get("generic_name") or [] if str(g).strip()]
            if not kind or not (substances or generic):
                continue
            route = "; ".join(sorted(set(str(r).lower() for r in fda.get("route") or [])))
            brands = [" ".join(str(b).split()) for b in fda.get("brand_name") or [] if str(b).strip()]
            sections = {}
            for field, name in SECTIONS:
                text = text_of(label, field)
                if text:
                    sections[name] = (sections[name] + "\n\n" + text) if name in sections else text
            application = str((fda.get("application_number") or [""])[0])
            score = (len([1 for name in ("uses", "side effects", "warnings") if name in sections]),
                     2 if application.startswith(("NDA", "BLA")) else 1 if application.startswith("ANDA") else 0,
                     1 if (fda.get("is_original_packager") or [False])[0] else 0,
                     str(label.get("effective_time") or ""), sum(len(t) for t in sections.values()))
            facts = {"generic": "; ".join(generic) or "; ".join(substances),
                     "brand": brands[0] if brands else "", "maker": " ".join(str((fda.get("manufacturer_name") or [""])[0]).split()),
                     "class": "; ".join(sorted(set(str(c) for c in fda.get("pharm_class_epc") or []))),
                     "application": application, "set_id": str(label.get("set_id") or ""),
                     "effective": str(label.get("effective_time") or "")}
            if substances and route:
                take(best, (kind, tuple(substances), route), score, facts, sections, brands)
            else:
                # FDA does not say what is in it, or how it is taken: a pack of two kinds of tablet, as a rule.
                # Where it belongs can only be told once every label has been seen
                aside.append((kind, substances, generic, route, score, facts, squeeze(sections) if sections else None, brands))
        say("read      %s: %d labels so far, %d kept" % (os.path.basename(path), seen, sum(1 for e in best.values() if e[0] is not None)))

    known = set(also_known)
    for parts in [key[1] for key in best] + [entry[1] for entry in aside]:
        for part in parts:
            known.update([core.key(part), core.key(base_name(part) or part)])
    # a name no list has, but that separate approvals agree on, is taken at its word
    approvals = {}
    for kind, substances, generic, route, score, facts, sections, brands in aside:
        if not substances and facts["application"].startswith(APPROVED):
            for part in parts_of(generic):
                if not is_known(part, known):
                    approvals.setdefault(part, set()).add(facts["application"])
    agreed = set(part for part, numbers in approvals.items() if len(numbers) >= AGREED)
    placed, left_out = [], []
    for kind, substances, generic, route, score, facts, sections, brands in aside:
        parts = substances or parts_of(generic)
        if substances or (parts and all(is_known(p, known) or p in agreed for p in parts)):
            placed.append((kind, tuple(sorted(parts)), route, score, facts, sections, brands))
        else:
            left_out.append("; ".join(generic))
    # the ones that give a route first: they may be the only word on how the others are taken
    for entry in placed:
        if entry[2]:
            take(best, entry[:3], *entry[3:])
    routes = {}
    for kind, parts, route in best:
        routes.setdefault((kind, parts), set()).add(route)
    for kind, parts, route, score, facts, sections, brands in placed:
        if not route:
            given = routes.get((kind, parts), ())
            take(best, (kind, parts, next(iter(given)) if len(given) == 1 else NO_ROUTE), score, facts, sections, brands)
    return dict((k, e) for k, e in best.items() if e[0] is not None), seen, left_out


def take(best, key, score, facts, sections, brands):
    """Count one label towards its group, and keep it if it is the best of the group so far."""
    entry = best.get(key)
    if entry is None:
        entry = best[key] = [None, None, None, {}, 0, ""]
    entry[4] += 1
    # the class is the substance's, so one label's will do for another that does not give it
    entry[5] = entry[5] or facts["class"]
    for brand in brands:
        # counted without regard to case, shown as it was first written
        entry[3].setdefault(brand.upper(), [0, brand])[0] += 1
    if sections and (entry[0] is None or score > entry[0]):
        # held squeezed while the rest is read: a few thousand full labels would otherwise fill the memory
        entry[0], entry[1], entry[2] = score, facts, sections if isinstance(sections, bytes) else squeeze(sections)


def squeeze(sections):
    return zlib.compress(json.dumps(sections).encode("utf-8"), 1)


def parts_of(generic):
    """A generic name read as a list of substances, for a label FDA gives no list for: "Norgestimate and
    Ethinyl Estradiol Tablets USP" is NORGESTIMATE and ETHINYL ESTRADIOL. Whether the parts are substances at
    all is for the caller to check."""
    parts = []
    for name in generic:
        for part in LIST.split(name.upper()):
            words = [SHORT.get(w, w) for w in part.split()]
            while words and (words[-1].lower() in FORMS or words[-1].lower() in FILLER):
                words.pop()
            if words and " ".join(words) not in parts:
                parts.append(" ".join(words))
    return parts


def is_known(part, known):
    """Whether a name is a substance some label lists, with or without the word for its salt, or one of the
    other names handed in."""
    return core.key(part) in known or core.key(base_name(part) or part) in known


def says_more(folded, own):
    """Whether a brand name says anything the substance does not. "Ibuprofen Tablets 200 mg" and "Acetaminophen
    and Codeine" do not, and would only find what the substance finds; "Motrin IB" and "Childrens Ibuprofen" do."""
    return any(not (w in own or w in FILLER or w in FORMS or w.isdigit() or (w[:1].isdigit() and w.lstrip("0123456789") in FORMS))
               for w in folded.split("_"))


def effective(text):
    """The day a label took effect, as the number FDA gives: 20260301. Nothing else counts as a date."""
    return int(text) if re.fullmatch(r"\d{8}", text or "") else 0


def set_id(text):
    """A set id as sixteen bytes where it is the usual kind, which is all of them so far; as it stands otherwise."""
    return bytes.fromhex(text.replace("-", "")) if SET_ID.fullmatch(text or "") else text


# ---- other names, from the file the interaction data uses

def other_names(substances, items):
    """{substance: [(name, language)]} from the one Wikidata item whose English name is the substance, with or
    without the word for its salt."""
    by_key = {}
    for qid, names in items.items():
        for name in names.get("en") or []:
            by_key.setdefault(core.key(name), set()).add(qid)
    out = {}
    for substance in substances:
        hits = set(by_key.get(core.key(substance), ()))
        if not hits and base_name(substance):
            hits = set(by_key.get(core.key(base_name(substance)), ()))
        if len(hits) != 1:
            continue
        seen, extra = set([core.key(substance)]), []
        for lang in core.NAME_LANGUAGES:
            for other in items[next(iter(hits))].get(lang) or []:
                other = " ".join(other.split())
                folded = core.key(other)
                if 3 <= len(other) <= 60 and len(folded) >= 3 and folded not in seen:
                    seen.add(folded)
                    extra.append((other, lang))
        out[substance] = extra
    return out


# ---- fetching

def fetch_all(folder):
    os.makedirs(folder, exist_ok=True)
    dbtools.fetch(TERMS_URL, TERMS_FILE, "text/html", folder=folder)
    index = dbtools.fetch(INDEX_URL, INDEX_FILE, "application/json", folder=folder)
    with open(index, encoding="utf-8") as f:
        parts = json.load(f)["results"]["drug"]["label"]["partitions"]
    for part in parts:
        name = part["file"].rsplit("/", 1)[1]
        dbtools.fetch_big(part["file"], name, folder=folder, expect=int(float(part["size_mb"]) * 1048576))
    names = os.path.join(folder, NAMES_FILE)
    if not os.path.isfile(names):
        import build_ddinter
        build_ddinter.fetch_names(names)


def check_terms(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = " ".join(re.sub(r"<[^>]+>", " ", f.read()).lower().split())
    except OSError:
        sys.exit("openFDA's terms page is not in the downloads folder ('--fetch' gets it): the build does not go on without it")
    missing = [w for w in TERMS_WORDS if w not in text]
    if missing:
        sys.exit("openFDA's terms page no longer says \"%s\": read %s before this data goes out, and put TERMS_WORDS, LICENCE and "
                 "the licence text in this script right" % (missing[0], TERMS_URL))
    return dbtools.origin(path)[1]


# ---- building

LICENCE_TEXT = """labels-us.db: what it is, and on what terms

This file holds product labels of medicines sold in the United States, as companies have filed them with
the Food and Drug Administration (FDA): one label for each combination of substance, type (prescription
or over the counter) and route, with the sections a person asks about. It was built from openFDA's drug
label download: https://open.fda.gov/apis/drug/label/download/

  Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)

Licence: Creative Commons CC0 1.0 Universal, a public domain dedication
  https://creativecommons.org/publicdomain/zero/1.0/
openFDA's terms (https://open.fda.gov/terms/): "Unless otherwise noted, the content, data, documentation,
code, and related materials on openFDA is public domain and made available with a Creative Commons CC0 1.0
Universal dedication. ... You can copy, modify, distribute, and perform the work, even for commercial
purposes, all without asking permission." The label data set carries no note to the contrary. FDA asks,
without requiring it, that it be credited as above, and that no endorsement by FDA be implied. There is
none: FDA does not endorse this skill.

What a label is. FDA: the labels "represent the most recent drug listing information companies have
submitted", their "content has neither been altered nor verified by FDA", and they "may not be the
labeling on currently distributed products or identical to the labeling that is approved". Do not rely on
this file to make decisions about medical care.

These are American labels. A medicine sold under the same name elsewhere may have other strengths, other
uses and other warnings: the leaflet of the product in the person's hand is the authority, and so are the
pharmacist and the prescriber.

What was changed in the making of this file: of the many labels for one substance, one was kept; of each
label, the sections on what it is for, warnings, side effects, interactions, special groups and the texts
for patients. The dose is left out on purpose. Line breaks were tidied, and curly quotes and long dashes
made straight. No wording was changed.

Other names for the substances come from Wikidata (property P267 items), also under CC0 1.0. They were
matched by name and not checked one by one.
"""


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    files = a.files or sorted(os.path.join(a.downloads, n) for n in (os.listdir(a.downloads) if os.path.isdir(a.downloads) else [])
                              if re.fullmatch(r"drug-label-\d{4}-of-\d{4}\.json\.zip", n))
    names_path = a.names or os.path.join(a.downloads, NAMES_FILE)
    if not files or not all(os.path.isfile(p) for p in files):
        sys.exit("--files: none found. Run with --fetch, or download them by hand and name them (see the top of this script)")
    if not os.path.isfile(names_path):
        sys.exit("--names: no such file. Run with --fetch")
    m = re.search(r"-of-(\d{4})\.json\.zip$", files[0])
    if m and not a.files and len(files) != int(m.group(1)):
        sys.exit("%d of the %d label files are in the downloads folder: run with --fetch to get the rest" % (len(files), int(m.group(1))))
    days = [dbtools.origin(p, retrieved=a.retrieved)[1] for p in files]
    names_day = dbtools.origin(names_path, retrieved=a.retrieved)[1]
    terms_day = core.a_date(a.terms_read, "--terms-read") if a.terms_read else check_terms(os.path.join(a.downloads, TERMS_FILE))
    try:
        with open(names_path, encoding="utf-8") as f:
            items = json.load(f)["items"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("%s is not the names file the builders write ('--fetch' makes one)" % os.path.basename(names_path))
    if len(items) < MIN_NAMES:
        sys.exit("only %d items are in the names file, where some 3,700 are expected: nothing was built" % len(items))

    wikidata = frozenset(core.key(name) for names in items.values() for name in names.get("en") or [])
    best, seen, left_out = pick(files, wikidata)
    if len(best) < MIN_LABELS:
        sys.exit("only %d labels were kept, where several thousand are expected: these are not all of openFDA's files" % len(best))
    substances = sorted(set(s for key in best for s in key[1]))
    extra = other_names(substances, items)

    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        src = dbtools.add_source(con, "openFDA drug labels: product labelling as companies have filed it with the United States "
                                      "Food and Drug Administration", "https://open.fda.gov/apis/drug/label/download/", min(days),
                                 LICENCE, CREDIT)
        src_names = dbtools.add_source(con, "Wikidata: other names for medicines (labels and aliases of items with an ATC code, P267)",
                                       "https://www.wikidata.org/wiki/Property:P267", names_day, "CC0 1.0, a public domain dedication", "")
        # a row is small on purpose. type: its place in labels.TYPES; route, maker and class: a row of 'word', since
        # a few thousand of them serve every label; what is in a label is in label_substance and is not said twice
        con.execute("CREATE TABLE label (id INTEGER PRIMARY KEY, type INTEGER NOT NULL, route INTEGER NOT NULL, parts INTEGER NOT NULL, "
                    "maker INTEGER NOT NULL, class INTEGER NOT NULL, set_id BLOB NOT NULL, effective INTEGER NOT NULL, "
                    "labels INTEGER NOT NULL, source INTEGER NOT NULL)")
        con.execute("CREATE TABLE word (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        # a name belongs to a substance, and a substance to every label it is in: stored once each
        con.execute("CREATE TABLE substance (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        # kind: its place in labels.NAME_KINDS
        con.execute("CREATE TABLE substance_name (folded TEXT NOT NULL, substance INTEGER NOT NULL, shown TEXT NOT NULL, kind INTEGER NOT NULL, "
                    "source INTEGER NOT NULL, PRIMARY KEY (folded, substance)) WITHOUT ROWID")
        con.execute("CREATE TABLE label_substance (substance INTEGER NOT NULL, label INTEGER NOT NULL, PRIMARY KEY (substance, label)) "
                    "WITHOUT ROWID")
        # the brand names of a label. place: 1 for the one most labels of the group carry, and so on down
        con.execute("CREATE TABLE label_name (folded TEXT NOT NULL, label INTEGER NOT NULL, shown TEXT NOT NULL, "
                    "place INTEGER NOT NULL, PRIMARY KEY (folded, label)) WITHOUT ROWID")
        # kind: its place in labels.KINDS
        con.execute("CREATE TABLE section (label INTEGER NOT NULL, kind INTEGER NOT NULL, block INTEGER NOT NULL, start INTEGER NOT NULL, "
                    "length INTEGER NOT NULL, PRIMARY KEY (label, kind)) WITHOUT ROWID")
        words = {}

        def word(text):
            if text not in words:
                words[text] = len(words) + 1
                con.execute("INSERT INTO word VALUES (?, ?)", (words[text], text))
            return words[text]
        numbers = {}
        for number, part in enumerate(substances, 1):
            numbers[part] = number
            con.execute("INSERT INTO substance VALUES (?, ?)", (number, part))
            add_name(con, part, number, part, "substance", src)
            if base_name(part):
                add_name(con, base_name(part), number, part, "substance", src)
            for other, lang in extra.get(part, ()):
                add_name(con, other, number, other, "also called (%s)" % lang, src_names)
        texts = dbtools.Texts(con, a.codec, HEAD_BLOCK)
        counts = dict((k, 0) for k in TYPES.values())
        names = 0
        # in the order of the names, so that one substance's labels sit together and squeeze together
        order = sorted(best, key=lambda k: (k[1], k[0], k[2]))

        def pack_sections(number, key, kinds):
            sections = json.loads(zlib.decompress(best[key][2]).decode("utf-8"))
            for name in kinds:
                if name in sections:
                    block, start, length = texts.add(sections[name])
                    con.execute("INSERT INTO section VALUES (?, ?, ?, ?, ?)", (number, KINDS.index(name), block, start, length))

        for number, key in enumerate(order, 1):
            kind, parts, route = key
            _, facts, packed, brands, labels_seen, group_class = best[key]
            counts[kind] += 1
            con.execute("INSERT INTO label VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (number, TYPE_NAMES.index(kind), word(route), len(parts), word(facts["maker"]),
                         word(facts["class"] or group_class), set_id(facts["set_id"]), effective(facts["effective"]),
                         labels_seen, src))
            pack_sections(number, key, ALWAYS)
            own = set()
            for part in parts:
                con.execute("INSERT INTO label_substance VALUES (?, ?)", (numbers[part], number))
                own.update(core.key(part).split("_"))
            # a name of its own ("Motrin IB") before one built on the substance ("Childrens Ibuprofen"), and
            # among those the one most labels carry
            ranked = sorted(brands.items(), key=lambda b: (any(w in own for w in core.key(b[1][1]).split("_")), -b[1][0], b[0]))
            kept = 0
            for _, (count, brand) in ranked:
                folded = core.key(brand)
                if folded and says_more(folded, own):
                    kept += con.execute("INSERT OR IGNORE INTO label_name VALUES (?, ?, ?, ?)",
                                        (folded, number, brand, kept + 1)).rowcount
            names += kept
        texts.new_blocks(SEARCHED_BLOCK)
        for number, key in enumerate(order, 1):
            pack_sections(number, key, SEARCHED)
        texts.new_blocks(BODY_BLOCK)
        for name in [k for k in KINDS if k not in ALWAYS and k not in SEARCHED]:
            for number, key in enumerate(order, 1):
                pack_sections(number, key, (name,))
        raw, packed_size = texts.close()
        size = dbtools.finish(con, path, core.today(), facts=(
            ("format", 3), ("labels", len(best)), ("labels-read", seen), ("prescription", counts["prescription"]),
            ("over-the-counter", counts["over the counter"]), ("substances", len(substances)), ("brand-names", names),
            ("left-out-no-substances", len(left_out)), ("named-through-wikidata", len(extra)), ("terms-read", terms_day.isoformat())))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE_TEXT, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d labels kept of %d read: %d prescription, %d over the counter; %d substances" % (
        len(best), seen, counts["prescription"], counts["over the counter"], len(substances)))
    say("          text: %s packed into %s (%.1f times smaller; blocks: %s)" % (
        dbtools.size_words(raw), dbtools.size_words(packed_size), raw / float(max(packed_size, 1)),
        ", ".join("%d %s" % (n, c) for c, n in sorted(texts.used.items()))))
    say("          brand names: %d; left out: %s that FDA lists no substances for, and whose generic name does not "
        "read as a list of them" % (names, core.plural(len(left_out), "label")))
    if left_out:
        common = sorted(set(left_out), key=lambda name: (-left_out.count(name), name))[:5]
        say("          the commonest of those: %s" % "; ".join("%s (%d)" % (name[:70], left_out.count(name)) for name in common))
    say("          other names: %d substances matched to one Wikidata item" % len(extra))
    say("          retrieved: labels %s, names %s; terms page read %s" % (min(days), names_day, terms_day))
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def add_name(con, name, owner, shown, kind, source):
    folded = core.key(name)
    if folded:
        con.execute("INSERT OR IGNORE INTO substance_name VALUES (?, ?, ?, ?, ?)", (folded, owner, shown, NAME_KINDS.index(kind), source))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download everything into the downloads folder first (about 1.8 GB)")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--files", metavar="FILE", nargs="+", help="openFDA's label files (default: every drug-label-NNNN-of-NNNN.json.zip in downloads/)")
    ap.add_argument("--names", metavar="FILE", help="the names file the interaction builder writes from Wikidata")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the files were downloaded, for files fetched by hand")
    ap.add_argument("--terms-read", metavar="DATE", help="for a build with no terms page in downloads/: the day you read openFDA's terms yourself")
    ap.add_argument("--codec", help="how to pack the text: smallest (default), or one of %s" % ", ".join(store.CODECS))
    ap.add_argument("--out", metavar="DIR", help="where to write labels-us.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads)
    return build(a)


if __name__ == "__main__":
    main()
