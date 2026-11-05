"""Recipe book and deterministic recipe checks. Plain Python, no LLM involved.

The recipes in data/recipes.json are transcribed from notes/notes.pdf, which
are the only recipes the Recipe Planner may use. The checks here back the
Recipe Planner's scale_portions tool and the Pantry Verifier's
check_ingredients tool, so "is this in the pantry?" is answered by code,
not by the model's memory.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import pantry_store

RECIPES_FILE = Path(__file__).resolve().parent.parent / "data" / "recipes.json"


def _book() -> dict:
    return json.loads(RECIPES_FILE.read_text(encoding="utf-8"))


def staples() -> list[str]:
    """Ingredients assumed on hand and not tracked in the pantry (water, salt, pepper)."""
    return _book()["staples"]


def list_recipes() -> list[dict]:
    return _book()["recipes"]


def get_recipe(name: str) -> dict:
    key = name.strip().lower()
    for recipe in list_recipes():
        if recipe["name"].lower() == key:
            return recipe
    raise ValueError(f"No recipe named '{name}'. Known recipes: "
                     + ", ".join(r["name"] for r in list_recipes()))


def scale_recipe(name: str, servings: int) -> dict:
    """Multiply every amount by (servings wanted / servings shown), as the notes say."""
    if servings < 1:
        raise ValueError("Servings must be at least 1.")
    recipe = get_recipe(name)
    factor = servings / recipe["servings"]
    ingredients = [
        {**ing, "quantity": round(ing["quantity"] * factor, 3)} for ing in recipe["ingredients"]
    ]
    return {**recipe, "servings": servings, "ingredients": ingredients}


def check_against_pantry(ingredients: list[dict]) -> dict:
    """Compare a list of {item, quantity, unit} with the pantry.

    Returns every problem found: items missing from the pantry, items in the
    wrong unit, and items there is not enough of. Staples are skipped.
    """
    on_hand = pantry_store.read_pantry()["items"]
    skip = {s.lower() for s in staples()}
    problems = []
    for ing in ingredients:
        item = ing["item"].strip().lower()
        if item in skip:
            continue
        have = on_hand.get(item)
        if have is None:
            problems.append(f"{item}: not in the pantry")
        elif ing.get("unit") and ing["unit"] != have["unit"]:
            problems.append(f"{item}: recipe uses {ing['unit']}, pantry tracks {have['unit']}")
        elif ing["quantity"] > have["quantity"]:
            problems.append(
                f"{item}: needs {ing['quantity']} {have['unit']}, only {have['quantity']} on hand"
            )
    return {"all_available": not problems, "problems": problems}


def cookable_recipes(servings: int) -> list[str]:
    """Names of recipes that can be made right now at the given servings."""
    return [
        r["name"] for r in list_recipes()
        if check_against_pantry(scale_recipe(r["name"], servings)["ingredients"])["all_available"]
    ]
