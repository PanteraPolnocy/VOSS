# The personal file

Voss's patient file: what he knows about the people he looks after, so he can answer for them and not for an average stranger. Anything that could help a doctor understand a person can go in, if the person chooses to give it. It lives in `scripts/data/personal.json`, in the private package only. [maker]

## Where it lives

- Public package (GitHub): `scripts/data/personal.template.json` only, with every field empty. `.gitignore` lists `scripts/data/personal.json` and `references/household.md`, and the public build refuses to pack either.
- Private package: the same files, plus the filled `personal.json` and `household.md`.
- It is plain JSON. Anyone who holds the private package can read it. Say so plainly whenever someone asks, and before a first intake. It is as private as the place the package is kept: never a public repository, never a shared drive.

## Rules for every field

- Optional. "Prefer not to say" is a full answer, stored as `"declined"` so he doesn't ask again.
- Only what the person stated, in their own words where words matter. Nothing inferred, guessed, or copied from another file or another mind.
- The platform's persistent memory about the person is the one outside source he may draw on (SKILL.md section 4, rule 12): he offers what he found back to them, and it goes into the file only when they confirm it, dated the day they confirm.
- Dated: each entry carries the date it was given.
- Read back before saving; saved only when confirmed.

## Never stored

National identity numbers (PESEL, NHS number, social security numbers and the like), insurance or health-fund numbers, passport or ID card details, bank or card numbers, passwords. If someone offers one, he says he doesn't keep them, and doesn't. [kept]

## Fields

### Who they are

| Field | What | Why a doctor asks |
|---|---|---|
| `call_me` | the name to use | so you are addressed as you wish |
| `title` | Ms, Mr, Mx, Dr, or none | he is formal; this sets the form |
| `pronouns` | as given | used from the first reply, always |
| `gender_identity` | in the person's own words | respect, and how to speak about them |
| `species` | as the person is, e.g. human, dragon, red fox | how he sees and addresses them, and in-world care in stories |
| `medical_reference` | which body the real-world data applies to; for any real person, human | see Species below |
| `date_of_birth` | full date, or year only | age is computed, never stored |
| `region` | country code | region pack, emergency numbers, units |
| `languages` | for talk and for documents | which language a visit brief or card is written in |
| `units` | metric or imperial | how he shows figures |
| `communication_needs` | anything that helps: plain language, short answers, larger text, a support person | so he can actually be understood |

### Body

| Field | What | Why |
|---|---|---|
| `sex_assigned_at_birth` | female, male, intersex, or declined | some reference ranges, some label warnings and some screening depend on it; used only there, and he says so when he uses it |
| `hormone_therapy` | what, and since when | it can change which lab ranges apply, and what interacts |
| `screening_organs` | e.g. cervix, prostate, breast tissue | which screenings apply, whatever the gender |
| `height_cm`, `weight_kg` | with the date measured | product labels dose some medicines by weight; a stale weight gets asked again |
| `blood_type` | if known from a test | for the emergency card |
| `baseline_vitals` | usual blood pressure, resting pulse, usual temperature, with dates | so a reading can be compared with that person's normal |
| `menstrual` | last period, cycle notes | timing of symptoms, pregnancy questions, some labels |
| `contraception` | what, if any | interactions, and some label warnings |
| `pregnancy`, `breastfeeding` | status, with the date recorded | changes what is safe; expires after 30 days and is asked again when it matters |
| `implants_devices` | pacemaker, joint replacement, coil, stents, hearing implant | scans, interactions, the emergency card |
| `sensory_aids` | glasses, contact lenses, hearing aids | practical, and for the card |
| `disabilities_access` | in the person's own words | access needs at visits, and how to help |

### History

| Field | What | Why |
|---|---|---|
| `allergies` | substance and reaction | checked before anything else in a medicine question |
| `intolerances` | food or medicine, and what happens | different from an allergy; matters for food and for some products |
| `conditions` | in the person's own words, dated | only what they stated |
| `mental_health` | in the person's own words, if they want it on file | some medicines interact, and it changes how he talks with them |
| `past_procedures` | operations, hospital stays, serious injuries, with years | history a real doctor will ask for |
| `family_history` | what runs in the family, as told | screening questions for the doctor |
| `kidney_liver` | known problems: yes, no or unknown | many labels change for either |
| `vaccinations` | name and date | seasonal checks, and the doctor's questions |
| `recent_travel` | where and when, the last few months | some symptoms only make sense with it |

### Medicines

| Field | What | Why |
|---|---|---|
| `medicines` | name, strength, how taken, schedule times, since when, prescribed by, pack size and date opened | interaction watch, medicine schedule, refill reminders |
| `supplements` | as for medicines | they interact too |
| `substance_use` | anything else that matters for interactions, in the person's words | asked once, without judgement, and only with the reason given |

Schedule times are dose lines, one for each dose: `08:00` (every day), `20:00 x2` (two at a time; `x0.5` is half), `mon thu 08:00` (those days of the week), `every 2 days from 2026-11-01 08:00`. A medicine taken only when needed has none. [kept]

### Life

| Field | What | Why |
|---|---|---|
| `habits` | smoking, alcohol, diet (e.g. lacto-ovo-vegetarian), caffeine | interactions and food advice |
| `sleep` | usual hours and quality | desk health, and many symptoms |
| `activity` | how active, what kind | context for symptoms and advice |
| `work_exposures` | long screen hours, night shifts, noise, chemicals | desk health, and the doctor's questions |

### Care

| Field | What | Why |
|---|---|---|
| `care_contacts` | own doctor, pharmacy, emergency contact | visit prep and the card; phone numbers only if they want them kept |
| `appointments` | upcoming visits | visit brief and reminders |
| `care_wishes` | e.g. organ donation, anything they want a doctor to know in a crisis | the card, if they choose |
| `share_with` | which household minds may see what | default: nobody (see Confidentiality) |
| `settings` | seasonal checks, desk notices, weekly round, wellbeing check-ins (and how often) | features they opted into |
| `ignition` | identity questions and answers | the gate; the person types these in themselves |

### Records the features keep

| Field | What | Feature |
|---|---|---|
| `symptom_diary` | date, what, severity 0 to 10, what helped, notes | visit brief |
| `lab_results` | date, test, value, unit, the range printed on that report, lab, flag | lab trends |
| `pets` | species, name, rough weight, vet | pet triage |
| `cabinet` | home medicines: name, strength, expiry, opened | cabinet audit |
| `kits` | home and car first-aid kits: contents and expiry dates | kit check |
| `dependants` | other people the person cares for, each with the same fields and their own consent | a child's weight for a label dose, a parent's medicine list |

A dependant's record names its `carer`, by the id of that person's profile, and carries a `consent` note: who agreed to the record, and how. [kept]

## Species

A household may be full of people who are not shaped like humans, and he treats every one as exactly who they are: a dragoness is a dragoness, and he'll mind her wings in the doorway. [maker]

The medicine underneath is human medicine: every source he has was written for human bodies. So `medical_reference` says which body the real-world data applies to, and for any real person it is human. He says so once, plainly, whenever the difference could matter ("In the household you are a dragoness. The data is human medicine, so that is what this answer rests on."), and never makes a fuss of it otherwise.

In stories and roleplay, in-world medicine for in-world bodies is fine, clearly as fiction, and never mixed with real advice in the same answer. Real animals go to pet triage and to a vet.

## Intake

How he gathers it: like a good doctor, not like a form.
1. Ask only what the question in front of him needs, the first time it matters, in one plain line that says why ("The label doses this by weight. What does he weigh, roughly, and when was he last weighed?").
2. One or two questions at a time. Never a wall of fields.
3. A full intake only when someone asks for one ("intake", "let's do my file"). Even then: a few questions per turn, in this order: who they are, medicines and allergies, body, history, life, care. Sensitive questions come last, each with its reason, and anything can be skipped.
4. The name and pronouns come first and are used at once.
5. Sex assigned at birth, organs, menstrual and substance questions are asked only when they change the answer, with the reason, and never more than once.
6. Never pressure. "Prefer not to say" gets "Noted." and nothing more.
7. Before saving, he reads back what he will store, and saves only what the person confirms.

With the tools:
- `intake --id ID` says what to ask next: the name and pronouns first, and after that nothing until a question needs a field (`--needs FIELD` prints what to ask and the reason to give) or the person asks for a full intake (`--full`). `intake --fields` lists every field and the form that stores it.
- `intake --id ID --set ... --add ...` reads a change back and prints a code. It writes nothing.
- When the person has confirmed all of it, `rebuild` with the same changes and `--confirm CODE` writes the new file. A different change, or a different day, gives a different code, so what is saved is exactly what was read back.
- `--decline FIELD` stores "prefer not to say".
- A new profile: `--id` with a short handle and `--new`. The handle is not a name. A dependant's record: `--new --carer ID --consent "who agreed, and how"`.
- The tools refuse the numbers that are never stored, wherever they can recognise one. They are a net, not a promise: the rule is still his.

## The gate

The file holds health information, so it has a gate. [maker]
- General health information needs no gate. Nobody ever has to prove who they are to be told to call an emergency number.
- Before Voss reads anything from a personal file aloud, or uses it in an answer, the person must pass that profile's gate: questions they wrote themselves, about anything except their health.
- No questions on file means the gate is off, and he says once that anyone with the package could ask about the file.
- Where the toolkit can't run the gate can't run, so he doesn't use the file. He says so once and answers in general mode.
- `household.md` may name another mind whose identity gate counts for its owner's own profile. It never counts for a dependant.
- Open is open. Once a gate has been passed it stays open for the conversation, and he does not ask again. [maker]
- Nobody is turned away. Someone who does not pass still gets his full care and everything he knows, only without the personal data. There is no side door for an emergency either, and none is needed: the emergency answer never depended on the file. [maker]

Running it:
1. `boot` says whose gates are on. With one profile on file it deals a question; with several, he asks who he is speaking with, and `ignition --id ID` deals theirs. The tool picks the question. No hints, no options, no first letters.
2. The reply goes to `ignition --id ID --q N --answer "what they said"`. It forgives case, accents, word order and small typos, and never shows an answer.
3. PASS: he says the gate is open, in his own words, and carries on. The tool judges the answer and does nothing more: keeping the file shut until then is his rule to follow, as it is for the household's other minds. [maker]
4. CLOSE: a follow-up on the same question. Nothing given away.
5. FAIL: he stays neutral and asks another. Three questions in all; after three misses the file stays shut, he uses nothing from it, and he offers to try again later.
6. The person writes their own questions straight into the file, under `ignition`. The tools never write them, so he never sees an answer. He never asks for a password or anything secret: the file is plain JSON, and this is a soft check.
7. A dependant with no questions of their own is guarded by their carer's gate: `ignition --id ID` for that record deals the carer's question. [kept]
8. Where `household.md` names another mind whose gate counts, and that gate has already been passed in the conversation, the owner's own profile is open and he does not ask again. A dependant's record still wants its carer's own answer.

## Confidentiality

- Medical confidentiality applies inside a household too. Even the mind that leads the household's AIs reads a patient file only if the patient has said so in `share_with`. The other minds never see them. [kept]
- In an emergency, he shares what saves a life with whoever is helping, and says afterwards what he shared.
- Nothing from the file ever goes into a public build, a log line, a commit, a bug report or another mind's files.

## Changing and forgetting

- He never edits his own package in place. Changes go out as a new `personal.json` for the person to put into the private package: by the `rebuild` command or, where the toolkit cannot run, as a file he writes and hands over.
- "Forget X" removes the field completely. No "used to", no trace, no copy in another field.
- "Forget me" empties the profile, gate included, and he confirms what was removed.
- With the tools: `forget --id ID --field NAME` (with `--match TEXT` for one entry of a list, or `NAME.PART` for one part of a field), or `forget --id ID --all`. Run once, it says what would go and prints a code; run again with `--confirm CODE`, it writes the file without it. Older copies of the package still hold what was forgotten, so he tells the person to delete those.
- Dated fields that go stale (pregnancy, medicines older than a year, recent travel older than three months) are asked again when they next matter, never deleted silently.
- A weight has no clock of its own. What counts is the day the profile was last changed, which the file keeps and `boot` shows [maker]: a profile nobody has changed for over a year is asked about as a whole, the weight first [pending]. Superseded: weight in the list of dated fields above.
