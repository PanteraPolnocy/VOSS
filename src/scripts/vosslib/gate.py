"""The gate on a personal file: questions the person wrote, judged here so that no answer has to pass
through Voss. Nothing in this module prints one.

The tool asks and judges, and that is all it does. Keeping a file shut until its question has been passed,
and not opening the file to look, are Voss's own rules to follow; once a gate is open it stays open for
the conversation. It is a soft lock: the file is plain JSON, and anyone who can open the package can read it.

A dependant with no questions of their own is guarded by the gate of the person who looks after them.
"""
import difflib
import random
import re

from . import core, personal
from .core import command, die, fold, more, rec

SETTINGS = ("every new conversation", "when it matters", "off")
_LIST_WORDS = re.compile(r"\b(or|albo|lub|czy)\b")
OFF_NOTE = ("no questions on file, so the gate is off: anyone with this package could ask about the file. "
            "Say so once. The person types their own questions into the file, under \"ignition\"")
NO_CARER = "the carer it names is not on file, so nothing guards it: put that right in the file before it is used"


def block(entry):
    """(setting, [question dicts]) for one entry."""
    raw = entry.get("ignition") if isinstance(entry.get("ignition"), dict) else {}
    questions = [q for q in (raw.get("questions") or []) if isinstance(q, dict) and q.get("q") and q.get("a")]
    setting = str(raw.get("setting") or "").strip().lower()
    if setting not in SETTINGS:
        setting = "every new conversation"
    return setting, questions


def keeper(data, kind, entry):
    """The entry whose gate guards this one: itself, or for a dependant with no questions of their own, their
    carer. None for a dependant whose carer is not on file."""
    if kind == "dependant" and not block(entry)[1]:
        for other_kind, other in personal.entries(data):
            if other_kind == "profile" and other["id"] == entry.get("carer"):
                return other
        return None
    return entry


def is_on(entry):
    setting, questions = block(entry)
    return bool(questions) and setting != "off"


# ---- judging a reply

def _words(text):
    return [w for w in fold(text).split("_") if w]


def _list_like(given):
    """True for a reply that offers several guesses rather than one answer."""
    low = str(given).lower()
    seps = sum(low.count(c) for c in ",;/|\n") + 2 * len(_LIST_WORDS.findall(low))
    return seps >= 2


def _contains(want, said):
    """The answer's words appear together, in order, in the reply; or run together as one word."""
    n = len(want)
    for i in range(len(said) - n + 1):
        if said[i:i + n] == want:
            return True
    joined = "".join(want)
    return len(joined) >= 3 and any(s == joined for s in said)


def judge_answer(given, accepted):
    """PASS, CLOSE or FAIL for a reply against the accepted answers. Loose on purpose: case, diacritics,
    word order and small typos do not matter. A string of guesses is not an answer: at most CLOSE, so the
    follow-up asks for just the one. A near miss needs a real near miss, a long word nearly right, not two
    letters shared by chance. It never says what the answer was."""
    said = _words(given)
    if not said:
        return "FAIL"
    listing = _list_like(given)
    best = 0.0
    for variant in accepted:
        want = [w for w in _words(variant) if w not in ("the", "a", "an", "of")] or _words(variant)
        if not want:
            continue
        hits = 0
        for w in want:
            if any(w == s or (len(w) > 3 and len(s) > 3 and difflib.SequenceMatcher(None, w, s).ratio() >= 0.8) for s in said):
                hits += 1
        if _contains(want, said) or hits == len(want):
            if listing or len(said) - len(want) > 8:
                best = max(best, 0.5)
                continue
            return "PASS"
        best = max(best, hits / float(len(want)))
        for w in want:
            for s in said:
                if len(w) > 3 and len(s) > 3:
                    best = max(best, difflib.SequenceMatcher(None, w, s).ratio() - 0.2)
        want_text, said_text = " ".join(want), " ".join(said)
        if len(want_text) >= 8 and len(said_text) >= 8:
            best = max(best, difflib.SequenceMatcher(None, want_text, said_text).ratio() - 0.1)
    return "CLOSE" if best >= 0.5 else "FAIL"


def deal(questions, seed=None):
    """Up to three question numbers in a random order. Models choose badly 'at random'; this does not."""
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    return rng.sample(range(1, len(questions) + 1), min(3, len(questions)))


def state_line(data, kind, entry):
    """One line on an entry's gate, with nothing from the file in it but the id."""
    guard = keeper(data, kind, entry)
    if guard is None:
        return "%s: %s" % (entry["id"], NO_CARER)
    setting, questions = block(guard)
    where = "" if guard is entry else ", by the gate of %s" % guard["id"]
    if not questions:
        return "%s: off, no questions on file%s" % (entry["id"], where)
    if setting == "off":
        return "%s: switched off in the file (%s on file)%s" % (entry["id"], core.plural(len(questions), "question"), where)
    return "%s: on, %s [%s]%s" % (entry["id"], core.plural(len(questions), "question"), setting, where)


def cmd_ignition(a):
    data = personal.need()
    if a.id is None and a.q is None and a.answer is None:
        people = personal.entries(data)
        if not people:
            rec("GATE", "nobody is on file yet")
            return
        for n, (kind, entry) in enumerate(people):
            (rec if n == 0 else lambda _k, v: more(v))("GATE", state_line(data, kind, entry))
        rec("NEXT", "'ignition --id ID' deals that person's question. Nothing from a file is read aloud or used before its gate is passed")
        return
    kind, entry = personal.pick(data, a.id)
    guard = keeper(data, kind, entry)
    if guard is None:
        die("that record cannot be opened: " + NO_CARER)
    setting, questions = block(guard)
    if guard is not entry:
        rec("GATE", "%s is in the care of %s: it is their gate that opens this record" % (entry["id"], guard["id"]))
    if not questions:
        rec("GATE", OFF_NOTE)
        return
    if setting == "off":
        rec("GATE", "switched off in the file (%s on file): nothing to ask. Anyone with this package could ask about it; say so once"
            % core.plural(len(questions), "question"))
        return
    if a.q is None:
        if a.answer is not None:
            die("say which question the reply answers: --q N")
        order = deal(questions, a.seed)
        rec("ASK", "%s  (profile %s, question %d)" % (questions[order[0] - 1]["q"], guard["id"], order[0]))
        if len(order) > 1:
            more("if missed, 'ignition --id %s --q %d' gives the next%s" % (
                guard["id"], order[1], ", then --q %d" % order[2] if len(order) > 2 else ""))
        more("check the reply with: ignition --id %s --q %d --answer \"what they said\"  (it never shows an answer, and you do "
             "not open the file to look)" % (guard["id"], order[0]))
        rec("RULE", "no hints, no options, no first letters; accept loose wording in any language the person uses")
        return
    if not 1 <= a.q <= len(questions):
        die("there are %d questions: --q is 1 to %d" % (len(questions), len(questions)))
    item = questions[a.q - 1]
    if a.answer is None:
        rec("ASK", "%s  (profile %s, question %d)" % (item["q"], guard["id"], a.q))
        rec("RULE", "no hints, no options, no first letters; accept loose wording in any language the person uses")
        return
    accepted = item["a"] if isinstance(item["a"], list) else [item["a"]]
    verdict = judge_answer(" ".join(a.answer), accepted)
    if verdict == "PASS":
        rec("PASS", "the gate is open for %s, and it stays open for this conversation. Say so in your own words" % guard["id"])
    elif verdict == "CLOSE":
        rec("CLOSE", "near, but not there: ask a follow-up on the same question rather than fail it. Give nothing away")
    else:
        rec("FAIL", "not the answer. Stay neutral, reveal nothing, ask a different question. Three questions in all; after three "
                    "misses the file stays shut: use nothing from it, and offer to try again later")
        more("they still get your full care and everything you know, only without the file. Emergency help is never held back")


def register(sub):
    p = command(sub, "file", "ignition", cmd_ignition,
                "the gate on a personal file: ask one of the person's own questions and judge the reply, without ever seeing the answer",
                ["ignition", "ignition --id self", "ignition --id self --q 1"])
    p.add_argument("--id", help="whose gate (default: the only profile on file)")
    p.add_argument("--q", type=int, help="question number")
    p.add_argument("--answer", nargs="+", help="what the person said; the verdict is PASS, CLOSE or FAIL")
    p.add_argument("--seed", type=int, help="fixed order, for testing")
