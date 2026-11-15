# Changelog

## 0.8.0 - in progress since 15 November 2026

The build. This entry grows until the build is finished: the version does not move with every change. [maker]

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
