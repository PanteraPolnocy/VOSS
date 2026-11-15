"""The tool index: which module carries which command, the grouped list of them all, and a search.

voss.py asks this which one module a call needs and loads only that one.
The answers come from data/commands.json, which tools/build_index.py writes from the commands themselves.
If that file is missing or from another version, every module is loaded and asked instead: slower, same result.
"""
import argparse
import importlib
import json
import math
import os
import re

from . import MODULES, VERSION, core
from .core import DATA, command, fold, more, rec

INDEX_FILE = os.path.join(DATA, "commands.json")

# Everyday words for a job that the command's own help does not use. 'tools --find' reads these too.
ALSO = {
    "boot": "start startup first hello banner begin conversation status",
    "theatre": "roleplay scene story stage mode clinic switch in-world",
    "sources": "database data installed licence attribution age stale credit where from",
    "check": "typography quotes dashes reply lint audit marker mood ears",
    "selftest": "test broken working diagnose integrity",
    "tools": "help commands list index find search",
    "triage": "emergency urgent red flag flags level how serious ambulance call symptoms number 112 999 911 country abroad",
    "term": "word meaning mean definition what is does explain plain english condition disease abbreviation glossary topic lookup",
    "code": "icd icd11 icd-11 diagnosis classification discharge letter referral",
    "visit": "appointment doctor prepare questions diary bring gp consultation",
    "labs": "blood test result value range reference report high low lab",
    "schedule": "medicine medication dose times calendar ics reminder pills tablets when to take",
    "refill": "pack run out left remaining tablets pills supply renew prescription reminder",
    "med": "medicine drug tablet pill what is it for substance class brand label leaflet uses indication box",
    "find": "where to go night holiday weekend out of hours clinic department helpline patient rights owed country arranged abroad",
    "sidefx": "side effect effects adverse reaction could this be my medicine symptom caused by tablets label",
    "interact": "interaction interactions mix together combine take with drug medicine tablets safe to take clash",
    "watch": "new medicine supplement started prescribed check against list on file interaction",
    "diary": "symptom symptoms log note write down how bad severity headache pain today what helped",
    "result": "keep store save add put on file lab figure history earlier ones",
    "labread": "lab report photo pdf scan read whole all results import",
    "trend": "lab results over time history change rising falling compare previous last time",
    "cabinet": "medicine cupboard cabinet at home expired out of date expiry opened duplicate twice same substance dispose throw away old",
    "kit": "first aid kit box home car contents expiry plasters bandage what should be in it law",
    "pet": "cat dog animal vet poison ate swallowed limping bitten paw",
    "round": "weekly round summary what is due this week refills appointments expiries reminder",
    "carer": "caregiver looking after relative parent child dependant in my care",
    "card": "medical id card wallet phone lock screen ice print carry",
    "passport": "health passport summary new doctor abroad travel hospital hand over history",
    "brief": "visit brief one page for the doctor appointment summary questions timeline",
    "staykit": "hospital stay admission admitted going in next week ward operation planned what to pack bring ask",
    "assess": "possible explanations what could it be why differential cause symptom three tiers must not miss",
    "look": "photo picture rash wound bite burn swelling mole skin image",
    "decode": "discharge letter referral doctor notes after visit what do i do next to do follow up",
    "translate": "translation polish english translate document letter result leaflet check numbers",
    "myth": "claim true false rumour forum video influencer does it work evidence debunk",
    "teach": "lesson explain how does the body work anatomy physiology heart kidneys",
    "firstaid": "first aid cpr recovery position bleeding burn choking while waiting for the ambulance",
    "boxread": "box packet leaflet photo of medicine read name strength active substance",
    "desk": "desk health screen break posture water long session bedtime late",
    "season": "seasonal flu vaccination autumn winter heat cold snap reminder",
    "checkin": "wellbeing how are you feeling mood check in listen",
    "recipe": "baking bake cake biscuits bread shortbread ingredients allergens vegetarian",
    "scale": "double halve batch bigger smaller recipe quantities grams",
    "ignition": "gate identity who questions answer check pass password",
    "intake": "file fill in add update details ask questions read back weight allergy medicine",
    "profile": "show on file read back what do you know about me record",
    "rebuild": "save write package personal file change store keep",
    "forget": "delete remove erase wipe forget me field entry",
}

_index = None
_built = {}


def build_parser(only=None):
    """The command-line parser: every command, or only those of the modules named."""
    core.REGISTRY[:] = []
    _built.clear()
    p = argparse.ArgumentParser(
        prog="voss.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="The Voss toolkit (stdlib only, no network). Run 'voss.py tools' for the grouped index.")
    p.add_argument("--version", action="version", version="voss toolkit " + VERSION)
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    for name in (MODULES if only is None else only):
        seen = len(core.REGISTRY)
        importlib.import_module("vosslib." + name).register(sub)
        for row in core.REGISTRY[seen:]:
            _built[row[1]] = name
    return p


def collect():
    """Load every module and ask it: the index, exactly as tools/build_index.py writes it."""
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    rows = []
    for group, name, summary, examples in core.REGISTRY:
        options = []
        for act in sub.choices[name]._actions:
            if isinstance(act, argparse._HelpAction):
                continue
            flags = " ".join(act.option_strings) or (act.metavar if isinstance(act.metavar, str) else act.dest)
            options.append([flags, act.help or ""])
        rows.append({"name": name, "module": _built[name], "group": group, "summary": summary, "examples": list(examples),
                     "also": ALSO.get(name, ""), "options": options})
    return {
        "note": "Generated by tools/build_index.py from the commands themselves. Do not edit: voss.py reads it to load only the "
                "module a command needs, and 'tools --find' searches it.",
        "version": VERSION,
        "commands": rows,
    }


def load():
    global _index
    if _index is None:
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != VERSION or not data.get("commands"):
                raise ValueError("stale")
        except (OSError, ValueError):
            data = collect()
        _index = data
    return _index


def module_of(name):
    """The one module that carries this command, or None if it is not in the index."""
    for c in load()["commands"]:
        if c["name"] == name:
            return c["module"]
    return None


# ---- search

_STOP = set("a an the of to for in on and or with is it my me i how do does what which can will be at from by this that "
            "much many get need want should would about into when go have we been are was they there any some up out if so "
            "than then you your our us am".split())
_WORD_RE = re.compile(r"[a-z0-9]+")


def _stem(word):
    for suffix in ("ing", "ed", "s"):
        if len(word) - len(suffix) >= 3 and word.endswith(suffix) and not word.endswith("ss"):
            return word[:-len(suffix)]
    return word


def _stems(text):
    return [_stem(w) for w in _WORD_RE.findall(fold(text).replace("_", " "))]


def _hit(want, have):
    """How well one word of the question matches a set of stems: 1 exact, 0.5 a prefix either way, 0 none."""
    if want in have:
        return 1.0
    for h in have:
        if (len(want) >= 4 and h.startswith(want)) or (len(h) >= 4 and want.startswith(h)):
            return 0.5
    return 0.0


def search(words):
    """Commands that answer the words, best first.

    Each word of the question counts for more the fewer commands it fits. A command's score is the sum over
    the words of that weight times the best place the word was found in (its name, its everyday words, its
    summary, its options, its examples)."""
    wanted = [w for w in _stems(" ".join(words)) if w not in _STOP] or _stems(" ".join(words))
    fields = (("name", 12.0), ("also", 7.0), ("summary", 6.0), ("group", 2.0), ("options", 3.0), ("examples", 1.5))
    commands = load()["commands"]
    found = {}
    for c in commands:
        text = {"name": c["name"], "also": c.get("also", ""), "summary": c["summary"], "group": c["group"],
                "options": " ".join("%s %s" % (o[0], o[1]) for o in c.get("options", [])),
                # the finder's own examples are questions, not a description of what it does
                "examples": "" if c["name"] == "tools" else " ".join(c.get("examples", []))}
        stems = dict((k, set(_stems(v))) for k, v in text.items())
        found[c["name"]] = [max(weight * _hit(w, stems[k]) for k, weight in fields) for w in wanted]
    rarity = []
    for n in range(len(wanted)):
        fits = sum(1 for hits in found.values() if hits[n] > 0)
        rarity.append(math.log(1.0 + len(commands) / float(fits)) if fits else 0.0)
    scores = {}
    for name, hits in found.items():
        total = sum(h * r for h, r in zip(hits, rarity))
        if total > 0:
            scores[name] = total
    ranked = sorted(scores, key=lambda n: (-scores[n], n))
    if ranked:
        ranked = [n for n in ranked if scores[n] >= 0.55 * scores[ranked[0]]]
    return wanted, ranked


def cmd_tools(a):
    data = load()
    if a.find:
        if a.limit < 1:
            core.die("--limit is at least 1")
        _, ranked = search(a.find)
        by_name = dict((c["name"], c) for c in data["commands"])
        question = " ".join(a.find)
        if not ranked:
            rec("FIND", "\"%s\": no command answers that" % question)
            more("try another word for the job, or 'tools' for every command by group")
            more("a job with no command yet is done by hand, with cited lookups")
            return
        rec("FIND", "\"%s\": %s, best first" % (question, core.plural(len(ranked), "command")))
        for name in ranked[:a.limit]:
            c = by_name[name]
            rec(name, c["summary"])
            if c["examples"]:
                more("voss.py " + c["examples"][0])
        if len(ranked) > a.limit:
            more("... and %d more: %s" % (len(ranked) - a.limit, ", ".join(ranked[a.limit:a.limit + 8])))
        rec("NEXT", "'voss.py <command> -h' for the options and more examples")
        return
    by_group = {}
    for c in data["commands"]:
        by_group.setdefault(c["group"], []).append(c)
    want = a.group.lower() if a.group else None
    shown = 0
    for key, title in core.GROUPS:
        items = by_group.get(key)
        if not items or (want and want not in (key, title.lower())):
            continue
        print(title.upper())
        for c in items:
            print("  %-9s %s" % (c["name"], c["summary"]))
            if a.examples:
                for e in c["examples"]:
                    print("  %-9s   voss.py %s" % ("", e))
            shown += 1
    if not shown:
        core.die("no such group; groups are: %s" % ", ".join(k for k, _ in core.GROUPS if k in by_group))
    print("%d commands. 'voss.py <command> -h' for options and examples; 'voss.py tools --find WORDS' finds one by the job." % shown)


def register(sub):
    p = command(sub, "desk", "tools", cmd_tools, "the index of every command, grouped; or find the command for a job",
                ["tools", "tools --group clinic --examples", "tools --find when do the tablets run out",
                 "tools --find get ready for the doctor"])
    p.add_argument("--group", help="one group only")
    p.add_argument("--examples", action="store_true", help="include example invocations")
    p.add_argument("--find", nargs="+", metavar="WORD", help="the job in a few words: the commands that do it, best first")
    p.add_argument("--limit", type=int, default=5, help="how many commands --find lists (default 5)")
