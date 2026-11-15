"""Build src/scripts/data/core-pd.db: health topics and definitions in plain English, and the emergency
numbers of every country.

  python tools/build_core.py --fetch      download what is needed into downloads/, then build
  python tools/build_core.py              build from what is already in downloads/
  python tools/build_core.py --topics FILE --definitions FILE [FILE ...] --numbers FILE --retrieved 2026-11-15
                                          build from files fetched by hand (an address works in place of a file)

Everything in the file is public domain or CC0, which is what "pd" stands for:

  MedlinePlus health topics    https://medlineplus.gov/xml.html, the compressed health topic XML, published daily.
                               The summaries on health topic pages are works of the United States government and
                               not copyrighted; MedlinePlus asks to be named as the source.
                               Terms: https://medlineplus.gov/about/using/usingcontent/
  MedlinePlus definitions      the five "Definitions of Health Terms" XML files on the same page: short
                               definitions, each with the NIH body it came from.
  Wikidata                     emergency telephone numbers by country (property P2852), CC0. Read through the
                               ordinary API, a few hundred small requests, because the query service is often
                               rate-limited.
  European Commission          one fact, checked on its page at every fetch: 112 reaches every emergency
                               service anywhere in the European Union.

What is deliberately left out of the MedlinePlus file: the links to other sites (they are other people's
pages), the Spanish topics (the core is English), and every picture. The A.D.A.M. encyclopedia and the ASHP
drug monographs are copyrighted, are not in these files, and must never be added.

What this script changes: a summary's HTML becomes plain text (paragraphs, "## " headings, "- " list items),
and curly quotes and long dashes become straight ones, as everywhere else in this skill. No wording is
changed. Emergency numbers are passed through as Wikidata lists them, with what it says each is for; they
are not verified one by one, and the tool says so every time it prints them.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

import dbtools
from dbtools import DATA, DOWNLOADS, say
from vosslib import core, desk, store

STEM = "core-pd"
XML_PAGE = "https://medlineplus.gov/xml.html"
TERMS_PAGE = "https://medlineplus.gov/about/using/usingcontent/"
TOPICS_RE = re.compile(r"https://medlineplus\.gov/xml/(mplus_topics_compressed_(\d{4}-\d{2}-\d{2})\.zip)")
DEFINITION_FILES = ("fitness", "generalhealth", "minerals", "nutrition", "vitamins")
DEFINITION_URL = "https://medlineplus.gov/xml/%sdefinitions.xml"
CREDIT = "Source: MedlinePlus, National Library of Medicine"
PD = "public domain: a work of the United States government, not copyrighted. MedlinePlus asks to be named as the source"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
NUMBERS_FILE = "emergency.wikidata.json"
EU_PAGE = "https://digital-strategy.ec.europa.eu/en/policies/112"
EU_FILE = "eu-112.html"
# the page must still say both of these, or somebody has to read it again before the fact is repeated
EU_WORDS = ("european emergency phone number", "available everywhere in the eu")
EU_FACT = "112 is the European emergency number: free of charge, and it reaches an ambulance, the fire brigade or the police anywhere in the European Union"
EU = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
MIN_TOPICS, MIN_COUNTRIES = 900, 150
MEDICAL = "emergency medical services"
PACE, MAX_PACE = 0.5, 6.0       # seconds between requests to Wikidata: where it starts, and how slow it may get

# Names as people say them, where the source's label is the formal one; and what else a country is called.
NAMES = {"CN": "China", "NL": "Netherlands", "DK": "Denmark", "US": "United States", "GB": "United Kingdom", "CD": "DR Congo",
         "CG": "Republic of the Congo", "KR": "South Korea", "KP": "North Korea", "FM": "Micronesia", "GM": "The Gambia",
         "BS": "The Bahamas", "PS": "Palestine", "TL": "Timor-Leste", "CZ": "Czechia", "MK": "North Macedonia", "IE": "Ireland"}
AKA = {"US": ["usa", "america", "united states of america", "the states"],
       "GB": ["uk", "britain", "great britain", "england", "scotland", "wales", "northern ireland"],
       "CN": ["prc", "peoples republic of china"], "CZ": ["czech republic"], "NL": ["holland", "the netherlands"], "KR": ["korea"],
       "RU": ["russian federation"], "AE": ["uae", "emirates"], "TR": ["turkiye"], "CI": ["ivory coast"], "CD": ["drc", "congo kinshasa"],
       "CG": ["congo brazzaville"], "MM": ["burma"], "SZ": ["swaziland"], "TL": ["east timor"], "CV": ["cape verde"], "VA": ["vatican"],
       "BA": ["bosnia"], "MK": ["macedonia"], "PL": ["polska"], "DE": ["deutschland"], "ES": ["espana"], "FR": ["la france"],
       "IT": ["italia"], "UA": ["ukraina"], "IE": ["eire", "republic of ireland"]}


# ---- a summary's HTML as plain text

class Plain(HTMLParser):
    """Paragraphs, '## ' headings, '- ' list items, table rows with ' | ' between cells. Links keep their words
    and lose their addresses; pictures are dropped."""
    HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
    BREAKS = ("p", "div", "table", "blockquote")

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out, self.depth, self.skip = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.HEADINGS:
            self.out.append("\n\n## ")
        elif tag in self.BREAKS:
            self.out.append("\n\n")
        elif tag in ("ul", "ol"):
            self.depth += 1
            if self.depth == 1:
                self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n%s- " % ("  " * max(self.depth - 1, 0)))
        elif tag in ("br", "tr"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(self.skip - 1, 0)
        elif tag in self.HEADINGS or tag in self.BREAKS:
            self.out.append("\n\n")
        elif tag in ("ul", "ol"):
            self.depth = max(self.depth - 1, 0)
            if self.depth == 0:
                self.out.append("\n\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def plain(html):
    """HTML as tidy plain text, in this skill's typography."""
    parser = Plain()
    parser.feed(html or "")
    parser.close()
    lines = []
    for line in "".join(parser.out).split("\n"):
        body = re.sub(r"\s*\|\s*$", "", " ".join(line.split()))
        # a list inside a list keeps its indent; nothing else is indented
        indent = len(line) - len(line.lstrip(" ")) if body.startswith("- ") else 0
        lines.append(" " * indent + body)
    text = "\n".join(lines)
    text = re.sub(r"(?m)^## *$", "", text)                 # a heading with nothing in it
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return desk.fix_text(text)


def tidy(text):
    return desk.fix_text(" ".join(str(text or "").split()))


# ---- reading the downloads

def iso_date(text):
    """MedlinePlus writes 10/22/1998; the database keeps 1998-10-22. Anything else is kept out."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})(?: .*)?", str(text or "").strip())
    return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2))) if m else ""


def read_topics(path):
    """Every English health topic in the file: [dict]. Also returns the day the file says it was generated."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if len(names) != 1:
                sys.exit("%s should hold exactly one XML file" % os.path.basename(path))
            with z.open(names[0]) as f:
                return _topics(f)
    with open(path, "rb") as f:
        return _topics(f)


def _topics(stream):
    topics, generated, total, seen = [], "", None, 0
    for event, el in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            if el.tag == "health-topics":
                generated, total = iso_date(el.get("date-generated")), el.get("total")
            continue
        if el.tag != "health-topic":
            continue
        seen += 1
        if el.get("language") == "English":
            try:
                number = int(el.get("id"))
            except (TypeError, ValueError):
                sys.exit("a health topic has no usable id: the file is not in the shape this script knows")
            institute = el.find("primary-institute")
            topics.append({
                "id": number, "title": tidy(el.get("title")), "url": (el.get("url") or "").strip(),
                "created": iso_date(el.get("date-created")), "brief": tidy(el.get("meta-desc")),
                "also": [tidy(x.text) for x in el.findall("also-called") if tidy(x.text)],
                "see": [tidy(x.text) for x in el.findall("see-reference") if tidy(x.text)],
                "mesh": [tidy(x.text) for x in el.findall("mesh-heading/descriptor") if tidy(x.text)],
                "groups": [tidy(x.text) for x in el.findall("group") if tidy(x.text)],
                "related": [int(x.get("id")) for x in el.findall("related-topic") if (x.get("id") or "").isdigit()],
                "institute": tidy(institute.text) if institute is not None else "",
                "text": plain(el.findtext("full-summary")),
            })
        el.clear()
    if total is not None and str(total).isdigit() and int(total) != seen:
        sys.exit("the topic file says it holds %s topics and %d were read: it is cut short or damaged" % (total, seen))
    if len(topics) < MIN_TOPICS:
        sys.exit("only %d English topics were read, where about a thousand are expected: this is not the health topic file"
                 % len(topics))
    topics.sort(key=lambda t: (core.key(t["title"]), t["id"]))
    return topics, generated


def read_definitions(paths):
    """Every term in the 'Definitions of Health Terms' files: [dict]. A term defined twice in the same words is kept once."""
    out, seen = [], set()
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            sys.exit("%s is not well-formed XML: %s" % (os.path.basename(path), e))
        if root.tag != "definition-page":
            sys.exit("%s is not a 'Definitions of Health Terms' file" % os.path.basename(path))
        page = tidy(root.get("title"))
        for group in root.findall("term-group"):
            # the files open each term and definition with a stray '>'
            title = tidy((group.findtext("term") or "").lstrip("> \n\t"))
            text = plain((group.findtext("definition") or "").lstrip("> \n\t"))
            if not title or not text:
                continue
            same = (core.key(title), text)
            if same in seen:
                continue
            seen.add(same)
            out.append({"title": title, "text": text, "origin": tidy(group.get("reference")), "page": page,
                        "url": (group.get("reference-url") or "").strip()})
    out.sort(key=lambda d: (core.key(d["title"]), d["origin"]))
    return out


# ---- Wikidata, through its ordinary API

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


def _item(snak):
    value = (snak.get("datavalue") or {}).get("value")
    return value.get("id") if isinstance(value, dict) else None


def fetch_numbers(path):
    """Every country's emergency-number statements, with what each number is for, saved as one tidy file."""
    found, more = [], {}
    while True:
        got = api(dict({"action": "query", "list": "search", "srnamespace": 0, "srlimit": 500, "srprop": "",
                        "srsearch": "haswbstatement:P2852 haswbstatement:P297"}, **more))
        found += [row["title"] for row in got.get("query", {}).get("search", [])]
        more = got.get("continue") or {}
        if not more:
            break
    found = sorted(set(found), key=lambda q: int(q[1:]))
    if len(found) < MIN_COUNTRIES:
        sys.exit("Wikidata named only %d countries with an emergency number: something is wrong, nothing was saved" % len(found))
    # what was read today is kept as it comes in, so a fetch that the server cuts short picks up where it stopped
    partial, day = path + ".partial", core.today().isoformat()
    done = {}
    try:
        with open(partial, encoding="utf-8") as f:
            kept = json.load(f)
        if kept.get("day") == day:
            done = kept["done"]
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    todo = [q for q in found if q not in done]
    say("wikidata  %d countries to read, two small requests each%s: this takes some minutes" % (
        len(todo), " (%d already read today)" % len(done) if done else ""))

    def keep():
        with open(partial, "w", encoding="utf-8") as f:
            json.dump({"day": day, "done": done}, f)

    try:
        for n, qid in enumerate(todo, 1):
            codes = []
            for claim in api({"action": "wbgetclaims", "entity": qid, "property": "P297"}).get("claims", {}).get("P297", []):
                code = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value")
                if isinstance(code, str) and claim.get("rank") != "deprecated" and not (claim.get("qualifiers") or {}).get("P582"):
                    codes.append(code.upper())
            numbers = []
            for claim in api({"action": "wbgetclaims", "entity": qid, "property": "P2852"}).get("claims", {}).get("P2852", []):
                item = _item(claim.get("mainsnak", {}))
                if not item:
                    continue
                quals = claim.get("qualifiers") or {}
                use = [q for q in (_item(s) for s in quals.get("P366", [])) if q]
                notes = [q for prop, snaks in sorted(quals.items()) if prop not in ("P366", "P580", "P582")
                         for q in (_item(s) for s in snaks) if q]
                numbers.append({"item": item, "rank": claim.get("rank") or "normal", "use": use, "notes": notes,
                                "ended": bool(quals.get("P582"))})
            done[qid] = {"item": qid, "codes": sorted(set(codes)), "numbers": numbers}
            if n % 5 == 0:
                keep()
            if n % 25 == 0:
                say("wikidata  %d of %d" % (n, len(todo)))
    finally:
        keep()
    countries = [done[q] for q in found]
    wanted = set()
    for country in countries:
        for row in country["numbers"]:
            wanted.update([row["item"]] + row["use"] + row["notes"])
    labels, phones = {}, {}
    # a country's item is huge, so only its label is asked for; a number's item is tiny, and may carry the digits
    for ids, props in ((found, "labels"), (sorted(wanted - set(found)), "labels|claims")):
        for i in range(0, len(ids), 50):
            got = api({"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "languages": "en", "props": props})
            for qid, entity in got.get("entities", {}).items():
                labels[qid] = (entity.get("labels", {}).get("en") or {}).get("value", "")
                for claim in entity.get("claims", {}).get("P1329", []):
                    value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value")
                    if isinstance(value, str):
                        phones.setdefault(qid, value)
    for country in countries:
        country["name"] = labels.get(country["item"], "")
        for row in country["numbers"]:
            label = labels.get(row["item"], "")
            row["number"] = label if _digits(label) else phones.get(row["item"], label)
            row["use"] = [labels.get(q) or q for q in row["use"]]
            row["notes"] = [labels.get(q) or q for q in row["notes"]]
    doc = {"what": "Emergency telephone numbers by country, as Wikidata lists them (property P2852), with what each is "
                   "for where it says. Read through the API by tools/build_core.py.",
           "countries": countries}
    dbtools.save(path, (json.dumps(doc, ensure_ascii=True, indent=1) + "\n").encode("utf-8"),
                 "https://www.wikidata.org/wiki/Property:P2852")
    os.remove(partial)
    say("fetched   %s (%d countries)" % (os.path.basename(path), len(countries)))
    return path


def _digits(text):
    return bool(re.fullmatch(r"[0-9]{2,6}", str(text).replace(" ", "").replace("-", "")))


def read_numbers(path):
    """{code: (name, [(number, what it is for, from the EU page or not)])}, in the order to say them, and what was left out."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        rows = doc["countries"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("%s is not the emergency numbers file this script writes ('--fetch' makes one)" % os.path.basename(path))
    out, left = {}, []
    for country in rows:
        kept = []
        for row in country.get("numbers") or []:
            number = str(row.get("number") or "").replace(" ", "").replace("-", "")
            if row.get("ended") or row.get("rank") == "deprecated":
                continue
            if not _digits(number):
                left.append("%s: a number without digits, left out" % "/".join(country.get("codes") or ["?"]))
                continue
            use = "; ".join(tidy(x) for x in list(row.get("use") or []) + list(row.get("notes") or []) if tidy(x))
            same = [k for k in kept if k[0] == number]
            if same:
                if use and use not in same[0][1]:
                    same[0][1] = "; ".join(x for x in (same[0][1], use) if x)
                continue
            kept.append([number, use, row.get("rank") == "preferred"])
        for code in country.get("codes") or []:
            if not re.fullmatch(r"[A-Z]{2}", code) or code in out:
                continue
            numbers = [(n, u, False, p) for n, u, p in kept]
            if code in EU and not any(n == "112" for n, _, _, _ in numbers):
                numbers.append(("112", "", True, False))
            # inside the EU 112 leads, whatever else is listed. Then the country's own first choice, the general
            # numbers, the ambulance, and everything else in the order the source has it
            numbers.sort(key=lambda r: (0 if r[0] == "112" and code in EU else 1 if r[3] else 2 if not r[1]
                                        else 3 if MEDICAL in r[1] else 4))
            if numbers:
                out[code] = (NAMES.get(code) or tidy(country.get("name")) or code, [(n, u, eu) for n, u, eu, _ in numbers],
                             tidy(country.get("name")))
    if len(out) < MIN_COUNTRIES:
        sys.exit("only %d countries have a usable number, where about two hundred are expected: nothing was built" % len(out))
    return out, left


def check_eu_page(path):
    """The Commission's page must still say what the tool repeats from it."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = " ".join(re.sub(r"<[^>]+>", " ", f.read()).lower().split())
    except OSError:
        sys.exit("the European Commission's page on 112 is not in downloads/ ('--fetch' gets it)")
    missing = [w for w in EU_WORDS if w not in text]
    if missing:
        sys.exit("the European Commission's page on 112 no longer says \"%s\": read %s, and put EU_WORDS and EU_FACT in "
                 "this script right before the fact is repeated" % (missing[0], EU_PAGE))


# ---- fetching

def fetch_all(folder):
    page, _ = dbtools.get(XML_PAGE)
    found = sorted(set(TOPICS_RE.findall(page.decode("utf-8", "replace"))), key=lambda m: m[1])
    if not found:
        sys.exit("no compressed health topic file is linked from %s: the page has changed" % XML_PAGE)
    name, day = found[-1]
    dbtools.fetch("https://medlineplus.gov/xml/" + name, name, folder=folder)
    for stem in DEFINITION_FILES:
        dbtools.fetch(DEFINITION_URL % stem, "%sdefinitions.xml" % stem, folder=folder)
    dbtools.fetch(EU_PAGE, EU_FILE, "text/html", folder=folder)
    fetch_numbers(os.path.join(folder, NUMBERS_FILE))


# ---- building

LICENCE = """core-pd.db: where its contents come from, and on what terms

Everything in this file is in the public domain or under CC0. It may be copied, passed on and built upon
without asking anyone. The credit lines below are kept all the same, because the sources ask for them and
because an answer should say where it came from.

1. MedlinePlus health topic summaries, and the "Definitions of Health Terms"
   National Library of Medicine (NLM), United States. https://medlineplus.gov/xml.html
   Works of the United States government, not copyrighted. NLM's own words: "Works produced by the federal
   government are not copyrighted under U.S. law. You may reproduce, redistribute, and link freely to
   non-copyrighted content", which includes the "Summaries on health topic pages".
   (https://medlineplus.gov/about/using/usingcontent/)
   Credit, to be kept with every answer drawn from it: Source: MedlinePlus, National Library of Medicine
   NLM does not endorse this skill. The file holds the topics as they stood on the day it was retrieved
   ('sources' prints the day): it is not the current MedlinePlus, and MedlinePlus is.
   Medical Subject Headings (MeSH) carried with the topics are NLM's too, and are named as such.
   Not in this file, and never to be added: the A.D.A.M. Medical Encyclopedia, the drug monographs of the
   American Society of Health-System Pharmacists, and the pictures. Those are copyrighted.
   Changed in the making of this file: HTML turned into plain text; curly quotes and long dashes made
   straight. No wording was changed.

2. Emergency telephone numbers by country
   Wikidata, property P2852. https://www.wikidata.org/wiki/Property:P2852
   Creative Commons CC0 1.0, a public domain dedication: https://creativecommons.org/publicdomain/zero/1.0/
   Passed through as Wikidata lists them. They were not verified one by one.

3. One fact about the number 112
   European Commission, "112 - the EU's emergency phone number".
   https://digital-strategy.ec.europa.eu/en/policies/112
   A fact, cited with its source. No text of the page is reproduced.
"""


def build(a):
    built = core.today()
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    topics_path = a.topics or dbtools.newest(a.downloads, "mplus_topics", (".zip", ".xml"))
    definition_paths = a.definitions or [p for p in (os.path.join(a.downloads, "%sdefinitions.xml" % s) for s in DEFINITION_FILES)
                                         if os.path.isfile(p)]
    numbers_path = a.numbers or os.path.join(a.downloads, NUMBERS_FILE)
    eu_path = a.eu_page or os.path.join(a.downloads, EU_FILE)
    for what, path in (("--topics", topics_path), ("--numbers", numbers_path), ("--eu-page", eu_path)):
        if not path or not os.path.isfile(path):
            sys.exit("%s: no such file. Run with --fetch, or download it by hand and name it (see the top of this script)" % what)
    if not definition_paths or not all(os.path.isfile(p) for p in definition_paths):
        sys.exit("--definitions: not found. Run with --fetch, or download them by hand and name them")
    topics_url, topics_day = dbtools.origin(topics_path, retrieved=a.retrieved)
    numbers_url, numbers_day = dbtools.origin(numbers_path, retrieved=a.retrieved)
    eu_url, eu_day = dbtools.origin(eu_path, retrieved=a.retrieved)
    definition_days = [dbtools.origin(p, retrieved=a.retrieved)[1] for p in definition_paths]
    check_eu_page(eu_path)

    topics, generated = read_topics(topics_path)
    definitions = read_definitions(definition_paths)
    countries, left_out = read_numbers(numbers_path)

    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        raw, packed, used = fill(con, a.codec, topics, definitions, countries, (topics_url or XML_PAGE, topics_day),
                                 min(definition_days), (numbers_url or "https://www.wikidata.org/wiki/Property:P2852", numbers_day),
                                 (eu_url or EU_PAGE, eu_day))
        size = dbtools.finish(con, path, built, facts=(
            ("format", 1), ("toolkit", vosslib_version()), ("topics", len(topics)), ("definitions", len(definitions)),
            ("countries", len(countries)), ("topics-file-generated", generated)))
    except BaseException:
        dbtools.discard(con, path)          # no half-built file is left where the skill would pack it
        raise
    dbtools.write_licence(STEM, LICENCE, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d health topics, %d definitions, %d countries with emergency numbers" % (len(topics), len(definitions), len(countries)))
    say("          text: %s packed into %s (%.1f times smaller; blocks: %s)" % (
        dbtools.size_words(raw), dbtools.size_words(packed), raw / float(max(packed, 1)),
        ", ".join("%d %s" % (n, c) for c, n in sorted(used.items()))))
    say("          retrieved: topics %s (file generated %s), definitions %s, numbers %s, the EU page %s" % (
        topics_day, generated or "?", min(definition_days), numbers_day, eu_day))
    added = [c for c in sorted(countries) if any(eu for _, _, eu in countries[c][1])]
    if added:
        say("          112 added from the EU page, where Wikidata does not list it: %s" % ", ".join(added))
    for line in left_out:
        say("          NOTE " + line)
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def fill(con, codec, topics, definitions, countries, topics_from, definitions_day, numbers_from, eu_from):
    """Write everything into the new database. Returns how much text went in, how much it packed to, and how."""
    src_topics = dbtools.add_source(con, "MedlinePlus health topics, National Library of Medicine", topics_from[0],
                                    topics_from[1], PD, CREDIT)
    src_defs = dbtools.add_source(con, "MedlinePlus definitions of health terms, National Library of Medicine", XML_PAGE,
                                  definitions_day, PD, CREDIT)
    src_numbers = dbtools.add_source(con, "Wikidata: emergency telephone numbers by country (property P2852)",
                                     numbers_from[0], numbers_from[1], "CC0 1.0, a public domain dedication", "")
    src_eu = dbtools.add_source(con, "European Commission: 112, the EU's emergency phone number", eu_from[0], eu_from[1],
                                "one fact cited from the page; none of its text is reproduced", "")
    con.execute("CREATE TABLE entry (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, "
                "origin TEXT NOT NULL, created TEXT NOT NULL, brief TEXT NOT NULL, block INTEGER, start INTEGER NOT NULL, "
                "length INTEGER NOT NULL, source INTEGER NOT NULL)")
    con.execute("CREATE TABLE name (folded TEXT NOT NULL, entry INTEGER NOT NULL, kind TEXT NOT NULL, shown TEXT NOT NULL)")
    con.execute("CREATE TABLE related (entry INTEGER NOT NULL, other INTEGER NOT NULL, PRIMARY KEY (entry, other)) WITHOUT ROWID")
    con.execute("CREATE TABLE grouping (entry INTEGER NOT NULL, name TEXT NOT NULL, PRIMARY KEY (entry, name)) WITHOUT ROWID")
    con.execute("CREATE TABLE country (code TEXT PRIMARY KEY, name TEXT NOT NULL, eu INTEGER NOT NULL) WITHOUT ROWID")
    con.execute("CREATE TABLE country_name (folded TEXT PRIMARY KEY, code TEXT NOT NULL) WITHOUT ROWID")
    con.execute("CREATE TABLE emergency (code TEXT NOT NULL, position INTEGER NOT NULL, number TEXT NOT NULL, use TEXT NOT NULL, "
                "source INTEGER NOT NULL, PRIMARY KEY (code, position)) WITHOUT ROWID")
    con.execute("CREATE TABLE fact (key TEXT PRIMARY KEY, value TEXT NOT NULL, source INTEGER NOT NULL) WITHOUT ROWID")

    texts = dbtools.Texts(con, codec)
    known = set(t["id"] for t in topics)
    for t in topics:
        block, start, length = texts.add(t["text"])
        con.execute("INSERT INTO entry VALUES (?, 'topic', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (t["id"], t["title"], t["url"], t["institute"], t["created"], t["brief"], block, start, length, src_topics))
        add_names(con, t["id"], [("title", t["title"])] + [("also called", x) for x in t["also"]]
                  + [("see reference", x) for x in t["see"]] + [("MeSH", x) for x in t["mesh"]])
        for other in sorted(set(t["related"])):
            if other in known and other != t["id"]:
                con.execute("INSERT INTO related VALUES (?, ?)", (t["id"], other))
        for group in sorted(set(t["groups"])):
            con.execute("INSERT INTO grouping VALUES (?, ?)", (t["id"], group))
    number = max(known) + 1000 - max(known) % 1000          # definitions have no number of their own: they follow the topics
    for d in definitions:
        number += 1
        block, start, length = texts.add(d["text"])
        con.execute("INSERT INTO entry VALUES (?, 'definition', ?, ?, ?, '', ?, ?, ?, ?, ?)",
                    (number, d["title"], d["url"], d["origin"], d["page"], block, start, length, src_defs))
        add_names(con, number, [("title", d["title"])])
    raw, packed = texts.close()
    con.execute("CREATE INDEX name_folded ON name (folded)")

    for code in sorted(countries):
        name, numbers, formal = countries[code]
        con.execute("INSERT INTO country VALUES (?, ?, ?)", (code, name, 1 if code in EU else 0))
        for alias in [code, name, formal] + AKA.get(code, []):
            if core.key(alias):
                con.execute("INSERT OR IGNORE INTO country_name VALUES (?, ?)", (core.key(alias), code))
        for position, (num, use, from_eu) in enumerate(numbers, 1):
            con.execute("INSERT INTO emergency VALUES (?, ?, ?, ?, ?)", (code, position, num, use, src_eu if from_eu else src_numbers))
    con.execute("INSERT INTO fact VALUES ('eu-112', ?, ?)", (EU_FACT, src_eu))
    return raw, packed, texts.used


def add_names(con, entry, names):
    """The names an entry is found under. "Daily Value (DV)" is also found as "Daily Value" and as "DV". Only an
    abbreviation is split off like that: in "Cold (Temperature)" the brackets say which cold is meant, and
    neither half is a name for it."""
    seen = set()
    for kind, shown in names:
        forms = [shown]
        m = re.fullmatch(r"(.+?)\s*\(([A-Za-z0-9][A-Za-z0-9\-]{1,11})\)", shown)
        if m and sum(1 for c in m.group(2) if c.isupper() or c.isdigit()) >= 2:
            forms += [m.group(1), m.group(2)]
        for form in forms:
            folded = core.key(form)
            if folded and folded not in seen:
                seen.add(folded)
                con.execute("INSERT INTO name VALUES (?, ?, ?, ?)", (folded, entry, kind, form))


def vosslib_version():
    import vosslib
    return vosslib.VERSION


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download everything into the downloads folder first")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--topics", metavar="FILE", help="the MedlinePlus health topic file, .zip or .xml (default: the newest in downloads/)")
    ap.add_argument("--definitions", metavar="FILE", nargs="+", help="the 'Definitions of Health Terms' XML files")
    ap.add_argument("--numbers", metavar="FILE", help="the emergency numbers file that --fetch writes")
    ap.add_argument("--eu-page", metavar="FILE", help="the European Commission's page on 112, as saved by --fetch")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the files were downloaded, for files fetched by hand")
    ap.add_argument("--codec", help="how to pack the text: smallest (default), or one of %s" % ", ".join(store.CODECS))
    ap.add_argument("--out", metavar="DIR", help="where to write core-pd.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.numbers and dbtools.is_url(a.numbers):
        sys.exit("--numbers is a file: the numbers are read from Wikidata request by request, which --fetch does")
    if a.fetch:
        fetch_all(a.downloads)
    # an address works wherever a file does: it is downloaded first, and its note says where it came from
    if a.topics and dbtools.is_url(a.topics):
        a.topics = dbtools.fetch(a.topics, os.path.basename(urllib.parse.urlparse(a.topics).path), folder=a.downloads)
    if a.eu_page and dbtools.is_url(a.eu_page):
        a.eu_page = dbtools.fetch(a.eu_page, EU_FILE, "text/html", folder=a.downloads)
    a.definitions = [dbtools.fetch(d, os.path.basename(urllib.parse.urlparse(d).path), folder=a.downloads)
                     if dbtools.is_url(d) else d for d in a.definitions or []] or None
    return build(a)


if __name__ == "__main__":
    main()
