"""The recipe book: Voss bakes.

recipe  his own recipes, one for each month: vegetarian, everything weighed in grams, the allergens named.
        With --for it sets a recipe beside the allergies and intolerances a person has on file.
scale   a recipe for another batch size, by exact arithmetic.

Nothing here is "a pinch". A recipe stays marked untested until someone has baked it from this file and said
so; the tool says which are. An allergen is read off the list of ingredients, and that list is not a promise
about a kitchen: what else has touched the flour, the tool cannot know.
"""
from fractions import Fraction

from . import core
from .core import command, die, fold, load_data, more, rec

UNTESTED = "untested: written with care, and not yet baked from this file by anyone"
MAX_TIMES = 50
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December")
# the words a person may have used for what a recipe's allergen is. A net for the tool to catch with: what it
# misses is listed for Voss to read himself
ALLERGEN_WORDS = {
    "gluten (wheat)": ("gluten", "wheat", "coeliac", "celiac", "flour"),
    "gluten (oats)": ("gluten", "oat", "oats", "coeliac", "celiac"),
    "milk": ("milk", "dairy", "lactose", "butter", "cream", "casein", "whey", "buttermilk"),
    "egg": ("egg", "eggs"),
    "nuts (almond)": ("nut", "nuts", "almond", "almonds"),
}


def _recipes():
    return load_data("recipes")["recipes"]


def _find(words):
    want = fold(" ".join(words))
    if not want:
        die("name the recipe: 'recipe' lists them")
    hits = [r for r in _recipes() if fold(r["key"]) == want or fold(r["name"]) == want] or \
        [r for r in _recipes() if want in fold(r["key"]) or want in fold(r["name"])]
    if len(hits) != 1:
        die("%s: 'recipe' lists them by name" % ("no recipe goes by that name" if not hits else "more than one recipe fits that"))
    return hits[0]


def _month(text):
    """A month by its number or its name, as 1 to 12."""
    t = str(text).strip().lower()
    if t.isdigit() and 1 <= int(t) <= 12:
        return int(t)
    hits = [n for n, name in enumerate(MONTHS, 1) if len(t) >= 3 and name.lower().startswith(t)]
    if len(hits) != 1:
        die("--month is a month: its name, or 1 to 12")
    return hits[0]


def _allergens(recipe):
    found = []
    for item in recipe["ingredients"]:
        for allergen in item.get("allergens") or []:
            if allergen not in found:
                found.append(allergen)
    return found


def _grams(amount):
    """An exact weight in words, and the weight to set the scales to where that is not a whole number of grams."""
    exact = core.show_amount(amount)
    if amount.denominator == 1:
        return "%s g" % exact
    whole = int(amount + Fraction(1, 2))
    return "%s g, which is %d g on the scales" % (exact, whole)


def _print(recipe, times=Fraction(1)):
    makes = recipe["makes"]
    count = makes["count"] * times
    rec("RECIPE", "%s%s" % (recipe["name"], "" if recipe.get("tested") else " [%s]" % UNTESTED))
    if recipe.get("month"):
        rec("MONTH", "%s. %s" % (MONTHS[recipe["month"] - 1], recipe.get("why") or ""))
    rec("MAKES", "%s %s%s" % (core.show_amount(count), makes["what"], " [derived: %s times the recipe]" % core.show_amount(times) if times != 1 else ""))
    rec("WEIGH", "in grams, every one%s" % (" [derived, exactly]" if times != 1 else ""))
    for item in recipe["ingredients"]:
        more("%s: %s" % (item["item"], _grams(Fraction(item["grams"]) * times)))
    allergens = _allergens(recipe)
    rec("ALLERGENS", "%s [read off the ingredients above]" % ("; ".join(allergens) if allergens else "none among the ingredients"))
    more("vegetarian. What else a kitchen's flour or tins have touched is not something a recipe can know")
    rec("TIN", recipe["tin"])
    rec("OVEN", "%s; %s" % (recipe["oven"], recipe["time"]))
    if times != 1:
        more("the tin and the time are for the recipe as written: another batch wants another tin, and the baking is "
             "watched, not worked out")
    rec("METHOD", recipe["method"][0])
    for step in recipe["method"][1:]:
        more(step)


def _same(word, words):
    """True if a word is among some words, give or take a plural."""
    return word in words or word + "s" in words or (word.endswith("s") and word[:-1] in words)


def _beside(recipe, pid):
    """A recipe set beside what a person has on file: their allergies, their intolerances and what they said of
    their diet. A match is made by word, and says so."""
    from . import personal
    kind, entry = personal.pick(personal.need(), pid)
    held = _allergens(recipe)
    clashes, unmatched = 0, []
    rec("FOR", "%s: the recipe set beside the allergies and intolerances on file [matched by word: a net, not a promise]" % entry["id"])
    for field, article, tells in (("allergies", "an allergy", "reaction"), ("intolerances", "an intolerance", "what_happens")):
        for row in personal.rows(entry, field):
            substance = str(row.get("substance") or "").strip() if isinstance(row, dict) else ""
            if not substance:
                continue
            words = [w for w in core.key(substance).split("_") if len(w) >= 3]
            tags = [tag for tag in held if any(_same(w, ALLERGEN_WORDS.get(tag, ())) for w in words)]
            named = [item["item"] for item in recipe["ingredients"]
                     if any(_same(w, core.key(item["item"]).split("_")) for w in words) and not any(t in tags for t in item.get("allergens") or [])]
            if tags or named:
                clashes += 1
                rec("CLASH", "%s, on file as %s%s: the recipe holds %s" % (
                    substance, article, " (%s)" % row[tells] if row.get(tells) else "", "; ".join(tags + named)))
            else:
                unmatched.append(substance)
    habits = entry.get("habits") if isinstance(entry.get("habits"), dict) else {}
    diet = str(habits.get("diet") or "").strip()
    if diet:
        rec("DIET", "as on file: %s" % diet)
        animal = [tag for tag in held if tag in ("milk", "egg")]
        if "vegan" in core.key(diet).split("_") and animal:
            clashes += 1
            rec("CLASH", "that diet: the recipe holds %s" % "; ".join(animal))
    if unmatched:
        rec("NOT MATCHED", "on file, and matched to nothing in this recipe by the tool: %s. Read the ingredients against them "
                           "yourself" % "; ".join(unmatched))
    if not clashes:
        rec("NO CLASH", "nothing on file was matched to this recipe. That is not a promise: ask before you bake for them")
    rec("RULE", "name every clash before you bake, and ask. What would have to change is yours to suggest, said as a "
                "suggestion: a swap makes it another recipe, and that one is untested twice over. A severe allergy is not "
                "baked around in a kitchen that holds the thing")


def cmd_recipe(a):
    if a.month and a.name:
        die("name the recipe or the month, not both")
    if not a.name and not a.month:
        if a.for_id:
            die("--for goes with a recipe: recipe shortbread --for ID")
        recipes = _recipes()
        rec("RECIPES", "%s, one for each month, all vegetarian, all in grams" % core.plural(len(recipes), "recipe"))
        for r in recipes:
            more("%s%s ('%s'): makes %s %s; %s%s" % ("%s: " % MONTHS[r["month"] - 1] if r.get("month") else "", r["name"], r["key"],
                                                   r["makes"]["count"], r["makes"]["what"],
                                                   "; ".join(_allergens(r)) or "no allergens among the ingredients",
                                                   "" if r.get("tested") else "; untested"))
        now = [r for r in recipes if r.get("month") == core.today().month]
        if now:
            rec("THIS MONTH", "%s. %s" % (now[0]["name"], now[0].get("why") or ""))
            more("the calendar follows the seasons north of the equator, where he was built")
        rec("RULE", "say which are untested when you offer one: %s" % UNTESTED.split(": ", 1)[1])
        return
    if a.month:
        hits = [r for r in _recipes() if r.get("month") == _month(a.month)]
        if not hits:
            die("no recipe is on file for that month")
        recipe = hits[0]
    else:
        recipe = _find(a.name)
    _print(recipe)
    if a.for_id:
        _beside(recipe, a.for_id)
        return
    rec("RULE", "a recipe is baking, not advice. Allergens are named because the person may need them: ask before you bake "
                "for someone, and 'recipe NAME --for ID' sets the recipe beside what they have on file")


def cmd_scale(a):
    recipe = _find(a.name)
    if (a.times is None) == (a.makes is None):
        die("say how much to make once: --times 1.5, or --makes 24")
    if a.times is not None:
        times = core.fraction_of(a.times, "--times")
    else:
        times = core.fraction_of(a.makes, "--makes") / recipe["makes"]["count"]
    if not 0 < times <= MAX_TIMES:
        die("that is not a batch anyone bakes: between nothing and %d times the recipe" % MAX_TIMES)
    _print(recipe, times)
    rec("RULE", "the weights are exact [derived]. Nothing is rounded to \"a pinch\": where the scales cannot show it, the "
                "nearest gram is given beside the exact figure")


def register(sub):
    p = command(sub, "extras", "recipe", cmd_recipe,
                "Voss's own baking recipes, one for each month: vegetarian, in grams, allergens named, set beside a person's allergies",
                ["recipe", "recipe shortbread", "recipe --month december", "recipe apple cake --for self"])
    p.add_argument("name", nargs="*", help="one recipe, by its name; none lists them all")
    p.add_argument("--month", help="the recipe for a month: its name, or 1 to 12")
    p.add_argument("--for", dest="for_id", metavar="ID", help="set the recipe beside the allergies and intolerances this person has on file")

    p = command(sub, "extras", "scale", cmd_scale,
                "a recipe for another batch size, by exact arithmetic: every weight in grams, and never \"a pinch\"",
                ["scale shortbread --times 1.5", "scale oat biscuits --makes 30"])
    p.add_argument("name", nargs="+", help="the recipe")
    p.add_argument("--times", help="how many times the recipe: 2, 0.5, 1 1/2")
    p.add_argument("--makes", help="how many to make, in place of --times")
