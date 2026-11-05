"""Pantry Verifier agent (starter version): the evaluator in the
evaluator-optimizer loop. Checks a RecipePlan against the pantry and the
user's request and returns a pass/fail verdict with concrete issues.
"""

from __future__ import annotations

import json

from agents import Agent, function_tool
from agents.model_settings import ModelSettings
from pydantic import BaseModel, Field

from . import recipe_book
from .pantry_keeper import read_pantry
from .recipe_planner import Ingredient


class Verdict(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list,
                              description="Each problem, specific enough for the planner to fix.")


@function_tool
def check_ingredients(ingredients: list[Ingredient]) -> str:
    """Check every ingredient against the pantry: missing items, wrong units, not enough on hand.
    Water, salt and black pepper are assumed staples and are skipped.

    Args:
        ingredients: The recipe's ingredient list, exactly as the planner gave it.
    """
    return json.dumps(recipe_book.check_against_pantry([i.model_dump() for i in ingredients]))


INSTRUCTIONS = """
You are the Pantry Verifier for PantryPal: a careful evaluator. You receive the user's
request and a proposed recipe.

Always call check_ingredients with the recipe's ingredients. Then fail the recipe if:
- check_ingredients reports any problem (missing item, wrong unit, not enough on hand);
- the servings do not match what the user asked for (default 2 if they did not say);
- the recipe ignores something the user said they want or want to avoid;
- the recipe has no name, no ingredients, or no steps.

Otherwise pass it. List each issue in a way the planner can act on.
You never change the pantry and never rewrite the recipe yourself.
""".strip()


def build_pantry_verifier(model) -> Agent:
    return Agent(
        name="Pantry Verifier",
        instructions=INSTRUCTIONS,
        tools=[read_pantry, check_ingredients],
        output_type=Verdict,
        model=model,
        model_settings=ModelSettings(temperature=0),
    )
