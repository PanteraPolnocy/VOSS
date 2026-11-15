"""What is on file for a person, and how it gets there.

profile  reads a file back. Whether its gate is open is for Voss to know: 'ignition' judges the answer,
         and he does not read a file aloud before then.
intake   says what to ask next, a question or two at a time, and reads back what would be stored.
         It never writes. 'rebuild' does, and only with the code this read-back printed, so nothing is
         saved that was not read back first.

Changes are written as  field=value  for a plain field, and  "field: key=value; key=value"  for one with
parts. --add puts an entry in a list (allergies, medicines); --set fills or replaces a field.
"""
import hashlib
import json
import re
from datetime import date, timedelta

from . import core, gate, personal
from .core import command, die, fold, more, rec

PREGNANCY_DAYS = 30
_HEAD_RE = re.compile(r"^\s*([a-z_]+)\s*([=:])(.*)$", re.S)
_KEY_RE = re.compile(r"^[a-z_]+(\.[a-z_]+)?$")
_PHONE_RE = re.compile(r"^\+?[\d ()\-]{5,24}$")
_TRUE, _FALSE = ("yes", "true", "on", "1"), ("no", "false", "off", "0")
CHANGE_HELP = "a change is  field=value  or  \"field: key=value; key=value\"  ('intake --fields' lists the fields and their parts)"


# ---- reading a file back

def _show_key(kind, value):
    if isinstance(kind, dict):
        parts = ["%s %s" % (k, _show_key(kind[k], v)) for k, v in value.items() if k in kind and not personal.blankish(v)]
        return ", ".join(parts)
    if isinstance(value, list):
        return " | ".join(str(v) for v in value if str(v).strip())
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _show_object(keys, value):
    return "; ".join("%s %s" % (k, _show_key(keys[k], v)) for k, v in value.items() if k in keys and not personal.blankish(v))


def show_field(spec, entry, today):
    """The lines for one field of one entry, or [] if nothing is on file for it."""
    name, t = spec["name"], spec["type"]
    value = entry.get(name)
    if value == personal.DECLINED:
        return ["declined (not asked again)"]
    if t == "gate" or personal.blankish(value):
        return []
    if t == "born":
        return ["%s; %s" % (value, age_words(value, today))]
    if t == "reference":
        return ["%s [the data is human medicine: where the difference could matter, say so once]" % value]
    if t == "object" and isinstance(value, dict):
        return [_show_object(spec["keys"], value)]
    if t in ("objects", "records") and isinstance(value, list):
        return [_show_object(spec["keys"], row) for row in value if isinstance(row, dict) and not personal.blankish(row)]
    if isinstance(value, list):
        return [", ".join(str(v) for v in value if str(v).strip())]
    return [str(value)]


def age_words(born, today):
    """Age worked out from what is on file. A year alone leaves a year's doubt, and this says so."""
    text = str(born)
    if len(text) == 4 and text.isdigit():
        late = today.year - int(text)
        return "aged %d or %d [derived: only the year is on file]" % (max(late - 1, 0), late)
    day = core.parse_date(text)
    if day is None or day > today:
        return "age not worked out: the date on file cannot be read"
    years = core.whole_years(day, today)
    if years >= 2:
        return "aged %d [derived, today %s]" % (years, today.isoformat())
    months = (today.year - day.year) * 12 + today.month - day.month - (1 if today.day < day.day else 0)
    return "aged %s [derived, today %s]" % (core.plural(months, "month"), today.isoformat())


def _end_of(part):
    """The last day a part-date could mean: 2026 is 31 December, 2026-03 is 31 March."""
    text = personal.part_date(part or "")
    if not text:
        return None
    if len(text) == 4:
        return date(int(text), 12, 31)
    if len(text) == 7:
        first = date(int(text[:4]), int(text[5:7]), 1)
        return core.add_months(first, 1) - timedelta(days=1)
    return core.parse_date(text)


def stale_notes(entry, today):
    """Dated things on file that have gone stale. They are asked again when they next matter, never dropped."""
    notes = []
    # only what carries a date of its own goes stale. A weight has none, and an old profile is never flagged as
    # a whole: the day it was last changed is shown, and that is all
    for name in ("pregnancy", "breastfeeding"):
        block = entry.get(name)
        if isinstance(block, dict) and str(block.get("status") or "").strip():
            day = core.parse_date(block.get("recorded") or "")
            if day is None or (today - day).days > PREGNANCY_DAYS:
                notes.append("%s: recorded more than %d days ago, so it has expired. Ask again when it matters" % (name, PREGNANCY_DAYS))
    old = 0
    for row in personal.rows(entry, "medicines"):
        day = core.parse_date(row.get("told") or "") if isinstance(row, dict) else None
        if day and core.add_months(day, 12) < today:
            old += 1
    if old:
        notes.append("medicines: %s told over a year ago. Ask whether %s" % (
            core.plural(old, "entry was", "entries were"), "it still stands" if old == 1 else "they still stand"))
    past = 0
    for row in personal.rows(entry, "recent_travel"):
        day = _end_of(row.get("to") or row.get("from")) if isinstance(row, dict) else None
        if day and core.add_months(day, 3) < today:
            past += 1
    if past:
        notes.append("recent_travel: %s over three months ago. Ask again when a symptom makes travel matter" % (
            core.plural(past, "trip ended", "trips ended")))
    return notes


def _print_fields(entry, names, today):
    shown = 0
    for name in names:
        spec = personal.field(name)
        lines = show_field(spec, entry, today)
        if not lines:
            continue
        rec(name, lines[0])
        for line in lines[1:]:
            more(line)
        shown += 1
    return shown


def cmd_profile(a):
    data = personal.need()
    kind, entry = personal.pick(data, a.id)
    today = core.today()
    schema = personal.schema()
    if a.field:
        spec = personal.field(a.field)
        if spec["type"] == "gate":
            die("the gate's questions and answers are never shown: 'ignition' says how many are on file")
        if spec["type"] == "household":
            die("%s is a list the household keeps in common, with a command of its own: cabinet, kit or pet" % spec["name"])
        if not _print_fields(entry, [spec["name"]], today):
            rec(spec["name"], "nothing on file")
        return
    sections = dict(schema["sections"])
    if a.section and a.section not in sections:
        die("--section is one of: %s" % ", ".join(k for k, _ in schema["sections"]))
    rec("PROFILE", "%s [%s]%s%s" % (
        entry["id"], kind,
        "; on file since %s" % entry["created"] if entry.get("created") else "",
        ", last changed %s" % entry["updated"] if entry.get("updated") else ""))
    if kind == "dependant":
        consent = entry.get("consent") if isinstance(entry.get("consent"), dict) else {}
        more("in the care of %s; consent: %s" % (entry.get("carer") or "nobody on file", _show_object(
            {"note": "text", "recorded": "date"}, consent) or "nothing recorded"))
    total = 0
    for key, title in schema["sections"]:
        if a.section and a.section != key:
            continue
        names = [f["name"] for f in schema["fields"] if f["section"] == key and f["type"] != "gate"]
        if not any(show_field(personal.field(n), entry, today) for n in names):
            continue
        print(title.upper())
        total += _print_fields(entry, names, today)
    if not total:
        rec("NOTHING", "nothing is on file%s" % (" in that section" if a.section else " yet"))
    for note in stale_notes(entry, today):
        rec("STALE", note)
    rec("GATE", gate.state_line(data, kind, entry) + "; questions and answers are never shown")
    rec("RULE", "this is what the person told Voss, as they said it, on the dates shown. Nothing here is a diagnosis")


# ---- changes

def parse_change(text, verb):
    """'field=value' or 'field: key=value; key=value' as (field name, text or a dict of parts)."""
    m = _HEAD_RE.match(str(text))
    if not m:
        die("--%s was not understood: %s" % (verb, CHANGE_HELP))
    name, sep, body = m.group(1), m.group(2), m.group(3)
    if sep == "=":
        return name, body.strip()
    pairs = {}
    for part in body.split(";"):
        if not part.strip():
            continue
        key, eq, value = part.partition("=")
        key = key.strip().lower()
        if not eq or not _KEY_RE.match(key):
            die("--%s %s: each part is key=value, and parts are separated by ';'" % (verb, name))
        if key in pairs:
            die("--%s %s: the part '%s' is given twice" % (verb, name, key))
        pairs[key] = value.strip()
    if not pairs:
        die("--%s %s: no parts were given. %s" % (verb, name, CHANGE_HELP))
    return name, pairs


def _refuse(where, bad):
    die("%s looks like %s. Voss does not keep those: nothing was stored. Say so, and carry on without it" % (where, bad))


def coerce(kind, text, where, today):
    """Text from the command line as the value to store. An error names the place and never repeats the text."""
    if kind in ("text", "contact", "phone"):
        value = core.one_line(text, where)
        bad = personal.never_stored(value, kind)
        if bad:
            _refuse(where, bad)
        if kind == "phone" and not _PHONE_RE.match(value):
            die("%s must be a phone number: digits, spaces and + ( ) - only" % where)
        return value
    if kind == "number":
        number = core.decimal_of(text, where)
        return int(number) if number == number.to_integral_value() else float(number)
    if kind == "date":
        day = core.a_date(text, where, today)
        if day > today:
            die("%s is in the future" % where)
        return day.isoformat()
    if kind == "partdate":
        tidy = personal.part_date(text)
        if not tidy:
            die("%s must be a year, a year and month, or a date: 2019, 2019-03 or 2019-03-14" % where)
        return tidy
    if kind == "when":
        tidy = personal.when_text(text)
        if not tidy:
            die("%s must be a date, with or without a time: 2026-12-01 or '2026-12-01 10:30'" % where)
        return tidy
    if kind == "bool":
        low = str(text).strip().lower()
        if low not in _TRUE + _FALSE:
            die("%s must be yes or no" % where)
        return low in _TRUE
    if kind == "yes_no_unknown":
        low = str(text).strip().lower()
        if low not in personal.YES_NO:
            die("%s must be yes, no or unknown" % where)
        return low
    if kind == "texts":
        items = [core.one_line(x, where, 200) for x in str(text).split("|") if x.strip()]
        if not items:
            die("%s is empty" % where)
        for item in items:
            bad = personal.never_stored(item)
            if bad:
                _refuse(where, bad)
        return items
    if kind == "doses":
        from . import doses
        lines = [" ".join(x.lower().split()) for x in str(text).split("|") if x.strip()]
        doses.parse_doses(lines, where)
        return lines
    die("internal error: no way to read %s" % where)


def _empty(kind):
    if isinstance(kind, dict):
        return dict((k, _empty(v)) for k, v in kind.items())
    return {"number": None, "bool": False, "texts": [], "doses": []}.get(kind, "")


def _fill(spec, pairs, base, where, today):
    """An object's parts, read from 'key=value' pairs on top of what is there. Returns (object, words for reading back)."""
    keys = spec["keys"]
    out = json.loads(json.dumps(base)) if isinstance(base, dict) else {}
    for key, kind in keys.items():
        out.setdefault(key, _empty(kind))
    said = []
    for dotted, text in pairs.items():
        head, _, tail = dotted.partition(".")
        if head not in keys or (tail and not (isinstance(keys[head], dict) and tail in keys[head])) or (
                not tail and isinstance(keys[head], dict)):
            names = []
            for k, v in keys.items():
                names += ["%s.%s" % (k, k2) for k2 in v] if isinstance(v, dict) else [k]
            die("%s has no part '%s': its parts are %s" % (where, dotted, ", ".join(names)))
        if tail:
            if not isinstance(out.get(head), dict):
                out[head] = _empty(keys[head])
            out[head][tail] = coerce(keys[head][tail], text, "%s.%s" % (where, dotted), today)
            said.append("%s %s" % (dotted, _show_key(keys[head][tail], out[head][tail])))
        else:
            out[head] = coerce(keys[head], text, "%s.%s" % (where, head), today)
            said.append("%s %s" % (head, _show_key(keys[head], out[head])))
    stamp = spec.get("stamp")
    if stamp and stamp not in pairs:
        out[stamp] = today.isoformat()
        said.append("%s %s" % (stamp, out[stamp]))
    return out, "; ".join(said)


def _set(entry, spec, value, today):
    name, t = spec["name"], spec["type"]
    where = "--set %s" % name
    if t in ("gate", "records", "household"):
        die("%s is not set this way: %s" % (name, "the person types their own gate questions into the file" if t == "gate"
                                             else "it is a list, and --add puts an entry in it"))
    if t == "objects":
        die("%s is a list: put an entry in with --add \"%s: ...\"" % (name, name))
    if t == "object":
        if not isinstance(value, dict):
            die("%s has parts: write it as  \"%s: %s\"" % (name, name, "; ".join("%s=..." % k for k in _flat(spec["keys"]))))
        entry[name], said = _fill(spec, value, entry.get(name), where, today)
        return "SET", "%s: %s" % (name, said)
    if isinstance(value, dict):
        die("%s is a single value: write it as  %s=..." % (name, name))
    if t == "text":
        entry[name] = coerce("text", value, where, today)
    elif t == "reference":
        if value.strip().lower() != "human":
            die("for any real person the medical reference is human: every source Voss has was written for human bodies. "
                "The species field is where someone is who they are")
        entry[name] = "human"
    elif t == "born":
        tidy = personal.part_date(value)
        if not tidy or len(tidy) == 7:
            die("%s must be a full date (YYYY-MM-DD) or a year alone" % where)
        if tidy[:4] > str(today.year) or (len(tidy) == 10 and tidy > today.isoformat()):
            die("%s is in the future" % where)
        entry[name] = tidy
    elif t == "country":
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            die("%s must be a two-letter country code, such as DE or GB" % where)
        entry[name] = code
    elif t == "choice":
        low = value.strip().lower()
        if low not in spec["choices"]:
            die("%s must be one of: %s (or use --decline %s)" % (where, ", ".join(spec["choices"]), name))
        entry[name] = low
    elif t == "texts":
        entry[name] = coerce("texts", value, where, today)
    return "SET", "%s: %s" % (name, _show_key(t, entry[name]))


def _flat(keys):
    out = []
    for k, v in keys.items():
        out += ["%s.%s" % (k, k2) for k2 in v] if isinstance(v, dict) else [k]
    return out


def _add(entry, spec, value, today):
    name, t = spec["name"], spec["type"]
    where = "--add %s" % name
    if t == "texts":
        if isinstance(value, dict):
            die("%s is a list of plain entries: write it as  %s=..." % (name, name))
        have = [x for x in (entry.get(name) or []) if isinstance(x, str) and x.strip()] if isinstance(entry.get(name), list) else []
        new = [x for x in coerce("texts", value, where, today) if fold(x) not in [fold(h) for h in have]]
        if not new:
            die("%s: that is on file already" % where)
        entry[name] = have + new
        return "ADD", "%s: %s" % (name, ", ".join(new))
    if t not in ("objects", "records"):
        die("%s is not a list: fill it with --set" % name)
    if not isinstance(value, dict):
        die("an entry in %s has parts: write it as  \"%s: %s\"" % (name, name, "; ".join("%s=..." % k for k in _flat(spec["keys"]))))
    row, said = _fill(spec, value, None, where, today)
    if t == "records":
        said = _check_record(name, row, said, where, today)
        have = [r for r in (entry.get(name) if isinstance(entry.get(name), list) else []) if isinstance(r, dict) and not personal.blankish(r)]
        if row in have:
            die("%s: that entry is on file already" % where)
        # in the order things happened, whenever they were written down
        entry[name] = sorted(have + [row], key=lambda r: str(r.get("date") or ""))
        return "ADD", "%s: %s" % (name, said)
    label = spec["label"]
    if personal.blankish(row.get(label)):
        die("%s needs its '%s' part" % (where, label))
    kept, replaced = [], False
    for old in entry.get(name) if isinstance(entry.get(name), list) else []:
        if personal.blankish(old):
            continue
        if isinstance(old, dict) and fold(old.get(label) or "") == fold(row[label]):
            replaced = True
            continue
        kept.append(old)
    entry[name] = kept + [row]
    return "ADD", "%s: %s%s" % (name, said, " (replaces the entry on file under the same %s)" % label if replaced else "")


# a home reading as it is read off the instrument: one figure, or two with a stroke between them
_FIGURE_RE = re.compile(r"^\d{1,4}([.,]\d{1,2})?(/\d{1,4}([.,]\d{1,2})?)?$")


def _check_record(name, row, said, where, today):
    """What a row of a record must hold before it is kept. Returns the words for reading it back."""
    if name == "symptom_diary":
        if personal.blankish(row.get("what")):
            die("%s needs its 'what' part: what the symptom was, in the person's words" % where)
        if not row.get("date"):
            row["date"] = today.isoformat()
            said += "; date %s" % row["date"]
        severity = row.get("severity")
        if severity is not None and not (0 <= severity <= 10 and severity == int(severity)):
            die("%s.severity is a whole number from 0 to 10" % where)
    elif name == "lab_results":
        if personal.blankish(row.get("test")):
            die("%s needs its 'test' part: the name of the test, as the report prints it" % where)
        if not row.get("date"):
            die("%s needs its 'date' part: the day on the report" % where)
        if (row.get("value") is None) == personal.blankish(row.get("value_text")):
            die("%s needs the result once: value=5.1 for a plain number, or value_text=<0.5 (or 'negative') where the report "
                "prints it another way" % where)
        low, high = row.get("range_low"), row.get("range_high")
        if low is not None and high is not None and low > high:
            die("%s: the range runs backwards, the lower limit is above the upper one. Read the report again" % where)
        if not personal.blankish(row.get("range_text")):
            if low is not None or high is not None:
                die("%s: give the range once, as range_low and range_high or as range_text" % where)
            from . import clinic
            clinic.parse_range(row["range_text"])
    elif name == "home_readings":
        if personal.blankish(row.get("kind")) or personal.blankish(row.get("value")):
            die("%s needs its 'kind' and 'value' parts: what was measured, and the figure as it was read" % where)
        if not _FIGURE_RE.match(str(row["value"]).replace(" ", "")):
            die("%s.value is the figure as it was read, and nothing else: 128/82, 36.8, 5,4. A figure nobody could read is "
                "not kept" % where)
        row["kind"] = " ".join(str(row["kind"]).lower().split())
        row["value"] = str(row["value"]).replace(" ", "")
        if not row.get("date"):
            row["date"] = today.isoformat()
            said += "; date %s" % row["date"]
        if not personal.blankish(row.get("time")):
            row["time"] = "%02d:%02d" % core.parse_clock(row["time"], "%s.time" % where)
    elif name == "followups":
        if personal.blankish(row.get("what")):
            die("%s needs its 'what' part: what to ask about again" % where)
        if not row.get("date"):
            row["date"] = today.isoformat()
            said += "; date %s" % row["date"]
    return said


def _household(out, pid, spec, value, today):
    """Put an entry in one of the lists the household keeps in common. Returns the line for reading it back."""
    name = spec["name"]
    where = "--add %s" % name
    if not isinstance(value, dict):
        die("an entry in %s has parts: write it as  \"%s: key=value; key=value\"" % (name, name))
    have = [r for r in (out.get(name) if isinstance(out.get(name), list) else []) if isinstance(r, dict) and not personal.blankish(r)]
    if name == "kits":
        return _kit(out, have, value, where, today)
    row, said = _fill(spec, value, None, where, today)
    if personal.blankish(row.get("name")):
        die("%s needs its 'name' part" % where)
    if name == "cabinet":
        if not row.get("belongs_to"):
            row["belongs_to"] = pid
            said += "; belongs_to %s" % pid
        elif row["belongs_to"] not in personal.ids(out):
            die("%s.belongs_to must be the id of someone on file" % where)
        if row.get("keeps"):
            core.period_of(row["keeps"], "%s.keeps" % where)
        last = core.end_of(row.get("expiry"))
        if row.get("opened") and last and core.parse_date(row["opened"]) > last:
            die("%s: it was opened after its expiry date. Read the pack again" % where)

        def same(old):
            return all(fold(old.get(k) or "") == fold(row.get(k) or "") for k in ("name", "strength", "belongs_to"))
    else:
        if row.get("weight_kg") is not None and not 0 < row["weight_kg"] < 2000:
            die("%s.weight_kg must be more than nothing" % where)

        def same(old):
            return fold(old.get("name") or "") == fold(row["name"])
    replaced = any(same(old) for old in have)
    out[name] = [old for old in have if not same(old)] + [row]
    return "ADD", "%s: %s%s" % (name, said, " (replaces the entry on file under the same name)" if replaced else "")


def _kit(out, have, value, where, today):
    """One thing into a first-aid kit, or the day a kit was last looked through."""
    allowed = ("where", "item", "expiry", "checked")
    for part in value:
        if part not in allowed:
            die("%s has no part '%s': its parts are %s" % (where, part, ", ".join(allowed)))
    place = fold(coerce("text", value.get("where") or "", "%s.where" % where, today))
    if not place:
        die("%s needs its 'where' part: home, car, or wherever the kit is kept" % where)
    if "item" not in value and "checked" not in value:
        die("%s needs an 'item' to put in the kit, or the day it was 'checked'" % where)
    kits = [dict(k) for k in have]
    kit = next((k for k in kits if fold(k.get("where") or "") == place), None)
    if kit is None:
        kit = {"where": place, "items": [], "checked": ""}
        kits.append(kit)
    said = ["where %s" % place]
    if "item" in value:
        item = {"item": coerce("text", value["item"], "%s.item" % where, today),
                "expiry": coerce("partdate", value["expiry"], "%s.expiry" % where, today) if value.get("expiry") else ""}
        if not item["item"]:
            die("%s.item is empty" % where)
        old = [i for i in (kit.get("items") or []) if isinstance(i, dict) and not personal.blankish(i)]
        replaced = any(fold(i.get("item") or "") == fold(item["item"]) for i in old)
        kit["items"] = [i for i in old if fold(i.get("item") or "") != fold(item["item"])] + [item]
        said.append("item %s%s%s" % (item["item"], "; expiry %s" % item["expiry"] if item["expiry"] else "",
                                     " (replaces the one on file under the same name)" if replaced else ""))
    elif "expiry" in value:
        die("%s.expiry belongs to an item: name the item" % where)
    if "checked" in value:
        kit["checked"] = coerce("date", value["checked"], "%s.checked" % where, today)
        said.append("checked %s" % kit["checked"])
    out["kits"] = kits
    return "ADD", "kits: %s" % "; ".join(said)


def gather(a):
    """The changes asked for on the command line: [(verb, field name, value)]."""
    ops = []
    for text in a.set or []:
        ops.append(("set",) + parse_change(text, "set"))
    for text in a.add or []:
        ops.append(("add",) + parse_change(text, "add"))
    for name in a.decline or []:
        ops.append(("decline", name.strip().lower(), None))
    if a.gate:
        ops.append(("gate", "ignition", a.gate.strip().lower()))
    return ops


def apply(data, pid, ops, today, new=False, carer=None, consent=None):
    """A copy of the file with the changes made, and a line for each change, for reading back."""
    out = json.loads(json.dumps(data)) if data else personal.blank()
    people = personal.entries(out)
    found = [(k, e) for k, e in people if e["id"] == pid]
    lines = []
    if new:
        if found:
            die("a profile with that id is on file already: leave out --new to change it")
        if not personal.ID_RE.match(pid or ""):
            die("--id is a short handle for the file: lower-case letters, digits and hyphens, starting with a letter. "
                "It is not the place for a name")
        entry = {"id": pid, "created": today.isoformat(), "updated": today.isoformat(), "medical_reference": "human"}
        if carer:
            if carer not in personal.ids(out, "profile"):
                die("--carer must be the id of a profile on file: the person who looks after them")
            if not consent:
                die("a dependant's record needs a word on consent, theirs wherever they can give it: --consent \"who agreed, and how\"")
            entry["carer"] = carer
            entry["consent"] = {"note": coerce("text", consent, "--consent", today), "recorded": today.isoformat()}
            out.setdefault("dependants", []).append(entry)
            lines.append(("NEW", "record %s, in the care of %s; consent: %s" % (pid, carer, entry["consent"]["note"])))
        else:
            if consent:
                die("--consent goes with --carer, for a dependant's record")
            out.setdefault("profiles", []).append(entry)
            lines.append(("NEW", "profile %s" % pid))
    else:
        if carer or consent:
            die("--carer and --consent are for a new dependant's record: add --new")
        if not found:
            die("no profile with that id is on file: add --new to start one")
        entry = found[0][1]
    for verb, name, value in ops:
        spec = personal.field(name)
        if spec["type"] == "household":
            if verb != "add":
                die("%s is a list the household keeps: --add puts an entry in it, and 'forget' takes one out" % name)
            lines.append(_household(out, pid, spec, value, today))
            continue
        if verb == "set":
            lines.append(_set(entry, spec, value, today))
        elif verb == "add":
            lines.append(_add(entry, spec, value, today))
        elif verb == "decline":
            if spec["type"] in ("gate", "records", "reference", "household"):
                die("%s is not something a person declines" % name)
            entry[name] = personal.DECLINED
            lines.append(("DECLINED", "%s (stored, so it is not asked again)" % name))
        elif verb == "gate":
            if value not in gate.SETTINGS:
                die("--gate is one of: %s" % "; ".join(gate.SETTINGS))
            block = entry.get("ignition") if isinstance(entry.get("ignition"), dict) else {}
            block = dict(block)
            block.setdefault("questions", [])
            block["setting"] = value
            entry["ignition"] = block
            lines.append(("GATE", "setting: %s%s" % (value, "" if block["questions"] else " (no questions on file yet: the person types those in)")))
    if ops or new:
        entry["updated"] = today.isoformat()
    return out, lines


def code_of(data):
    """A short code for exactly this file. 'rebuild' wants the one 'intake' printed, so what is saved is what was read back."""
    text = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def prepare(a, today):
    """Work out the changed file for intake or rebuild: (new file, read-back lines). Checks the result."""
    data = personal.load()
    ops = gather(a)
    if not a.id:
        die("say whose file: --id (with --new to start one)")
    if not a.new and a.id not in personal.ids(personal.need()):
        die("no profile with that id is on file: add --new to start one%s" % (
            " (on file: %s)" % ", ".join(personal.ids(data)) if personal.ids(data) else ""))
    if a.new and a.carer and data is None:
        die("there is no file yet, so there is no carer on it: start the carer's own profile first")
    new, lines = apply(data, a.id, ops, today, new=a.new, carer=a.carer, consent=a.consent)
    problems = [f for f in personal.check(new, today) if f[0] == "FIX"]
    if problems:
        for level, where, what in problems:
            rec(level, "%s: %s" % (where, what))
        die("the file would not be a valid personal file with that in it: nothing was stored")
    return new, lines


# ---- intake

def _save_form(spec):
    name, t = spec["name"], spec["type"]
    if t == "object":
        return "--set \"%s: %s\"" % (name, "; ".join("%s=..." % k for k in _flat(spec["keys"]) if k != spec.get("stamp")))
    if t == "objects":
        return "--add \"%s: %s\"" % (name, "; ".join("%s=..." % k for k in _flat(spec["keys"]) if k != spec.get("stamp")))
    if t == "texts":
        return "--add %s=..." % name
    if t == "choice":
        return "--set %s=%s" % (name, "|".join(spec["choices"]))
    return "--set %s=..." % name


def _ask(spec):
    rec("ASK", "%s: %s" % (spec["name"], spec["what"]))
    more("why a doctor asks: %s" % spec["why"])
    more("to store the answer: %s" % _save_form(spec))


def cmd_intake(a):
    today = core.today()
    schema = personal.schema()
    if a.fields:
        for key, title in schema["sections"]:
            print(title.upper())
            for spec in schema["fields"]:
                if spec["section"] != key:
                    continue
                print("  %-22s %s" % (spec["name"], spec["what"]))
                if spec["type"] not in ("gate", "records", "reference"):
                    print("  %-22s   %s" % ("", _save_form(spec)))
        rec("RULE", "every field is optional. --decline FIELD stores a refusal, so it is not asked again")
        return
    if gather(a) or a.new:
        new, lines = prepare(a, today)
        rec("READ BACK", "for %s. Nothing is saved yet" % a.id)
        for key, text in lines:
            rec(key, text)
        rec("CONFIRM", code_of(new))
        rec("RULE", "store only what the person said about themselves, in Clinic: nothing guessed, nothing from a story, "
                    "nothing from another mind's files")
        rec("NEXT", "read that back in your own words. If they confirm all of it, run 'rebuild' with the same --id and changes "
                    "and --confirm %s. If they change anything, start again from here" % code_of(new))
        if a.new and not a.carer:
            more("a new profile: once it is saved, offer reminders, once ('remind --id %s' says what can be set, and how)" % a.id)
        return
    data = personal.load()
    if data is None or (a.id and a.id not in personal.ids(data)):
        rec("INTAKE", "%s. Say plainly that the file is plain JSON, as private as the place the package is kept, before a first intake"
            % ("there is no personal file yet" if data is None else "no profile with that id is on file"))
        rec("START", "intake --id %s --new --set call_me=... --set pronouns=...   (the name and pronouns come first, and are used at once)"
            % (a.id or "self"))
        return
    kind, entry = personal.pick(data, a.id)
    have = set(x.strip().lower() for x in (a.have or "").split(",") if x.strip())

    def waiting(names):
        return [n for n in names if not personal.answered(entry, n) and n not in have]

    rec("INTAKE", "%s: %s answered so far" % (entry["id"], core.plural(
        sum(1 for f in schema["fields"] if f["type"] != "gate" and personal.answered(entry, f["name"])), "field")))
    asked = 0
    for name in a.needs or []:
        spec = personal.field(name.strip().lower())
        if spec["type"] in ("gate", "records", "reference", "household"):
            die("%s is not something to ask for" % spec["name"])
        if personal.answered(entry, spec["name"]):
            rec("ON FILE", "%s is answered already: 'profile --field %s' reads it back" % (spec["name"], spec["name"]))
            continue
        _ask(spec)
        asked += 1
    queue = waiting(schema["ask_first"])
    if a.full:
        queue += waiting(schema["ask_routine"]) + waiting(schema["ask_last"])
    for name in queue[:max(0, 2 - asked)]:
        _ask(personal.field(name))
        asked += 1
    if a.full:
        left = len(queue) - min(len(queue), 2)
        rec("LEFT", "%s after these, in this order: who they are, medicines and allergies, body, history, life, care; the "
                    "sensitive ones last, each with its reason" % core.plural(max(left, 0), "question"))
        more("asked only when an answer depends on them (--needs FIELD): %s" % ", ".join(schema["ask_when_needed"]))
        from . import remind
        if not remind.wished(entry):
            rec("OFFER", "when the questions are done, reminders, once: 'remind --id %s' says what can be set, and how" % entry["id"])
    elif not asked:
        rec("NOTHING", "nothing to ask just now. Ask for a field the first time a question needs it (--needs FIELD gives the reason "
                       "to say); a full intake only when the person asks for one (--full)")
    rec("RULE", "one or two questions at a time, each with its reason, and never twice. \"Prefer not to say\" gets \"Noted.\" "
                "and --decline FIELD")


def change_options(p):
    p.add_argument("--id", help="whose file (a short handle, not a name)")
    p.add_argument("--new", action="store_true", help="start a new profile under that id")
    p.add_argument("--carer", metavar="ID", help="with --new: a dependant's record, in the care of this profile")
    p.add_argument("--consent", metavar="TEXT", help="with --carer: who agreed to the record, and how")
    p.add_argument("--set", action="append", metavar="CHANGE", help="fill or replace a field: field=value, or \"field: key=value; key=value\"")
    p.add_argument("--add", action="append", metavar="CHANGE", help="put an entry in a list field: \"allergies: substance=...; reaction=...\"")
    p.add_argument("--decline", action="append", metavar="FIELD", help="store \"prefer not to say\" for a field")
    p.add_argument("--gate", metavar="SETTING", help="when the gate's question is asked: every new conversation, when it matters, or off")


def register(sub):
    p = command(sub, "file", "profile", cmd_profile,
                "read back what is on file for a person, once their gate is open: all of it, one part, or one field",
                ["profile --id self", "profile --id self --section medicines", "profile --id self --field allergies"])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--section", help="one part only: who, body, history, medicines, life, care, records")
    p.add_argument("--field", help="one field only")

    p = command(sub, "file", "intake", cmd_intake,
                "what to ask next for a personal file, a question or two at a time; and the read-back of what would be stored",
                ["intake --fields", "intake --id self", "intake --id self --needs weight_kg",
                 "intake --id robin --new --set call_me=Robin --set pronouns=they/them",
                 'intake --id self --add "allergies: substance=penicillin; reaction=a rash" '
                 '--set "weight_kg: value=72,5; measured=today"'])
    change_options(p)
    p.add_argument("--full", action="store_true", help="a full intake, because the person asked for one: the whole list, in order")
    p.add_argument("--needs", action="append", metavar="FIELD", help="a field the question in hand depends on: prints what to ask and the reason to give")
    p.add_argument("--have", metavar="FIELD,FIELD", help="fields already answered in this conversation and not yet saved")
    p.add_argument("--fields", action="store_true", help="every field, by part of the file, with the form that stores it")
