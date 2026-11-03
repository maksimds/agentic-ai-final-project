"""Pantry data layer for PantryPal.

Plain Python, no LLM involved. The Pantry Keeper agent's tools call these
functions, and the Recipe Planner / Verifier will reuse read_pantry() later.
Data lives in a JSON file so it persists between sessions.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = REPO_ROOT / "data" / "pantry_seed.json"
DEFAULT_PANTRY_FILE = REPO_ROOT / "data" / "pantry.json"


def pantry_path() -> Path:
    """Where the live pantry is stored. Override with the PANTRY_FILE env var."""
    return Path(os.getenv("PANTRY_FILE", DEFAULT_PANTRY_FILE))


def _today() -> date:
    # PANTRY_TODAY lets tests and demos pin the date (format YYYY-MM-DD).
    override = os.getenv("PANTRY_TODAY")
    return date.fromisoformat(override) if override else date.today()


def load_pantry() -> dict:
    """Load the pantry, creating it from the seed file on first run."""
    path = pantry_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SEED_FILE, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_pantry(pantry: dict) -> None:
    path = pantry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pantry, f, indent=2, sort_keys=True)


def reset_pantry() -> None:
    """Restore the pantry to the seed data (useful before a demo)."""
    save_pantry(json.loads(SEED_FILE.read_text(encoding="utf-8")))


def _key(name: str) -> str:
    return name.strip().lower()


def read_pantry() -> dict:
    """Return every item with quantity, unit, purchase date and days since purchase."""
    pantry = load_pantry()
    today = _today()
    items = {}
    for name, item in pantry["items"].items():
        days = (today - date.fromisoformat(item["purchased"])).days
        items[name] = {**item, "days_since_purchase": days}
    return {"items": items, "item_count": len(items)}


def update_item(name: str, change: float, unit: str | None = None,
                restock_at: float | None = None) -> dict:
    """Add (positive change) or use up (negative change) an item.

    Returns a summary of what changed. Raises ValueError on bad input so the
    agent gets a clear error instead of silently corrupting the pantry.
    """
    key = _key(name)
    if not key:
        raise ValueError("Item name cannot be empty.")
    if change == 0:
        raise ValueError("Change must be non-zero.")

    pantry = load_pantry()
    items = pantry["items"]
    before = items.get(key, {}).get("quantity", 0)

    if key not in items:
        if change < 0:
            raise ValueError(f"'{key}' is not in the pantry, so it cannot be used up.")
        if not unit:
            raise ValueError(f"'{key}' is a new item; a unit is required (e.g. 'count', 'lb', 'oz').")
        items[key] = {
            "quantity": 0,
            "unit": unit,
            "purchased": _today().isoformat(),
            "restock_at": restock_at if restock_at is not None else 1,
        }
    elif unit and unit != items[key]["unit"]:
        raise ValueError(
            f"'{key}' is tracked in {items[key]['unit']}, not {unit}. Convert the amount first."
        )

    after = round(before + change, 2)
    if after < 0:
        raise ValueError(f"Only {before} {items[key]['unit']} of '{key}' on hand; cannot remove {-change}.")

    if after == 0:
        del items[key]
        action = "removed (used up)"
    else:
        items[key]["quantity"] = after
        if change > 0:
            items[key]["purchased"] = _today().isoformat()
        if restock_at is not None:
            items[key]["restock_at"] = restock_at
        action = "added" if change > 0 else "used"

    save_pantry(pantry)
    return {"item": key, "action": action, "before": before, "after": after}


def check_restock() -> dict:
    """Items that are at/below their restock level or older than their shelf life."""
    today = _today()
    needs = []
    for name, item in load_pantry()["items"].items():
        reasons = []
        if item["quantity"] <= item.get("restock_at", 0):
            reasons.append(f"low: {item['quantity']} {item['unit']} left (restock at {item['restock_at']})")
        shelf = item.get("shelf_life_days")
        days = (today - date.fromisoformat(item["purchased"])).days
        if shelf is not None and days >= shelf:
            reasons.append(f"bought {days} days ago (usually lasts {shelf})")
        if reasons:
            needs.append({"item": name, "reasons": reasons})
    return {"needs_restock": needs, "count": len(needs)}


def build_grocery_list(extra_items: list[str] | None = None) -> dict:
    """Combine restock needs with anything the user asked to add."""
    lines = {entry["item"]: "; ".join(entry["reasons"]) for entry in check_restock()["needs_restock"]}
    for extra in extra_items or []:
        key = _key(extra)
        if key:
            lines.setdefault(key, "requested by user")
    grocery_list = [{"item": k, "why": v} for k, v in sorted(lines.items())]
    return {"grocery_list": grocery_list, "count": len(grocery_list)}
