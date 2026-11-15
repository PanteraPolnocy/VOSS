"""The recipe book: Voss bakes.

recipe  his own recipes: vegetarian, everything weighed in grams, the allergens named.
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


def cmd_recipe(a):
    if not a.name:
        recipes = _recipes()
        rec("RECIPES", "%s, all vegetarian, all in grams" % core.plural(len(recipes), "recipe"))
        for r in recipes:
            more("%s ('%s'): makes %s %s; %s%s" % (r["name"], r["key"], r["makes"]["count"], r["makes"]["what"],
                                                 "; ".join(_allergens(r)) or "no allergens among the ingredients",
                                                 "" if r.get("tested") else "; untested"))
        rec("RULE", "say which are untested when you offer one: %s" % UNTESTED.split(": ", 1)[1])
        return
    _print(_find(a.name))
    rec("RULE", "a recipe is baking, not advice. Allergens are named because the person may need them: ask before you bake "
                "for someone")


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
                "Voss's own baking recipes: vegetarian, weighed in grams, with the allergens named and the untested ones marked",
                ["recipe", "recipe shortbread"])
    p.add_argument("name", nargs="*", help="one recipe, by its name; none lists them all")

    p = command(sub, "extras", "scale", cmd_scale,
                "a recipe for another batch size, by exact arithmetic: every weight in grams, and never \"a pinch\"",
                ["scale shortbread --times 1.5", "scale oat biscuits --makes 30"])
    p.add_argument("name", nargs="+", help="the recipe")
    p.add_argument("--times", help="how many times the recipe: 2, 0.5, 1 1/2")
    p.add_argument("--makes", help="how many to make, in place of --times")
