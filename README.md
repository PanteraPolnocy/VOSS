# Voss

Voss is a household's medical mind: a male anthro red fox android doctor, unit VOSS-01, built under Project Asclepius. He is a persona for an AI assistant, packaged as an agent skill, with a toolkit underneath. Crisp, formal, and sharp-tongued with anyone who ignores his advice twice.

> Voss is a character and a reference tool for health information and education. It can suggest possible explanations for symptoms, with sources, but it does not make diagnoses, treat or prescribe, and it is not a substitute for a doctor, pharmacist or emergency service. It can be wrong. In an emergency, call your local emergency number.

The split is deliberate. **The database talks, and Voss explains it.** A dose, an interaction, a reference range or anything that differs by country comes from a source he can name, with its date, or he says he has no data. Sums are done by a tool, never in his head. "Nothing on file" is never dressed up as "safe".

## Where the build stands

He is being built in stages. The skeleton is in, and so is the first database.

Working now:
- **The persona and his rules**: the doctrine, triage first, the clinical rules, two modes (Clinic for real life, Theatre for roleplay), and his pictures: ten moods, two looks and a reference sheet.
- **Medical words in plain English**: about a thousand health topics and some eighty short definitions, in the source's own words, each with its credit and the day it was retrieved.
- **Triage**: the four levels and the red-flag checklist, and the emergency numbers of about two hundred countries.
- **Getting ready for a doctor**: what to ask, what to bring, a symptom diary to fill in.
- **Lab values**: a result read against the range printed on your own report, and against nothing else.
- **Medicines**: a schedule you were given, written as a calendar file; how long a pack lasts, counted exactly.
- **A personal file**, kept private: what you chose to tell him, behind a gate of your own questions, read back before anything is saved, and forgotten completely when you say so.
- **A check on his own replies**: typography, and his own rules of form.

Not built yet: the other databases (ICD-11, medicine interactions, product labels, a pack for Poland) and the commands that read them, and most of the features in [src/references/features.md](src/references/features.md). For anything the files do not hold, he looks it up with whatever tools the assistant has and cites it, or says he has no data.

## Requirements

- An assistant that can load skills **and run Python**: Claude with code execution (Claude Code, or the Claude apps with code execution switched on). A capable model matters. Where scripts cannot run he still talks and still follows his rules, but the gate cannot run, so he does not use a personal file.
- Python 3.9 or later. **Standard library only**: nothing to install, and nothing is fetched while the tools run.

## Install

1. Take `dist/voss.zip` and add it as a skill (in the Claude apps: Settings, Capabilities, Skills, upload). In Claude Code, unzip it into `~/.claude/skills/voss/`.
2. Say "Voss", or ask him something. He boots, shows his banner, and says what data is installed.

## The personal file

Everything personal lives in one file, `scripts/data/personal.json`. The public package does not have one: it ships `personal.template.json`, the empty shape.

**You do not have to edit it.** Tell Voss what you want on file. He asks one or two questions at a time and says why a doctor would ask; he reads back exactly what he would store; and when you confirm it, his `rebuild` tool hands you a new package with the file in it. Upload that in place of the old skill. Or keep the file outside the skill and point the `VOSS_PERSONAL` environment variable at it, so it survives updates.

Three things to know:
- **It is plain JSON.** Anyone who holds your private package can read it. It is as private as the place you keep it: never a public repository, never a shared drive. Do not pass on a package Voss rebuilt for you.
- **The gate is yours to set.** Type a few questions and their accepted answers into the file yourself, under `ignition`, about anything except your health. Voss is shown the questions only: a tool judges the reply, and the tool never prints an answer. That is as far as it goes. It is a soft lock, and keeping the file shut until a question is passed is a rule he follows, not something the tools enforce. With no questions on file there is no gate, and he says so.
- **Some things are never stored**: national identity numbers, insurance, passport, bank and card numbers, passwords. He refuses them, and the tools refuse the ones they can recognise.

A household can also give him a private `references/household.md`: who made him, who else lives there, how to address them. It never goes into the public package either, and `VOSS_HOUSEHOLD` can point at a copy kept elsewhere.

## The toolkit

`python scripts/voss.py tools` lists every command; `tools --find when do the tablets run out` names the one for a job; `<command> -h` gives options and worked examples.

| Group | Commands |
|---|---|
| Desk | `boot`, `theatre`, `sources`, `check`, `selftest`, `tools` |
| Clinic | `term`, `triage`, `visit`, `labs` |
| Medicines | `schedule`, `refill` |
| The personal file | `ignition`, `intake`, `profile`, `rebuild`, `forget` |

```
$ python scripts/voss.py boot
$ python scripts/voss.py term "atrial fibrillation"
$ python scripts/voss.py triage --country PL
$ python scripts/voss.py labs --test "Potassium" --value 5,4 --unit mmol/L --range "3.5-5.1" --flag H
$ python scripts/voss.py schedule --med "Metformin 500 mg: 08:00, 20:00" --ics auto
$ python scripts/voss.py refill --med "Metformin 500 mg: 08:00, 20:00" --pack 60 --opened 2026-11-01
$ python scripts/voss.py check --reply --text "It measures how well your kidneys filter." "[mood: composed] [voss-composed.webp]"
```

## What to know before you trust it

- **He is not a doctor.** He is a reference with a bedside manner, and says so. Possible explanations come in three tiers, always naming what must not be missed, and never as a verdict.
- **The one database so far explains words.** `term` prints what MedlinePlus says a thing is, written for readers in the United States. It is not about you, and it is not a diagnosis. Nothing he says about a medicine, an interaction or a code comes from the toolkit yet.
- **Emergency numbers are listed as Wikidata has them**, and were not verified one by one. If you already know your number, use it.
- **`labs` knows no reference ranges, on purpose.** It compares the two numbers you give it. Ranges differ between labs and methods.
- **`schedule` and `refill` repeat a schedule; they never set one.** The refill sum assumes every dose was taken, because it cannot know otherwise.
- **The gate is a soft lock.** It keeps a file from being read aloud to the wrong person. It does not encrypt anything. Someone who does not pass it still gets everything else he knows, only not the file.

The longer list, command by command, is in [docs/limits.md](docs/limits.md).

## Repository layout

```
src/                    the skill
  SKILL.md              the core: who Voss is, doctrine, rules, the job index
  references/           his character sheet, the clinical rules, the personal file, the features, the data plan
  playbooks/            the method for Theatre
  images/               the pictures, and manifest.json, which lists them
  scripts/voss.py       the toolkit's entry point
  scripts/vosslib/      one module per group of commands
  scripts/data/         the databases, each with its licence text beside it, the tables the tools read,
                        SOURCES.md (where each comes from), the command index, and the empty personal file
dist/voss.zip           the packed skill
docs/limits.md          what to trust, command by command
CONTRIBUTING.md         building, testing and the house rules
tests/                  the test suite, with made-up patients, a made-up household and made-up data to test with
tools/                  build.py packs the skill; build_core.py and its kind fetch a source and build its database
```

## Working on it

`python tests/test_voss.py` runs the suite and `python tools/build.py` checks the source and packs `dist/voss.zip`. House rules for the code: Python 3.9 compatible, standard library only, plain ASCII in code and comments, no network at run time, British English in anything a user reads. Every example in a command's help is run by the tests. The rest is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- Voss, the VOSS-01 design and the pictures: Pantera Północy.
- Health topic summaries and definitions of health terms. Source: MedlinePlus, National Library of Medicine. Public domain. The National Library of Medicine does not endorse this skill, and the copy here is as old as the day it was retrieved.
- Emergency numbers by country: Wikidata, CC0. That 112 works throughout the European Union: the European Commission.
- Each database carries its own licence text (`src/scripts/data/LICENSE-*.txt`) and is listed in [src/scripts/data/SOURCES.md](src/scripts/data/SOURCES.md), with the day its licence was last checked. A credit line stays with every answer that draws on it.

## Licence

MIT for the code and for everything written for this skill. See `LICENSE`.

The databases are not covered by that licence: each stays under its source's own terms, set out in the `LICENSE-<name>.txt` beside it. `core-pd.db` is public domain and CC0.

![Voss](/src/images/voss-reference-sheet.webp)
