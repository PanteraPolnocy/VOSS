# Where the data comes from

Every table the tools read is in this folder. Nothing is fetched while the tools run.

A database sits here as `<name>.db` with its licence text beside it as `LICENSE-<name>.txt`. It carries its own record of source, address, retrieval date and licence, and `python scripts/voss.py sources` prints all of that, with each file's age. One database per licence family, so that the terms of one source never spread to another.

| File | What it holds | Source | Licence |
|---|---|---|---|
| `core-pd.db` | health topic summaries and short definitions in plain English; emergency numbers by country | MedlinePlus health topic XML and "Definitions of Health Terms" XML (National Library of Medicine); Wikidata, property P2852; one fact from the European Commission's page on 112 | public domain and CC0: see below, and `LICENSE-core-pd.txt` |
| `triage.json` | the four triage levels and the red flags | written for this skill; word for word from `references/clinical-rules.md` | MIT, with the code |
| `visit.json` | what to ask a doctor, what to bring, the symptom diary's columns | written for this skill as general advice; the diary columns are those in `references/features.md` | MIT, with the code |
| `fields.json` | the personal file's fields, with what each holds and why a doctor asks | written for this skill; the wording is that of `references/personal-file.md` | MIT, with the code |
| `personal.template.json` | the empty shape of a personal file | written for this skill | MIT, with the code |
| `commands.json` | the command index | generated from the commands by `tools/build_index.py` | MIT, with the code |
| in the tools | check digits for the numbers Voss refuses to keep (payment cards, bank accounts, two national number formats) | the published algorithms: Luhn (ISO/IEC 7812), ISO 13616 for IBAN, the PESEL and NHS number check digits | public methods, no data taken |
| in the tools | the calendar file format | RFC 5545 (iCalendar) | a public standard |

## core-pd.db

Built by `tools/build_core.py`, which names every download. Licences checked on each source's own page on 15 November 2026:

- **MedlinePlus health topic summaries.** Public domain. NLM's page "Linking to and Using Content from MedlinePlus" (https://medlineplus.gov/about/using/usingcontent/) says: "Works produced by the federal government are not copyrighted under U.S. law. You may reproduce, redistribute, and link freely to non-copyrighted content", and lists the "Summaries on health topic pages" among it. It asks for the credit "Source: MedlinePlus, National Library of Medicine", which every answer from this file carries. The XML page (https://medlineplus.gov/xml.html) says the data sets are ones "you are welcome to download and use".
- **MedlinePlus "Definitions of Health Terms".** Five small XML files on the same page, each term with the NIH body it comes from. Same terms, same credit.
- **Medical Subject Headings (MeSH)** arrive with the topics and are used as names to find a topic by. NLM's terms for MeSH ask that NLM be named as the source, that no endorsement be implied, and that a copy which is not current says so: the tool names NLM, and prints the day the file was retrieved.
- **Not taken, on purpose:** the links to other organisations' pages, the Spanish topics, and every picture. **Never to be taken:** the A.D.A.M. Medical Encyclopedia and the ASHP drug monographs, which the same page says are copyrighted and licensed to MedlinePlus alone.
- **Wikidata.** Emergency numbers by country, property P2852, with what each number is for where Wikidata says. "All structured data from the main, Property, Lexeme, and EntitySchema namespaces is available under the Creative Commons CC0 License" (https://www.wikidata.org/wiki/Wikidata:Copyright). The numbers are passed through as listed and were not verified one by one; the tool says so each time.
- **European Commission.** One fact, with its source: 112 reaches an ambulance, the fire brigade or the police anywhere in the European Union (https://digital-strategy.ec.europa.eu/en/policies/112). No text of the page is reproduced. The build checks at every fetch that the page still says it.

Changed in the making: a summary's HTML becomes plain text, and curly quotes and long dashes become straight ones. No wording is changed.

## How the text is packed

SQLite has no compression of its own. Long text is therefore packed into blocks of about half a megabyte, each compressed with whichever of the standard library's codecs makes it smallest (zlib, bz2 or lzma), and a piece is found again by block, start and length. The health topic summaries come out about four times smaller for it. Reading one costs one block: a few milliseconds.

## Databases to come

| File | What it will hold | Source | Licence |
|---|---|---|---|
| `icd11.db` | diagnosis codes and titles, word for word | ICD-11 (World Health Organization) | CC BY-ND 3.0 IGO |
| `ddinter.db` | interactions between medicines, foods and conditions | DDInter 2.0 | CC BY-NC-SA 4.0 |
| `region-pl.db` | the Poland pack | to be confirmed source by source | to be confirmed |

Each licence is checked again, and the date written down here, before its file is built. A source whose terms do not clearly allow its data to be passed on in a public repository and in the packed skill is left out.
