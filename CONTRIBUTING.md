Pull requests are always welcomed, same as reporting issues with the code here (via GitHub, e-mail or Discord). ~

This repository will not host anything that is even remotely harmful to the users.

## Before you send a change

- `python tests/test_voss.py` passes, on Python 3.9 as well as on the one you use.
- `python tools/build.py` passes. It checks the source and packs `dist/voss.zip`.
- A new or re-described command has worked examples in its help, and `python tools/build_index.py` has been run after it. Every example is run by the tests.
- A new figure names its source on the line that prints it, and the source is listed in `src/scripts/data/SOURCES.md` with its licence. Nothing is quoted from memory, and no data goes in whose licence does not allow passing it on.
- The doctrine, the clinical rules and the hard rules in `src/SKILL.md` are never weakened, by code or by documentation. Anything that changes who Voss is, what he may do, or which features he has is put to the maker first, and goes in once the maker has agreed.
- Voss is an original character. Nothing here compares him with any other fictional doctor or android.
- **No personal data, anywhere.** Never commit a `personal.json`, a `household.md`, or a package Voss rebuilt for you. Tests use made-up people only. An error message names the argument that was wrong and never repeats what was typed: it may be somebody's date of birth.

## House rules for the code

Python 3.9 compatible, standard library only, plain ASCII in code and comments, no network at run time, British English in anything a user reads. Straight quotes and the plain hyphen only, in code and in text. SQL is always parameterised. All arithmetic that a person will rely on (ages, refills, dates) is done by code, exactly, and tagged `[derived]`.

Three things a tool never does, whatever it is for: print a dose, call anything "safe" because a file has no entry for it, or guess. A medicine is not guessed from a name, a figure is not guessed from a smudge, and where the data stops the tool says "nothing on file" and leaves the looking-up, with a citation, to Voss.

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
python tools/build_ddinter.py --fetch     downloads DDInter's files and the medicine names, and builds ddinter.db again
python tools/build_labels.py --fetch      downloads openFDA's label files (1.8 GB) and builds labels-us.db again
python tools/build_advice.py --fetch      downloads the pages behind advice-by.db, with their terms, and builds it again
python tools/build_firstaid.py --fetch    downloads the Wikipedia revisions that were read, and builds firstaid-sa.db again
```

## The public build, the private build and the leak check

Two files are private and never go into this repository: `src/references/household.md` (a household: names, places, other minds) and `src/scripts/data/personal.json` (patients). So is anything in `src/images/private/`. `.gitignore` lists all three, and the build checks that it does, and that git is not already tracking them.

The public build works on a copy of `src/` that leaves those out, so they cannot be packed by accident even when they are sitting in the folder. It then runs the leak check. The household file ends with a section headed "Leak words": a list of words and phrases, one to a line. Each is looked for, as a whole word and in any case, in every file of the package and in every other file git would publish from this repository, file names and picture metadata included. One hit and nothing is packed; the build prints the file and the line. Two places are passed over, because they are signed with the author's name: `LICENSE`, and the one line under Credits in `README.md` that says whose work Voss is.

The household file is found through the `VOSS_HOUSEHOLD` environment variable, or at `src/references/household.md` if a copy was dropped in. With neither, the build runs every other check and says the leak check was skipped: run it with the real file before anything is published. `tests/fixtures/household.example.md` is a made-up one to try it with.

The private build (`--private --out DIR`) adds the household file and the personal file (`VOSS_PERSONAL`, or the copy under `src/`) on top of the public files and writes `voss-private.zip` into a folder outside any git repository.

## Adding a command

A command lives in one module of `src/scripts/vosslib/`, which has a `register(sub)` that calls `command(sub, group, name, function, summary, examples)` for each of its commands. A new module is added to `MODULES` in `vosslib/__init__.py`.

- The group is one of `desk`, `clinic`, `medicines`, `household`, `file` and `extras`. The summary is one line of at most 125 characters, and there is at least one example. The examples have to run against the made-up people in `tests/fixtures/`, because the tests run every one.
- Output goes through `rec` and `more`, in the record style of the rest: a KEY, then the value, with the source and the rule that goes with it.
- An error is `die("...")`: one line that says what to change, and never repeats what was typed.
- Everyday words for the job go into `ALSO` in `vosslib/index.py`, so that `tools --find` can name the command. Then run `python tools/build_index.py`.
- The README's table of commands and `docs/limits.md` both name every command, and the tests check that they do. What a command cannot do belongs in the limits as much as what it can.

A command that puts something into a personal file does not write it. It hands the change to `rebuild.save`, which reads it back and prints a code, and writes a new file only when the same command comes back with that code (`rebuild.out_options` adds the options). A page for somebody else to read works the same way: the page is printed with a code, and written only with `--write --confirm CODE`. A new field goes into `scripts/data/fields.json`, the empty template and `references/personal-file.md` together, once the maker has agreed to it.

## Databases

The principles, in short: everything is offline, standard-library Python over read-only SQLite; every row can be traced to a source; one database per licence family; one builder per source, which anyone can run again; and the built files are in the repository, inside the package, so that the skill works the moment it is unzipped. Nothing in them is about one country's services or its register of medicines: that kind of data changes by the day and would have to be kept up for every country, so Voss looks it up and cites it.

A database lives in `src/scripts/data/` as a single SQLite file, with its licence text beside it as `LICENSE-<name>.txt` and a row in `SOURCES.md`. The tools open it read-only. It must carry two tables, and is not answered from without them:

- `meta`, one row for each source: `source`, `url`, `retrieved` (YYYY-MM-DD), `licence`, and `credit` where the licence asks for a credit line.
- `build`, of `key` and `value`: `built` is the day the file was made, and `format` is the number of its layout. `vosslib/library.py` knows which number this version reads, and does not answer from a file with another: change a table, and both numbers move together.

The banner shows the oldest `built`. A file's age is counted from its oldest `retrieved`, because a file built today from old downloads is still old; the limits are in `SOURCES.md` and in `vosslib/library.py`. One database per licence family, so that a share-alike or no-derivatives licence never spreads to a file it does not belong to.

No file in this repository may be larger than 49 MB, and the build refuses one that is; it prints the size of every database it packs. The figure sits just under the size at which GitHub starts to warn about a file (50 MiB; it refuses one over 100 MiB). A database that would come out bigger is cut into parts. Putting one out as a Release asset instead is the maker's decision, file by file, and has not been needed.

Each database has a builder in `tools/` (`build_core.py` is the first) that names every address it downloads from, keeps the downloads in `downloads/` (which git ignores) with a note of the day beside each, and can be run again by anyone. `tools/dbtools.py` holds what the builders share. Before a source goes in, read its terms on its own page, and write what you found and the date into `SOURCES.md`. If the terms do not clearly allow the data to be passed on in a public repository and inside the packed skill, it stays out: ship the builder without the data, and say so. Where a licence could change under a file (ICD-11, DDInter, openFDA), the builder reads the terms again at every fetch and stops if they are no longer the ones that were read.

`icd11.db` has rules of its own, because WHO's licence allows no adaptation. Nothing in it may be reworded, shortened, re-ordered, translated or mapped to another code system, and nothing may be added to an entry that is not marked as not WHO's. Do not add a translated title, an ICD-10 column or a "plain English" gloss to that file, however useful it looks: put such a thing somewhere else, under its own source and licence, or leave it out.

`ddinter.db` is non-commercial and share-alike. Nothing from it may be copied into another database or into the code, and nothing may go into it that could not be passed on under the same licence.

`firstaid-sa.db` is share-alike too, and it comes from a source that anyone can edit. Its revisions are pinned in `tools/build_firstaid.py`: a newer revision goes in only after somebody has read every passage of it (`--fetch --latest --show`) and written its number into the script. A section that says something no first-aid body teaches stays out, however useful the rest of it looks.

`advice-by.db` holds passages whose sources ask for a credit and for nothing more. A passage is taken whole and word for word, with the page it stood on and the page's own date, and the builder stops when a page has changed shape or its terms no longer say what was read.

Long text is not stored row by row. The builder packs it into blocks, compresses each block with zlib or lzma, whichever makes it smaller, and stores where each piece sits; `vosslib/store.py` reads it back. That is why a database here is a fraction of the size of its text. What is read often goes into small blocks and what is read seldom into large ones, which squeeze harder and take longer to open. A table is kept lean in the same spirit: numbers where a word would repeat, and nothing stored twice. The whole skill has to stay under 30 MB unpacked, which is the most a skill may weigh when it is uploaded through the API.

The builders send a plain client name and nothing about you or this project. Wikidata asks scripts to say who runs them and is slow with those that do not, so its part of `build_core.py --fetch` can take the better part of an hour. If you want it faster, put a line of your own in the `VOSS_BUILD_AGENT` environment variable, as their policy describes.

## Data nobody has found yet

Some commands say "nothing on file" because no source turned up whose terms clearly allow its content to be passed on. If you know of one, read its terms on its own page first, and say in the pull request what they are and when you read them.

- First aid: a guideline of a first-aid body whose terms allow it to be shipped. Wikipedia's account stands in for one, and would gladly give way.
- What poisons a cat or a dog, species by species. FDA's list is on file, and names only the more common things.
- Advice for heat, cold and sun: from a health authority whose terms allow it.
- Help for carers: a source that is not about one country.
- Why two medicines interact, what to do about it, and anything on food: DDInter shows these on its website and does not offer them for download.
- Product information from outside the United States. European and national leaflets come as PDF documents, which the standard library cannot read.

## The documents

`README.md` carries the intended-purpose statement, word for word from `src/references/clinical-rules.md`, and a credit line for every source. `docs/limits.md` says what each command cannot do. `src/CHANGELOG.md` gets a line with every change, and it is the only place for history: every other file says what holds now, with no dates of decisions and no account of who proposed or accepted what.

## Why a call is fast

A call loads only the module its command lives in, which it finds in `scripts/data/commands.json`; that is why the index must match the commands (the build and the tests both check). Where the skill's folder is read-only, Python cannot keep its compiled files beside the scripts, so `voss.py` points it at a folder of its own in the temp directory instead (`VOSS_NO_CACHE=1` turns that off).
