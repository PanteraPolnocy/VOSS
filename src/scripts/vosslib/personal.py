"""The personal file: where it lives, what shape it has, and what never goes into it.

One JSON file holds everything Voss was told about the people he looks after. It is read from the path in
the VOSS_PERSONAL environment variable if that is set (so it can live outside the skill and survive
updates), else from scripts/data/personal.json. No file means no patients: general mode.

Nothing in this module prints a value from the file. A problem is reported by where it is, never by what
was written there.
"""
import difflib
import json
import os
import re

from . import core
from .core import DATA, VossError, die, load_data

FILE = "scripts/data/personal.json"
VERSION = 3
DECLINED = "declined"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
HOUSEHOLD_LISTS = ("pets", "cabinet", "kits")
ENTRY_KEYS = ("id", "created", "updated")
DEPENDANT_KEYS = ("carer", "consent")
YES_NO = ("yes", "no", "unknown")
ABOUT = ("Voss personal file. PRIVATE: it holds health information, in plain JSON, and belongs in the private package "
         "only. Never commit it and never put it on a shared drive. Every field is optional; \"declined\" means "
         "prefer not to say. No national ID, insurance, card or bank numbers, and no passwords. "
         "See references/personal-file.md.")

_loaded = {}


def path():
    return os.environ.get("VOSS_PERSONAL") or os.path.join(DATA, "personal.json")


def outside():
    """True when the file is kept outside the skill, at the path VOSS_PERSONAL names."""
    return bool(os.environ.get("VOSS_PERSONAL"))


def reset():
    _loaded.clear()


def load():
    """The personal file as a dict, or None where there is none. A broken file is an error, never a silent empty."""
    p = path()
    if _loaded.get("path") == p:
        return _loaded["data"]
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        data = None         # no file yet, wherever it is meant to live: that is general mode, not a fault
    except OSError:
        die("the personal file cannot be read")
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            die("the personal file is not UTF-8 text: nothing from it was used")
        except ValueError as e:
            where = "line %d, column %d" % (e.lineno, e.colno) if hasattr(e, "lineno") else "somewhere in it"
            die("the personal file is not valid JSON (%s): nothing from it was used. A comma or a quote is the usual culprit" % where)
        if not isinstance(data, dict):
            die("the personal file must be one JSON object: nothing from it was used")
    _loaded.update(path=p, data=data)
    return data


def need():
    data = load()
    if data is None:
        die("there is no personal file here, so nothing is on file: answer in general mode. "
            "'intake --id self --new' starts a file when someone asks for one")
    return data


def blank():
    return {"_about": ABOUT, "version": VERSION, "profiles": [], "pets": [], "cabinet": [], "kits": [], "dependants": []}


def entries(data):
    """Every person on file: [('profile' or 'dependant', their entry)]."""
    out = []
    for kind, key in (("profile", "profiles"), ("dependant", "dependants")):
        rows = data.get(key) if isinstance(data, dict) else None
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]:
                out.append((kind, row))
    return out


def ids(data, kind=None):
    return [e["id"] for k, e in entries(data) if kind is None or k == kind]


def pick(data, pid):
    """The entry with that id; with no id, the only profile on file."""
    people = entries(data)
    if pid is None:
        own = [(k, e) for k, e in people if k == "profile"]
        if len(own) == 1:
            return own[0]
        if not own:
            die("no profile is on file yet: 'intake --id self --new' starts one")
        die("say whose file: --id is one of %s" % ", ".join(e["id"] for _, e in people))
    for kind, entry in people:
        if entry["id"] == pid:
            return kind, entry
    die("no profile with that id is on file%s" % (": on file are %s" % ", ".join(ids(data)) if people else ""))


# ---- the field list

def schema():
    return load_data("fields")


def fields():
    return schema()["fields"]


def household(name=None):
    """The lists a household keeps in common (pets, cabinet, kits), as the field list describes them: all of
    them by name, or one."""
    specs = dict((h["name"], h) for h in schema()["household"] if h.get("keys"))
    return specs if name is None else specs[name]


def field(name):
    for spec in fields() + list(household().values()):
        if spec["name"] == name:
            return spec
    near = difflib.get_close_matches(str(name), [f["name"] for f in fields()], n=1, cutoff=0.6)
    die("that is not a field of the personal file%s ('intake --fields' lists them)" % (": did you mean %s?" % near[0] if near else ""))


def blankish(value):
    """True for a value that holds nothing: empty text, null, false, or a list or object of only such."""
    if value is None or value == "" or value is False:
        return True
    if isinstance(value, dict):
        return all(blankish(v) for v in value.values())
    if isinstance(value, list):
        return all(blankish(v) for v in value)
    return False


def answered(entry, name):
    """True once a field holds something, or was declined."""
    return not blankish(entry.get(name))


def rows(entry, name):
    """The entries of a list field that hold something. The template's empty rows do not count."""
    value = entry.get(name)
    return [r for r in value if not blankish(r)] if isinstance(value, list) else []


# ---- what is never stored

_CARD_RE = re.compile(r"(?<![\d+])\d(?:[ -]?\d){12,18}(?!\d)")
_ELEVEN_RE = re.compile(r"(?<![\d+-])\d{11}(?![\d-])")
_TEN_RE = re.compile(r"(?<![\d+-])\d{3}[ -]?\d{3}[ -]?\d{4}(?![\d-])")
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b", re.I)
_SECRET_RE = re.compile(
    r"\b(pesel|nhs\s*(?:no|number)|national insurance|social security|ssn|passport|id card|identity card|"
    r"insurance (?:no|number)|policy (?:no|number)|iban|account (?:no|number)|card (?:no|number)|password|passcode|pin code)\b"
    r"[^\n]{0,25}?\b(?=[a-z-]*\d)[a-z0-9-]{6,}", re.I)
# dates and clock times are full of digits and are nobody's card number
_DATEISH_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}:\d{2}")


def _luhn(digits):
    total = 0
    for n, ch in enumerate(reversed(digits)):
        d = int(ch)
        if n % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _pesel(digits):
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    if (10 - sum(w * int(d) for w, d in zip(weights, digits)) % 10) % 10 != int(digits[10]):
        return False
    month, day = int(digits[2:4]) % 20, int(digits[4:6])
    return 1 <= month <= 12 and 1 <= day <= 31


def _nhs(digits):
    check = 11 - sum((10 - n) * int(d) for n, d in enumerate(digits[:9])) % 11
    return check != 10 and (0 if check == 11 else check) == int(digits[9])


def _iban(text):
    t = text.replace(" ", "").upper()
    moved = t[4:] + t[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def never_stored(text, kind="text"):
    """What kind of forbidden number this text holds, or None.

    Identity, insurance, card and bank numbers and passwords are never kept. This is a net, not a promise: it
    knows the common shapes and their check digits, and Voss still refuses the rest himself. A field meant
    for a contact or a phone number is spared the ten- and eleven-digit checks, which a phone number can pass."""
    t = str(text)
    if _SECRET_RE.search(t):
        return "an identity, insurance, bank or password detail"
    if _SSN_RE.search(t):
        return "a social security number"
    for m in _IBAN_RE.finditer(t):
        if _iban(m.group(0)):
            return "a bank account number"
    plain = _DATEISH_RE.sub(" / ", t)
    for m in _CARD_RE.finditer(plain):
        if _luhn(re.sub(r"\D", "", m.group(0))):
            return "a payment card number"
    if kind == "text":
        for m in _ELEVEN_RE.finditer(plain):
            if _pesel(m.group(0)):
                return "a national identity number"
        for m in _TEN_RE.finditer(plain):
            if _nhs(re.sub(r"\D", "", m.group(0))):
                return "a health service number"
    return None


# ---- dates as people give them

def part_date(text):
    """A year, a year and month, or a full date, tidied to YYYY, YYYY-MM or YYYY-MM-DD; None if it is none of those."""
    t = str(text).strip()
    if re.fullmatch(r"\d{4}", t):
        return t if 1850 <= int(t) <= 2200 else None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m:
        return "%s-%02d" % (m.group(1), int(m.group(2))) if 1850 <= int(m.group(1)) <= 2200 and 1 <= int(m.group(2)) <= 12 else None
    day = core.parse_date(t)
    return day.isoformat() if day and 1850 <= day.year <= 2200 else None


def when_text(text):
    """A date, or a date and a time, tidied to 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'; None if it is neither."""
    parts = str(text).strip().replace("T", " ", 1).split()
    if not 1 <= len(parts) <= 2:
        return None
    day = core.parse_date(parts[0])
    if day is None:
        return None
    if len(parts) == 1:
        return day.isoformat()
    try:
        hour, minute = core.parse_clock(parts[1])
    except VossError:
        return None
    return "%s %02d:%02d" % (day.isoformat(), hour, minute)


# ---- one pass over a whole file

def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_key(kind, value, where, out):
    if isinstance(kind, dict):
        if not isinstance(value, dict):
            out.append(("FIX", where, "must be an object with %s" % ", ".join(kind)))
            return
        for key, inner in value.items():
            if key not in kind:
                out.append(("CHECK", "%s.%s" % (where, key), "not a key Voss reads; it is ignored"))
            else:
                _check_key(kind[key], inner, "%s.%s" % (where, key), out)
        return
    if value is None or value == "":
        return
    if kind in ("text", "contact", "phone"):
        if not isinstance(value, str):
            out.append(("FIX", where, "must be text"))
        elif len(value) > core.MAX_TEXT:
            out.append(("FIX", where, "is longer than %d characters" % core.MAX_TEXT))
        else:
            bad = never_stored(value, kind)
            if bad:
                out.append(("FIX", where, "holds what looks like %s: Voss does not keep those. Take it out" % bad))
    elif kind == "number":
        if not _is_num(value):
            out.append(("FIX", where, "must be a number, or null"))
    elif kind == "date":
        if not (isinstance(value, str) and core.parse_date(value)):
            out.append(("FIX", where, "must be a date, YYYY-MM-DD, or empty"))
    elif kind == "partdate":
        if not (isinstance(value, str) and part_date(value)):
            out.append(("FIX", where, "must be a year, a year and month, or a date (2019, 2019-03, 2019-03-14), or empty"))
    elif kind == "when":
        if not (isinstance(value, str) and when_text(value)):
            out.append(("FIX", where, "must be a date, with or without a time (2026-12-01 or 2026-12-01 10:30), or empty"))
    elif kind == "bool":
        if not isinstance(value, bool):
            out.append(("FIX", where, "must be true or false"))
    elif kind == "yes_no_unknown":
        if value not in YES_NO:
            out.append(("FIX", where, "must be yes, no or unknown, or empty"))
    elif kind == "texts":
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            out.append(("FIX", where, "must be a list of texts"))
        else:
            for n, item in enumerate(value, 1):
                bad = never_stored(item)
                if bad:
                    out.append(("FIX", "%s.%d" % (where, n), "holds what looks like %s: Voss does not keep those. Take it out" % bad))
    elif kind == "doses":
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            out.append(("FIX", where, "must be a list of dose lines, such as [\"08:00\", \"20:00\"]"))
        else:
            from . import doses
            try:
                doses.parse_doses([x for x in value if x.strip()], "the schedule")
            except VossError as e:
                out.append(("FIX", where, str(e)))


def _check_gate(block, where, out):
    from . import gate
    if not isinstance(block, dict):
        out.append(("FIX", where, "must be an object: {\"setting\": ..., \"questions\": [...]}"))
        return
    setting = str(block.get("setting") or "").strip().lower()
    good = 0
    questions = block.get("questions") or []
    if not isinstance(questions, list):
        out.append(("FIX", where + ".questions", "must be a list"))
        questions = []
    for n, q in enumerate(questions, 1):
        answers = q.get("a") if isinstance(q, dict) else None
        if isinstance(answers, str):
            answers = [answers]
        if not (isinstance(q, dict) and isinstance(q.get("q"), str) and q["q"].strip() and isinstance(answers, list)
                and answers and all(isinstance(x, str) and x.strip() for x in answers)):
            out.append(("FIX", "%s.questions.%d" % (where, n), "needs \"q\" (the question) and \"a\" (a list of accepted answers)"))
        else:
            good += 1
    if setting and setting not in gate.SETTINGS:
        near = difflib.get_close_matches(setting, gate.SETTINGS, n=1, cutoff=0.4)
        out.append(("FIX", where + ".setting", "must be one of: %s%s" % (
            "; ".join(gate.SETTINGS), " (did you mean '%s'?)" % near[0] if near else "")))
    for key in block:
        if key not in ("setting", "questions"):
            out.append(("CHECK", "%s.%s" % (where, key), "not a part of the gate Voss reads; it is ignored"))
    if setting == "off" and good:
        out.append(("CHECK", where, "questions are on file but the gate is switched off, so anyone with the package can ask about this file"))
    elif 0 < good < 3:
        out.append(("CHECK", where, "%s on file: three are asked before the file stays shut, so add more" % core.plural(good, "question")))


def _check_entry(kind, entry, where, known, out, today):
    allowed = set(known) | set(ENTRY_KEYS) | (set(DEPENDANT_KEYS) if kind == "dependant" else set())
    for key, value in entry.items():
        here = "%s.%s" % (where, key)
        if key not in allowed:
            near = difflib.get_close_matches(key, sorted(allowed), n=1, cutoff=0.7)
            out.append(("CHECK", here, "not a field Voss reads%s; it is ignored" % (": did you mean %s?" % near[0] if near else "")))
            continue
        if key in ENTRY_KEYS or key in DEPENDANT_KEYS or value == DECLINED:
            continue
        spec = known[key]
        t = spec["type"]
        if t == "text":
            _check_key("text", value, here, out)
        elif t == "reference":
            if value not in ("", None, "human"):
                out.append(("FIX", here, "for any real person the medical reference is human: the data is human medicine"))
        elif t == "born":
            if value not in ("", None):
                tidy = part_date(value) if isinstance(value, str) else None
                if not tidy or len(tidy) == 7:
                    out.append(("FIX", here, "must be a full date (YYYY-MM-DD) or a year, or empty"))
                elif tidy[:4] > str(today.year) or (len(tidy) == 10 and tidy > today.isoformat()):
                    out.append(("FIX", here, "is in the future"))
        elif t == "country":
            if value not in ("", None) and not (isinstance(value, str) and re.fullmatch(r"[A-Za-z]{2}", value)):
                out.append(("FIX", here, "must be a two-letter country code such as PL or GB, or empty"))
        elif t == "choice":
            if value not in ("", None) and value not in spec["choices"]:
                out.append(("FIX", here, "must be one of %s, or \"declined\", or empty" % ", ".join(spec["choices"])))
        elif t == "texts":
            _check_key("texts", value, here, out)
        elif t == "object":
            _check_key(spec["keys"], value, here, out)
        elif t in ("objects", "records"):
            if not isinstance(value, list):
                out.append(("FIX", here, "must be a list"))
            else:
                for n, row in enumerate(value, 1):
                    _check_key(spec["keys"], row, "%s.%d" % (here, n), out)
        elif t == "gate":
            _check_gate(value, here, out)


def check(data, today):
    """Every problem in a personal file, in one pass: [(FIX or CHECK, where, what to do)]."""
    out = []
    if not isinstance(data, dict):
        return [("FIX", "file", "the file must be one JSON object: { ... }")]
    if data.get("version") != VERSION:
        out.append(("CHECK", "version", "this toolkit reads version %d of the file" % VERSION))
    known = dict((f["name"], f) for f in fields())
    top = ("_about", "version", "profiles", "dependants") + HOUSEHOLD_LISTS
    for key in data:
        if key not in top:
            out.append(("CHECK", key, "not a part of the file Voss reads; it is ignored"))
    seen = set()
    for kind, key in (("profile", "profiles"), ("dependant", "dependants")):
        rows_ = data.get(key)
        if rows_ is None:
            continue
        if not isinstance(rows_, list):
            out.append(("FIX", key, "must be a list"))
            continue
        for n, entry in enumerate(rows_, 1):
            where = "%s.%d" % (key, n)
            if not isinstance(entry, dict):
                out.append(("FIX", where, "must be an object"))
                continue
            pid = entry.get("id")
            if not (isinstance(pid, str) and ID_RE.match(pid)):
                out.append(("FIX", where + ".id", "needs an id: a short handle in lower-case letters, digits and hyphens"))
            elif pid in seen:
                out.append(("FIX", where + ".id", "is used twice: every profile and dependant needs its own id"))
            else:
                seen.add(pid)
                where = "%s.%s" % (key, pid)
            if kind == "dependant":
                carers = [p.get("id") for p in data.get("profiles") or [] if isinstance(p, dict)]
                if entry.get("carer") not in carers:
                    out.append(("FIX", where + ".carer", "must name the profile, by id, of the person who looks after them"))
                if blankish(entry.get("consent")):
                    out.append(("CHECK", where + ".consent", "nothing is recorded about consent: theirs, wherever they can give it"))
            _check_entry(kind, entry, where, known, out, today)
    for key in HOUSEHOLD_LISTS:
        value = data.get(key)
        if value is None:
            continue
        if not (isinstance(value, list) and all(isinstance(r, dict) for r in value)):
            out.append(("FIX", key, "must be a list of objects"))
            continue
        keys = household(key)["keys"]
        for n, row in enumerate(value, 1):
            where = "%s.%d" % (key, n)
            plain = dict((k, v) for k, v in keys.items() if not isinstance(v, dict))
            _check_key(plain, dict((k, v) for k, v in row.items() if k in plain or k not in keys), where, out)
            # a kit holds a list of things, each with its own expiry
            for inner, shape in keys.items():
                if isinstance(shape, dict) and row.get(inner) is not None:
                    if not (isinstance(row[inner], list) and all(isinstance(x, dict) for x in row[inner])):
                        out.append(("FIX", "%s.%s" % (where, inner), "must be a list of objects"))
                    else:
                        for m, item in enumerate(row[inner], 1):
                            _check_key(shape, item, "%s.%s.%d" % (where, inner, m), out)
    for n, row in enumerate(data.get("cabinet") or [], 1):
        if isinstance(row, dict) and not blankish(row) and row.get("belongs_to") not in seen and row.get("belongs_to") not in ("", None):
            out.append(("CHECK", "cabinet.%d.belongs_to" % n, "names no profile on file"))
    return out


def dump(data):
    """The file as text: readable JSON, and it must read back as the same thing."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if json.loads(text) != data:
        die("internal error: the personal file would not read back the same; nothing was written")
    return text
