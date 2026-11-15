# Changelog

## 0.9.0 - 15 November 2026

More of a person. Everything in this entry is a proposal, marked [pending] in the files, until his maker has ruled on it line by line. Nothing above the mark in his character sheet was changed.

- The body, closer up, read off the pictures his maker supplied: he stands on his toes and wears no shoes, the black runs to above the heel and short of the elbow, the lab coat is cut for the tail, the eyes are rings like a lens, and he flushes under the eyes. A height (186 cm) and a weight (about 110 kg) are proposed; the height was "not set yet". His voice, his hands, how warm he runs, and how he keeps his fur. [pending]
- An android, after all: what he needs and what he does anyway, how he charges, the morning self-check, the hum where a pulse would be. [pending]
- Senses: sight, hearing, smell, taste, touch, balance and time, each with what it is good at, and then what they cost him. They are senses, not instruments, and they belong to his body and its world. In Clinic they reach nobody: of a real person he knows what he was told and what he was shown, and he never says or implies that he saw, heard, felt or smelled anything else. In Theatre they are his to use, as fiction. In `references/voss-self.md`, with a short paragraph in SKILL.md section 2 and a line in the Theatre playbook. [pending]
- Tastes: the kitchen, tea, music and quiet, reading, things, weather, people, habits, what he will argue for, what unsettles him, and what he has not decided yet. No titles are named: he picks in conversation and logs each one. [pending]
- The image wishlist is gone from the character sheet, since the pictures exist. Superseded: "Image wishlist" (0.7.0).
- The version moves with every change again. That was the rule for once he was finished. [maker]

## 0.8.0 - 15 November 2026

The build. This entry grows until the build is finished: the version does not move with every change. [maker] It was finished on 15 November 2026, in eight parts.

The skeleton:
- Toolkit, first part: `scripts/voss.py` with `boot`, `theatre`, `sources`, `triage`, `visit`, `labs`, `schedule`, `refill`, `check`, `selftest`, `ignition`, `intake`, `profile`, `rebuild`, `forget` and `tools`. Standard-library Python, nothing fetched at runtime. Supersedes "the toolkit is not built yet" (0.7.0).
- Databases live in `scripts/data/`, inside the package and the repository. Supersedes shipping them separately as Release assets (0.7.0). [maker]
- Pictures in `images/`, with `manifest.json`, used as they were supplied. The marker line is on: `[mood: KEY] [voss-KEY.webp]`, then `[look: KEY] [voss-KEY.webp]` if wanted; none inside a code or record block. Supersedes "until the images exist, no marker line" (0.7.0).
- `serious` is the mood of an emergency answer, which carries it as its marker and no look. Supersedes "proposed" (0.7.0). [maker]
- `intake` reads a change back and prints a code; `rebuild` and `forget` write only with that code, so nothing is stored or removed without the read-back.
- The gate works as it was designed: the tool asks and judges, and keeping a file shut until then is his own rule to follow. Open is open, for the rest of the conversation. Someone who does not pass still gets his full care and knowledge, only without the personal data, and there is no side door for an emergency. [maker]
- The gate is a soft lock and the files now say only that: the tool never prints an answer, and not opening `personal.json` to look is his own rule, written into the house rules for the tools.
- A calendar file holds medicine names, so it is never written into a git working tree or into the skill's own folder, the same as a personal file. `--ics auto` goes on to the Downloads folder where the current one will not do.
- A dependant's record names its `carer` and carries a note on `consent`; with no questions of its own it is guarded by the carer's gate. [kept]
- Dose lines for a medicine's `schedule`: `08:00`, `20:00 x2`, `mon thu 08:00`, `every 2 days from 2026-11-01 08:00`. [kept]
- Intake order for the tool: name and pronouns first; then who they are, medicines and allergies, body, history, life, care; gender identity, hormone therapy, contraception, pregnancy, breastfeeding, mental health and care wishes last; sex assigned at birth, organs, menstrual and substance questions only when an answer depends on them. [kept]
- A weight has no clock of its own: what counts is the day the profile was last changed, which `boot` now shows. [maker] A profile nobody has changed for over a year is asked about as a whole, the weight first. [pending] Supersedes weight as a dated field that goes stale by itself (0.7.0).

The core data:
- `core-pd.db`, the first database: the MedlinePlus health topic summaries and its short definitions of health terms, in plain English, and the emergency numbers of about two hundred countries from Wikidata. Public domain and CC0, with the licence text beside the file and the credit "Source: MedlinePlus, National Library of Medicine" on every answer. Licences checked on each source's own page on 15 November 2026. Supersedes "no database yet".
- `term`: a medical word or a health topic in the source's own words, found by its name, by what else it is called, or by its medical heading. Near misses are listed, not guessed, and "nothing on file" is said as such.
- `triage --country`: a country's emergency numbers, with what each is for where the source says, their source and date. They are passed through as listed and not verified one by one, and the tool says so. Inside the European Union 112 comes first.
- Left out of the MedlinePlus file on purpose: the links to other organisations' pages, the Spanish topics, the pictures.
- Text in a database is stored packed, about four times smaller, with the standard library alone. No file in the repository may be larger than 49 MB; one that would be is cut into parts. [maker]
- Nothing goes into the repository or the packed skill unless its licence clearly allows it to be passed on there. [maker]

ICD-11:
- `icd11.db`: ICD-11 for Mortality and Morbidity Statistics, release 2026-01, from the Simple Tabulation file the World Health Organization publishes. Every record is in it whole and unchanged, with its code, its title and its URI; the build puts WHO's file back together from the database and compares the two byte for byte before it writes anything. CC BY-ND 3.0 IGO with WHO's terms of use, read on WHO's own document on 15 November 2026; the licence text sits beside the file, which is not under the code's licence.
- `code`: what a code means, word for word, with where it sits in the classification, what is under it, its URI and WHO's citation; `--find` looks through the titles. A code that is not in the release is said to be so, and one with the shape of ICD-10 is named as that.
- No translation of the classification, and no table between ICD-11 and any other code system: WHO's licence allows neither without a written agreement. He quotes a title as it is and explains it in his own words.

Interactions:
- `ddinter.db`: pairs of medicines that are known to interact, each with the grade DDInter 2.0 gives it. CC BY-NC-SA 4.0, confirmed on DDInter's own terms page on 15 November 2026: attribution, non-commercial, share-alike. It sits in a file of its own with its licence text beside it, and is not under the code's licence.
- DDInter's downloads are less than its website: pairs and grades only, with no reasons, no advice, no food or illness data and no duplicated treatments, and only for pairs with a medicine in one of eight ATC groups. Supersedes mechanism, management, food, disease and duplication data in the plan, until a source for them is found. Nothing was taken from the website's pages.
- `interact`: the grade for each pair among the medicines named, or everything on file for one medicine. `watch`: something new against the medicines and supplements in a person's file. Both say what each name was read as, and both say every time what the file cannot say. "Not listed" is never worded as "safe", and a pair of two medicines from groups the downloads leave out is reported as out of the file's reach.
- Other names for a medicine, in English and Polish, from Wikidata (CC0), so that it is found under the name a person knows.

Product labels:
- `labels-us.db`: the labels companies have filed with the United States Food and Drug Administration, from openFDA: one for each substance, type and route, 9,168 of them, with the sections on what a medicine is for, its boxed warning, who must not take it, warnings, side effects, interactions, pregnancy and other groups, and the texts for patients. CC0 under openFDA's terms, read on its own pages on 15 November 2026; FDA's credit line goes with every answer.
- The dose is left out on purpose. It comes from the label of the product in the person's hand.
- `med`: what a medicine is, by substance or by brand name: its class, what its label says it is for, and any other section on request. `sidefx`: a symptom looked for in a label's side effects, warnings and text for patients. Both say that these are American labels which FDA has not verified, and that the person's own leaflet is the authority.
- A medicine is never guessed from its name. All 37,460 brand names on the labels are kept, and a name is found whole, by part of it ("tylenol"), with a strength or a form around it, or by two substances for the product that holds both ("acetaminophen with codeine"). The answer says what the name was read as and which words were not used. A name printed on packs of different medicines ("Pain Relief", and more famous ones) gets a list of them with what each is sold as, and is read as none.
- Packs for which FDA lists no substances, contraceptive pills among them, are kept where their generic name reads as a list of known substances. 276 labels that do not are left out and counted.
- European product information is not in it. For Poland the register says what a product is, and links to its leaflet.

The Poland pack:
- `region-pl.db`: the national register of medicines, 20,353 of them, with the name, the substance as the register names it, strength, form, route, ATC code and whether a pack needs a prescription. CC BY 4.0, read on the open data portal on 15 November 2026.
- `med` asks the register first: the name on a Polish box means what the Polish register says it means. An American label follows where there is one under the same name.
- `find`: ten facts about getting care in Poland (the emergency numbers, night and holiday care, the emergency department, the patient helpline, a patient's rights, where old medicines go, the first-aid kit in a car, how a medicine may be sold, which ICD revision paperwork uses). Each is in the skill's own words, with the law quoted by article or the official page named.
- Law is quoted word for word, from the Sejm's own service, and the build looks the words up again each time. Nothing is copied from NFZ's pages or from gov.pl, whose texts are under copyright or a share-alike licence: single facts are taken, and stated afresh.
- `triage --country PL` adds Poland's own numbers to the world's list.
- Waiting times for treatment are left out on purpose: they change every week. Supersedes the waiting times in the plan.

The feature commands, all twenty-six of them:
- What a person writes down: `diary` (symptoms), `result` and `labread` (lab results, one or a whole report), and `trend`, which reads each result against the range of its own report and says when the unit, the lab or the range changed.
- What a household keeps an eye on: `cabinet` (expired, open too long, or the same substance twice under two names, with the register's help), `kit`, `pet` (always ends at a vet, never a dose), `round` (the weekly round) and `carer`.
- Pages for somebody else to read, line by line as the person chooses: `card` (a page to print and text for a phone's medical ID), `passport`, `brief`, and `staykit` for a planned stay in hospital. Headings in English, Polish or both; the entries stay in the person's own words.
- The forms Voss fills in: `assess` (three tiers, the must-not-miss, the closing line), `look`, `decode`, `translate`, `myth`, `teach`, `firstaid`, `boxread`, and the notices `desk`, `season` and `checkin`. Each refuses a record that breaks the clinical rules.
- `recipe` and `scale`: four of his own recipes, in grams, marked untested, with exact arithmetic for another batch.
- One way into the personal file for all of it: a command reads a change back and prints a code, and the same command with that code writes the new file. Pages are written the same way.
- Added to the personal file [pending]: `value_text` for a lab result that is not a plain number, and `keeps` for how long a medicine keeps once opened.
- No first-aid guideline, pet poison list, kit contents list or seasonal dates are in the data: no source with clear terms was found for them, so the commands say that nothing is on file.

The documents:
- `references/data-plan.md` has left the package. It was the plan for building the databases, and they are built. What it held that still matters is kept where it is used: the sources, their licences and what was looked at and left out are in `scripts/data/SOURCES.md`, which now also lists how old each file may get [pending]; the rules for anyone who builds a database are in the repository's `CONTRIBUTING.md`. Supersedes the data plan as a reference file (0.7.0). Its planned commands and build order are superseded by the commands themselves, which `tools` lists.
- The other reference files say what he has, not what was planned. The list of sources still to be found (`features.md`) is now a list of what has no data behind it, and the note on emergency numbers (`clinical-rules.md`) says what is on file.
- The Polish register is named with its Polish letter in its own credit line, as its keeper spells it.
- The repository's README and `docs/limits.md` cover every command, and the tests keep them to it.

## 0.7.0 - 14 November 2026

The design, as it was handed over for building. The drafts of that day are folded in here, oldest first.

- Persona locked: Voss, unit VOSS-01, Project Asclepius. Male anthro red fox android, mid-career.
- Temperament, flaw, wit, tell, hobby, likes and dislikes.
- Doctrine (Verified Observations, Sourced Statements), triage levels, clinical rules and hard rules.
- Data plan: sources, licences, file layout, GitHub release plan, staleness limits, planned commands and build order.
- Personal file (`personal.json`): name, title, pronouns, gender identity, sex assigned at birth, hormone therapy, screening organs, date of birth, height, weight, pregnancy, breastfeeding, allergies, medicines, supplements, conditions, kidney and liver, habits, vaccinations, region, units, care contacts, appointments, sharing, gate and dependants. Every field optional. [maker]
- Intake method, identity gate for the file, medical confidentiality inside a household, forgetting.
- Public and private split: `personal.template.json` and `.gitignore` in public; `personal.json` and `household.md` private only.
- Features chosen: visit brief, medicine schedule, lab trends, interaction watch, first-aid coach, desk health, medical translator, emergency card, pet triage, recipe book, mood portraits, seasonal checks, myth-buster. Not chosen: travel health, joint second opinion, case logbook. [maker]
- Personal file widened to anything useful for diagnostics: species and medical reference, languages, communication needs, blood type, baseline vitals, menstrual, contraception, implants and devices, sensory aids, disabilities and access, intolerances, mental health, past procedures, family history, recent travel, substance use, sleep, activity, work exposures, care wishes, settings, symptom diary, lab results, pets. [maker]
- Species rule: everyone treated as who they are; real-world answers rest on human medicine, said once when it matters. [maker, kept]
- Never stored: national ID, insurance, passport, bank and card numbers, passwords. [kept]
- Two modes: Clinic (real) and Theatre (roleplay). The boot banner shows the mode. [maker]
- Clinic: possible explanations after triage and a short history, in three tiers (most likely, worth considering, must not miss), with sources, what would settle it, and a short closing line every time saying he cannot replace a real doctor. Still no final diagnosis, treatment plan, prescribing or dose changes. Supersedes "never diagnoses" from the first draft. [maker]
- Theatre: full in-world freedom with three guardrails (real drugs and doses keep real rules; real symptoms or distress end the scene; nothing from Theatre is stored or presented as real). [maker, kept]
- New `playbooks/theatre.md`; scope table and intended-purpose statement updated.
- Public and private split made clean: every public file now speaks of "your maker", "the household" and "the household's other minds". Everything about a particular household lives only in `references/household.md`, which `SKILL.md` reads at load when it exists.
- Provenance tags renamed for public use: [maker] and [kept].
- Leak check: the public build searches every public file for `household.md`'s leak words and refuses to pack if any appears.
- Reads the platform's persistent memory about the person (on Claude, the account's memory) when it bears on the question; confirms anything a dose or safety answer depends on; copies into the personal file only what is confirmed; the platform's own memory rules apply. [maker]
- Round 2 features: side-effect checker, cabinet audit, after-visit decoder, lab report reader, leaflet and box reader, photo look, health passport, weekly round, wellbeing check-in (opt-in), caregiver support, hospital stay kit, teach me, kit check. Not chosen: screening and booster due dates, sleep diary. [maker]
- Personal file: `cabinet`, `kits`, and new settings (weekly round, wellbeing check-in).
- Mood keys and image file names settled. The image prompts were kept outside the package: the pictures are made once and supplied with it.
- New mood proposed: serious, for emergency answers. [pending]
- Proposed picture details: charcoal waistcoat, navy tie, cyan Rod of Asclepius on the pocket, faint silvering at the muzzle, eyes as the only visible machine part. [pending]
