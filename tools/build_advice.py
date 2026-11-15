"""Build src/scripts/data/advice-by.db: a few short passages of published guidance, in their sources' own words.

  python tools/build_advice.py --fetch    download the pages and their terms into downloads/, then build
  python tools/build_advice.py            build from what is already in downloads/
  python tools/build_advice.py --show     print every passage as it would be stored, and build nothing

What is in it, and on what terms ("by" stands for attribution: each source asks to be named, and for no more):

  U.S. Food and Drug Administration   "Potentially Dangerous Items for Your Pet". Public domain: the contents
                                      of FDA's website are not copyrighted.
  Health and Safety Executive (GB)    "Work routine and breaks", from its guide to display screen equipment;
                                      and two answers on the first-aid box, from its first aid questions.
                                      Open Government Licence v3.0.
  nidirect (Northern Ireland)         "First aid kits", from its page on first aid. Open Government Licence v3.0.
  ECDC                                "Timing of influenza vaccination". CC BY 4.0.

Each source's terms page is downloaded with it, and the build stops if a page no longer says what was read
there. It also stops if a passage has lost the words it is known by, because then the page has changed shape
and somebody has to look at it again.

What this script changes: HTML becomes plain text (paragraphs, "- " list items), and curly quotes and long
dashes become straight ones. No wording is changed, and a passage is taken whole.
"""
import argparse
import os
import re
import sys

import dbtools
from build_core import plain
from dbtools import DATA, DOWNLOADS, say
from vosslib import core

STEM = "advice-by"
OGL = "Open Government Licence v3.0"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
HSE_CREDIT = ("Contains public sector information published by the Health and Safety Executive and licensed under the "
              "Open Government Licence")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
          "december")

# key: (file, address, the source as it is named, licence, credit, how the page gives its own date)
# in the order their sources are numbered
PAGES = {
    "fda": ("fda-pets.html", "https://www.fda.gov/animal-veterinary/animal-health-literacy/potentially-dangerous-items-your-pet",
            "U.S. Food and Drug Administration: Potentially Dangerous Items for Your Pet",
            "public domain: the contents of FDA's website are not copyrighted. A credit is appreciated, not required",
            "Source: U.S. Food and Drug Administration",
            r"Content current as of:\s*(?P<m>\d{2})/(?P<d>\d{2})/(?P<y>\d{4})"),
    "hse-dse": ("hse-dse-breaks.html", "https://www.hse.gov.uk/msd/dse/work-routine.htm",
                "Health and Safety Executive (Great Britain): Working safely with display screen equipment", OGL, HSE_CREDIT,
                r"Updated:\s*(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"),
    "hse-faq": ("hse-firstaid-faqs.html", "https://www.hse.gov.uk/firstaid/faqs.htm",
                "Health and Safety Executive (Great Britain): First aid at work, frequently asked questions", OGL, HSE_CREDIT,
                r"Updated:\s*(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"),
    "nidirect": ("nidirect-first-aid.html", "https://www.nidirect.gov.uk/articles/first-aid",
                 "nidirect (Northern Ireland Executive): First aid", OGL,
                 "Contains public sector information licensed under the Open Government Licence v3.0. Source: nidirect", None),
    "ecdc": ("ecdc-flu-timing.html", "https://www.ecdc.europa.eu/en/seasonal-influenza/prevention-and-control/vaccines/timing",
             "European Centre for Disease Prevention and Control (ECDC): Timing of influenza vaccination",
             "CC BY 4.0",
             "European Centre for Disease Prevention and Control (ECDC), \"Timing of influenza vaccination\". CC BY 4.0 "
             "(https://creativecommons.org/licenses/by/4.0/). The text is unchanged",
             r"Page last updated\s*(?P<d>\d{1,2}) (?P<month>[A-Za-z]+) (?P<y>\d{4})"),
}
# the terms that were read, each on its own page: (file, address, what the page must still say)
TERMS = (
    ("fda-policies.html", "https://www.fda.gov/about-fda/about-website/website-policies",
     ("are not copyrighted", "they are in the public domain and may be republished, reprinted and otherwise used freely by anyone")),
    ("hse-copyright.html", "https://www.hse.gov.uk/help/copyright.htm",
     ("under the terms of the open government licence",
      "contains public sector information published by the health and safety executive and licensed under the open government licence")),
    ("nidirect-crown-copyright.html", "https://www.nidirect.gov.uk/articles/crown-copyright",
     ("free of charge in any format or medium, under the terms of the open government licence",)),
    ("ecdc-ip-notices.html", "https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices",
     ("are licenced in accordance with the cc by 4.0 licence", "ecdc is always acknowledged as the creator")),
    ("ogl-v3.html", OGL_URL,
     ("copy, publish, distribute and transmit the information", "adapt the information",
      "contains public sector information licensed under the open government licence v3.0",
      "compatible with the creative commons attribution license 4.0")),
)
# topic, page, the title it is stored under, the heading it stands under, where it stops (the next heading, if
# nothing is given), and words it is known by
PASSAGES = (
    ("pets", "fda", "Edible Dangers", r"^Edible Dangers$", None, ("Chocolate", "Xylitol", "Grapes and raisins")),
    ("pets", "fda", "Non-Edible Dangers", r"^Non-Edible Dangers$", None, ("Antifreeze", "Rat and mouse bait")),
    ("pets", "fda", "Plants and Flowers", r"^Plants and Flowers$", None, ("Lilies", "Sago Palm")),
    ("pets", "fda", "Toxicity Can Vary", r"^Toxicity Can Vary$", None, ("How much the animal ate",)),
    ("pets", "fda", "Act Quickly", r"^Act Quickly$", None, ("call your veterinarian",)),
    ("breaks", "hse-dse", "Work routine and breaks", r"Work routine and breaks$", None,
     ("5 to 10 minutes every hour is better than 20 minutes every 2 hours",)),
    ("kit", "nidirect", "First aid kits", r"^First aid kits$", None, ("plasters", "out of reach of children")),
    ("kit", "hse-faq", "What should a first-aid box in the workplace contain?",
     r"^What should a first-aid box in the workplace contain\?$", None, ("sterile eye pads", "This is only a suggested contents list")),
    ("kit", "hse-faq", "How often should the contents of first-aid boxes be replaced?",
     r"^How often should the contents of first-aid boxes be replaced\?$", None, ("expiry dates",)),
    ("flu", "ecdc", "Timing of influenza vaccination", r"^Timing of influenza vaccination$", r"^Page last updated",
     ("10 to 14 days", "early autumn")),
)

LICENCE = """advice-by.db: where its contents come from, and on what terms

Short passages of published guidance, each in its source's own words. Every source here asks to be named
and for nothing more, so the passages may be copied, passed on and used commercially, each with its credit.
None of these bodies endorses this skill, and nothing here has any official standing. The file holds each
page as it stood on the day it was retrieved ('sources' prints the day): the page itself is the current one.

Changed in the making of this file: HTML turned into plain text; curly quotes and long dashes made straight.
No wording was changed, and each passage is whole.

1. What may be dangerous to a pet
   U.S. Food and Drug Administration, "Potentially Dangerous Items for Your Pet".
   https://www.fda.gov/animal-veterinary/animal-health-literacy/potentially-dangerous-items-your-pet
   Public domain. FDA's own words: "Unless otherwise noted, the contents of the FDA website (www.fda.gov) -
   both text and graphics - are not copyrighted. They are in the public domain and may be republished,
   reprinted and otherwise used freely by anyone without the need to obtain permission from FDA. Credit to
   the U.S. Food and Drug Administration as the source is appreciated but not required."
   (https://www.fda.gov/about-fda/about-website/website-policies)
   Credit: Source: U.S. Food and Drug Administration
   The telephone numbers on the page are American and were not taken.

2. Breaks from a screen, and the first-aid box at work
   Health and Safety Executive (Great Britain): "Work routine and breaks", from "Working safely with display
   screen equipment" (https://www.hse.gov.uk/msd/dse/work-routine.htm), and two answers from "First aid at
   work, frequently asked questions" (https://www.hse.gov.uk/firstaid/faqs.htm).
   Crown copyright, under the Open Government Licence v3.0 (https://www.hse.gov.uk/help/copyright.htm).
   Credit, as HSE asks for it: Contains public sector information published by the Health and Safety
   Executive and licensed under the Open Government Licence

3. A first-aid kit for the home
   nidirect (Northern Ireland Executive), "First aid". https://www.nidirect.gov.uk/articles/first-aid
   Crown copyright, under the Open Government Licence v3.0 (https://www.nidirect.gov.uk/articles/crown-copyright).
   Credit: Contains public sector information licensed under the Open Government Licence v3.0. Source: nidirect

4. When the flu vaccination is given
   European Centre for Disease Prevention and Control (ECDC), "Timing of influenza vaccination".
   https://www.ecdc.europa.eu/en/seasonal-influenza/prevention-and-control/vaccines/timing
   CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), as ECDC's notice says of what it publishes
   (https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices). ECDC is the creator; the text is
   unchanged.

The Open Government Licence v3.0: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
It allows copying, publishing, adapting and commercial use, asks for the source to be acknowledged, and
grants no right to suggest official status or endorsement.
"""


def page_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return plain(f.read())
    except OSError:
        sys.exit("%s is not in the downloads folder ('--fetch' gets it)" % os.path.basename(path))


def check_terms(folder):
    """Every terms page must still say what was read there."""
    for name, url, phrases in TERMS:
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError:
            sys.exit("%s is not in the downloads folder ('--fetch' gets it)" % name)
        raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
        text = " ".join(re.sub(r"<[^>]+>", " ", raw).replace("&nbsp;", " ").replace("\u00a0", " ").lower().split())
        text = text.replace(" ,", ",").replace(" ;", ";").replace("\u2014", "-").replace("\u2013", "-")
        for phrase in phrases:
            if phrase not in text:
                sys.exit("%s no longer says \"%s\": read %s again before anything from that source is passed on" % (name, phrase, url))


def cut(lines, start, stop, what):
    """The text under a heading: from the first heading that matches to the next heading, or to the first line
    that matches 'stop'."""
    begin = next((n + 1 for n, line in enumerate(lines) if line.startswith("## ") and re.search(start, line[3:])), None)
    if begin is None:
        sys.exit("%s: its heading is not on the page any more. The page has changed: read it again" % what)
    out = []
    for line in lines[begin:]:
        if line.startswith("## ") or (stop and re.search(stop, line)):
            break
        out.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    if not text:
        sys.exit("%s: nothing stands under its heading any more. The page has changed: read it again" % what)
    return text


def page_date(text, pattern):
    """The day a page says it was last changed, as YYYY-MM-DD, or '' where it does not say."""
    m = re.search(pattern, text) if pattern else None
    if not m:
        return ""
    parts = m.groupdict()
    month = parts.get("m") or (MONTHS.index(parts["month"].lower()) + 1 if parts.get("month", "").lower() in MONTHS else 0)
    try:
        return "%04d-%02d-%02d" % (int(parts["y"]), int(month), int(parts["d"]))
    except (TypeError, ValueError):
        return ""


def read_passages(folder):
    """[(topic, page key, title, text, the page's own date)], in the order they are stored."""
    texts, out = {}, []
    for topic, page, title, start, stop, known in PASSAGES:
        if page not in texts:
            texts[page] = page_text(os.path.join(folder, PAGES[page][0]))
        text = cut(texts[page].split("\n"), start, stop, "%s, \"%s\"" % (PAGES[page][0], title))
        for words in known:
            if words not in text:
                sys.exit("%s, \"%s\": the passage no longer holds \"%s\". The page has changed: read it again, and put this "
                         "script right" % (PAGES[page][0], title, words))
        if "\ufffd" in text:
            sys.exit("%s, \"%s\": the passage holds a character that could not be read" % (PAGES[page][0], title))
        out.append((topic, page, title, text, page_date(texts[page], PAGES[page][5])))
    return out


def fetch_all(folder):
    os.makedirs(folder, exist_ok=True)
    for name, url, _ in TERMS:
        dbtools.fetch(url, name, "text/html", folder=folder)
    for key in PAGES:
        dbtools.fetch(PAGES[key][1], PAGES[key][0], "text/html", folder=folder)


def build(a):
    out_folder = a.out or DATA
    if not os.path.isdir(out_folder):
        sys.exit("--out must be a folder that exists")
    check_terms(a.downloads)
    found = read_passages(a.downloads)
    if a.show:
        for topic, page, title, text, dated in found:
            print("=== %s | %s | %s%s\n%s\n" % (topic, PAGES[page][2], title, " | page dated %s" % dated if dated else "", text))
        return None
    days = dict((key, dbtools.origin(os.path.join(a.downloads, PAGES[key][0]), retrieved=a.retrieved)[1]) for key in PAGES)
    path = os.path.join(out_folder, STEM + ".db")
    con = dbtools.create(path)
    try:
        sources = {}
        for key in PAGES:
            name, url, source, licence, credit, _ = PAGES[key]
            sources[key] = dbtools.add_source(con, source, url, days[key], licence, credit)
        con.execute("CREATE TABLE passage (id INTEGER PRIMARY KEY, topic TEXT NOT NULL, part INTEGER NOT NULL, title TEXT NOT NULL, "
                    "text TEXT NOT NULL, url TEXT NOT NULL, dated TEXT NOT NULL, source INTEGER NOT NULL)")
        for part, (topic, page, title, text, dated) in enumerate(found, 1):
            con.execute("INSERT INTO passage (topic, part, title, text, url, dated, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (topic, part, title, text, PAGES[page][1], dated, sources[page]))
        con.execute("CREATE INDEX passage_topic ON passage (topic, part)")
        import vosslib
        size = dbtools.finish(con, path, core.today(), facts=(("format", 1), ("toolkit", vosslib.VERSION), ("passages", len(found))))
    except BaseException:
        dbtools.discard(con, path)
        raise
    dbtools.write_licence(STEM, LICENCE, out_folder)
    say("built     %s: %s" % (path, dbtools.size_words(size)))
    say("          %d passages on %s" % (len(found), ", ".join(sorted(set(t for t, _, _, _, _ in found)))))
    say("          retrieved: %s" % ", ".join("%s %s" % (key, days[key]) for key in sorted(days)))
    say("next      python tools/build.py   (it checks the file, its licence text and SOURCES.md, and packs the skill)")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download the pages and their terms into the downloads folder first")
    ap.add_argument("--downloads", default=DOWNLOADS, help="where the downloads are kept (default: downloads/, which git ignores)")
    ap.add_argument("--retrieved", metavar="DATE", help="the day the pages were downloaded, for pages saved by hand")
    ap.add_argument("--show", action="store_true", help="print every passage as it would be stored, and build nothing")
    ap.add_argument("--out", metavar="DIR", help="where to write advice-by.db and its licence text (default: src/scripts/data)")
    a = ap.parse_args(argv)
    if a.fetch:
        fetch_all(a.downloads)
    return build(a)


if __name__ == "__main__":
    main()
