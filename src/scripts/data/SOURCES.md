# Where the data comes from

Every table the tools read is in this folder. Nothing is fetched while the tools run.

A database sits here as `<name>.db` with its licence text beside it as `LICENSE-<name>.txt`. It carries its own record of source, address, retrieval date and licence, and `python scripts/voss.py sources` prints all of that, with each file's age. One database per licence family, so that the terms of one source never reach another. Every one of them is optional: take a file and its licence text out, and the commands that read it say that nothing is installed, and the rest carry on.

The terms of every source below were read on that source's own page on 15 November 2026. Where terms could change under a file (ICD-11, DDInter, openFDA, the pages behind `advice-by.db`, Wikipedia), its builder reads them again each time it fetches, and stops if they are no longer the ones that were read.

| File | What it holds | Source | Licence |
|---|---|---|---|
| `core-pd.db` | health topic summaries and short definitions in plain English; emergency numbers by country | MedlinePlus health topic XML and "Definitions of Health Terms" XML (National Library of Medicine); Wikidata, property P2852; one fact from the European Commission's page on 112 | public domain and CC0: see below, and `LICENSE-core-pd.txt` |
| `icd11.db` | ICD-11 for Mortality and Morbidity Statistics: every code and grouping with its title and URI, whole and unchanged | the "Simple Tabulation" release file of the World Health Organization | CC BY-ND 3.0 IGO with WHO's terms of use: see below, and `LICENSE-icd11.txt`. Not under the code's licence |
| `ddinter.db` | pairs of medicines that are known to interact, each with a severity grade; other names for the medicines | DDInter 2.0, its download files; Wikidata for the other names | CC BY-NC-SA 4.0 (non-commercial, share-alike): see below, and `LICENSE-ddinter.txt`. Not under the code's licence. The names are CC0 |
| `labels-us.db` | product labels of medicines sold in the United States: what each is for, its warnings, side effects and interactions, in the label's own words; other names for the substances | openFDA drug labels (United States Food and Drug Administration); Wikidata for the other names | CC0: see below, and `LICENSE-labels-us.txt` |
| `advice-by.db` | short passages of published guidance, in their sources' own words: what may be dangerous to a pet, breaks from a screen, what a first-aid kit may hold, when the flu vaccination is given | one page of the U.S. Food and Drug Administration, two of the Health and Safety Executive (Great Britain), one of nidirect (Northern Ireland) and one of ECDC | public domain, Open Government Licence v3.0 and CC BY 4.0: see below, and `LICENSE-advice-by.txt` |
| `firstaid-sa.db` | first aid as Wikipedia has it: CPR, the recovery position, bleeding, burns and choking, each passage from one named revision of an article | five articles of the English Wikipedia | CC BY-SA 4.0 (share-alike): see below, and `LICENSE-firstaid-sa.txt`. Not under the code's licence |
| `triage.json` | the four triage levels and the red flags | written for this skill; word for word from `references/clinical-rules.md` | MIT, with the code |
| `visit.json` | what to ask a doctor, what to bring, the symptom diary's columns | written for this skill as general advice; the diary columns are those in `references/features.md` | MIT, with the code |
| `stay.json` | what to think of before a planned stay in hospital | written for this skill as general, practical advice; no hospital's list, and nothing about what to do before a procedure | MIT, with the code |
| `recipes.json` | Voss's baking recipes, in grams, with allergens | written for this skill; marked untested until someone has baked them | MIT, with the code |
| `fields.json` | the personal file's fields, with what each holds and why a doctor asks | written for this skill; the wording is that of `references/personal-file.md` | MIT, with the code |
| `personal.template.json` | the empty shape of a personal file | written for this skill | MIT, with the code |
| `commands.json` | the command index | generated from the commands by `tools/build_index.py` | MIT, with the code |
| in the tools | check digits for the numbers Voss refuses to keep (payment cards, bank accounts, two national number formats) | the published algorithms: Luhn (ISO/IEC 7812), ISO 13616 for IBAN, the PESEL and NHS number check digits | public methods, no data taken |
| in the tools | the calendar file format | RFC 5545 (iCalendar) | a public standard |

## core-pd.db

Built by `tools/build_core.py`, which names every download.

- **MedlinePlus health topic summaries.** Public domain. NLM's page "Linking to and Using Content from MedlinePlus" (https://medlineplus.gov/about/using/usingcontent/) says: "Works produced by the federal government are not copyrighted under U.S. law. You may reproduce, redistribute, and link freely to non-copyrighted content", and lists the "Summaries on health topic pages" among it. It asks for the credit "Source: MedlinePlus, National Library of Medicine", which every answer from this file carries. The XML page (https://medlineplus.gov/xml.html) says the data sets are ones "you are welcome to download and use".
- **MedlinePlus "Definitions of Health Terms".** Five small XML files on the same page, each term with the NIH body it comes from. Same terms, same credit.
- **Medical Subject Headings (MeSH)** arrive with the topics and are used as names to find a topic by. NLM's terms for MeSH (https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html) ask that NLM be named as the source, that no endorsement be implied, and that a copy which is not current says so: the tool names NLM, and prints the day the file was retrieved.
- **Not taken, on purpose:** the links to other organisations' pages, the Spanish topics, and every picture. MedlinePlus's pages on medical tests are public domain as well, but they come as pages only and not as a file, so they were not taken either. **Never to be taken:** the A.D.A.M. Medical Encyclopedia and the ASHP drug monographs, which the same page says are copyrighted and licensed to MedlinePlus alone.
- **Wikidata.** Emergency numbers by country, property P2852, with what each number is for where Wikidata says. "All structured data from the main, Property, Lexeme, and EntitySchema namespaces is available under the Creative Commons CC0 License" (https://www.wikidata.org/wiki/Wikidata:Copyright). The numbers are passed through as listed and were not verified one by one; the tool says so each time.
- **European Commission.** One fact, with its source: 112 reaches an ambulance, the fire brigade or the police anywhere in the European Union (https://digital-strategy.ec.europa.eu/en/policies/112). No text of the page is reproduced. The build checks at every fetch that the page still says it.

Changed in the making: a summary's HTML becomes plain text, and curly quotes and long dashes become straight ones. No wording is changed.

## icd11.db

Built by `tools/build_icd11.py` from WHO's release file, which needs no account: `https://icdcdn.who.int/static/releasefiles/<release>/SimpleTabulation-ICD-11-MMS-en.zip`. The licence is WHO's "Terms of Use and License Agreement" (https://icd.who.int/en/docs/icd11-license.pdf, dated 7 October 2025).

- **The licence** is Creative Commons Attribution-NoDerivs 3.0 IGO (clause 1.2): the classification may be copied and passed on, with attribution, and may not be adapted.
- **Software.** Clause 1.2.2: "WHO does not consider incorporation of the Classifications into a software product to be an 'adaptation'", provided it is not distributed under a different name or without attribution, without the codes, or without the URIs. Clause 1.2.3: it "must include Classifications code, title and URI". Every entry here has all three.
- **No translations, no mappings.** Clause 1.2.4: "Mapping or producing crosswalks between other classifications and terminologies and Classifications and producing translations are not covered by the Classifications License and are subject to a separate written agreement from WHO." There is no translation and no table to ICD-10 or anything else in this file, and none may be added.
- **Additions** must be "clearly identified as additions that do not originate from WHO" (clause 1.2.5). The table that lets a record be found (its position, its parent's, and its code, kind and chapter copied out) is named as such in `LICENSE-icd11.txt`. No title is copied anywhere: a title is read from WHO's own record each time.
- **Attribution** is WHO's own wording (clause 1.3), printed with every answer. **No endorsement**: WHO's name is used to say where the classification comes from and for nothing else (clause 4.1).
- **Nothing is changed.** Every record of WHO's file is stored whole. `python tools/build_icd11.py --verify` puts the file back together from the database and compares it with the download byte for byte, the build does the same before it writes anything, and the tests check the shipped file against the checksum taken at the build.
- **What is not in it:** descriptions, definitions and index terms. The release file carries codes, titles and structure only.
- WHO is preparing an updated licence. The build checks, by checksum, that the licence document is still the one that was read, and stops if it is not.

## ddinter.db

Built by `tools/build_ddinter.py`. DDInter's own terms page (https://ddinter2.scbdd.com/terms/) says: "The DDInter data is made available under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license."

- **What that means here.** The file may be passed on with DDInter's credit, under the same licence, and not for commercial purposes. It is kept in a file of its own for that reason, apart from the MIT code and from the other databases. Anyone who uses the skill commercially has to take this one file out; the tools then say that no interaction data is installed.
- **Why it does not bind the rest.** The licence covers "the artistic or literary work, database, or other material to which the Licensor applied this Public License" (section 1), and its share-alike condition applies "if You Share Adapted Material You produce" (section 3(b)). Creative Commons' own answer on collections: "CC licenses do not require the collection or the compilation itself to be made available under an SA license, even though each individual work is still licensed individually under an SA license" (https://creativecommons.org/faq/). So the non-commercial and share-alike terms stay with this file. The code and the other databases keep their own terms.
- **Credit**, printed with every answer: DDInter 2.0 (https://ddinter2.scbdd.com/). Tian Y, Yi J, Wang N, Wu C, et al. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic Acids Research 53(D1):D1356, doi:10.1093/nar/gkae726.
- **What was changed:** the eight download files were merged into one list of pairs, a pair listed twice is stored once, the grade is stored as a number, and the pairs are stored packed, each medicine with the numbers of the medicines it is paired with. No pair and no grade was added, removed or altered.
- **How current it is.** DDInter's paper says of its reading: "For DDInter 2.0, we collected publications between March 2021 and May 2023." Whatever was found out about a pair after that is not in it, however new the copy.
- **What DDInter's downloads hold, and what they do not.** The paper counts 302,516 interaction records between 2,310 medicines, with 857 records on food, 8,359 on illnesses and 6,033 on duplicated treatments. The downloads hold less. Pairs of medicines with a grade (Major, Moderate, Minor, Unknown): 160,235 pairs of 1,939 medicines on the day of the build. No account of why two medicines interact or what to do about it, and nothing on food, illnesses or duplicated treatments: those are on DDInter's website only, and are not taken from it. And only eight of the fourteen ATC groups have a download (A, B, D, H, L, P, R, V), so a pair of two medicines from the other groups is not in the file at all. The tools say this every time, and never let "not listed" read as "safe". The files also show which medicines are outside those groups: one whose pairs are spread over several files, with no file holding them all, is in none of the groups that have a download (903 of the 1,939). A pair of two such medicines is reported as out of the file's reach, since it could not be there whether or not the two interact.
- **Other names.** DDInter has one name for each medicine, sometimes the American one. So that "paracetamol" finds "Acetaminophen", the English and Polish labels and aliases of Wikidata items that carry an ATC code (property P267, CC0) are added where an item's English name is the DDInter name and no other item's. They were matched by name, not checked one by one, and the tools say what each name was read as.

## labels-us.db

Built by `tools/build_labels.py` from openFDA's drug label download (https://open.fda.gov/apis/drug/label/download/). The terms are openFDA's (https://open.fda.gov/terms/ and https://open.fda.gov/license/).

- **The licence.** "Unless otherwise noted, the content, data, documentation, code, and related materials on openFDA is public domain and made available with a Creative Commons CC0 1.0 Universal dedication. ... You can copy, modify, distribute, and perform the work, even for commercial purposes, all without asking permission." Data that is not covered is "clearly marked by a warning in the relevant documentation"; the drug label documentation (https://open.fda.gov/apis/drug/label/) carries no such warning.
- **Credit.** FDA asks, "while not required", for: "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)". Every answer carries it. "When using or citing the work, you should not imply endorsement": FDA does not endorse this skill, and the licence text says so.
- **What a label is,** in FDA's words on the same page: the labels "represent the most recent drug listing information companies have submitted", their "content has neither been altered nor verified by FDA", and they "may not be the labeling on currently distributed products or identical to the labeling that is approved". The tools say this every time.
- **What is kept.** Of 264,748 labels on the day of the build, the 9,168 that are one each for a substance, a type (prescription or over the counter) and a route: only labels FDA has matched to a product, the fullest one of each kind, an original maker's before a copy. Of each label, the sections on what it is for, the boxed warning, who must not take it, warnings, side effects, interactions, pregnancy and other groups, and the texts for patients; with them its maker, its class, its date and the number that leads to its page.
- **Brand names.** Every brand name the labels of a kind carry is kept (37,460), so that a medicine is found under the name on the pack. Left out are only the ones that say no more than the substance does ("Ibuprofen Tablets 200 mg"). One name can be on packs of different medicines; the tools then list them and read the name as none of them.
- **What is in a product** is FDA's own list of substances. For 1,653 labels FDA gives none: packs of two kinds of tablet, as a rule, contraceptive pills among them. Such a label is kept when its generic name reads as a list ("norgestimate and ethinyl estradiol") and every part of it is a substance FDA lists for another label, a medicine Wikidata knows by that name, or a name used under at least three separate approvals. 276 labels fit none of that and are left out, a few newer medicines among them: nothing is guessed. Where such a label gives no route either, it is counted with the labels of the same substances that do, if those agree; otherwise its route reads "route not given".
- **What is left out on purpose: the dose.** A dose comes from the label of the product in the person's hand. Also left out: how the medicine works, the studies, the chemistry, how it is supplied.
- **Changed in the making:** line breaks tidied, curly quotes and long dashes made straight. No wording was changed.
- **American labels.** A medicine sold under the same name elsewhere may have other uses, strengths and warnings. The tools say that too.
- **Other names** for the substances come from the same Wikidata file the interaction data uses (CC0), matched by name and not checked one by one.

## advice-by.db

Built by `tools/build_advice.py`. Every source in it asks to be named and for nothing more, so the passages may be passed on, commercially too, each with its credit. A passage is taken whole and word for word, with the page it stood on and the day that page says it was last changed.

- **What may be dangerous to a pet.** U.S. Food and Drug Administration, "Potentially Dangerous Items for Your Pet" (https://www.fda.gov/animal-veterinary/animal-health-literacy/potentially-dangerous-items-your-pet). Public domain. FDA's website policies (https://www.fda.gov/about-fda/about-website/website-policies) say: "Unless otherwise noted, the contents of the FDA website (www.fda.gov) - both text and graphics - are not copyrighted. They are in the public domain and may be republished, reprinted and otherwise used freely by anyone without the need to obtain permission from FDA. Credit to the U.S. Food and Drug Administration as the source is appreciated but not required." Taken: the lists of food, household things and plants, and what the page says about how toxicity varies and about acting quickly. Not taken: the American telephone numbers.
- **Breaks from a screen, and the first-aid box at work.** Health and Safety Executive (Great Britain): "Work routine and breaks" from its guide to display screen equipment (https://www.hse.gov.uk/msd/dse/work-routine.htm), and two answers from its questions on first aid at work (https://www.hse.gov.uk/firstaid/faqs.htm). HSE's copyright page (https://www.hse.gov.uk/help/copyright.htm) says: "You may re-use the Crown material featured on this website free of charge in any format or medium, under the terms of the Open Government Licence", and gives the acknowledgement it prefers, which every answer carries.
- **A first-aid kit for the home.** nidirect (Northern Ireland Executive), "First aid" (https://www.nidirect.gov.uk/articles/first-aid). Its page on Crown copyright (https://www.nidirect.gov.uk/articles/crown-copyright) says: "You may use and re-use the information featured on this website (not including logos) free of charge in any format or medium, under the terms of the Open Government Licence".
- **The Open Government Licence v3.0** (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) lets anyone "copy, publish, distribute and transmit the Information", "adapt the Information" and "exploit the Information commercially and non-commercially". It asks for the source to be acknowledged, and gives no right to suggest "any official status or that the Information Provider and/or Licensor endorse you". None of these bodies endorses this skill.
- **When the flu vaccination is given.** European Centre for Disease Prevention and Control, "Timing of influenza vaccination" (https://www.ecdc.europa.eu/en/seasonal-influenza/prevention-and-control/vaccines/timing). ECDC's notice (https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices) says that what it publishes is "licenced in accordance with the CC BY 4.0 licence", on condition that ECDC is named as the creator, that the licence is linked, and that changes are indicated. The text is unchanged.
- **Whom each was written for.** Pet owners in the United States, employers in Great Britain, households in Northern Ireland, health authorities in Europe. The tools say so, and none of it is a rule for the person asking.
- **Changed in the making:** HTML became plain text, and curly quotes and long dashes became straight ones. No wording was changed.

## firstaid-sa.db

Built by `tools/build_firstaid.py` from the English Wikipedia, through its API. Wikipedia's page on reusing its content (https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content) says that its text "can be used under the terms of the Creative Commons Attribution Share-Alike license (CC BY-SA)".

- **What that means here.** The file may be passed on, commercially too, with a link to each page it draws on and the name of the licence, and whatever is made from it has to carry the same licence. It is kept in a file of its own for that reason. As with `ddinter.db`, the condition stays with the file: a collection does not take on a share-alike licence because one work in it has one.
- **Credit.** Wikipedia asks for "a hyperlink (where possible) or URL to the page or pages you are re-using". Each passage carries the address of the exact revision it was taken from, and every answer prints it.
- **Why Wikipedia.** No first-aid body's guideline was found whose terms allow it to be passed on. The NHS website no longer has first-aid pages of its own: on 15 November 2026 their addresses led to St John Ambulance. The Health and Safety Executive's leaflet "Basic advice on first aid at work" would come under the Open Government Licence, but it is a PDF document, which the standard library cannot read.
- **What it is, and what it is not.** An encyclopaedia's account of what first-aid bodies teach. It is not a guideline, anyone can edit it, and parts of it are dated. The tools say so every time, and the instructions of an emergency operator come first.
- **The revisions are pinned.** The builder names the revision of each article that was read, passage by passage, before it went in, and fetches exactly that one. A newer revision is fetched only to be read (`--fetch --latest --show`), and goes in once its number has been written into the builder.
- **What was left out.** Sections that are not first aid, and sections that say something no first-aid body teaches: the article on choking, as read, suggests reaching into an unconscious person's throat with kitchen tools. The build stops if such words turn up in a passage.
- **Taken:** from "Cardiopulmonary resuscitation", the order of CPR in a first-aid sequence, compressions with rescue breaths, and compression only; from "Recovery position", the opening and its purpose; from "Emergency bleeding control", direct pressure and the tourniquet; from "Burn", the first two paragraphs on wound care, which are the ones on cooling; from "Choking", the general strategy, coughing, back blows, abdominal thrusts, chest thrusts, and infants.
- **Changed in the making:** HTML became plain text, footnote marks were dropped, and curly quotes and long dashes became straight ones. No wording was changed.

## How the data is kept small

The whole skill has to stay under 30 MB unpacked, which is the most a skill may weigh when it is uploaded through the API. SQLite has no compression of its own, so the builders do it.

- **Long text** is packed into blocks, each compressed with zlib or lzma, whichever is smaller, and a piece is found again by block, start and length. The same text is stored once. The health topic summaries come out about four times smaller for it, the product labels between eight and nine times, and the ICD-11 records, which repeat each other a great deal, thirteen times.
- **Blocks are sized by how the text is read.** What `med` prints unasked sits label by label in blocks of a megabyte, and what `sidefx` searches sits label by label in blocks of four, so each of those answers opens one block. The long sections that are read only when asked for sit kind by kind in blocks of eight, which squeeze hardest. Opening a block costs about six milliseconds a megabyte.
- **Tables hold numbers** where a word would repeat, and nothing is stored twice: a label's substances are in one table, a title of ICD-11 is in WHO's record and nowhere else, and a medicine's interaction partners are packed into a few bytes each.
- **The two small files of passages** keep their text as it is: there is too little of it to be worth packing.

## How old a file may get

A copy goes out of date. Each database has a limit, counted from the day the oldest of its sources was retrieved: a file built today from old downloads is still old. Past its limit a file is still answered from, but the tools print a STALE line first, and Voss says so before the answer. `python scripts/voss.py sources` shows every file's age beside its limit.

| File | Warn when older than |
|---|---|
| `core-pd.db` | 12 months |
| `labels-us.db` | 12 months |
| `ddinter.db` | 24 months, or when a new DDInter release appears |
| `advice-by.db` | 12 months |
| `firstaid-sa.db` | 12 months |
| `icd11.db` | when WHO publishes a new yearly release. The tools cannot see that from here, so they say it each time and never call the file stale |

## Looked at and left out

- **Anything about one country.** Where to get care, what a patient is owed, a national register of medicines, waiting times: none of it is on file for any country. Such data changes by the day and would have to be kept up for each country in turn. `find` lists what to establish, and Voss looks it up and cites it.
- **A first-aid body's own guideline.** None was found whose terms allow it to be passed on, so first aid is Wikipedia's account: see `firstaid-sa.db` above.
- **Help for carers.** Nothing was found that is not about one country.
- **Reference ranges for lab tests.** None, on purpose. They differ between labs and between methods, so a value is read against the range printed on the person's own report and against nothing else.
- **Product information from outside the United States.** European and national leaflets and summaries of product characteristics come as PDF documents, which the standard library cannot read.
- **RxNorm** (National Library of Medicine), for the names of medicines. Not used: parts of it need a licence of their own, and its terms were never read for this skill. Other names for a medicine come from Wikidata.
- **The National Library of Medicine's interaction service.** "RxNav's drug/drug interaction features were discontinued on January 2, 2024" (https://lhncbc.nlm.nih.gov/RxNav/information/FAQs.html). Older guides still point at it; there is nothing there to take.

A source whose terms do not clearly allow its data to be passed on in a public repository and in the packed skill is left out.
