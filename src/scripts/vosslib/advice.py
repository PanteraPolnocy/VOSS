"""Short passages of published guidance, in their sources' own words.

advice-by.db    what may be dangerous to a pet (FDA), breaks from a screen (HSE), what a first-aid kit holds
                (nidirect for a home, HSE for a workplace), and when the flu vaccination is given in Europe
                (ECDC). Public domain, the Open Government Licence and CC BY 4.0: sources that ask to be
                named and for nothing more.
firstaid-sa.db  first aid, from Wikipedia. CC BY-SA 4.0, and so in a file of its own.

Neither is a guideline, and no list in them claims to be complete. A passage is printed whole, with the page
it stood on, the day that page says it was last changed, and the credit its licence asks for.
"""
from . import core, library
from .core import more, rec

ADVICE, FIRST_AID = "advice-by", "firstaid-sa"


def passages(stem, topic):
    """(what the file says about itself, [(title, text, page, dated, source)]) for one topic, in the order to
    read them. (None, []) where the file is not installed or cannot be answered from."""
    info = library.have(stem)
    if not info:
        return None, []
    con = library.connect(info["path"])
    try:
        rows = con.execute("SELECT title, text, url, dated, source FROM passage WHERE topic = ? ORDER BY part",
                           (topic,)).fetchall()
    finally:
        con.close()
    return info, rows


def show(stem, topic, key, lead):
    """Print a topic's passages under one record, page by page, each page with its source and its credit.
    Returns False, and prints nothing, where there is nothing on file for the topic."""
    info, rows = passages(stem, topic)
    if not rows:
        return False
    library.warn_if_stale(info, core.today())
    rec(key, lead)
    for n, (title, text, url, dated, source) in enumerate(rows):
        rec("PASSAGE", title)
        print(text)
        last = n + 1 == len(rows) or (rows[n + 1][2], rows[n + 1][4]) != (url, source)
        if last:
            rec("PAGE", "%s%s" % (url, " [the page's own date: %s]" % dated if dated else ""))
            rec("SOURCE", library.tag(info, source))
            credit = library.credit(info, source)
            if credit:
                rec("CREDIT", credit)
    return True


def have(stem, topic):
    """True if something is on file for a topic."""
    return bool(passages(stem, topic)[1])


def missing(stem, what):
    """One line for a command whose file is not there."""
    more("%s.db is not installed, so nothing is on file for %s" % (stem, what))
