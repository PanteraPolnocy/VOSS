"""What a household keeps an eye on together: the medicines at home, the first-aid kits, the pets, and the
people someone looks after.

cabinet  the medicines kept at home: what has expired, what was opened too long ago, and what is in there
         twice under two names.
kit      the first-aid kits at home and in the car, with two published lists of what a kit may hold.
pet      the pets on file, the record of a pet's trouble, and a published list of what may be dangerous to
         one: it always ends at a vet, and never at a dose.
round    the weekly round, where the person switched it on: refills, appointments, expiries, and what has
         gone stale in the file. One short message.
carer    the people in someone's care, and a word for the carer too.

Dates are worked out by the tool and tagged [derived]. An expiry is the maker's own date: the tool counts
days, and knows nothing of whether a medicine is still good.
"""
from datetime import timedelta
from decimal import Decimal

from . import advice, core, doses, journal, personal, rebuild, record, remind
from .core import command, die, fold, more, one_line, rec

SOON_DAYS = 30
ROUND_DAYS = 14
VET_WHEN = ("now", "today", "tomorrow")
NO_DOSE = ("Never a dose for an animal, of anything, from any source: what is safe for a person can kill a cat or a dog, "
           "and the weight on file is for the vet")


def _given(pairs):
    return dict((k, str(v)) for k, v in pairs if v is not None and str(v).strip())


def _shared(data, name):
    return [r for r in (data.get(name) or []) if isinstance(r, dict) and not personal.blankish(r)]


def _expiry(text, today):
    """(the last day of an expiry date, the words for it): 'expired', 'expires within 30 days', or ''."""
    last = core.end_of(text)
    if last is None:
        return None, ""
    if last < today:
        return last, "expired"
    if last <= today + timedelta(days=SOON_DAYS):
        return last, "soon"
    return last, ""


# ---- the medicine cabinet

def _same_substance(names):
    """([(a, b, the substance both hold)], the names that could not be compared, the label file's own account of
    itself or None). Two names are compared through the American labels, which is where a brand name leads to
    its substance: a name those do not know, or know as several medicines, is compared with nothing."""
    from . import labels
    known, info = labels.known_as(names)
    if not info:
        return [], list(names), None
    pairs = []
    listed = sorted(known)
    for i, a in enumerate(listed):
        for b in listed[i + 1:]:
            both = known[a][0] & known[b][0]
            if both and fold(a) != fold(b):
                # the plainest of the names they share: "ibuprofen", not "ibuprofen sodium"
                pairs.append((a, b, min(both, key=lambda n: (len(n), n)).replace("_", " ")))
    return pairs, [n for n in names if n not in known], info


def cmd_cabinet(a):
    data = personal.need()
    today = core.today()
    if a.name:
        kind, entry = personal.pick(data, a.id)
        value = _given((("name", a.name), ("strength", a.strength), ("expiry", a.expiry), ("opened", a.opened),
                        ("keeps", a.keeps), ("belongs_to", a.belongs_to)))
        rebuild.save(a, entry["id"], [("add", "cabinet", value)], today)
        return
    rows = _shared(data, "cabinet")
    rec("CABINET", "%s at home on file" % core.plural(len(rows), "medicine"))
    if not rows:
        more("to add one: cabinet --id ID --name \"...\" --strength \"...\" --expiry 2027-03 (--opened DATE --keeps \"6 months\")")
    flagged = []
    for row in rows:
        name = " ".join(x for x in (str(row.get("name") or ""), str(row.get("strength") or "")) if x)
        more("%s%s%s%s" % (
            name, "; expires %s" % row["expiry"] if row.get("expiry") else "; no expiry date on file",
            "; opened %s" % row["opened"] if row.get("opened") else "",
            "; belongs to %s" % row["belongs_to"] if row.get("belongs_to") else ""))
        last, state = _expiry(row.get("expiry"), today)
        if state == "expired":
            flagged.append(("EXPIRED", "%s: its expiry date (%s) has passed [derived, today %s]" % (name, row["expiry"], today.isoformat())))
        elif state == "soon":
            flagged.append(("SOON", "%s: expires within %d days (%s) [derived]" % (name, SOON_DAYS, row["expiry"])))
        opened = core.parse_date(row.get("opened") or "")
        if opened and row.get("keeps"):
            until = core.after(opened, core.period_of(row["keeps"], "how long %s keeps" % name))
            if until < today:
                flagged.append(("OPENED", "%s: opened %s, and its label gives it %s once opened: that ran out on %s [derived]" % (
                    name, row["opened"], row["keeps"], until.isoformat())))
        elif opened:
            flagged.append(("ASK", "%s: opened %s, and nothing on file says how long it keeps once opened. The label does: "
                                   "ask, and store it as --keeps" % (name, row["opened"])))
    for key, text in flagged:
        rec(key, text)
    names = []
    for row in rows:
        if row.get("name") and row["name"] not in names:
            names.append(str(row["name"]))
    pairs, unknown, info = _same_substance(names)
    for first, second, substance in pairs:
        rec("TWICE", "%s and %s: both hold %s, going by the American labels [sourced: %s.db, built %s]" % (
            first, second, substance, info["stem"], info["built"].isoformat()))
    if len(names) > 1:
        if info is None:
            rec("NOT CHECKED", "whether two of these are the same substance under two names: no file of medicines is "
                               "installed. Read the active ingredient on each pack")
        elif unknown:
            rec("NOT CHECKED", "%s: not in the American labels under that name, or on packs of different medicines there, so "
                               "not compared with the rest. Read the active ingredient on the pack" % "; ".join(unknown))
        if pairs:
            more("a brand name can be another medicine outside the United States: the active ingredient printed on each pack "
                 "settles it")
    rec("DISPOSAL", "nothing on file for any country: look up how old medicines are taken back where the person lives, and "
                    "cite it. Never down the drain or into the bin unless the source says so")
    rec("RULE", "an expiry date is the maker's, and the tool only counts days to it. A medicine past its date, or open "
                "too long, goes back and not into use. Two packs of one substance are easy to take twice: say so, and "
                "leave what to do about it to the pharmacist")


# ---- the first-aid kits

def cmd_kit(a):
    data = personal.need()
    today = core.today()
    if a.item or a.checked:
        if not a.where:
            die("say which kit: --where home, --where car")
        kind, entry = personal.pick(data, a.id)
        value = _given((("where", a.where), ("item", a.item), ("expiry", a.expiry), ("checked", a.checked)))
        rebuild.save(a, entry["id"], [("add", "kits", value)], today)
        return
    kits = _shared(data, "kits")
    if a.where:
        kits = [k for k in kits if fold(k.get("where") or "") == fold(a.where)]
    rec("KITS", "%s on file%s" % (core.plural(len(kits), "first-aid kit"), " kept there" if a.where else ""))
    for kit in kits:
        items = [i for i in (kit.get("items") or []) if isinstance(i, dict) and not personal.blankish(i)]
        rec("KIT", "%s: %s%s" % (kit.get("where") or "no place given", core.plural(len(items), "thing"),
                                 "; last looked through %s" % kit["checked"] if kit.get("checked") else "; never looked through, as far as the file knows"))
        for item in items:
            last, state = _expiry(item.get("expiry"), today)
            more("%s%s%s" % (item.get("item") or "", "; expires %s" % item["expiry"] if item.get("expiry") else "",
                             " - EXPIRED [derived, today %s]" % today.isoformat() if state == "expired"
                             else " - expires within %d days [derived]" % SOON_DAYS if state == "soon" else ""))
    if not kits:
        more("to add to one: kit --id ID --where home --item \"plasters\" --expiry 2027-05")
    if not advice.show(advice.ADVICE, "kit", "CONTENTS",
                       "two published lists, in their sources' own words: one for a home, one for a workplace with low "
                       "hazards. Each calls itself a suggestion: say whose it is, and add nothing to it from memory"):
        rec("CONTENTS", "no published list of what a kit should hold is on file. Look one up from a named body, such as a "
                        "Red Cross society or the national health service, and give its name and date: do not make one up")
    rec("CAR", "nothing on file about what any country's law asks for in a car: look it up for where the car is driven, and "
               "cite it")
    rec("RULE", "a kit is for the first minutes, not for treatment. What has expired is replaced, not used")


# ---- pets

def _poisons():
    return advice.show(advice.ADVICE, "pets", "POISONS",
                       "what FDA's page lists as potentially dangerous to a pet, in its own words. It names the more "
                       "common things and is not complete: something that is not on it is not thereby harmless")


def cmd_pet(a):
    if a.poisons and not a.problem:
        if not _poisons():
            rec("POISONS", "no list of what poisons a cat or a dog is on file. Look the thing up with a named source and "
                           "its date, or say you have none")
        rec("RULE", "on the list or not, something that may be a poison is a call to the vet now. %s" % NO_DOSE)
        return
    # a pet's trouble needs no personal file, unless the pet is named from one
    data = personal.need() if a.name or not a.problem else (personal.load() or {})
    today = core.today()
    if a.name and (a.species or a.weight is not None or a.vet):
        kind, entry = personal.pick(data, a.id)
        value = _given((("name", a.name), ("species", a.species), ("weight_kg", a.weight), ("vet", a.vet)))
        rebuild.save(a, entry["id"], [("add", "pets", value)], today)
        return
    pets = _shared(data, "pets")
    if a.problem:
        animal = None
        if a.name:
            hits = [p for p in pets if fold(p.get("name") or "") == fold(a.name)]
            if not hits:
                die("no pet of that name is on file: leave --name out and give --species, or add the pet first")
            animal = hits[0]
        species = one_line(a.species, "--species", 60) if a.species else (animal or {}).get("species") or ""
        if not species:
            die("say what kind of animal it is: --species cat")
        if not a.when or a.when not in VET_WHEN:
            die("--when is your reading of how soon a vet should hear of it: %s. In doubt, sooner" % ", ".join(VET_WHEN))
        when = "now" if a.poison else a.when
        rec("PET", "%s%s%s" % (species, ", %s" % animal["name"] if animal else "",
                               ", about %s kg as on file" % core.plain(Decimal(str(animal["weight_kg"])))
                               if animal and animal.get("weight_kg") is not None else ""))
        rec("PROBLEM", one_line(a.problem, "--problem", 400))
        rec("VET", "%s [Voss's reading, not a vet's]" % {
            "now": "call the vet now, or the nearest emergency vet if theirs is shut",
            "today": "ring the vet today",
            "tomorrow": "ring the vet tomorrow, and sooner if anything changes"}[when])
        if a.poison:
            more("something that may be a poison was swallowed or touched: that is always \"now\", whatever was chosen. "
                 "Take the packet or a photo of the plant to the telephone")
        if animal and animal.get("vet"):
            more("their vet, as on file: %s" % animal["vet"])
        if not advice.have(advice.ADVICE, "pets"):
            rec("POISONS", "no list of what poisons a cat or a dog is on file. Look the thing up with a named source and "
                           "its date, or say you have none: do not answer from memory that something is harmless")
        elif a.poison or a.poisons:
            _poisons()
        else:
            rec("POISONS", "a list of what may be dangerous to a pet is on file: 'pet --poisons' prints it, and --poison "
                           "prints it with the record")
        rec("RULE", "it always ends at a vet. %s" % NO_DOSE)
        more("first aid for an animal is keeping it still, warm and away from what hurt it, until the vet says more")
        return
    rec("PETS", "%s on file" % core.plural(len(pets), "pet"))
    for pet in pets:
        more("%s%s%s%s" % (
            pet.get("name") or "no name", ", %s" % pet["species"] if pet.get("species") else "",
            ", about %s kg" % core.plain(Decimal(str(pet["weight_kg"]))) if pet.get("weight_kg") is not None else "",
            "; vet: %s" % pet["vet"] if pet.get("vet") else ""))
    if not pets:
        more("to add one: pet --id ID --name \"...\" --species cat --weight 4 --vet \"...\"")
    rec("RULE", "a pet's trouble goes to a vet: 'pet --species ... --problem \"...\" --when now|today|tomorrow' writes the "
                "record. %s" % NO_DOSE)


# ---- the weekly round

def _run_out(med, now):
    """The day a medicine on file runs out by its schedule, or None where that cannot be worked out."""
    if med["pack"] is None or med["opened"] is None or med["opened"] > now.date():
        return None
    if any(d.every and not d.anchor for d in med["doses"]):
        return None
    try:
        state = doses.run_down(med["doses"], med["pack"], med["opened"], now)
    except core.VossError:
        return None
    return state["out"]


def cmd_round(a):
    data = personal.need()
    kind, entry = personal.pick(data, a.id)
    now = core.a_moment(a.now, "--now", core.today()) if a.now else core.now()
    today = now.date()
    if not 1 <= a.days <= 60:
        die("--days is how far ahead to look: 1 to 60")
    settings = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
    if not settings.get("weekly_round") and not a.asked:
        rec("ROUND", "off for %s: the weekly round is not switched on in their file, so none is sent" % entry["id"])
        more("if they ask for one now, run it with --asked. To switch it on: intake --id %s --set \"settings: weekly_round=yes\"" % entry["id"])
        return
    ahead = today + timedelta(days=a.days)
    rec("ROUND", "%s, the %s from %s [%s]" % (entry["id"], core.plural(a.days, "day"), today.isoformat(),
                                             "they asked for it" if not settings.get("weekly_round") else "switched on in their file"))
    said = 0
    meds, left_out = doses.from_file(entry)
    for med in meds:
        out = _run_out(med, now)
        if out is not None and out.date() <= ahead:
            rec("REFILL", "%s: by its schedule the pack runs out on %s [derived; 'refill --id %s' has the sum]" % (
                med["name"], out.date().isoformat(), entry["id"]))
            said += 1
    for row in personal.rows(entry, "appointments"):
        when = str(row.get("when") or "")
        day = core.parse_date(when[:10])
        if day and today <= day <= ahead:
            rec("VISIT", "%s%s%s" % (when, ", %s" % row["with"] if row.get("with") else "", ": %s" % row["why"] if row.get("why") else ""))
            more("'visit' has what to ask and what to bring")
            said += 1
    due = journal.due_followups(entry, today)
    if due:
        # what they are about is not said in a round, which may be read where others see it
        rec("FOLLOW UP", "%s to ask about again: 'followup --id %s' lists %s" % (
            core.plural(len(due), "thing"), entry["id"], "it" if len(due) == 1 else "them"))
        said += 1
    for when, who in journal.past_visits(entry, today):
        rec("PAST", "the visit of %s%s: ask how it went, once" % (when, ", %s" % who if who else ""))
        said += 1
    for row in _shared(data, "cabinet"):
        last, state = _expiry(row.get("expiry"), today)
        if state:
            rec("CABINET", "%s: %s (%s) [derived]" % (" ".join(x for x in (str(row.get("name") or ""), str(row.get("strength") or "")) if x),
                                                    "its expiry date has passed" if state == "expired" else "expires within %d days" % SOON_DAYS,
                                                    row["expiry"]))
            said += 1
    for kit in _shared(data, "kits"):
        for item in kit.get("items") or []:
            last, state = _expiry(item.get("expiry") if isinstance(item, dict) else "", today)
            if state:
                rec("KIT", "%s kit, %s: %s (%s) [derived]" % (kit.get("where"), item.get("item"),
                                                              "expired" if state == "expired" else "expires within %d days" % SOON_DAYS,
                                                              item["expiry"]))
                said += 1
    private = [f for key in ("ask_last", "ask_when_needed") for f in personal.schema()[key]]
    for note in record.stale_notes(entry, today):
        # a round may be read where others can see it: what the person keeps to themselves is not named in one
        if note.split(":")[0] in private:
            continue
        rec("STALE", note)
        said += 1
    if not said:
        rec("NOTHING", "nothing is due in that time, and nothing on file has gone stale")
    if settings.get("weekly_round") and not remind.wished(entry):
        rec("REMINDER", "nothing reminds them of the round between conversations: offer a reminder, once ('remind --id %s')" % entry["id"])
    rec("RULE", "one short message, of what is here and no more. Raise nothing sensitive that the person has not raised "
                "themselves, and leave out anything they would not want said where others can read it")


# ---- looking after someone

def cmd_carer(a):
    data = personal.need()
    kind, entry = personal.pick(data, a.id)
    today = core.today()
    wards = [d for d in data.get("dependants") or [] if isinstance(d, dict) and d.get("carer") == entry["id"]]
    rec("CARER", "%s looks after %s on file" % (entry["id"], core.plural(len(wards), "person", "people")))
    if not wards:
        more("a record for someone in their care: intake --id NEW-ID --new --carer %s --consent \"who agreed, and how\"" % entry["id"])
    for ward in wards:
        consent = ward.get("consent") if isinstance(ward.get("consent"), dict) else {}
        born = ward.get("date_of_birth")
        rec("IN CARE", "%s%s%s" % (ward["id"], ", called %s" % ward["call_me"] if isinstance(ward.get("call_me"), str) and ward.get("call_me") else "",
                                   "; %s" % record.age_words(born, today) if born and born != personal.DECLINED else ""))
        more("consent: %s" % (("%s (recorded %s)" % (consent.get("note"), consent.get("recorded") or "no date")) if consent.get("note")
                              else "nothing recorded. Theirs comes first, wherever they can give it: ask"))
        meds = personal.rows(ward, "medicines")
        timed = [m for m in meds if isinstance(m, dict) and m.get("schedule")]
        more("%s on file, %d with dose times ('schedule --id %s', 'refill --id %s')" % (
            core.plural(len(meds), "medicine"), len(timed), ward["id"], ward["id"]))
        coming = [r for r in personal.rows(ward, "appointments") if (core.parse_date(str(r.get("when") or "")[:10]) or today) >= today]
        for row in coming[:3]:
            more("visit: %s%s" % (row.get("when"), ", %s" % row["with"] if row.get("with") else ""))
        for note in record.stale_notes(ward, today):
            more("stale: %s" % note)
        more("their file is theirs: 'profile --id %s' reads it, behind their carer's gate" % ward["id"])
    rec("SUPPORT", "nothing on file about help for carers in this country: look it up and cite it")
    rec("RULE", "the person cared for is asked wherever they can answer, and their consent is recorded with their record. "
                "The carer's own load counts too: ask how they are, once in a while, and mean it")


def register(sub):
    p = command(sub, "household", "cabinet", cmd_cabinet,
                "the medicines kept at home: what has expired, what was opened too long ago, what is there twice under two names",
                ["cabinet", 'cabinet --id self --name "Eye drops" --expiry 2027-06 --opened 2026-11-01 --keeps "28 days"'])
    p.add_argument("--id", help="who is adding the entry (default: the only profile on file)")
    p.add_argument("--name", help="a medicine to put on the list, by the name on its pack")
    p.add_argument("--strength", help="its strength, as on the pack")
    p.add_argument("--expiry", help="its expiry date: 2027-03, or a full date")
    p.add_argument("--opened", help="the day it was opened")
    p.add_argument("--keeps", help="how long its label says it keeps once opened: 28 days, 6 months")
    p.add_argument("--belongs-to", dest="belongs_to", metavar="ID", help="whose it is (default: whoever is adding it)")
    rebuild.out_options(p)

    p = command(sub, "household", "kit", cmd_kit,
                "the first-aid kits at home and in the car: what is in them, what has expired, and two published lists of contents",
                ["kit", "kit --where car", 'kit --id self --where home --item "plasters" --expiry 2027-05', "kit --id self --where car --checked today"])
    p.add_argument("--id", help="who is adding the entry (default: the only profile on file)")
    p.add_argument("--where", help="which kit: home, car")
    p.add_argument("--item", help="a thing to put on that kit's list")
    p.add_argument("--expiry", help="its expiry date: 2027-05, or a full date")
    p.add_argument("--checked", help="the day the kit was last looked through")
    rebuild.out_options(p)

    p = command(sub, "household", "pet", cmd_pet,
                "the pets on file, a pet's trouble and how soon a vet should hear of it, FDA's list of pet dangers, and never a dose",
                ["pet", 'pet --species cat --problem "limping since this morning" --when today',
                 'pet --species dog --problem "ate a bar of chocolate" --when now --poison', "pet --poisons",
                 'pet --id self --name Biscuit --species dog --weight 12 --vet "the practice on the corner"'])
    p.add_argument("--id", help="who is adding the entry (default: the only profile on file)")
    p.add_argument("--name", help="the pet's name")
    p.add_argument("--species", help="what kind of animal")
    p.add_argument("--weight", help="rough weight in kilograms: it is the vet who needs it")
    p.add_argument("--vet", help="their vet, and a number if the person wants it kept")
    p.add_argument("--problem", help="what is wrong, as the person describes it")
    p.add_argument("--when", help="your reading of how soon a vet should hear of it: %s" % ", ".join(VET_WHEN))
    p.add_argument("--poison", action="store_true", help="something that may be a poison is involved: always a call now")
    p.add_argument("--poisons", action="store_true", help="print the list on file of what may be dangerous to a pet")
    rebuild.out_options(p)

    p = command(sub, "household", "round", cmd_round,
                "the weekly round, where it is switched on: refills, visits, expiries and what has gone stale, in one short message",
                ["round --id self", "round --id self --asked --days 30"])
    p.add_argument("--id", help="whose round (default: the only profile on file)")
    p.add_argument("--asked", action="store_true", help="the person asked for one now, though it is not switched on")
    p.add_argument("--days", type=int, default=ROUND_DAYS, help="how far ahead to look (default %d)" % ROUND_DAYS)
    p.add_argument("--now", help="the person's local date and time, if this machine's clock differs: 2026-11-15T10:30")

    p = command(sub, "household", "carer", cmd_carer,
                "the people in someone's care: their consent, their medicines and visits, and a word for the carer",
                ["carer --id self"])
    p.add_argument("--id", help="the carer's own profile (default: the only profile on file)")
