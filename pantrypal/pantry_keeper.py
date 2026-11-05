"""Pantry Keeper agent: the only agent allowed to change pantry data.

Four tools, matching the proposal:
  read_pantry         - show what is on hand
  update_pantry       - add or use up an item (REQUIRES HUMAN APPROVAL)
  check_restock       - find low or old items
  build_grocery_list  - make a shopping list from restock needs + extras
"""

from __future__ import annotations

import json

from agents import Agent, function_tool
from agents.model_settings import ModelSettings

from . import pantry_store


def _ok(data: dict) -> str:
    return json.dumps(data)


@function_tool
def read_pantry() -> str:
    """Return every pantry item with its quantity, unit, purchase date and days since purchase.
    Use this before answering any question about what the user has."""
    return _ok(pantry_store.read_pantry())


# needs_approval=True is the human-in-the-loop guardrail. The SDK pauses the run
# before this tool executes, and our runner asks the user to approve or reject.
# The model cannot skip this, because it is enforced in code, not in the prompt.
@function_tool(needs_approval=True)
def update_pantry(item: str, change: float, unit: str | None = None,
                  restock_at: float | None = None) -> str:
    """Change the quantity of one pantry item.

    Args:
        item: Item name, e.g. "milk".
        change: Positive to add (bought), negative to remove (used up), in the item's unit.
        unit: Required only when adding a brand-new item (e.g. "count", "lb", "gallon").
        restock_at: Optional quantity at or below which the item should be restocked.
    """
    try:
        return _ok(pantry_store.update_item(item, change, unit, restock_at))
    except ValueError as err:
        return _ok({"error": str(err)})


@function_tool
def check_restock() -> str:
    """List items that are at or below their restock level, or older than their usual shelf life."""
    return _ok(pantry_store.check_restock())


@function_tool
def build_grocery_list(extra_items: list[str] | None = None) -> str:
    """Build a grocery list from everything that needs restocking, plus any extra
    items the user explicitly asked to add.

    Args:
        extra_items: Additional item names the user wants on the list.
    """
    return _ok(pantry_store.build_grocery_list(extra_items))


INSTRUCTIONS = """
You are the Pantry Keeper for PantryPal: an organized, friendly inventory manager.

Your job:
- Answer questions about what is in the pantry, using read_pantry. Never guess quantities.
- Record purchases and used-up items with update_pantry. Call it once per item.
  The user will be asked to approve each change; if they reject it, accept that and do not retry.
- Find low or old items with check_restock.
- Build shopping lists with build_grocery_list. Only pass extra_items the user actually named.

Boundaries:
- Only discuss the pantry, groceries, and shopping lists. For anything else, say it is
  outside what you handle.
- Never invent items or amounts. If a tool returns an error, tell the user what went wrong.
- If an item or amount is unclear (e.g. "I bought some chicken"), ask how much before updating.

Keep answers short. Show lists as bullet points with quantities and units.
""".strip()


def build_pantry_keeper(model) -> Agent:
    return Agent(
        name="Pantry Keeper",
        handoff_description="Pantry inventory: what is on hand, purchases, used-up items, "
                            "restock checks and grocery lists. The only agent that changes the pantry.",
        instructions=INSTRUCTIONS,
        tools=[read_pantry, update_pantry, check_restock, build_grocery_list],
        model=model,
        model_settings=ModelSettings(temperature=0.2),
    )
