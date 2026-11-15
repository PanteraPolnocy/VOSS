# Where the data comes from

Every table the tools read is in this folder. Nothing is fetched while the tools run.

A database sits here as `<name>.db` with its licence text beside it as `LICENSE-<name>.txt`. It carries its own record of source, address, retrieval date and licence, and `python scripts/voss.py sources` prints all of that, with each file's age. One database per licence family, so that the terms of one source never spread to another.

| File | What it holds | Source | Licence |
|---|---|---|---|
| `core-pd.db` | health topic summaries and short definitions in plain English; emergency numbers by country | MedlinePlus health topic XML and "Definitions of Health Terms" XML (National Library of Medicine); Wikidata, property P2852; one fact from the European Commission's page on 112 | public domain and CC0: see below, and `LICENSE-core-pd.txt` |
| `icd11.db` | ICD-11 for Mortality and Morbidity Statistics: every code and grouping with its title and URI, whole and unchanged | the "Simple Tabulation" release file of the World Health Organization | CC BY-ND 3.0 IGO with WHO's terms of use: see below, and `LICENSE-icd11.txt`. Not under the code's licence |
| `ddinter.db` | pairs of medicines that are known to interact, each with a severity grade; other names for the medicines | DDInter 2.0, its download files; Wikidata for the other names | CC BY-NC-SA 4.0 (non-commercial, share-alike): see below, and `LICENSE-ddinter.txt`. Not under the code's licence. The names are CC0 |
| `labels-us.db` | product labels of medicines sold in the United States: what each is for, its warnings, side effects and interactions, in the label's own words; other names for the substances | openFDA drug labels (United States Food and Drug Administration); Wikidata for the other names | CC0: see below, and `LICENSE-labels-us.txt` |
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

## icd11.db

Built by `tools/build_icd11.py` from WHO's release file, which needs no account: `https://icdcdn.who.int/static/releasefiles/<release>/SimpleTabulation-ICD-11-MMS-en.zip`. The licence was read on WHO's own document on 15 November 2026: "Terms of Use and License Agreement" (https://icd.who.int/en/docs/icd11-license.pdf, dated 7 October 2025).

- **The licence** is Creative Commons Attribution-NoDerivs 3.0 IGO (clause 1.2): the classification may be copied and passed on, with attribution, and may not be adapted.
- **Software.** Clause 1.2.2: "WHO does not consider incorporation of the Classifications into a software product to be an 'adaptation'", provided it is not distributed under a different name or without attribution, without the codes, or without the URIs. Clause 1.2.3: it "must include Classifications code, title and URI". Every entry here has all three.
- **No translations, no mappings.** Clause 1.2.4: "Mapping or producing crosswalks between other classifications and terminologies and Classifications and producing translations are not covered by the Classifications License and are subject to a separate written agreement from WHO." There is no translation and no table to ICD-10 or anything else in this file, and none may be added.
- **Additions** must be "clearly identified as additions that do not originate from WHO" (clause 1.2.5). The three helper columns and the copy of each title without the file's quoting are named as such in `LICENSE-icd11.txt`.
- **Attribution** is WHO's own wording (clause 1.3), printed with every answer. **No endorsement**: WHO's name is used to say where the classification comes from and for nothing else (clause 4.1).
- **Nothing is changed.** Every record of WHO's file is stored whole. `python tools/build_icd11.py --verify` puts the file back together from the database and compares it with the download byte for byte, the build does the same before it writes anything, and the tests check the shipped file against the checksum taken at the build.
- **What is not in it:** descriptions, definitions and index terms. The release file carries codes, titles and structure only.
- WHO is preparing an updated licence. The build checks, by checksum, that the licence document is still the one that was read, and stops if it is not.

## ddinter.db

Built by `tools/build_ddinter.py`. The terms were read on DDInter's own page on 15 November 2026 (https://ddinter2.scbdd.com/terms/): "The DDInter data is made available under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license."

- **What that means here.** The file may be passed on with DDInter's credit, under the same licence, and not for commercial purposes. It is kept in a file of its own for that reason, apart from the MIT code and from the other databases. Anyone who uses the skill commercially has to take this one file out; the tools then say that no interaction data is installed.
- **Credit**, printed with every answer: DDInter 2.0 (https://ddinter2.scbdd.com/). Tian Y, Yi J, Wang N, Wu C, et al. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic Acids Research 53(D1):D1356, doi:10.1093/nar/gkae726.
- **What was changed:** the eight download files were merged into one table of pairs, a pair listed twice is stored once, and the grade is stored as a number. No pair and no grade was added, removed or altered.
- **What DDInter's downloads hold, and what they do not.** Pairs of medicines with a grade (Major, Moderate, Minor, Unknown): 160,235 pairs of 1,939 medicines on the day of the build. No account of why two medicines interact or what to do about it, and nothing on food, illnesses or duplicated treatments: those are on DDInter's website only, and are not taken from it. And only eight of the fourteen ATC groups have a download (A, B, D, H, L, P, R, V), so a pair of two medicines from the other groups is not in the file at all. The tools say this every time, and never let "not listed" read as "safe". The files also show which medicines are outside those groups: one whose pairs are spread over several files, with no file holding them all, is in none of the groups that have a download (903 of the 1,939). A pair of two such medicines is reported as out of the file's reach, since it could not be there whether or not the two interact.
- **Other names.** DDInter has one name for each medicine, sometimes the American one. So that "paracetamol" finds "Acetaminophen", the English and Polish labels and aliases of Wikidata items that carry an ATC code (property P267, CC0) are added where an item's English name is the DDInter name and no other item's. They were matched by name, not checked one by one, and the tools say what each name was read as.
- The build checks at every fetch that DDInter's terms page still names the same licence, and stops if it does not.

## labels-us.db

Built by `tools/build_labels.py` from openFDA's drug label download (https://open.fda.gov/apis/drug/label/download/). The terms were read on openFDA's own pages on 15 November 2026 (https://open.fda.gov/terms/ and https://open.fda.gov/license/).

- **The licence.** "Unless otherwise noted, the content, data, documentation, code, and related materials on openFDA is public domain and made available with a Creative Commons CC0 1.0 Universal dedication. ... You can copy, modify, distribute, and perform the work, even for commercial purposes, all without asking permission." Data that is not covered is "clearly marked by a warning in the relevant documentation"; the drug label documentation (https://open.fda.gov/apis/drug/label/) carries no such warning.
- **Credit.** FDA asks, "while not required", for: "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)". Every answer carries it. "When using or citing the work, you should not imply endorsement": FDA does not endorse this skill, and the licence text says so.
- **What a label is,** in FDA's words on the same page: the labels "represent the most recent drug listing information companies have submitted", their "content has neither been altered nor verified by FDA", and they "may not be the labeling on currently distributed products or identical to the labeling that is approved". The tools say this every time.
- **What is kept.** Of 264,748 labels on the day of the build, the 9,168 that are one each for a substance, a type (prescription or over the counter) and a route: only labels FDA has matched to a product, the fullest one of each kind, an original maker's before a copy. Of each label, the sections on what it is for, the boxed warning, who must not take it, warnings, side effects, interactions, pregnancy and other groups, and the texts for patients.
- **Brand names.** Every brand name the labels of a kind carry is kept (37,460), so that a medicine is found under the name on the pack. Left out are only the ones that say no more than the substance does ("Ibuprofen Tablets 200 mg"). One name can be on packs of different medicines; the tools then list them and read the name as none of them.
- **What is in a product** is FDA's own list of substances. For 1,653 labels FDA gives none: packs of two kinds of tablet, as a rule, contraceptive pills among them. Such a label is kept when its generic name reads as a list ("norgestimate and ethinyl estradiol") and every part of it is a substance FDA lists for another label, a medicine Wikidata knows by that name, or a name used under at least three separate approvals. 276 labels fit none of that and are left out, a few newer medicines among them: nothing is guessed. Where such a label gives no route either, it is counted with the labels of the same substances that do, if those agree; otherwise its route reads "route not given".
- **What is left out on purpose: the dose.** A dose comes from the label of the product in the person's hand. Also left out: how the medicine works, the studies, the chemistry, how it is supplied.
- **Changed in the making:** line breaks tidied, curly quotes and long dashes made straight. No wording was changed.
- **American labels.** A medicine sold under the same name elsewhere may have other uses, strengths and warnings. The tools say that too.
- **Other names** for the substances come from the same Wikidata file the interaction data uses (CC0), matched by name and not checked one by one.
- The build checks at every fetch that openFDA's terms page still names the same dedication, and stops if it does not.

## How the text is packed

SQLite has no compression of its own. Long text is therefore packed into blocks of about half a megabyte, each compressed with whichever of the standard library's codecs makes it smallest (zlib, bz2 or lzma), and a piece is found again by block, start and length. The health topic summaries come out about four times smaller for it, the product labels seven times, and the ICD-11 records, which repeat each other a great deal, thirteen times. Reading one costs one block: a few milliseconds.

## Databases to come

| File | What it will hold | Source | Licence |
|---|---|---|---|
| `region-pl.db` | the Poland pack | to be confirmed source by source | to be confirmed |

Each licence is checked again, and the date written down here, before its file is built. A source whose terms do not clearly allow its data to be passed on in a public repository and in the packed skill is left out.
