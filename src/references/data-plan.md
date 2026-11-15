# Data plan

The databases Voss answers from. The first part of the toolkit and the core database are built (package 0.8.0); the others are not yet. Licence facts marked "verified" were checked on 14 November 2026, and those of the core data again on 15 November 2026, on each source's own page; everything marked "to check" must be confirmed before that source ships. Where a source's terms do not clearly allow its data to be passed on in a public repository and in the packed skill, the data stays out. [maker]

## Principles

1. Offline: standard-library Python over read-only SQLite. Nothing is fetched while the tools run.
2. Every row traces to a source: a `meta` table in each file holds the source name, download URL, retrieval date and licence.
3. One database file per licence family, attached together at runtime, each with its own `LICENSE-*.txt`. The code stays MIT.
4. A build script per source names every download, so anyone can rebuild from scratch.
5. English core, plus optional region packs (country-specific registers, services and numbers).
6. Shareable: the public repository holds the code, the build scripts and the built databases, which sit in `scripts/data/` inside the package. [maker] Supersedes shipping the databases separately as GitHub Release assets.

What every database carries: a `meta` table with one row for each source (`source`, `url`, `retrieved` as YYYY-MM-DD, `licence`, and where the licence asks for one a `credit` line), and a `build` table of key and value whose `built` is the day the file was made. The banner's status is the oldest `built`. Staleness is counted from the oldest `retrieved`, because a file built today from old downloads is still old. A file without these, or without its `LICENSE-*.txt` beside it, is not answered from.

## Sources

| Source | Gives | Licence | Status |
|---|---|---|---|
| MedlinePlus health topic XML (NLM) | plain-English health topic summaries, synonyms, MeSH terms | health topic summaries are public domain; credit "Source: MedlinePlus, National Library of Medicine" | verified; checked again 15 November 2026; built into core-pd.db |
| ICD-11 (WHO) | diagnosis codes and titles | CC BY-ND 3.0 IGO: verbatim only, attribution, no implied WHO endorsement; crosswalks to other code systems need a separate WHO agreement | verified |
| DDInter 2.0 | drug-drug, drug-food and drug-disease interactions, therapeutic duplications | CC BY-NC-SA 4.0: attribution, non-commercial, share-alike | verified via the BioThings plugin's note; confirm on DDInter's own terms page |
| RxNorm (NLM) | drug name normalisation | free API; licence of the bulk files to check (some RxNorm sources need a UMLS licence) | to check |
| DailyMed / openFDA labels | US product labels | US government data; terms to check | to check |
| Rejestr Produktów Leczniczych (Poland) | Polish medicines: substance, strength, Rx or OTC, ATC code | public search exists; bulk export format and terms of use to check | to check |
| NFZ API Terminy Leczenia (Poland) | waiting-list sizes and first free appointment dates per provider | open data via dane.gov.pl; terms to check | to check |
| Emergency numbers | per-country numbers, with what each is for where the source says | Wikidata (CC0), property P2852 | checked 15 November 2026; built into core-pd.db |

Facts worth keeping:
- MedlinePlus: the A.D.A.M. Medical Encyclopedia and the ASHP drug monographs are copyrighted and licensed to NLM only; they must never be ingested. Topics come in English and Spanish only, so Voss explains them in other languages himself.
- ICD-11: converting it into SQLite counts as a change of format, which no Creative Commons licence treats as an adaptation. Rewording it or making a translation of our own does count. Polish paperwork probably still uses ICD-10: to check before the Polish pack.
- NLM's drug-drug interaction API was discontinued on 2 January 2024. Old tutorials still point at it.
- DDInter 2.0 covers 302,516 drug-drug interactions, 857 drug-food interactions, 8,359 drug-disease interactions and 6,033 therapeutic duplications across 2,310 drugs. Its literature stops at May 2023. Its non-commercial term also covers extraction and reuse of the contents.
- Lab reference ranges: deliberately none. They differ between labs and methods; Voss reads the range on the person's own report.
- MedlinePlus, from the check of 15 November 2026: the same page offers five small "Definitions of Health Terms" files, each term with the NIH body it comes from; they are in the core database beside the topics. The topic file's links to other organisations' pages, its Spanish topics and its pictures are left out. MedlinePlus's medical test pages are public domain as well, but there is no file of them, only the pages: not taken.
- The MeSH headings that come with the topics are used as names to find a topic by. NLM asks that it be named as their source, that no endorsement be implied, and that a copy which is not current says so.
- Emergency numbers: Wikidata lists them country by country, most with what the number is for (police, fire department, emergency medical services). They are passed through as listed and not verified one by one, and the tool says so. Inside the European Union 112 is put first, on the European Commission's word that it reaches every emergency service there; where Wikidata does not list 112 for a member state it is added, with that source.
- Wikidata's query service turned unnamed scripts away on 15 November 2026 (a rule made during an outage), so the build reads the ordinary API instead: a few hundred small requests, slowly. Wikimedia asks scripts to name who runs them; the build does not do that for anyone, and takes such a line from the `VOSS_BUILD_AGENT` environment variable if one is set.

## File layout

```
voss/
  SKILL.md
  references/
  playbooks/
  images/
  scripts/
    voss.py                  one entry point, subcommands below
    vosslib/
    data/
      personal.template.json public: empty template
      personal.json          PRIVATE ONLY: never committed (see personal-file.md)
      SOURCES.md
      core-pd.db             MedlinePlus summaries (public domain)
      icd11.db               ICD-11, verbatim
      ddinter.db             DDInter 2.0
      region-pl.db           Poland pack
      LICENSE-core-pd.txt
      LICENSE-icd11.txt
      LICENSE-ddinter.txt
      LICENSE-region-pl.txt
```

In the repository the package is `src/`, and the build scripts (`build_core.py`, `build_icd11.py`, `build_ddinter.py`, `build_labels.py`, `build_region_pl.py`) are in `tools/`, outside it. Superseded: the first layout kept the databases in a `data/` folder of their own, outside git, and the build scripts inside the package.

DDInter keeps its distinct mechanism and management texts once each, with interactions stored as integer pairs pointing at them, so the file stays small. Check every built file against the limit below.

Keeping the files small. SQLite has no compression of its own, so the build does it: long text is packed into blocks of about half a megabyte, each compressed with whichever standard-library codec makes it smallest (zlib, bz2 or lzma), and a piece of text is found again by block, start and length. The same text is stored once. Measured on the health topic summaries: about four times smaller, and a few milliseconds to read one. A database that still comes out over the limit is cut into parts. [maker]

## GitHub

- Normal git history: a warning above 50 MiB per file, a hard block above 100 MiB.
- Release assets: up to 2 GiB each, with no cap on total size or bandwidth.
- So: the databases live in the repository, and no file in it may be larger than 49 MB; the build refuses one that is. [maker] A file that cannot be brought under that goes out as a Release asset after all. That is decided file by file, once each has been built and its size is known. [maker] Superseded: the databases were to go out as Release assets, with the repository holding only code, scripts and text.
- README carries the intended-purpose statement from `clinical-rules.md` and every attribution line.

## Staleness limits [pending]

| File | Warn when older than |
|---|---|
| region packs (registers, waiting lists) | 1 month |
| ddinter.db | 12 months, or when a new DDInter release appears |
| core-pd.db | 6 months |
| icd11.db | when WHO publishes a new annual release |

## Planned commands

| Command | Reads | Notes |
|---|---|---|
| boot | all | prints the banner, the mode and the data status |
| assess | core-pd, personal | Clinic: history prompts and a three-tier record (most likely, worth considering, must not miss) with sources and the closing line |
| theatre | none | switches mode and prints the banner |
| term | core-pd | plain-English topic summary with its credit line |
| code | icd11 | verbatim code and title |
| med | core-pd, region | substance, class, use; never a dose |
| interact | ddinter | severity, mechanism, management, source; "nothing on file" worded as such |
| labs | none | explains a test; compares a value only to a range the person supplies |
| triage | built-in list, core-pd | red flags and the four levels; a country's emergency numbers |
| visit | none | question list and symptom diary template |
| find | region | where to get care |
| schedule | none | medicine schedule as an .ics file |
| sources | all | what is installed, licences, ages |
| check | none | typography and reply audit |
| selftest | all | integrity checks |
| intake | personal | gathers or updates a profile a few questions at a time; reads back before saving |
| profile | personal | shows what is on file, after the gate |
| ignition | personal | the identity gate, judged by the tool so Voss never sees the answers |
| rebuild | personal | writes a new private package with the changed personal file |
| forget | personal | removes a field or a profile completely |

Feature commands (diary, brief, refill, result, trend, watch, firstaid, desk, translate, card, pet, recipe, scale, season, myth) and the sources they still need are in `features.md`.

Built in 0.8.0: boot, theatre, term, labs, triage, visit, schedule, sources, check, selftest, intake, profile, ignition, rebuild and forget, with refill from the feature commands and `tools`, the index of them all. `labs` still carries no account of what a test measures: where a health topic covers a test, `term` finds it.

## Build order (cheapest first)

1. Skeleton (built, 0.8.0): `voss.py`, `boot`, `sources`, `triage`, `visit`, `labs`, `schedule`, and the personal file (`ignition`, `intake`, `profile`, `rebuild`, `forget`). No downloads. The public build refuses `personal.json` and `household.md`, and runs the leak check (household.md's leak words against every public file).
2. Core (built, 0.8.0): MedlinePlus summaries and definitions, and emergency numbers. Small, public domain and CC0. `tools/build_core.py`.
3. ICD-11.
4. DDInter, after confirming its terms.
5. Poland pack, after confirming the register's and NFZ's terms.

## Source pages consulted (14 November 2026)

- MedlinePlus copyright: https://medlineplus.gov/copyright.html
- MedlinePlus XML files: https://medlineplus.gov/xml.html
- ICD-11 licence: https://icd.who.int/docs/icd-api/license
- ICD-11 terms of use: https://icd.who.int/en/docs/ICD11-license.pdf
- WHO-FIC Interoperability Hub: https://www.who.int/standards/classifications/who-fic-interoperability-hub
- RxNav FAQs: https://lhncbc.nlm.nih.gov/RxNav/information/FAQs.html
- DDInter 2.0 paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC11701621/
- DDInter in Database Commons: https://ngdc.cncb.ac.cn/databasecommons/database/id/7473
- BioThings DDInter plugin: https://github.com/biothings/DDInter
- NFZ API Terminy Leczenia: https://www.nfz.gov.pl/o-nfz/programy-i-projekty/projekt-otwarte-dane-dostep-standard-edukacja-api-terminy-leczenia,10.html
- Rejestr Produktów Leczniczych: https://rejestrymedyczne.ezdrowie.gov.pl/rpl/
- GitHub large files: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
- Creative Commons and format changes: https://ecampusontario.pressbooks.pub/oer4students/?p=634
- Creative Commons 4.0 and database rights: https://wiki.creativecommons.org/4.0/Sui_generis_database_rights

## Source pages consulted (15 November 2026, for the core data)

- MedlinePlus, linking to and using its content: https://medlineplus.gov/about/using/usingcontent/
- MedlinePlus XML files: https://medlineplus.gov/xml.html
- NLM terms and conditions for MeSH: https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html
- Wikidata copyright: https://www.wikidata.org/wiki/Wikidata:Copyright
- Wikidata, emergency phone number (P2852): https://www.wikidata.org/wiki/Property:P2852
- European Commission, 112: https://digital-strategy.ec.europa.eu/en/policies/112
