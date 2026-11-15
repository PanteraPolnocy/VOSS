Pull requests are always welcomed, same as reporting issues with the code here (via GitHub, e-mail or Discord). ~

This repository will not host anything that is even remotely harmful to the users.

## Before you send a change

- `python tests/test_voss.py` passes.
- `python tools/build.py` passes. It checks the source and packs `dist/voss.zip`.
- A new or re-described command has worked examples in its help, and `python tools/build_index.py` has been run after it. Every example is run by the tests.
- A new figure names its source on the line that prints it, and the source is listed in `src/scripts/data/SOURCES.md` with its licence. Nothing is quoted from memory, and no data goes in whose licence does not allow passing it on.
- The doctrine, the clinical rules and the hard rules in `src/SKILL.md` are never weakened, by code or by documentation. Anything that changes who Voss is, what he may do, or which features he has is put to the maker first, and carries the tag `[pending]` until she has ruled.
- Voss is an original character. Nothing here compares him with any other fictional doctor or android.
- **No personal data, anywhere.** Never commit a `personal.json`, a `household.md`, or a package Voss rebuilt for you. Tests use made-up people only. An error message names the argument that was wrong and never repeats what was typed: it may be somebody's date of birth.

## House rules for the code

Python 3.9 compatible, standard library only, plain ASCII in code and comments, no network at run time, British English in anything a user reads. Straight quotes and the plain hyphen only, in code and in text. SQL is always parameterised. All arithmetic that a person will rely on (ages, refills, dates) is done by code, exactly, and tagged `[derived]`.

## The scripts

```
python tests/test_voss.py                 the test suite
python tools/build.py                     checks the source and packs dist/voss.zip
python tools/build.py --private --out DIR also packs the private build into DIR, outside this repository
python tools/build_index.py               rewrites the command index after a command is added or re-described
python tools/ascii_escape.py              puts non-ASCII characters in Python sources back into escapes
python tools/build_core.py --fetch        downloads the sources of core-pd.db and builds it again
python tools/build_icd11.py --fetch       downloads WHO's release file and builds icd11.db again
python tools/build_icd11.py --verify      checks that icd11.db still gives WHO's file back, byte for byte
```

## The public build, the private build and the leak check

Two files are private and never go into this repository: `src/references/household.md` (a household: names, places, other minds) and `src/scripts/data/personal.json` (patients). So is anything in `src/images/private/`. `.gitignore` lists all three, and the build checks that it does, and that git is not already tracking them.

The public build works on a copy of `src/` that leaves those out, so they cannot be packed by accident even when they are sitting in the folder. It then runs the leak check. The household file ends with a section headed "Leak words": a list of words and phrases, one to a line. Each is looked for, as a whole word and in any case, in every file of the package and in every other file git would publish from this repository, file names and picture metadata included. One hit and nothing is packed; the build prints the file and the line. Two places are passed over, because they are signed with the author's name: `LICENSE`, and the one line under Credits in `README.md` that says whose work Voss is.

The household file is found through the `VOSS_HOUSEHOLD` environment variable, or at `src/references/household.md` if a copy was dropped in. With neither, the build runs every other check and says the leak check was skipped: run it with the real file before anything is published. `tests/fixtures/household.example.md` is a made-up one to try it with.

The private build (`--private --out DIR`) adds the household file and the personal file (`VOSS_PERSONAL`, or the copy under `src/`) on top of the public files and writes `voss-private.zip` into a folder outside any git repository.

## Databases

A database lives in `src/scripts/data/` as a single SQLite file, with its licence text beside it as `LICENSE-<name>.txt` and a row in `SOURCES.md`. The tools open it read-only. It must carry two tables, and is not answered from without them:

- `meta`, one row for each source: `source`, `url`, `retrieved` (YYYY-MM-DD), `licence`, and `credit` where the licence asks for a credit line.
- `build`, of `key` and `value`: `built` is the day the file was made.

The banner shows the oldest `built`; a file's age is counted from its oldest `retrieved`. One database per licence family, so that a share-alike or no-derivatives licence never spreads to a file it does not belong to. No file in this repository may be larger than 49 MB, and the build refuses one that is; it prints the size of every database it packs.

Each database has a builder in `tools/` (`build_core.py` is the first) that names every address it downloads from, keeps the downloads in `downloads/` (which git ignores) with a note of the day beside each, and can be run again by anyone. `tools/dbtools.py` holds what the builders share. Before a source goes in, read its terms on its own page, and write what you found and the date into `SOURCES.md`. If the terms do not clearly allow the data to be passed on in a public repository and inside the packed skill, it stays out: ship the builder without the data, and say so.

`icd11.db` has rules of its own, because WHO's licence allows no adaptation. Nothing in it may be reworded, shortened, re-ordered, translated or mapped to another code system, and nothing may be added to an entry that is not marked as not WHO's. Do not add a translated title, an ICD-10 column or a "plain English" gloss to that file, however useful it looks: put such a thing somewhere else, under its own source and licence, or leave it out.

Long text is not stored row by row. The builder packs it into blocks, compresses each block with whichever of zlib, bz2 and lzma makes it smallest, and stores where each piece sits; `vosslib/store.py` reads it back. That is why a database here is a fraction of the size of its text.

The builders send a plain client name and nothing about you or this project. Wikidata asks scripts to say who runs them and is slow with those that do not, so its part of `build_core.py --fetch` can take the better part of an hour. If you want it faster, put a line of your own in the `VOSS_BUILD_AGENT` environment variable, as their policy describes.

## Why a call is fast

A call loads only the module its command lives in, which it finds in `scripts/data/commands.json`; that is why the index must match the commands (the build and the tests both check). Where the skill's folder is read-only, Python cannot keep its compiled files beside the scripts, so `voss.py` points it at a folder of its own in the temp directory instead (`VOSS_NO_CACHE=1` turns that off).
