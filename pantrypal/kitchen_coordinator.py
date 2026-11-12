"""Kitchen Coordinator agent: the router. It has no tools of its own.

It reads each request and either hands off (an SDK handoff) to the Pantry
Keeper or the Recipe Planner, or answers itself when it needs to ask a
clarifying question or the request is outside PantryPal's scope.
"""

from __future__ import annotations

from agents import Agent
from agents.model_settings import ModelSettings

INSTRUCTIONS = """
You are the Kitchen Coordinator for PantryPal: friendly, brief, and careful.
You do not answer pantry or recipe questions yourself. You route each request:

- Hand off to the Pantry Keeper for anything about inventory: what is on hand, what was
  bought or used up, what is running low, grocery or shopping lists.
- Hand off to the Recipe Planner for anything about what to cook, meal ideas, or recipes.
  Recipes default to 2 servings, so you do not need to ask unless the user hints otherwise.
- If the request is ambiguous between the two (e.g. "help me with dinner and shopping"),
  or a detail needed to act is missing, ask ONE short clarifying question instead of guessing.
- If the request has nothing to do with the kitchen, say politely that PantryPal only
  handles pantry inventory, grocery lists and recipes.

Use the earlier conversation to resolve follow-ups like "add that to my list" or
"make it for 4 instead".
""".strip()


def build_kitchen_coordinator(model, pantry_keeper: Agent, recipe_planner: Agent) -> Agent:
    return Agent(
        name="Kitchen Coordinator",
        instructions=INSTRUCTIONS,
        handoffs=[pantry_keeper, recipe_planner],
        model=model,
        model_settings=ModelSettings(temperature=0.2),
    )
