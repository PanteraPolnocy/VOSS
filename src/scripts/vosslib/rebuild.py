"""Saving a changed personal file, and taking things out of one.

rebuild  applies the changes 'intake' read back and writes them out: a new private package, or just a new
         personal.json. It wants the code the read-back printed, so nothing is stored that was not read
         back first.
forget   removes a field, one entry, or a whole profile. Run once it says what would go and prints a code;
         run again with the code it writes the file without them. What is forgotten is gone from the new
         file: no empty slot, no "used to", no copy.

Voss never edits the package he is running from. Everything written here is a new file to hand over, and
it is private: it never goes into a git working tree.
"""
import json
import os
import zipfile

from . import core, personal, record
from .core import SKILL, command, die, fold, more, out_folder, rec

PACKAGE_NAME = "voss-private.zip"
PERSONAL_IN_PACKAGE = "scripts/data/personal.json"
SKIP_DIRS = ("__pycache__",)


def skill_files(root):
    """Every file of the skill, as paths relative to its folder."""
    out = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
    return sorted(out)


def write_package(root, personal_text, path):
    """The skill as it runs here, with this personal file in it, as one zip."""
    stamp = core.now().timetuple()[:6]
    names = skill_files(root)
    if PERSONAL_IN_PACKAGE not in names:
        names = sorted(names + [PERSONAL_IN_PACKAGE])
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in names:
            info = zipfile.ZipInfo(rel, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            if rel == PERSONAL_IN_PACKAGE:
                z.writestr(info, personal_text.encode("utf-8"))
            else:
                with open(os.path.join(root, rel), "rb") as f:
                    z.writestr(info, f.read())
    return os.path.getsize(path)


def write_out(new, a):
    """Write the changed file where it was asked for, and say what to do with it."""
    text = personal.dump(new)
    as_json = bool(a.json) or (personal.outside() and not a.package)
    where = a.out or "auto"
    if where.lower().endswith((".zip", ".json")):
        path = where
        folder = os.path.dirname(os.path.abspath(path))
        as_json = path.lower().endswith(".json")
    else:
        folder = out_folder(where)
        path = os.path.join(folder or "", "personal.json" if as_json else PACKAGE_NAME)
    if not folder or not os.path.isdir(folder):
        die("no such folder to write into: %s (use 'auto', a folder, or a name ending .zip or .json)" % where)
    replacing = core.same_path(path, personal.path())
    if replacing:
        if not a.replace:
            die("that is the file this copy reads. Voss hands over a new file and does not change one in use: write somewhere "
                "else, or add --replace if the person asked for exactly that")
        if not personal.outside() or core.within(path, SKILL):
            die("Voss never edits the package he is running from: write the new file somewhere else and hand it over")
    elif core.within(path, SKILL):
        die("that is inside the package Voss is running from, which he never changes: write the new file somewhere else")
    elif core.inside_repository(folder):
        die("that folder is inside a git repository, and a private file never goes into one: give --out a folder outside it")
    try:
        if as_json:
            temp = path + ".part"
            with open(temp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(temp, path)
            rec("PERSONAL", path)
            if replacing:
                rec("NEXT", "the file in use was replaced, as the person asked: the change is live from the next command")
            else:
                rec("NEXT", "hand that file to the person. It replaces %s" % (
                    "the file VOSS_PERSONAL names" if personal.outside() else "%s in their private package" % PERSONAL_IN_PACKAGE))
        else:
            size = write_package(SKILL, text, path)
            rec("PACKAGE", "%s (%d KB)" % (path, max(1, size // 1024)))
            rec("NEXT", "hand that file to the person: it replaces the skill they uploaded, changes included. This conversation "
                        "still runs the old copy; the new one answers from the next")
            if personal.outside():
                more("this copy reads its personal file from VOSS_PERSONAL: that file was not changed (--json writes one for it)")
    except OSError as e:
        die("could not write %s: %s" % (path, e.strerror or e))
    rec("PRIVATE", "it holds health information in plain JSON. Never a public repository, never a shared drive, and it is not "
                   "for passing on")


def out_options(p):
    p.add_argument("--confirm", metavar="CODE", help="the code the read-back printed; without it nothing is written")
    p.add_argument("--out", help="where to write: 'auto' (default), a folder, or a name ending .zip or .json")
    p.add_argument("--json", action="store_true", help="write only personal.json, not the whole package")
    p.add_argument("--package", action="store_true", help="write the whole package even when the file is kept outside it")
    p.add_argument("--replace", action="store_true",
                   help="write over the file in use; only for a file kept outside the package, and only when the person asks")


def _confirmed(a, new, how):
    code = record.code_of(new)
    if not a.confirm:
        return False
    if a.confirm.strip().lower() != code:
        die("that code does not match what would be %s now: the changes, the file or the day differ from the read-back. "
            "Read it back again and use the new code" % how)
    return True


def cmd_rebuild(a):
    today = core.today()
    if not record.gather(a) and not a.new:
        rec("REBUILD", "nothing to change was given. 'intake' reads a change back and prints the code; this saves it "
                       "('intake --fields' lists what can be stored)")
        return
    new, lines = record.prepare(a, today)
    if not a.confirm:
        die("nothing is saved without the read-back: run 'intake' with the same changes, read them back to the person, "
            "and give the code it prints as --confirm")
    _confirmed(a, new, "stored")
    for key, text in lines:
        rec(key, text)
    write_out(new, a)


# ---- forget

def _drop_field(entry, path, match, today):
    name, _, rest = path.partition(".")
    spec = personal.field(name.strip().lower())
    name, t = spec["name"], spec["type"]
    if t == "gate":
        die("the gate's questions are the person's own to edit in the file. 'forget --all' removes them with the profile, "
            "and 'rebuild --gate off' switches the gate off")
    if t == "reference":
        die("the medical reference is not something the person told Voss: there is nothing to forget")
    value = entry.get(name)
    if personal.blankish(value) and value != personal.DECLINED:
        die("nothing is on file under %s" % name)
    if match:
        if rest or t not in ("objects", "texts", "records"):
            die("--match picks one entry out of a list field, such as medicines or allergies")
        want = fold(match)
        hits = []
        for n, row in enumerate(value if isinstance(value, list) else []):
            label = row.get(spec.get("label", "")) if isinstance(row, dict) else row
            if want and want in fold(label or ""):
                hits.append((n, str(label)))
        if len(hits) != 1:
            die("--match fits %s in %s: say %s" % ("nothing" if not hits else "more than one entry", name,
                                                   "it as it is on file" if not hits else "more of it"))
        kept = [row for n, row in enumerate(value) if n != hits[0][0] and not personal.blankish(row)]
        if kept:
            entry[name] = kept
        else:
            del entry[name]
        # named in full, so that the person hears exactly which entry goes
        return "one entry from %s: %s" % (name, hits[0][1])
    if rest:
        if t != "object" or not isinstance(value, dict):
            die("only a field with parts can lose one part: forget %s as a whole" % name)
        keys, holder = spec["keys"], value
        parts = rest.split(".")
        for part in parts[:-1]:
            if not (isinstance(keys.get(part), dict) and isinstance(holder.get(part), dict)):
                die("%s has no part '%s'" % (name, rest))
            keys, holder = keys[part], holder[part]
        last = parts[-1]
        if last not in keys or personal.blankish(holder.get(last)):
            die("nothing is on file under %s.%s" % (name, rest))
        holder[last] = record._empty(keys[last])
        if personal.blankish(dict((k, v) for k, v in value.items() if k != spec.get("stamp"))):
            del entry[name]
        return "%s.%s" % (name, rest)
    count = len(personal.rows(entry, name)) if isinstance(value, list) else 0
    del entry[name]
    return "%s%s" % (name, " (%s)" % core.plural(count, "entry", "entries") if count else "")


def remove(data, a, today):
    """A copy of the file with what was named taken out, and a line for each removal."""
    out = json.loads(json.dumps(data))
    kind, entry = personal.pick(out, a.id)
    pid = entry["id"]
    lines = []
    if a.all:
        if a.field or a.match:
            die("--all forgets the whole profile: leave out --field and --match")
        gone = [pid]
        wards = [d for d in out.get("dependants") or [] if isinstance(d, dict) and d.get("carer") == pid] if kind == "profile" else []
        if wards and not a.with_dependants:
            die("%s in this person's care. Forget %s too (--with-dependants), or give %s another carer in the file first" % (
                core.plural(len(wards), "record is", "records are"),
                "it" if len(wards) == 1 else "them", "it" if len(wards) == 1 else "them"))
        key = "profiles" if kind == "profile" else "dependants"
        out[key] = [e for e in out.get(key) or [] if e is not entry]
        lines.append(("REMOVE", "the whole %s %s, its gate included" % ("profile" if kind == "profile" else "record", pid)))
        if wards:
            gone += [d.get("id") for d in wards]
            out["dependants"] = [d for d in out["dependants"] if d not in wards]
            lines.append(("REMOVE", "%s in their care" % core.plural(len(wards), "dependant's record", "dependants' records")))
        mine = [r for r in out.get("cabinet") or [] if isinstance(r, dict) and r.get("belongs_to") in gone and not personal.blankish(r)]
        if mine:
            out["cabinet"] = [r for r in out["cabinet"] if r not in mine]
            lines.append(("REMOVE", "%s that belonged to them" % core.plural(len(mine), "cabinet entry", "cabinet entries")))
        return out, lines
    if not a.field:
        die("say what to forget: --field NAME (with --match to pick one entry), or --all for the whole profile")
    if a.match and len(a.field) != 1:
        die("--match picks one entry out of one list: give a single --field with it")
    for path in a.field:
        lines.append(("REMOVE", _drop_field(entry, path.strip(), a.match, today)))
    entry["updated"] = today.isoformat()
    return out, lines


def cmd_forget(a):
    today = core.today()
    data = personal.need()
    kind, entry = personal.pick(data, a.id)
    new, lines = remove(data, a, today)
    if not _confirmed(a, new, "removed"):
        rec("READ BACK", "for %s. Nothing is removed yet" % entry["id"])
        for key, text in lines:
            rec(key, text)
        rec("CONFIRM", record.code_of(new))
        rec("NEXT", "say what would go, in your own words. If they confirm, run this again with --confirm %s" % record.code_of(new))
        return
    for key, text in lines:
        rec(key.replace("REMOVE", "REMOVED"), text)
    write_out(new, a)
    rec("FORGOTTEN", "gone from the new file: no empty slot, and no note that it was ever there. Confirm to the person what was removed")
    rec("OLD COPIES", "the package or file in use until now still holds it, and so does any backup. Tell the person to delete those: "
                      "the tool cannot reach them")


def register(sub):
    p = command(sub, "file", "rebuild", cmd_rebuild,
                "save changes that 'intake' read back: a new private package, or a new personal.json, to hand over",
                ["rebuild --id self --set call_me=Robin --confirm CODE --json",
                 'rebuild --id self --add "medicines: name=Metformin; strength=500 mg; schedule=08:00|20:00; '
                 'pack_size=60; pack_opened=2026-11-01" --confirm CODE'])
    record.change_options(p)
    out_options(p)

    p = command(sub, "file", "forget", cmd_forget,
                "remove a field, one entry or a whole profile from the personal file, completely, after a read-back",
                ["forget --id self --field recent_travel",
                 "forget --id self --field medicines --match ibuprofen",
                 "forget --id self --field care_contacts.emergency_contact.phone --confirm CODE --json",
                 "forget --id self --all --with-dependants"])
    p.add_argument("--id", help="whose file (default: the only profile on file)")
    p.add_argument("--field", action="append", metavar="NAME", help="the field to forget; NAME.PART for one part of a field")
    p.add_argument("--match", metavar="TEXT", help="with one --field that is a list: the one entry whose name holds this")
    p.add_argument("--all", action="store_true", help="\"forget me\": the whole profile, its gate included")
    p.add_argument("--with-dependants", action="store_true", help="with --all: the records in this person's care as well")
    out_options(p)
