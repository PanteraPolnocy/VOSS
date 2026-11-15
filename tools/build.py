"""Check the source and pack the skill.

  python tools/build.py                       the public build:  dist/voss.zip
  python tools/build.py --private --out DIR   the private build: DIR/voss-private.zip  (DIR outside this repository)

The public build never packs the two private files, references/household.md and scripts/data/personal.json,
nor anything in images/private/: it works on a copy that leaves them out. It then runs the leak check:
every word or phrase listed under "Leak words" in the household file is looked for, as a whole word and in
any case, in every file of the package and every other file this repository would publish. One hit and
nothing is packed. With no household file to read, the other checks still run and the build says the leak
check was skipped.

The private build adds the household file and the personal file on top of the public ones. Each is taken
from the path in VOSS_HOUSEHOLD or VOSS_PERSONAL if that is set, else from its place under src/ if a copy
was dropped in there (git ignores both). Nothing private is ever written into this repository.
"""
import argparse
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "scripts"))

import vosslib  # noqa: E402
from vosslib import core, desk, library, personal  # noqa: E402

HOUSEHOLD = "references/household.md"
PERSONAL = "scripts/data/personal.json"
PRIVATE_FILES = (HOUSEHOLD, PERSONAL)
PRIVATE_DIRS = ("images/private",)
SKIP_DIRS = ("__pycache__",)
SKIP_EXT = (".pyc",)
IMAGE_EXT = (".webp", ".png", ".jpg", ".jpeg", ".gif")
TEXT_EXT = (".md", ".py", ".json", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html", ".css", ".js", ".csv", ".ics")
# the licence is signed with its holder's name, and that is hers to sign
LEAK_EXEMPT = ("LICENSE",)
IGNORED = ("src/" + HOUSEHOLD, "src/" + PERSONAL, "src/images/private/")
ENV_KEYS = ("VOSS_PERSONAL", "VOSS_HOUSEHOLD", "VOSS_DATA", "VOSS_OUTPUTS", "VOSS_NOW")
# no single file in the repository may be larger than this: the owner's rule, kept a little under the size at
# which the host starts to complain
MAX_FILE_BYTES = 49 * 1000 * 1000
STAMP = (2026, 11, 15, 12, 0, 0)        # one date for every entry, so the same source packs to the same bytes


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^\s*([a-z_]+):\s*(.*)$", line)
        if km:
            value = km.group(2).strip()
            if len(value) > 1 and value[0] == value[-1] == "'":
                value = value[1:-1].replace("''", "'")
            out[km.group(1)] = value.strip('"')
    return out


def is_private(rel):
    return rel in PRIVATE_FILES or any(rel == d or rel.startswith(d + "/") for d in PRIVATE_DIRS)


def gather(folder, private=True):
    """Relative paths of every file under a folder, sorted. With private=False the private ones are left out."""
    files = []
    for here, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            if n.endswith(SKIP_EXT):
                continue
            rel = os.path.relpath(os.path.join(here, n), folder).replace(os.sep, "/")
            if private or not is_private(rel):
                files.append(rel)
    return sorted(files)


def private_source(src, rel, env):
    """Where a private file is to be taken from: the path in its environment variable, else its place under src/."""
    named = os.environ.get(env)
    if named:
        if not os.path.isfile(named):
            sys.exit("%s names a file that is not there" % env)
        return named
    inside = os.path.join(src, *rel.split("/"))
    return inside if os.path.isfile(inside) else None


def stage(src, folder, private=False, household=None, personal_file=None):
    """Copy what ships into an empty folder: the public files, and for a private build the private ones on top."""
    for rel in gather(src, private=False):
        target = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(src, *rel.split("/")), target)
    if not private:
        return
    for rel, source in ((HOUSEHOLD, household), (PERSONAL, personal_file)):
        if source:
            target = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
    for rel in gather(src, private=True):
        if any(rel.startswith(d + "/") for d in PRIVATE_DIRS):
            target = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(src, *rel.split("/")), target)


# ---- checks that hold for any build

def run_tool(folder, *args):
    env = dict(os.environ)
    for key in ENV_KEYS:
        env.pop(key, None)
    return subprocess.run([sys.executable, "-B", os.path.join(folder, "scripts", "voss.py")] + list(args),
                          capture_output=True, text=True, env=env)


def check_images(folder):
    problems = []
    path = os.path.join(folder, "images", "manifest.json")
    if not os.path.isfile(path):
        return ["images/manifest.json is missing"], None
    try:
        manifest = json.loads(read(path))
    except ValueError as e:
        return ["images/manifest.json is not valid JSON: %s" % e], None
    named = []
    for group, text_key in (("moods", "face"), ("looks", "description"), ("other", "shows")):
        for row in manifest.get(group) or []:
            if not (isinstance(row, dict) and row.get("file") and row.get(text_key) and (group == "other" or row.get("key"))):
                problems.append("images/manifest.json: an entry under %s lacks its key, file or %s" % (group, text_key))
                continue
            named.append(row["file"])
            if group != "other" and row["file"] != "voss-%s.webp" % row["key"]:
                problems.append("images/manifest.json: the file for %s must be voss-%s.webp" % (row["key"], row["key"]))
            if not os.path.isfile(os.path.join(folder, "images", row["file"])):
                problems.append("images/manifest.json names %s, which is not in images/" % row["file"])
    if len(named) != len(set(named)):
        problems.append("images/manifest.json names a file twice")
    for rel in gather(folder):
        if rel.startswith("images/") and rel.lower().endswith(IMAGE_EXT) and not is_private(rel):
            if rel[len("images/"):] not in named:
                problems.append("%s is not in images/manifest.json" % rel)
    return problems, manifest


def check_data(folder):
    """Every database says where it came from and has its licence beside it; no file is too big for the repository."""
    problems, notes = [], []
    data = os.path.join(folder, "scripts", "data")
    sources_path = os.path.join(data, "SOURCES.md")
    sources = read(sources_path) if os.path.isfile(sources_path) else ""
    if not sources:
        problems.append("scripts/data/SOURCES.md is missing")
    # a file that is installed belongs in the main table, not still under the ones to come
    sources = re.split(r"(?m)^## Databases to come\s*$", sources)[0]
    for name in sorted(os.listdir(data)) if os.path.isdir(data) else []:
        if not name.lower().endswith(".db"):
            continue
        info = library.read(os.path.join(data, name))
        for problem in info["problems"]:
            problems.append("scripts/data/%s %s" % (name, problem))
        if name not in sources:
            problems.append("scripts/data/SOURCES.md does not list %s among the files that are installed" % name)
    for rel in gather(folder):
        if is_private(rel):
            continue
        size = os.path.getsize(os.path.join(folder, *rel.split("/")))
        if size > MAX_FILE_BYTES:
            problems.append(too_big(rel, size))
        elif rel.lower().endswith(".db"):
            notes.append("%s is %s" % (rel, megabytes(size)))
    return problems, notes


def megabytes(size):
    return "%.1f MB" % (size / 1e6) if size >= 100000 else "%d KB" % max(1, size // 1000)


def too_big(rel, size):
    return "%s is %s: no file in the repository may be over %d MB" % (rel, megabytes(size), MAX_FILE_BYTES // 1000000)


def check_sizes(root):
    """The same limit for everything else the repository would publish: tools, tests, documents."""
    return [too_big(rel, os.path.getsize(os.path.join(root, *rel.split("/")))) for rel in repository_files(root)
            if os.path.getsize(os.path.join(root, *rel.split("/"))) > MAX_FILE_BYTES]


def check_tree(folder, label):
    """Checks that hold for any build. Returns (problems, notes, frontmatter, number of commands)."""
    problems, notes = [], []
    skill_path = os.path.join(folder, "SKILL.md")
    if not os.path.isfile(skill_path):
        return ["SKILL.md is missing"], notes, {}, "?"
    skill = read(skill_path)
    fm = frontmatter(skill)
    if not fm:
        problems.append("SKILL.md has no frontmatter")
    if fm.get("name") != "voss":
        problems.append("frontmatter name is %r, expected 'voss'" % fm.get("name"))
    desc = fm.get("description", "")
    if not 50 <= len(desc) <= 1024:
        problems.append("description is %d characters; it must be between 50 and 1024" % len(desc))
    image_problems, manifest = check_images(folder)
    problems += image_problems
    changelog_path = os.path.join(folder, "CHANGELOG.md")
    newest = re.search(r"(?m)^## (\d+\.\d+\.\d+)\b", read(changelog_path)) if os.path.isfile(changelog_path) else None
    versions = {"SKILL.md": fm.get("version"), "images/manifest.json": (manifest or {}).get("version"),
                "vosslib": vosslib.VERSION, "CHANGELOG.md": newest.group(1) if newest else None}
    if len(set(versions.values())) != 1:
        problems.append("versions disagree: %s" % versions)
    for rel in gather(folder):
        path = os.path.join(folder, *rel.split("/"))
        if rel.endswith(".md"):
            for ln, col, ch, what, _ in desk.check_text(read(path)):
                problems.append("%s line %d col %d: %s (U+%04X)" % (rel, ln, col, what, ord(ch)))
        if rel.endswith(".py"):
            with open(path, "rb") as f:
                raw = f.read()
            if any(b > 127 for b in raw):
                problems.append("%s has non-ASCII bytes" % rel)
            if b"\t" in raw:
                problems.append("%s has a tab in it" % rel)
        if rel.endswith(".json"):
            try:
                json.loads(read(path))
            except ValueError as e:
                problems.append("%s is not valid JSON: %s" % (rel, e))
    for link in sorted(set(re.findall(r"`((?:playbooks|references|images|scripts)/[A-Za-z0-9_./-]+\.[a-z]+)`", skill))):
        if not is_private(link) and not os.path.exists(os.path.join(folder, *link.split("/"))):
            problems.append("SKILL.md points at %s, which is not in the package" % link)
    data_problems, data_notes = check_data(folder)
    problems += data_problems
    notes += data_notes
    out = run_tool(folder, "tools")
    real = re.search(r"(\d+) commands\.", out.stdout or "")
    if out.returncode != 0 or not real:
        problems.append("the packed toolkit does not run: %s" % (out.stderr or out.stdout)[:200])
    test = run_tool(folder, "selftest")
    if test.returncode != 0:
        problems.append("selftest failed in the %s build:\n%s" % (label, (test.stdout + test.stderr)[-600:]))
    return problems, notes, fm, (real.group(1) if real else "?")


def check_index(root):
    """The command index must match the commands: a stale one would send a call to the wrong module."""
    out = subprocess.run([sys.executable, "-B", os.path.join(root, "tools", "build_index.py"), "--check"], capture_output=True, text=True)
    return [] if out.returncode == 0 else [(out.stderr or out.stdout).strip() or "tools/build_index.py --check failed"]


# ---- checks for the public build

def check_template(folder):
    """The template that ships must be empty: a shape to copy, with nobody in it."""
    path = os.path.join(folder, "scripts", "data", "personal.template.json")
    if not os.path.isfile(path):
        return ["scripts/data/personal.template.json is missing"]
    try:
        data = json.loads(read(path))
    except ValueError as e:
        return ["scripts/data/personal.template.json is not valid JSON: %s" % e]
    problems = []
    defaults = {"id": "self", "medical_reference": "human", "units": "metric"}
    for n, entry in enumerate(data.get("profiles") or [], 1):
        for key, value in entry.items():
            if key == "ignition":
                if (value or {}).get("questions"):
                    problems.append("personal.template.json has gate questions in it")
                continue
            if defaults.get(key) == value:
                continue
            if not personal.blankish(value):
                problems.append("personal.template.json has '%s' filled in (profile %d)" % (key, n))
    for key in personal.HOUSEHOLD_LISTS + ("dependants",):
        value = data.get(key)
        if key == "cabinet":
            value = [dict((k, v) for k, v in row.items() if k != "belongs_to") for row in value or [] if isinstance(row, dict)]
        if key == "kits":
            value = [dict((k, v) for k, v in row.items() if k != "where") for row in value or [] if isinstance(row, dict)]
        if not personal.blankish(value):
            problems.append("personal.template.json has '%s' filled in" % key)
    return problems


def check_ignore(root):
    """The private files must be on git's ignore list, and must not already be in its index."""
    problems = []
    path = os.path.join(root, ".gitignore")
    lines = [ln.strip() for ln in read(path).splitlines()] if os.path.isfile(path) else []
    for rel in IGNORED:
        if rel not in lines and "/" + rel not in lines:
            problems.append(".gitignore does not list %s" % rel)
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "--"] + [r.rstrip("/") for r in IGNORED],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return problems
    if out.returncode == 0:
        for rel in out.stdout.splitlines():
            if rel.strip():
                problems.append("%s is tracked by git: take it out of the index before anything is pushed" % rel.strip())
    return problems


# ---- the leak check

def leak_words(text):
    """The words and phrases listed under the household file's 'Leak words' heading, one to a line."""
    m = re.search(r"(?mi)^##\s+Leak words\s*$", text)
    if not m:
        return None
    body = text[m.end():]
    nxt = re.search(r"(?m)^##\s", body)
    if nxt:
        body = body[:nxt.start()]
    fenced = re.search(r"(?ms)^```[^\n]*\n(.*?)^```", body)
    lines = fenced.group(1).splitlines() if fenced else [ln for ln in body.splitlines() if re.match(r"^\s*[-*]\s+", ln)]
    words = []
    for line in lines:
        word = " ".join(re.sub(r"^\s*[-*]\s+", "", line).split())
        if word and word not in words:
            words.append(word)
    return words


def leak_pattern(word):
    parts = [re.escape(p) for p in word.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.I | re.U)


def webp_text(raw):
    """The metadata a WebP file carries (EXIF, XMP), as text. The picture itself is not text and is not read."""
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        return ""
    out, pos = [], 12
    while pos + 8 <= len(raw):
        tag, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        if tag in (b"EXIF", b"XMP "):
            out.append(raw[pos + 8:pos + 8 + size].decode("utf-8", "replace"))
        pos += 8 + size + (size & 1)
    return "\n".join(out)


def repository_files(root):
    """Every file this repository would publish, apart from the package (src/) and the packed copies (dist/).
    git is asked first, because it knows what is ignored; without git, the folder is walked."""
    found = None
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, timeout=60)
        if out.returncode == 0:
            found = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        found = None
    if found is None:
        found = []
        for here, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and d != ".git")
            for n in sorted(names):
                found.append(os.path.relpath(os.path.join(here, n), root).replace(os.sep, "/"))
    keep = []
    for rel in sorted(set(found)):
        if rel.startswith(("src/", "dist/")) or rel.endswith(SKIP_EXT) or rel in LEAK_EXEMPT:
            continue
        if os.path.isfile(os.path.join(root, *rel.split("/"))):
            keep.append(rel)
    return keep


def scan_leaks(words, files):
    """Look for every leak word in every file given as (name to print, path). Returns [(name, line, word)];
    line 0 means the file's own name."""
    patterns = [(w, leak_pattern(w)) for w in words]
    hits = []
    for name, path in files:
        for word, rx in patterns:
            if rx.search(name.replace("/", " ").replace("_", " ").replace(".", " ")):
                hits.append((name, 0, word))
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if name.lower().endswith(".webp"):
            text = webp_text(raw)
        elif name.lower().endswith(TEXT_EXT) or b"\0" not in raw[:8192]:
            text = raw.decode("utf-8", "replace")
        else:
            continue
        for word, rx in patterns:
            for m in rx.finditer(text):
                hits.append((name, text.count("\n", 0, m.start()) + 1, word))
    return sorted(set(hits))


def leak_check(root, staged, household):
    """(problems, a line for the report). staged: the folder holding the public package as it will be packed."""
    if not household:
        return [], "LEAK CHECK skipped: there is no household file to take the words from (set VOSS_HOUSEHOLD, or drop it in src/references/)"
    words = leak_words(read(household))
    if words is None:
        return ["the household file has no 'Leak words' section: the leak check cannot run"], ""
    if not words:
        return ["the household file's 'Leak words' section is empty: the leak check cannot run"], ""
    files = [("src/" + rel, os.path.join(staged, *rel.split("/"))) for rel in gather(staged)]
    # the list of words is not itself a leak: a household file kept in the repository (the made-up one the tests use) is passed over
    files += [(rel, os.path.join(root, *rel.split("/"))) for rel in repository_files(root)
              if not core.same_path(os.path.join(root, *rel.split("/")), household)]
    hits = scan_leaks(words, files)
    problems = []
    for name, line, word in hits:
        where = "%s, in the file's name" % name if line == 0 else "%s line %d" % (name, line)
        problems.append("leak word in %s%s" % (where, ": %s" % word if SHOW_WORDS else ""))
    if problems and not SHOW_WORDS:
        problems.append("(--words also prints which word each one is)")
    return problems, "LEAK CHECK passed: %d words and phrases against %d files" % (len(words), len(files))


SHOW_WORDS = False


# ---- packing

def pack(folder, zip_path):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in gather(folder):
            info = zipfile.ZipInfo(rel, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(folder, *rel.split("/")), "rb") as f:
                z.writestr(info, f.read())
    return os.path.getsize(zip_path)


def report(label, zip_path, size, fm, commands, folder):
    files = gather(folder)
    md = sum(os.path.getsize(os.path.join(folder, *r.split("/"))) for r in files if r.endswith(".md"))
    print("%-8s %s  (%d KB, %d files, %s commands, description %d chars, SKILL.md %d KB, all documents %d KB)" % (
        label, zip_path, size // 1024, len(files), commands, len(fm.get("description", "")),
        os.path.getsize(os.path.join(folder, "SKILL.md")) // 1024, md // 1024))


def build_public(root):
    """Check and pack the public build. Returns the list of problems; empty means dist/voss.zip was written."""
    src = os.path.join(root, "src")
    with tempfile.TemporaryDirectory() as tmp:
        staged = os.path.join(tmp, "voss")
        os.makedirs(staged)
        stage(src, staged)
        problems, notes, fm, commands = check_tree(staged, "public")
        problems += check_template(staged)
        problems += check_ignore(root)
        problems += check_index(root)
        problems += check_sizes(root)
        leaked = [rel for rel in gather(staged) if is_private(rel)]
        if leaked:
            problems.append("private files reached the public copy: %s" % ", ".join(leaked))
        leak_problems, leak_line = leak_check(root, staged, private_source(src, HOUSEHOLD, "VOSS_HOUSEHOLD"))
        problems += leak_problems
        if problems:
            return problems
        zip_path = os.path.join(root, "dist", "voss.zip")
        size = pack(staged, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            inside = [n for n in z.namelist() if is_private(n)]
        if inside:
            os.remove(zip_path)
            return ["private files reached the packed copy, which was deleted: %s" % ", ".join(inside)]
        report("PUBLIC", zip_path, size, fm, commands, staged)
        held_back = [rel for rel in gather(src) if is_private(rel)]
        if held_back:
            print("         left out, as always: %s" % ", ".join(held_back))
        print("         " + leak_line)
        for note in notes:
            print("         NOTE " + note)
        if size > MAX_FILE_BYTES:
            # the packed skill is still good to use; it just cannot live in the repository at that size
            print("         TOO BIG TO COMMIT: " + too_big("dist/voss.zip", size) + ". Ship it as a Release asset instead")
    return []


def build_private(root, out_dir):
    """Check and pack the private build into a folder outside the repository. Returns the list of problems."""
    src = os.path.join(root, "src")
    target = os.path.abspath(out_dir)
    if core.within(target, root) or core.inside_repository(target):
        return ["the private build is never written inside a git repository: give --out a folder outside one"]
    if not os.path.isdir(target):
        return ["--out must be a folder that exists: %s" % out_dir]
    household = private_source(src, HOUSEHOLD, "VOSS_HOUSEHOLD")
    personal_file = private_source(src, PERSONAL, "VOSS_PERSONAL")
    if not household and not personal_file:
        return ["there is nothing private to add: set VOSS_HOUSEHOLD or VOSS_PERSONAL, or drop the files in under src/"]
    with tempfile.TemporaryDirectory() as tmp:
        staged = os.path.join(tmp, "voss")
        os.makedirs(staged)
        stage(src, staged, private=True, household=household, personal_file=personal_file)
        problems, notes, fm, commands = check_tree(staged, "private")
        if problems:
            return problems
        zip_path = os.path.join(target, "voss-private.zip")
        size = pack(staged, zip_path)
        report("PRIVATE", zip_path, size, fm, commands, staged)
        print("         with %s" % " and ".join(x for x in (
            "the household file" if household else "", "the personal file" if personal_file else "") if x))
        for missing, env in ((household, "VOSS_HOUSEHOLD"), (personal_file, "VOSS_PERSONAL")):
            if not missing:
                print("         without %s: %s is not set and no copy is under src/" % (
                    "a household file" if env == "VOSS_HOUSEHOLD" else "a personal file", env))
        print("         it holds private files: never a public repository, never a shared drive")
        for note in notes:
            print("         NOTE " + note)
    return []


def main(argv=None):
    global SHOW_WORDS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public", action="store_true", help="the public build (what happens with no option at all)")
    ap.add_argument("--private", action="store_true", help="the private build: the public files plus the household and personal files")
    ap.add_argument("--out", metavar="DIR", help="with --private: the folder to write voss-private.zip into, outside this repository")
    ap.add_argument("--words", action="store_true", help="when the leak check finds something, also print which word it was")
    a = ap.parse_args(argv)
    SHOW_WORDS = a.words
    if a.out and not a.private:
        sys.exit("--out goes with --private: the public build always writes dist/voss.zip")
    if a.public or not a.private:
        problems = build_public(ROOT)
        if problems:
            sys.exit("NOT BUILT. Problems:\n  " + "\n  ".join(problems))
    if a.private:
        if not a.out:
            sys.exit("the private build needs --out DIR, a folder outside this repository")
        problems = build_private(ROOT, a.out)
        if problems:
            sys.exit("PRIVATE NOT BUILT:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    main()
