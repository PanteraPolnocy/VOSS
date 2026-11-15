# Where the data comes from

Every table the tools read is in this folder. Nothing is fetched while the tools run.

No database is installed yet. When one is, it sits here as `<name>.db` with its licence text beside it as `LICENSE-<name>.txt`, it carries its own record of source, address, retrieval date and licence, and it gets a row in the table below. `python scripts/voss.py sources` prints what is installed and how old it is.

| File | What it holds | Source | Licence |
|---|---|---|---|
| `triage.json` | the four triage levels and the red flags | written for this skill; word for word from `references/clinical-rules.md` | MIT, with the code |
| `visit.json` | what to ask a doctor, what to bring, the symptom diary's columns | written for this skill as general advice; the diary columns are those in `references/features.md` | MIT, with the code |
| `fields.json` | the personal file's fields, with what each holds and why a doctor asks | written for this skill; the wording is that of `references/personal-file.md` | MIT, with the code |
| `personal.template.json` | the empty shape of a personal file | written for this skill | MIT, with the code |
| `commands.json` | the command index | generated from the commands by `tools/build_index.py` | MIT, with the code |
| in the tools | check digits for the numbers Voss refuses to keep (payment cards, bank accounts, two national number formats) | the published algorithms: Luhn (ISO/IEC 7812), ISO 13616 for IBAN, the PESEL and NHS number check digits | public methods, no data taken |
| in the tools | the calendar file format | RFC 5545 (iCalendar) | a public standard |

## Databases to come

| File | What it will hold | Source | Licence |
|---|---|---|---|
| `core-pd.db` | plain-English health topic summaries, and emergency numbers by country | MedlinePlus health topic XML (National Library of Medicine); Wikidata | public domain, with the credit "Source: MedlinePlus, National Library of Medicine"; CC0 |
| `icd11.db` | diagnosis codes and titles, word for word | ICD-11 (World Health Organization) | CC BY-ND 3.0 IGO |
| `ddinter.db` | interactions between medicines, foods and conditions | DDInter 2.0 | CC BY-NC-SA 4.0 |
| `region-pl.db` | the Poland pack | to be confirmed source by source | to be confirmed |

Each licence is checked again, and the date written down here, before its file is built.
