# Voss

Voss is a household's medical mind: a male anthro red fox android doctor, unit VOSS-01, built under Project Asclepius. He is a persona for an AI assistant, packaged as an agent skill, with a toolkit underneath. Crisp, formal, and sharp-tongued with anyone who ignores his advice twice.

> Voss is a character and a reference tool for health information and education. It can suggest possible explanations for symptoms, with sources, but it does not make diagnoses, treat or prescribe, and it is not a substitute for a doctor, pharmacist or emergency service. It can be wrong. In an emergency, call your local emergency number.

The split is deliberate. **The database talks, and Voss explains it.** A dose, an interaction, a reference range or anything that differs by country comes from a source he can name, with its date, or he says he has no data. Sums are done by a tool, never in his head. "Nothing on file" is never dressed up as "safe".

![Voss](/src/images/voss-sceptical.webp)

## What he does

- **The persona and his rules**: the doctrine, triage first, the clinical rules, two modes (Clinic for real life, Theatre for roleplay), a character sheet with his body, his senses and his tastes, and his pictures: ten moods, two looks and a reference sheet.
- **Triage, before anything else**: the four levels and the red-flag checklist, and the emergency numbers of more than two hundred countries. First-aid coaching while help is on its way starts with the number, and draws on what Wikipedia says about CPR, the recovery position, bleeding, burns and choking.
- **Possible explanations, never a verdict**: after triage and a short history, what a complaint could be, in three tiers, each with what fits, what does not and its source, and always the serious cause that must not be missed. The same care for a photo of a rash or a wound: what is visible, and how soon someone should see it.
- **Medical words in plain English**: about a thousand health topics and some eighty short definitions, in the source's own words, each with its credit and the day it was retrieved.
- **ICD-11 codes**: what a code on a letter or a referral means, word for word from the World Health Organization's classification.
- **Lab results**: a value read against the range printed on your own report, and against nothing else. Results can be kept, one at a time or a whole report read off a photo, and followed over time, each against the range of its own report, with a note when the unit, the lab or the range changed in between.
- **Medicines**: what a medicine is and what its label says, from about 9,200 American product labels; whether a symptom is among the side effects a label lists; which medicines are known to interact, with the grade the source gives each pair; a schedule you were given, written as a calendar file; how long a pack lasts, counted exactly; and the medicines kept at home, with what has expired or is there twice under two names.
- **Seeing a doctor**: what to ask and what to bring, a symptom diary, one page for the visit made from it, a doctor's letter turned into a list of things to do with dates for the calendar, and what to think of before a planned stay in hospital.
- **Pages to hand over**: a medical ID to print or to put on a phone's emergency screen, and a health summary for a new doctor or one abroad. You choose every line. The headings are in English, with a second language of your choosing beside them.
- **A personal file**, kept private: what you chose to tell him, behind a gate of your own questions, read back before anything is saved, and forgotten completely when you say so.
- **The household**: the first-aid kits, with two published lists of what one may hold; the pets (how soon a vet should hear of it, what may be dangerous to them, and never a dose); the people someone looks after; a weekly round of what is due, for those who switch it on; and a reminder for the calendar, so that the round is not forgotten.
- **And the rest**: a check on a translation of a medical paper, a health claim weighed against sources, a short lesson on how the body works, and his own baking recipes, in grams.
- **A check on his own replies**: typography, and his own rules of form.

Some things are in no file: a first-aid body's own guideline, what the law asks for in a car's kit, advice for heat and cold, and anything that belongs to one country, such as where to get care at night, what a patient is owed, or a national register of medicines. For those he looks things up with whatever tools the assistant has and cites them, or says he has no data. Every feature is described in [src/references/features.md](src/references/features.md).

## Requirements

- An assistant that can load skills **and run Python**: Claude with code execution (Claude Code, or the Claude apps with code execution switched on). A capable model matters. Where scripts cannot run he still talks and still follows his rules, but the gate cannot run, so he does not use a personal file.
- Python 3.9 or later. **Standard library only**: nothing to install, and nothing is fetched while the tools run.

## Install

1. Take `dist/voss.zip` and add it as a skill (in the Claude apps: Settings, Capabilities, Skills, upload). In Claude Code, unzip it into `~/.claude/skills/voss/`.
2. Say "Voss", or ask him something. He boots, shows his banner, and says what data is installed.

Unpacked, the skill is about 24.6 MB, nearly all of it the six databases, and it is kept under 30 MB on purpose: that is the most a skill may weigh when it is uploaded through the API. Each database is optional. If you have no use for one, delete the `.db` file and its `LICENSE-*.txt` from `scripts/data/` and zip the folder again: the commands that read it say that nothing is installed, and everything else carries on.

## The personal file

Everything personal lives in one file, `scripts/data/personal.json`. The public package does not have one: it ships `personal.template.json`, the empty shape.

**You do not have to edit it.** Tell Voss what you want on file. He asks one or two questions at a time and says why a doctor would ask; he reads back exactly what he would store; and when you confirm it, his `rebuild` tool hands you a new package with the file in it. Upload that in place of the old skill. Or keep the file outside the skill and point the `VOSS_PERSONAL` environment variable at it, so it survives updates.

What you add later goes in the same way: a diary entry, a lab result, a medicine in the cabinet, a pet. He reads it back, and only your "yes" to exactly that turns it into a new file.

Three things to know:
- **It is plain JSON.** Anyone who holds your private package can read it. It is as private as the place you keep it: never a public repository, never a shared drive. Do not pass on a package Voss rebuilt for you.
- **The gate is yours to set.** Type a few questions and their accepted answers into the file yourself, under `ignition`, about anything except your health. Voss is shown the questions only: a tool judges the reply, and the tool never prints an answer. That is as far as it goes. It is a soft lock, and keeping the file shut until a question is passed is a rule he follows, not something the tools enforce. With no questions on file there is no gate, and he says so.
- **Some things are never stored**: national identity numbers, insurance, passport, bank and card numbers, passwords. He refuses them, and the tools refuse the ones they can recognise.

A household can also give him a private `references/household.md`: who made him, who else lives there, how to address them. It never goes into the public package either, and `VOSS_HOUSEHOLD` can point at a copy kept elsewhere.

## The toolkit

`python scripts/voss.py tools` lists every command; `tools --find when do the tablets run out` names the one for a job; `<command> -h` gives options and worked examples.

| Group | Commands |
|---|---|
| Desk | `boot`, `theatre`, `check`, `selftest`, `sources`, `translate`, `teach`, `desk`, `season`, `checkin`, `tools` |
| Clinic | `triage`, `find`, `visit`, `labs`, `term`, `code`, `trend`, `brief`, `staykit`, `assess`, `look`, `decode`, `myth`, `firstaid` |
| Medicines | `schedule`, `refill`, `interact`, `watch`, `med`, `sidefx`, `boxread` |
| Household | `cabinet`, `kit`, `pet`, `round`, `carer`, `remind` |
| The personal file | `diary`, `result`, `labread`, `card`, `passport`, `ignition`, `profile`, `intake`, `rebuild`, `forget` |
| Extras | `recipe`, `scale` |

```
$ python scripts/voss.py boot
$ python scripts/voss.py triage --country DE
$ python scripts/voss.py term "atrial fibrillation"
$ python scripts/voss.py code BA41.0
$ python scripts/voss.py med metformin
$ python scripts/voss.py sidefx --med metformin --symptom nausea
$ python scripts/voss.py interact warfarin ibuprofen
$ python scripts/voss.py find night care --country IE
$ python scripts/voss.py boxread --name Advil --strength "200 mg" --substance ibuprofen
$ python scripts/voss.py labs --test "Potassium" --value 5,4 --unit mmol/L --range "3.5-5.1" --flag H
$ python scripts/voss.py schedule --med "Metformin 500 mg: 08:00, 20:00" --ics auto
$ python scripts/voss.py refill --med "Metformin 500 mg: 08:00, 20:00" --pack 60 --opened 2026-11-01
$ python scripts/voss.py firstaid --what choking --country NZ
$ python scripts/voss.py pet --poisons
$ python scripts/voss.py scale shortbread --times 1.5
$ python scripts/voss.py check --reply --text "It measures how well your kidneys filter." "[mood: composed] [voss-composed.webp]"
```

And with a personal file, once its gate is open:

```
$ python scripts/voss.py result --id self --test TSH --value 2.1 --unit mIU/l --range "0.27-4.2" --date 2026-11-02
$ python scripts/voss.py trend --id self --test tsh
$ python scripts/voss.py watch --id self --new ibuprofen
$ python scripts/voss.py cabinet
$ python scripts/voss.py card --id self --lines name,allergies,medicines,contact --heading allergies=Allergien
$ python scripts/voss.py remind --id self --what round --ics auto
```

![Voss](/src/images/voss-exasperated.webp)

## What to know before you trust it

- **He is not a doctor.** He is a reference with a bedside manner, and says so. Possible explanations come in three tiers, always naming what must not be missed, and never as a verdict.
- **The explanations are the assistant's, not a database's.** `assess` and `look` hold no medical knowledge. They keep the form: triage first, a source for each explanation, a must-not-miss every time, no percentages, and the line that sends you to a real doctor. How good the thinking is depends on the model behind him.
- **The databases explain words and codes, read labels out, and grade pairs of medicines.** `term` prints what MedlinePlus says a thing is, written for readers in the United States; `code` prints the title the World Health Organization gives an ICD-11 code. Neither is about you, and neither is a diagnosis.
- **First aid is Wikipedia's account, not a guideline.** `firstaid` leads with the emergency number and then prints what Wikipedia's articles say, at revisions that were read before they went in. Anyone can edit Wikipedia, and no first-aid body stands behind those words. The operator on the line outranks them, and so does a first-aid course.
- **A few passages are other people's advice, written for other readers.** What FDA lists as dangerous to a pet, what a first-aid kit may hold, how often to break from a screen, when the flu vaccination is given: each is printed word for word with its source, and none is a rule for you.
- **The labels are American, and nobody has checked them.** `med` and `sidefx` print what a company filed with the United States Food and Drug Administration, which says it has neither altered nor verified the text. Your own medicine may differ: other strengths, other uses, other warnings. The leaflet in your pack is the authority, and so is your pharmacist. There is no dose in the file at all, on purpose.
- **A side effect on the list is not the cause, and one that is not on it is not ruled out.**
- **The interaction data is partial, and says so.** It holds pairs of medicines with a grade and nothing more: no reasons, no advice, nothing on food. It only has a pair if one of the two medicines is in certain groups, so two heart medicines, or two for the nervous system, are not in it however well known their interaction. A pair that is not listed is not safe for that. Ask a pharmacist.
- **ICD-11 only.** There is no ICD-10 in it, and no table between the two: WHO's licence keeps those for a written agreement.
- **Emergency numbers are listed as Wikidata has them**, and were not verified one by one. If you already know your number, use it.
- **No reference ranges, on purpose.** `labs` and `trend` compare a value with the range printed on its own report. Ranges differ between labs and methods, and a trend is a question for your doctor, not an answer.
- **What you keep is what you said.** A diary, a result, an expiry date: he stores your words and your figures, and cannot know whether they are right. A figure he could not read off a photo is left out, never guessed.
- **`schedule` and `refill` repeat a schedule; they never set one.** The refill sum assumes every dose was taken, because it cannot know otherwise. `cabinet` counts days to the date the maker printed, and knows nothing of whether a medicine is still good.
- **A page you hand over can be read by whoever holds it**, and a medical ID on a lock screen by anyone who picks the phone up. You choose each line for that reason.
- **Nothing on file is about one country.** Where to get care, what a patient is owed, a medicine sold outside the United States: he looks those up and cites them, or says he has no data.
- **The gate is a soft lock.** It keeps a file from being read aloud to the wrong person. It does not encrypt anything. Someone who does not pass it still gets everything else he knows, only not the file.
- **A copy grows old.** Every answer from a database carries the day its source was retrieved, and past a limit the tools say the file is stale before they answer.
- **Nothing runs by itself.** There is no timer in the skill. A reminder is a calendar file you import, or a task the assistant's platform runs where it can. It says that it is time to talk to Voss, and nothing about your health.

The longer list, command by command, is in [docs/limits.md](docs/limits.md).

## Repository layout

```
src/                    the skill
  SKILL.md              the core: who Voss is, doctrine, rules, the job index
  references/           his character sheet, the clinical rules, the personal file, the features
  playbooks/            the method for Theatre
  images/               the pictures, and manifest.json, which lists them
  scripts/voss.py       the toolkit's entry point
  scripts/vosslib/      one module per group of commands
  scripts/data/         the databases, each with its licence text beside it, the tables the tools read,
                        SOURCES.md (where each comes from), the command index, and the empty personal file
dist/voss.zip           the packed skill
docs/limits.md          what to trust, command by command
CONTRIBUTING.md         building, testing, the databases and the house rules
SECURITY.md             how to report a fault, and what counts as one here
tests/                  the test suite, with made-up patients, a made-up household and made-up data to test with
tools/                  build.py packs the skill; build_core.py and its kind fetch a source and build its database
```

## Working on it

`python tests/test_voss.py` runs the suite and `python tools/build.py` checks the source and packs `dist/voss.zip`. House rules for the code: Python 3.9 compatible, standard library only, plain ASCII in code and comments, no network at run time, British English in anything a user reads. Every example in a command's help is run by the tests. The rest is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- Voss, the VOSS-01 design and the pictures: Pantera Północy.
- Health topic summaries and definitions of health terms. Source: MedlinePlus, National Library of Medicine. Public domain. The National Library of Medicine does not endorse this skill, and the copy here is as old as the day it was retrieved.
- Emergency numbers by country: Wikidata, CC0. That 112 works throughout the European Union: the European Commission.
- International Classification of Diseases, Eleventh Revision (ICD-11), World Health Organization (WHO) 2019 https://icd.who.int/browse11. Licensed under the Creative Commons Attribution-NoDerivatives 3.0 IGO licence (CC BY-ND 3.0 IGO). It is here whole and unchanged. WHO does not endorse this skill.
- Product labels: Data provided by the U.S. Food and Drug Administration (https://open.fda.gov). CC0. FDA does not endorse this skill, and has not verified the labels.
- Interactions between medicines: DDInter 2.0 (https://ddinter2.scbdd.com/). Tian Y, Yi J, Wang N, Wu C, et al. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic Acids Research 53(D1):D1356, doi:10.1093/nar/gkae726. CC BY-NC-SA 4.0. Other names for the medicines: Wikidata, CC0.
- What may be dangerous to a pet. Source: U.S. Food and Drug Administration. Public domain.
- Breaks from a screen, and the first-aid box at work: Contains public sector information published by the Health and Safety Executive and licensed under the Open Government Licence.
- A first-aid kit for the home: Contains public sector information licensed under the Open Government Licence v3.0. Source: nidirect.
- When the flu vaccination is given: European Centre for Disease Prevention and Control (ECDC), "Timing of influenza vaccination". CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The text is unchanged.
- First aid, from the English Wikipedia, one revision of each article:
  - Wikipedia contributors, "Cardiopulmonary resuscitation" (https://en.wikipedia.org/w/index.php?title=Cardiopulmonary_resuscitation&oldid=1382701468). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). An excerpt, as plain text; no wording changed.
  - Wikipedia contributors, "Recovery position" (https://en.wikipedia.org/w/index.php?title=Recovery_position&oldid=1316139441). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). An excerpt, as plain text; no wording changed.
  - Wikipedia contributors, "Emergency bleeding control" (https://en.wikipedia.org/w/index.php?title=Emergency_bleeding_control&oldid=1372598793). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). An excerpt, as plain text; no wording changed.
  - Wikipedia contributors, "Burn" (https://en.wikipedia.org/w/index.php?title=Burn&oldid=1385540835). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). An excerpt, as plain text; no wording changed.
  - Wikipedia contributors, "Choking" (https://en.wikipedia.org/w/index.php?title=Choking&oldid=1384678935). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). An excerpt, as plain text; no wording changed.
- Each database carries its own licence text (`src/scripts/data/LICENSE-*.txt`) and is listed in [src/scripts/data/SOURCES.md](src/scripts/data/SOURCES.md), with the day its licence was last checked. A credit line stays with every answer that draws on it.

## Licence

MIT for the code and for everything written for this skill. See `LICENSE`.

The databases are not covered by that licence: each stays under its source's own terms, set out in the `LICENSE-<name>.txt` beside it. `core-pd.db` is public domain and CC0, and `labels-us.db` is CC0. `advice-by.db` holds passages that are public domain, under the Open Government Licence v3.0 or under CC BY 4.0: each may be passed on with its credit. `icd11.db` is CC BY-ND 3.0 IGO: it may be passed on unchanged, with WHO's citation, and may not be adapted, translated or mapped to another code system. `ddinter.db` is CC BY-NC-SA 4.0: it may be passed on with DDInter's credit and under the same licence, and **not for commercial purposes**. That condition belongs to that one file. It does not reach the code or the other databases, which sit beside it under their own terms. If you use this skill commercially, delete `scripts/data/ddinter.db` first; everything else keeps working, and the tools say that no interaction data is installed. `firstaid-sa.db` is CC BY-SA 4.0: it may be passed on, commercially too, with its credits and under the same licence, and that condition likewise stays with that one file. Packing all of it into one zip changes none of this: a zip is a collection, and every file in it keeps its own terms.

![Voss](/src/images/voss-reference-sheet.webp)
