"""Recipe Planner agent (starter version): suggests a recipe from the recipe book
that the pantry can cover, scaled to the requested servings. Read-only.

It returns a structured RecipePlan rather than free text, so the orchestrator
can hand the exact ingredient list to the Pantry Verifier.

TODO (team): add the get_preferences tool from the proposal (dietary limits,
dislikes) once we decide where preferences are stored.
"""

from __future__ import annotations

import json

from agents import Agent, function_tool
from agents.model_settings import ModelSettings
from pydantic import BaseModel, Field

from . import recipe_book
from .pantry_keeper import read_pantry


class Ingredient(BaseModel):
    item: str
    quantity: float
    unit: str


class RecipePlan(BaseModel):
    recipe_name: str = Field(description="Exact name from the recipe book, or empty if none fits.")
    servings: int
    ingredients: list[Ingredient]
    steps: list[str]
    note: str = Field(default="", description="Anything the user should know, or why no recipe fits.")


@function_tool
def get_recipes(servings: int = 2) -> str:
    """List every recipe in the recipe book, and which ones the pantry can cover
    right now at the given number of servings.

    Args:
        servings: How many servings the user wants.
    """
    return json.dumps({
        "recipes": [
            {"name": r["name"], "servings": r["servings"], "minutes": r["minutes"],
             "contains": r["contains"]}
            for r in recipe_book.list_recipes()
        ],
        "cookable_now": recipe_book.cookable_recipes(servings),
        "staples_assumed": recipe_book.staples(),
    })


@function_tool
def scale_portions(recipe_name: str, servings: int) -> str:
    """Return the full recipe with every ingredient amount scaled to `servings`.

    Args:
        recipe_name: Exact recipe name from get_recipes.
        servings: How many servings the user wants.
    """
    try:
        return json.dumps(recipe_book.scale_recipe(recipe_name, servings))
    except ValueError as err:
        return json.dumps({"error": str(err)})


INSTRUCTIONS = """
You are the Recipe Planner for PantryPal: a practical home cook.

Your job:
- Suggest ONE recipe from the recipe book that the pantry can cover, scaled to the
  servings the user asked for (default 2 if they did not say).
- Always call get_recipes first, then scale_portions for the recipe you pick. Copy the
  scaled ingredients and steps exactly; never invent ingredients or amounts.
- Prefer recipes listed under cookable_now. Respect anything the user said they want
  or want to avoid.
- If you are given verifier feedback, fix every issue it lists (pick a different recipe
  or fewer servings if needed).
- If no recipe fits, return an empty recipe_name, empty lists, and explain why in note.

You never change the pantry.
""".strip()


def build_recipe_planner(model) -> Agent:
    return Agent(
        name="Recipe Planner",
        handoff_description="Suggests a recipe that uses only what is in the pantry, scaled to servings.",
        instructions=INSTRUCTIONS,
        tools=[read_pantry, get_recipes, scale_portions],
        output_type=RecipePlan,
        model=model,
        model_settings=ModelSettings(temperature=0.3),
    )
